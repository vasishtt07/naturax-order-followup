"""Validation, import, exception rules, and report queries."""
from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

import pandas as pd

from db import add_audit, connection, init_db

REQUIRED_COLUMNS = [
    "order_id", "order_date", "customer_name", "phone_number", "order_value",
    "payment_type", "order_status", "dispatch_date", "expected_delivery_date", "assigned_employee",
]
DATE_COLUMNS = ["order_date", "dispatch_date", "expected_delivery_date"]
STATUS_ALIASES = {
    "unconfirmed": "unconfirmed", "confirmed": "confirmed", "dispatched": "dispatched",
    "delivered": "delivered", "failed delivery": "failed_delivery", "failed_delivery": "failed_delivery",
}

# Business-rule thresholds are kept here so they can be changed directly during
# the interview. For example, set DISPATCH_DEADLINE_HOURS to 12.
UNCONFIRMED_DEADLINE_HOURS = 2
DISPATCH_DEADLINE_HOURS = 24


def now_utc() -> datetime:
    return datetime.now().replace(microsecond=0)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def read_upload(raw: bytes, name: str) -> pd.DataFrame:
    return normalize_columns(pd.read_excel(BytesIO(raw)) if name.lower().endswith((".xlsx", ".xls")) else pd.read_csv(BytesIO(raw)))


