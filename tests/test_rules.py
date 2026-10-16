"""Rule-engine coverage for every exception required in section B."""
from datetime import datetime, timedelta

import pandas as pd

import db
from engine import REQUIRED_COLUMNS, import_orders, run_rules, task_frame


def row(order_id, order_date, status, dispatch_date, expected_date, value=1000):
    return [order_id, order_date, "Test Customer", "9876543210", value, "COD", status,
            dispatch_date, expected_date, "Asha"]


def test_required_rules_and_data_correction(monkeypatch, tmp_path):
    # Point the persistent layer at a disposable database for this test.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    at = datetime(2026, 10, 16, 12, 0, 0)
    rows = [
        row("U-1", at - timedelta(hours=3), "unconfirmed", "", at + timedelta(days=2)),
        row("D-1", at - timedelta(hours=25), "confirmed", "", at + timedelta(days=2)),
        # A supplied dispatch timestamp prevents a false dispatch-delay task.
        row("D-OK", at - timedelta(hours=30), "confirmed", at - timedelta(hours=20), at + timedelta(days=2)),
        row("S-1", at - timedelta(days=5), "dispatched", at - timedelta(days=4), at - timedelta(days=1)),
        row("F-1", at - timedelta(days=1), "failed_delivery", at - timedelta(days=1), at + timedelta(days=1)),
        row("H-1", at - timedelta(days=4), "unconfirmed", "", at - timedelta(days=1), 6500),
        row("C-1", at - timedelta(days=1), "dispatched", "", ""),
    ]
    frame = pd.DataFrame(rows, columns=REQUIRED_COLUMNS)
    # Values are already clean; use the import path to test persistence too.
    from engine import validate_orders
    valid, errors, structural = validate_orders(frame)
    assert errors.empty and not structural
    import_orders(valid, "rules.csv", "Tester")
    run_rules("Tester", at)
    tasks = task_frame()
    kinds = set(tasks.exception_type)
    assert {"Unconfirmed order", "Dispatch delay", "Shipment delay", "Failed delivery", "High-value overdue", "Data correction"} <= kinds
    assert {"High", "Medium", "Low"} <= set(tasks.priority)
    assert set(tasks.loc[tasks.exception_type == "Unconfirmed order", "priority"]) == {"Low"}
    assert not ((tasks.order_id == "D-OK") & (tasks.exception_type == "Dispatch delay")).any()

    # A newer delivered status should close a stale dispatch-delay task rather
    # than leave an obsolete open item on the dashboard.
    corrected = valid[valid.order_id == "D-1"].copy()
    corrected.loc[:, "order_status"] = "delivered"
    corrected.loc[:, "dispatch_date"] = at.isoformat(sep=" ")
    import_orders(corrected, "rules-corrected.csv", "Tester")
    refreshed = task_frame()
    assert refreshed[(refreshed.order_id == "D-1") & (refreshed.exception_type == "Dispatch delay")].iloc[0].task_status == "Resolved"
