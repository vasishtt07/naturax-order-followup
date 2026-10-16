# NaturaX order follow-up app

This is a small internal tool for keeping an eye on D2C orders that need someone to step in. Instead of checking a spreadsheet and then following up on WhatsApp, a manager can upload the latest order file and get a proper task list with an owner, priority, and deadline.

The app is built with Streamlit and SQLite. SQLite keeps the orders, tasks, and activity history saved locally, so refreshing the browser does not wipe the work.

## Starting the app

From this project folder, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_sample_data.py
streamlit run app.py
```

Streamlit will print a local link in the terminal. Open it, go to **Import orders**, and upload `data/sample_orders.csv`.

The sample file has 105 usable orders as well as three intentionally bad rows. Those rows are handy for showing the validation behaviour: there is a duplicate ID, an invalid date, and a missing customer name.

## File format

The importer accepts CSV, XLS, and XLSX files. It expects these columns:

`order_id`, `order_date`, `customer_name`, `phone_number`, `order_value`, `payment_type`, `order_status`, `dispatch_date`, `expected_delivery_date`, `assigned_employee`

Use one of these statuses: `unconfirmed`, `confirmed`, `dispatched`, `delivered`, or `failed_delivery`. Payment type is either `prepaid` or `COD`.

Dispatch and delivery dates can be blank while an order is still being processed. If a dispatched order has no expected delivery date, the app puts it in the data-correction queue rather than pretending it can calculate a shipment delay. Bad rows are shown before import and can be downloaded as a CSV for correction.

## What the app checks

- An unconfirmed order older than 2 hours gets a low-priority follow-up.
- A confirmed order waiting more than 24 hours for dispatch gets a high-priority follow-up.
- A dispatched order past its expected delivery date is treated as a shipment delay.
- A failed delivery attempt needs immediate attention.
- An undelivered order above Rs. 5,000, past its expected delivery date, is escalated as high priority.

The rule thresholds are constants near the top of `engine.py`: `UNCONFIRMED_DEADLINE_HOURS = 2` and `DISPATCH_DEADLINE_HOURS = 24`. To demonstrate the interview challenge, change the second value to `12`, save the file, and rerun the app. The `run_rules()` function reads that constant whenever new data is imported; import the same sample file again to re-evaluate the existing orders. Existing matching tasks are updated rather than duplicated, and affected deadlines/reasons are refreshed.

## A quick walk-through

1. Import the sample CSV and look at the three invalid rows before importing the valid ones.
2. Open the dashboard to see total orders, urgent cases, overdue work, and each employee's queue.
3. Go to **Tasks**, reassign one overdue item, and change its status.
4. Check **Audit trail** to see who made that change and when.
5. Download the **Daily report** CSV.

Uploading the same file again updates the existing order records. Tasks use the order ID and exception type as a unique pair, so a repeat upload does not keep creating copies of the same follow-up.
If a later upload shows that an issue is no longer present - for example, a delayed order is now delivered - the old open task is automatically marked resolved and that action is recorded in the audit trail.

## Notes

This is a local prototype, so it deliberately does not include logins, role permissions, automated messages, or a live courier connection. Those would be the next things to add for a production version, along with scheduled imports, notifications, database backups, and deployment configuration.
