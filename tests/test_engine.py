from datetime import datetime, timedelta

from engine import REQUIRED_COLUMNS, validate_orders


def test_duplicate_and_bad_date_are_reported():
    import pandas as pd
    now = datetime.now().isoformat(sep=" ")
    df = pd.DataFrame([
        ["NX-1", now, "A", "9876543210", 100, "COD", "confirmed", now, now, "Asha"],
        ["NX-1", "not-a-date", "B", "9876543211", 100, "COD", "confirmed", now, now, "Asha"],
    ], columns=REQUIRED_COLUMNS)
    valid, errors, structural = validate_orders(df)
    assert not structural
    assert len(valid) == 1
    assert len(errors) == 1
    assert "duplicate" in errors.iloc[0].errors


def test_valid_row_normalizes_status():
    import pandas as pd
    now = datetime.now().isoformat(sep=" ")
    df = pd.DataFrame([["NX-2", now, "A", "9876543210", 100, "COD", "failed delivery", now, now, "Asha"]], columns=REQUIRED_COLUMNS)
    valid, errors, _ = validate_orders(df)
    assert errors.empty
    assert valid.iloc[0].order_status == "failed_delivery"


def test_impossible_order_timeline_is_reported():
    import pandas as pd
    df = pd.DataFrame([[
        "NX-3", "2026-10-16 10:00", "A", "9876543210", 100, "COD", "dispatched",
        "2026-10-16 09:00", "2026-10-16 08:00", "Asha",
    ]], columns=REQUIRED_COLUMNS)
    valid, errors, _ = validate_orders(df)
    assert valid.empty
    assert "before order_date" in errors.iloc[0].errors
