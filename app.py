from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from db import connection, init_db
from engine import (
    audit_frame, dashboard_metrics, import_orders, read_upload, run_rules,
    task_frame, update_task, validate_orders,
)

st.set_page_config(page_title="NaturaX Order Follow-up", page_icon="📦", layout="wide")
init_db()


def apply_theme() -> None:
    """Presentation-only styling for a calmer, operational dashboard."""
    st.markdown(
        """
        <style>
        :root { --nx-ink:#17251f; --nx-forest:#1f5b45; --nx-mint:#dceee3; --nx-canvas:#f5f7f3; --nx-line:#dbe4dc; --nx-orange:#df7b3c; }
        .stApp { background: var(--nx-canvas); color:var(--nx-ink); }
        .block-container { max-width: 1440px; padding-top: 2.1rem; padding-bottom: 3rem; }
        [data-testid="stSidebar"] { background: linear-gradient(180deg,#143d30 0%,#1f5b45 100%); }
        [data-testid="stSidebar"] * { color: #f7fbf8 !important; }
        [data-testid="stSidebar"] [data-baseweb="input"],
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-testid="stDateInput"] input { background:#fff !important; border-radius:10px; }
        #stSidebar input[data-testid="stTextInputField"],
        #stSidebar input[role="combobox"],
        #stSidebar input[type="date"] { color:#000 !important; -webkit-text-fill-color:#000 !important; caret-color:#000 !important; }
        #stSidebar [role="group"][aria-label^="Order date"] * { color:#000 !important; -webkit-text-fill-color:#000 !important; }
        #stSidebar [data-testid="stDateInput"] button,
        #stSidebar [data-testid="stDateInput"] svg { color:#17251f !important; fill:#17251f !important; }
        #stSidebar input::placeholder { color:#4b554f !important; -webkit-text-fill-color:#4b554f !important; opacity:1 !important; }
        #stSidebar [data-baseweb="select"] * { color:#17251f !important; }
        [data-testid="stSidebar"] [data-baseweb="select"] svg { fill:#17251f !important; }
        [data-testid="stSidebar"] hr { border-color:#ffffff2a; }
        [data-testid="stSidebar"] .stRadio label { border-radius:8px; padding:3px 6px; }
        .nx-brand { padding: 0.4rem 0 1.3rem; }
        .nx-brand__mark { color:#9cd3ad; font-size:0.78rem; letter-spacing:0.14em; text-transform:uppercase; font-weight:700; }
        .nx-brand__name { font-size:1.7rem; font-weight:750; line-height:1.1; margin-top:0.25rem; }
        .nx-brand__sub { color:#c6ddcf; font-size:0.82rem; margin-top:0.3rem; }
        .nx-hero { background:linear-gradient(118deg,#164a38 0%,#28795b 68%,#54a572 100%); border-radius:22px; padding:2rem 2.1rem; color:#fff; margin-bottom:1.35rem; box-shadow:0 16px 30px rgba(23,70,53,.15); }
        .nx-hero__eyebrow { color:#c9efd5; font-size:0.75rem; font-weight:700; letter-spacing:0.13em; text-transform:uppercase; }
        .nx-hero h1 { color:#fff; font-size:2rem; line-height:1.16; margin:0.38rem 0 0.4rem; }
        .nx-hero p { color:#e4f4e9; font-size:1rem; margin:0; max-width:44rem; }
        .nx-kpi-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:0.8rem; margin:0.2rem 0 1.5rem; }
        .nx-kpi { background:#fff; border:1px solid var(--nx-line); border-radius:16px; padding:1rem 1.05rem; min-height:102px; box-shadow:0 4px 12px rgba(18,61,48,.045); }
        .nx-kpi__label { color:#67766d; font-size:0.78rem; font-weight:650; letter-spacing:0.015em; }
        .nx-kpi__value { color:var(--nx-ink); font-size:2rem; line-height:1.1; font-weight:760; margin-top:0.4rem; }
        .nx-kpi--attention { border-top:4px solid #d09c3d; }
        .nx-kpi--open { border-top:4px solid #3d8a8c; }
        .nx-kpi--overdue { border-top:4px solid var(--nx-orange); }
        .nx-kpi--urgent { border-top:4px solid #c8554e; }
        .nx-section-title { color:var(--nx-ink); font-size:1.1rem; font-weight:750; margin:0 0 0.12rem; }
        .nx-section-note { color:#68786e; font-size:0.86rem; margin:0 0 0.8rem; }
        [data-testid="stVerticalBlockBorderWrapper"] { background:#fff; border:1px solid var(--nx-line); border-radius:16px; box-shadow:0 4px 12px rgba(18,61,48,.04); }
        [data-testid="stDataFrame"] { border:1px solid var(--nx-line); border-radius:12px; overflow:hidden; }
        @media (max-width: 1000px) { .nx-kpi-grid { grid-template-columns:repeat(3,minmax(0,1fr)); } }
        @media (max-width: 650px) { .block-container { padding:1rem; } .nx-hero { padding:1.5rem; border-radius:16px; } .nx-hero h1 { font-size:1.6rem; } .nx-kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_cards(metrics: dict[str, int]) -> None:
    cards = [
        ("Orders uploaded", metrics["total"], ""),
        ("Need attention", metrics["attention"], "nx-kpi--attention"),
        ("Open tasks", metrics["open"], "nx-kpi--open"),
        ("Overdue tasks", metrics["overdue"], "nx-kpi--overdue"),
        ("High priority", metrics["high"], "nx-kpi--urgent"),
    ]
    html = "".join(f'<div class="nx-kpi {style}"><div class="nx-kpi__label">{label}</div><div class="nx-kpi__value">{value}</div></div>' for label, value, style in cards)
    st.markdown(f'<div class="nx-kpi-grid">{html}</div>', unsafe_allow_html=True)


def options(column: str, table: str = "exceptions") -> list[str]:
    with connection() as conn:
        return [r[0] for r in conn.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY {column}")]


def employee_options() -> list[str]:
    """Return every employee known from uploaded orders and existing tasks."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT assigned_employee FROM orders
               UNION
               SELECT assigned_employee FROM exceptions
               ORDER BY assigned_employee"""
        ).fetchall()
    return [row[0] for row in rows if row[0]]


def filters_ui() -> dict:
    with st.sidebar:
        st.header("Filters")
        start = st.date_input("Order date from", value=None)
        end = st.date_input("Order date to", value=None)
        kinds = st.multiselect("Exception type", options("exception_type"))
        employees = st.multiselect("Employee", options("assigned_employee"))
        priorities = st.multiselect("Priority", ["High", "Medium", "Low"])
    return {"start": start, "end": end, "types": kinds, "employees": employees, "priorities": priorities}


def dashboard() -> None:
    st.markdown(
        """<section class="nx-hero">
        <div class="nx-hero__eyebrow">NaturaX operations</div>
        <h1>Order Follow-up Command Center</h1>
        <p>A focused view of exceptions, ownership, and the work that needs attention today.</p>
        </section>""",
        unsafe_allow_html=True,
    )
    filters = filters_ui()
    df = task_frame(filters)
    m = dashboard_metrics(df, filters)
    metric_cards(m)
    if df.empty:
        st.info("No exceptions match these filters. Import the supplied sample data to begin.")
        return
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown('<div class="nx-section-title">Exceptions by category</div><div class="nx-section-note">Open workload grouped by the reason for follow-up.</div>', unsafe_allow_html=True)
            st.bar_chart(df[df.task_status != "Resolved"].groupby("exception_type").size(), color="#28795b")
    with right:
        with st.container(border=True):
            st.markdown('<div class="nx-section-title">Employee workload</div><div class="nx-section-note">Pending tasks currently assigned to each team member.</div>', unsafe_allow_html=True)
            st.bar_chart(df[df.task_status != "Resolved"].groupby("assigned_employee").size(), color="#3d8a8c")
    st.markdown('<div class="nx-section-title">Immediate action queue</div><div class="nx-section-note">High-priority cases that should be handled first.</div>', unsafe_allow_html=True)
    urgent = df[(df.priority == "High") & (df.task_status != "Resolved")]
    st.dataframe(urgent[["order_id", "customer_name", "exception_type", "reason", "assigned_employee", "deadline", "task_status"]], use_container_width=True, hide_index=True)


def import_page() -> None:
    st.title("Import orders")
    st.write("Upload a CSV, XLS, or XLSX containing the ten required columns. Invalid rows are not imported; review them as the data-correction queue.")
    uploaded = st.file_uploader("Order file", type=["csv", "xlsx", "xls"])
    if uploaded:
        try:
            raw = uploaded.getvalue()
            data = read_upload(raw, uploaded.name)
            valid, errors, structural = validate_orders(data)
            if structural:
                st.error(" · ".join(structural)); return
            st.success(f"{len(valid)} valid rows ready to import")
            if not errors.empty:
                st.warning(f"{len(errors)} invalid or incomplete rows require data correction and will not be imported.")
                st.dataframe(errors, use_container_width=True, hide_index=True)
                st.download_button("Download data-correction errors", errors.to_csv(index=False).encode(), "data_correction_errors.csv", "text/csv")
            st.dataframe(valid.head(10), use_container_width=True, hide_index=True)
            if len(valid) and st.button("Import valid orders and generate exceptions", type="primary"):
                imported = import_orders(valid, uploaded.name, st.session_state.get("user", "Manager"))
                st.success(f"Imported/updated {imported} orders. Rules have been applied; repeat uploads update orders and do not create duplicate tasks.")
        except Exception as exc:
            st.error(f"Could not read this file: {exc}")


def tasks_page() -> None:
    st.title("Task assignment")
    df = task_frame(filters_ui())
    if df.empty:
        st.info("There are no tasks yet."); return
    st.dataframe(df[["id", "order_id", "customer_name", "phone_number", "exception_type", "reason", "priority", "assigned_employee", "action_required", "deadline", "task_status"]], use_container_width=True, hide_index=True)
    st.divider()
    st.subheader("Manage selected task")
    task_ids = df.id.tolist()
    with st.form("task_update"):
        selected = st.selectbox("Task", task_ids, format_func=lambda item: f"#{item} - {df.loc[df.id == item, 'order_id'].iloc[0]} | {df.loc[df.id == item, 'exception_type'].iloc[0]}")
        selected_row = df[df.id == selected].iloc[0]
        employees = employee_options()
        employee = st.selectbox(
            "Assigned employee",
            employees,
            index=employees.index(selected_row.assigned_employee) if selected_row.assigned_employee in employees else 0,
            help="Choose the employee who should own this follow-up.",
        )
        status = st.selectbox("Task status", ["Open", "In Progress", "Resolved"], index=["Open", "In Progress", "Resolved"].index(selected_row.task_status))
        submitted = st.form_submit_button("Save task update", type="primary")
    if submitted:
        try:
            update_task(int(selected), status, employee.strip(), st.session_state.get("user", "Manager"))
            st.success("Task updated and audit entry recorded.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def reports_page() -> None:
    st.title("Daily exception report")
    df = task_frame(filters_ui())
    if df.empty:
        st.info("No reportable exceptions."); return
    now = pd.Timestamp.now()
    overdue = pd.to_datetime(df.deadline, errors="coerce") < now
    new_today = pd.to_datetime(df.first_detected_at, errors="coerce").dt.date == now.date()
    report = df.copy()
    # Keep separate report markers so a case can correctly appear in more than
    # one required section (for example: new, unresolved, and high priority).
    report["is_new_exception"] = new_today
    report["is_unresolved"] = report.task_status != "Resolved"
    report["is_overdue"] = overdue
    report["is_high_priority"] = report.priority == "High"
    pending_by_employee = report[report["is_unresolved"]].groupby("assigned_employee").size()
    report["employee_pending_actions"] = report["assigned_employee"].map(pending_by_employee).fillna(0).astype(int)
    st.caption(f"{new_today.sum()} new · {(df.task_status != 'Resolved').sum()} unresolved · {overdue.sum()} overdue · {(df.priority == 'High').sum()} high priority")
    st.subheader("Employee-wise pending actions")
    st.dataframe(df[df.task_status != "Resolved"].groupby("assigned_employee").size().rename("pending_actions").reset_index(), hide_index=True, use_container_width=True)
    new_tab, unresolved_tab, overdue_tab, high_tab = st.tabs(["New exceptions", "Unresolved", "Overdue", "High priority"])
    with new_tab:
        st.dataframe(report[report.is_new_exception], hide_index=True, use_container_width=True)
    with unresolved_tab:
        st.dataframe(report[report.is_unresolved], hide_index=True, use_container_width=True)
    with overdue_tab:
        st.dataframe(report[report.is_overdue], hide_index=True, use_container_width=True)
    with high_tab:
        st.dataframe(report[report.is_high_priority], hide_index=True, use_container_width=True)
    st.download_button("Download daily exception report (CSV)", report.to_csv(index=False).encode(), "daily_exception_report.csv", "text/csv", type="primary")


def audit_page() -> None:
    st.title("Audit trail")
    st.caption("Every import, generated exception, reassignment, and status change is retained in SQLite.")
    audit = audit_frame()
    st.dataframe(audit, use_container_width=True, hide_index=True)


apply_theme()
st.sidebar.markdown('<div class="nx-brand"><div class="nx-brand__mark">Operations workspace</div><div class="nx-brand__name">NaturaX D2C</div><div class="nx-brand__sub">Order follow-up system</div></div>', unsafe_allow_html=True)
st.session_state.setdefault("user", "Manager")
st.session_state["user"] = st.sidebar.text_input("Signed in as", st.session_state["user"])
page = st.sidebar.radio("Navigate", ["Dashboard", "Import orders", "Tasks", "Daily report", "Audit trail"])
{"Dashboard": dashboard, "Import orders": import_page, "Tasks": tasks_page, "Daily report": reports_page, "Audit trail": audit_page}[page]()
