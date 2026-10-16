"""Generate deterministic interview demo data with 100+ normal and exceptional orders."""
from datetime import datetime, timedelta
from pathlib import Path
import csv
import random

random.seed(21)
now = datetime.now().replace(minute=0, second=0, microsecond=0)
employees = ["Asha", "Rahul", "Meera", "Vikram"]
names = ["Ananya Shah", "Rohan Patel", "Isha Nair", "Karan Singh", "Diya Menon", "Arjun Rao"]
rows = []
for i in range(1, 106):
    order_date = now - timedelta(hours=random.randint(1, 120), minutes=random.randint(0, 55))
    status = "delivered"
    dispatch = order_date + timedelta(hours=5)
    expected = dispatch + timedelta(days=3)
    value = random.choice([699, 899, 1299, 2499, 3499])
    if i <= 12: status, dispatch = "unconfirmed", ""
    elif i <= 25: status, dispatch = "confirmed", ""
    elif i <= 38:
        # Make these genuinely late while keeping a valid order -> dispatch ->
        # expected-delivery timeline for the import validation demo.
        order_date = now - timedelta(days=random.randint(5, 8))
        dispatch = order_date + timedelta(hours=5)
        status, expected = "dispatched", now - timedelta(days=random.randint(1, 3))
    elif i <= 46: status = "failed_delivery"
    elif i <= 54:
        order_date = now - timedelta(days=random.randint(4, 6))
        dispatch = order_date + timedelta(hours=5)
        status, value, expected = "dispatched", random.choice([5500, 7999, 12500]), now - timedelta(days=1)
    rows.append([f"NX-{1000+i}", order_date, names[i % len(names)], f"98765{10000+i:05d}", value, "COD" if i % 3 == 0 else "prepaid", status, dispatch, expected, employees[i % len(employees)]])
# Deliberate bad records are retained in the downloadable sample so the import
# validation/data-correction workflow can be demonstrated in the interview.
rows.extend([
    ["NX-1001", now, "Duplicate demo", "9876500000", 699, "COD", "confirmed", now, now + timedelta(days=2), "Asha"],
    ["NX-BAD-DATE", "not-a-date", "Date error demo", "9876500001", 999, "prepaid", "confirmed", now, now + timedelta(days=2), "Rahul"],
    ["NX-INCOMPLETE", now, "", "9876500002", 899, "prepaid", "confirmed", now, now + timedelta(days=2), "Meera"],
])
target = Path(__file__).parent / "data" / "sample_orders.csv"
target.parent.mkdir(exist_ok=True)
with target.open("w", newline="") as f:
    writer = csv.writer(f); writer.writerow(["order_id","order_date","customer_name","phone_number","order_value","payment_type","order_status","dispatch_date","expected_delivery_date","assigned_employee"])
    writer.writerows(rows)
print(f"Wrote {len(rows)} sample rows (105 valid + 3 validation examples) to {target}")