def validate_orders(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    df = normalize_columns(df)
    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        return pd.DataFrame(), pd.DataFrame(), ["Missing required columns: " + ", ".join(missing_columns)]
    df = df[REQUIRED_COLUMNS].copy()
    errors: list[dict[str, Any]] = []
    valid_rows = []
    # Keep the first occurrence and reject later copies. This both identifies
    # duplicate IDs and lets a mixed upload retain its original valid order.
    duplicate_rows = set(df.index[df["order_id"].astype(str).duplicated(keep="first")])
    for index, row in df.iterrows():
        row = row.copy()
        row_errors = []
        # Dispatch and expected-delivery timestamps are legitimately absent before
        # fulfilment. They are validated when present and handled by the rule
        # engine as a data-correction task if a later status requires them.
        for col in [c for c in REQUIRED_COLUMNS if c not in {"dispatch_date", "expected_delivery_date"}]:
            if pd.isna(row[col]) or str(row[col]).strip() == "":
                row_errors.append(f"missing {col}")
        order_id = str(row["order_id"]).strip()
        if index in duplicate_rows:
            row_errors.append("duplicate order_id in upload")
        for col in DATE_COLUMNS:
            if not pd.isna(row[col]) and str(row[col]).strip():
                parsed = pd.to_datetime(row[col], errors="coerce")
                if pd.isna(parsed):
                    row_errors.append(f"invalid {col}")
                else:
                    row[col] = parsed.to_pydatetime().replace(microsecond=0).isoformat(sep=" ")
        try:
            row["order_value"] = float(row["order_value"])
            if row["order_value"] <= 0:
                row_errors.append("order_value must be greater than zero")
        except (ValueError, TypeError):
            row_errors.append("invalid order_value")
        phone_digits = "".join(char for char in str(row["phone_number"]) if char.isdigit())
        if not pd.isna(row["phone_number"]) and str(row["phone_number"]).strip() and len(phone_digits) < 7:
            row_errors.append("invalid phone_number")
        row["payment_type"] = str(row["payment_type"]).strip().lower()
        if row["payment_type"] not in {"prepaid", "cod"}:
            row_errors.append("payment_type must be prepaid or COD")
        status_key = str(row["order_status"]).strip().lower().replace("-", " ")
        row["order_status"] = STATUS_ALIASES.get(status_key, status_key)
        if row["order_status"] not in set(STATUS_ALIASES.values()):
            row_errors.append("invalid order_status")
        # Date values can be syntactically valid but still impossible for an order.
        parsed_order = pd.to_datetime(row["order_date"], errors="coerce")
        parsed_dispatch = pd.to_datetime(row["dispatch_date"], errors="coerce")
        parsed_expected = pd.to_datetime(row["expected_delivery_date"], errors="coerce")
        if not pd.isna(parsed_order) and not pd.isna(parsed_dispatch) and parsed_dispatch < parsed_order:
            row_errors.append("dispatch_date is before order_date")
        if not pd.isna(parsed_order) and not pd.isna(parsed_expected) and parsed_expected < parsed_order:
            row_errors.append("expected_delivery_date is before order_date")
        if not pd.isna(parsed_dispatch) and not pd.isna(parsed_expected) and parsed_expected < parsed_dispatch:
            row_errors.append("expected_delivery_date is before dispatch_date")
        if row_errors:
            errors.append({"row": index + 2, "order_id": order_id, "errors": "; ".join(row_errors)})
        else:
            row["order_id"] = order_id
            row["customer_name"] = str(row["customer_name"]).strip()
            row["phone_number"] = str(row["phone_number"]).strip()
            row["assigned_employee"] = str(row["assigned_employee"]).strip()
            valid_rows.append(row)
    return pd.DataFrame(valid_rows, columns=REQUIRED_COLUMNS), pd.DataFrame(errors), []


def import_orders(df: pd.DataFrame, source_file: str, user: str = "Manager") -> int:
    init_db()
    timestamp = now_utc().isoformat(sep=" ")
    count = 0
    with connection() as conn:
        for _, r in df.iterrows():
            conn.execute(
                """INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(order_id) DO UPDATE SET order_date=excluded.order_date, customer_name=excluded.customer_name,
                phone_number=excluded.phone_number, order_value=excluded.order_value, payment_type=excluded.payment_type,
                order_status=excluded.order_status, dispatch_date=excluded.dispatch_date,
                expected_delivery_date=excluded.expected_delivery_date, assigned_employee=excluded.assigned_employee,
                source_file=excluded.source_file, imported_at=excluded.imported_at""",
                (*[r[c] for c in REQUIRED_COLUMNS], source_file, timestamp),
            )
            add_audit(conn, r["order_id"], None, "Order imported", f"Imported from {source_file}", user, timestamp)
            count += 1
    run_rules(user)
    return count


def _priority_deadline(priority: str, at: datetime) -> str:
    hours = {"High": 2, "Medium": 8, "Low": 24}[priority]
    return (at + timedelta(hours=hours)).isoformat(sep=" ")


def _upsert_exception(conn, order: dict, kind: str, reason: str, priority: str, action: str, timestamp: datetime, user: str, due_from: datetime | None = None) -> None:
    existing = conn.execute("SELECT id, task_status FROM exceptions WHERE order_id=? AND exception_type=?", (order["order_id"], kind)).fetchone()
    if existing:
        conn.execute(
            "UPDATE exceptions SET reason=?, priority=?, action_required=?, deadline=?, last_detected_at=? WHERE id=?",
            (reason, priority, action, _priority_deadline(priority, due_from or timestamp), timestamp.isoformat(sep=" "), existing["id"]),
        )
        return
    cur = conn.execute(
        """INSERT INTO exceptions(order_id,exception_type,reason,priority,action_required,assigned_employee,deadline,task_status,first_detected_at,last_detected_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (order["order_id"], kind, reason, priority, action, order["assigned_employee"], _priority_deadline(priority, due_from or timestamp), "Open", timestamp.isoformat(sep=" "), timestamp.isoformat(sep=" ")),
    )
    add_audit(conn, order["order_id"], cur.lastrowid, "Task assigned", f"{kind} task assigned to {order['assigned_employee']}: {reason}", user, timestamp.isoformat(sep=" "))


def run_rules(user: str = "System", at: datetime | None = None) -> int:
    init_db()
    at = at or now_utc()
    unconfirmed_hours = UNCONFIRMED_DEADLINE_HOURS
    dispatch_hours = DISPATCH_DEADLINE_HOURS
    created_before = exception_count()
    active_exceptions: set[tuple[str, str]] = set()
    with connection() as conn:
        orders = [dict(r) for r in conn.execute("SELECT * FROM orders")]
        for o in orders:
            order_date = datetime.fromisoformat(o["order_date"]) if o["order_date"] else None
            dispatch = datetime.fromisoformat(o["dispatch_date"]) if o["dispatch_date"] else None
            expected = datetime.fromisoformat(o["expected_delivery_date"]) if o["expected_delivery_date"] else None
            status = o["order_status"]
            data_issues = []
            if status == "dispatched" and not dispatch:
                data_issues.append("dispatch date")
            if status == "dispatched" and not expected:
                data_issues.append("expected delivery date")
            if o["order_value"] > 5000 and status != "delivered" and not expected:
                data_issues.append("expected delivery date for high-value delivery monitoring")
            if data_issues:
                _upsert_exception(
                    conn, o, "Data correction", f"Missing {', '.join(dict.fromkeys(data_issues))}", "Medium",
                    "Update the order data before delivery monitoring can continue.", at, user,
                )
                active_exceptions.add((o["order_id"], "Data correction"))
            if status == "unconfirmed" and order_date and at - order_date > timedelta(hours=unconfirmed_hours):
                _upsert_exception(conn, o, "Unconfirmed order", f"Unconfirmed for more than {unconfirmed_hours} hours", "Low", "Call customer to confirm the order.", at, user, order_date + timedelta(hours=unconfirmed_hours))
                active_exceptions.add((o["order_id"], "Unconfirmed order"))
            if status == "confirmed" and not dispatch and order_date and at - order_date > timedelta(hours=dispatch_hours):
                _upsert_exception(conn, o, "Dispatch delay", f"Confirmed but not dispatched within {dispatch_hours} hours", "High", "Coordinate dispatch and update tracking.", at, user, order_date + timedelta(hours=dispatch_hours))
                active_exceptions.add((o["order_id"], "Dispatch delay"))
            if status == "dispatched" and expected and expected < at:
                _upsert_exception(conn, o, "Shipment delay", "Expected delivery date has passed without delivery", "Medium", "Check courier status and contact the customer.", at, user, expected)
                active_exceptions.add((o["order_id"], "Shipment delay"))
            if status == "failed_delivery":
                _upsert_exception(conn, o, "Failed delivery", "A delivery attempt failed", "High", "Contact customer immediately and schedule redelivery.", at, user, order_date)
                active_exceptions.add((o["order_id"], "Failed delivery"))
            if o["order_value"] > 5000 and status != "delivered" and expected and expected < at:
                _upsert_exception(conn, o, "High-value overdue", "High-value order remains undelivered past expected date", "High", "Escalate to courier and manager immediately.", at, user, expected)
                active_exceptions.add((o["order_id"], "High-value overdue"))
        managed_types = {"Data correction", "Unconfirmed order", "Dispatch delay", "Shipment delay", "Failed delivery", "High-value overdue"}
        current = conn.execute("SELECT id, order_id, exception_type, task_status FROM exceptions WHERE task_status != 'Resolved'").fetchall()
        for exception in current:
            key = (exception["order_id"], exception["exception_type"])
            if exception["exception_type"] in managed_types and key not in active_exceptions:
                resolved_at = at.isoformat(sep=" ")
                conn.execute("UPDATE exceptions SET task_status='Resolved', resolved_at=? WHERE id=?", (resolved_at, exception["id"]))
                add_audit(conn, exception["order_id"], exception["id"], "Task auto-resolved", "A refreshed order no longer matches this exception rule", user, resolved_at)
    return exception_count() - created_before


def exception_count() -> int:
    with connection() as conn:
        return conn.execute("SELECT COUNT(*) n FROM exceptions").fetchone()["n"]


def update_task(exception_id: int, status: str, employee: str, user: str) -> None:
    timestamp = now_utc().isoformat(sep=" ")
    with connection() as conn:
        row = conn.execute("SELECT * FROM exceptions WHERE id=?", (exception_id,)).fetchone()
        if not row:
            raise ValueError("Task not found")
        changes = []
        if row["assigned_employee"] != employee:
            changes.append(f"Reassigned from {row['assigned_employee']} to {employee}")
        if row["task_status"] != status:
            changes.append(f"Status changed from {row['task_status']} to {status}")
        if not changes:
            return
        resolved = timestamp if status == "Resolved" else None
        conn.execute("UPDATE exceptions SET task_status=?, assigned_employee=?, resolved_at=? WHERE id=?", (status, employee, resolved, exception_id))
        add_audit(conn, row["order_id"], exception_id, "Task updated", "; ".join(changes), user, timestamp)


def task_frame(filters: dict[str, Any] | None = None) -> pd.DataFrame:
    filters = filters or {}
    query = """SELECT e.*, o.customer_name, o.phone_number, o.order_value, o.order_date, o.order_status, o.expected_delivery_date
               FROM exceptions e JOIN orders o ON o.order_id=e.order_id WHERE 1=1"""
    params: list[Any] = []
    if filters.get("types"):
        query += " AND e.exception_type IN ({})".format(",".join("?" * len(filters["types"])))
        params.extend(filters["types"])
    if filters.get("employees"):
        query += " AND e.assigned_employee IN ({})".format(",".join("?" * len(filters["employees"])))
        params.extend(filters["employees"])
    if filters.get("priorities"):
        query += " AND e.priority IN ({})".format(",".join("?" * len(filters["priorities"])))
        params.extend(filters["priorities"])
    if filters.get("start"):
        query += " AND date(o.order_date) >= date(?)"; params.append(str(filters["start"]))
    if filters.get("end"):
        query += " AND date(o.order_date) <= date(?)"; params.append(str(filters["end"]))
    query += " ORDER BY CASE e.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, e.deadline"
    with connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def audit_frame() -> pd.DataFrame:
    with connection() as conn:
        return pd.read_sql_query("SELECT * FROM audit_log ORDER BY created_at DESC", conn)


def dashboard_metrics(df: pd.DataFrame, filters: dict[str, Any] | None = None) -> dict[str, int]:
    now = now_utc()
    filters = filters or {}
    total_query = "SELECT COUNT(*) n FROM orders WHERE 1=1"
    total_params: list[Any] = []
    if filters.get("start"):
        total_query += " AND date(order_date) >= date(?)"; total_params.append(str(filters["start"]))
    if filters.get("end"):
        total_query += " AND date(order_date) <= date(?)"; total_params.append(str(filters["end"]))
    with connection() as conn:
        total = conn.execute(total_query, total_params).fetchone()["n"]
    active = df[df.task_status != "Resolved"] if not df.empty else df
    overdue = active[pd.to_datetime(active.deadline, errors="coerce") < now] if not active.empty else active
    return {"total": total, "attention": len(active), "open": int((active.task_status == "Open").sum()) if not active.empty else 0, "overdue": len(overdue), "high": int((active.priority == "High").sum()) if not active.empty else 0}
