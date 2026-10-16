"""SQLite persistence layer for the D2C order follow-up prototype."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "d2c_followup.db"


def connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                order_date TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                order_value REAL NOT NULL,
                payment_type TEXT NOT NULL,
                order_status TEXT NOT NULL,
                dispatch_date TEXT,
                expected_delivery_date TEXT,
                assigned_employee TEXT NOT NULL,
                source_file TEXT,
                imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS exceptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                exception_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                priority TEXT NOT NULL,
                action_required TEXT NOT NULL,
                assigned_employee TEXT NOT NULL,
                deadline TEXT NOT NULL,
                task_status TEXT NOT NULL DEFAULT 'Open',
                first_detected_at TEXT NOT NULL,
                last_detected_at TEXT NOT NULL,
                resolved_at TEXT,
                UNIQUE(order_id, exception_type),
                FOREIGN KEY(order_id) REFERENCES orders(order_id)
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                exception_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                performed_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(exception_id) REFERENCES exceptions(id)
            );
            """
        )


def add_audit(conn: sqlite3.Connection, order_id: str, exception_id: int | None, action: str, details: str, user: str, timestamp: str) -> None:
    conn.execute(
        "INSERT INTO audit_log(order_id,exception_id,action,details,performed_by,created_at) VALUES (?,?,?,?,?,?)",
        (order_id, exception_id, action, details, user, timestamp),
    )
