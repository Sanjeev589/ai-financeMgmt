"""Local paths and SQLite schema. Financial modules will extend the schema."""

import os
from pathlib import Path
import sqlite3
import sys


def default_data_directory():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    return base / "OfflineFinance"


class Database:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else default_data_directory()
        self.directory = self.directory.expanduser().resolve()
        source_root = Path(__file__).resolve().parent.parent
        if self.directory == source_root or source_root in self.directory.parents:
            raise ValueError("Application data must be stored outside the source repository.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "finance.sqlite3"
        self.connection = sqlite3.connect(self.path)
        try:
            if os.name != "nt":
                self.path.chmod(0o600)
            self.connection.execute("PRAGMA foreign_keys = ON")
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 4:
                raise RuntimeError("This database requires a newer application version.")
            # Explicit BEGIN makes SQLite DDL and user_version one transaction.
            self.connection.execute("BEGIN")
            with self.connection:
                if version < 1:
                    self.connection.execute(
                        "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                    )
                if version < 2:
                    self.connection.execute("""
                        CREATE TABLE monthly_finance (
                            year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 9999),
                            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
                            asset TEXT NOT NULL CHECK (asset IN ('stocks', 'mutual_funds', 'fd', 'rd')),
                            invested INTEGER NOT NULL CHECK (
                                typeof(invested) = 'integer' AND invested BETWEEN 0 AND 99999999999999
                            ),
                            current INTEGER NOT NULL CHECK (
                                typeof(current) = 'integer' AND current BETWEEN 0 AND 99999999999999
                            ),
                            PRIMARY KEY (year, month, asset)
                        )
                    """)
                if version < 3:
                    self.connection.execute("""
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY,
                            name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
                            name_key TEXT NOT NULL UNIQUE CHECK (name_key != 'all')
                        )
                    """)
                    self.connection.execute("ALTER TABLE monthly_finance RENAME TO monthly_finance_legacy")
                    self.connection.execute("""
                        CREATE TABLE monthly_finance (
                            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                            year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 9999),
                            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
                            asset TEXT NOT NULL CHECK (asset IN ('stocks', 'mutual_funds', 'fd', 'rd')),
                            invested INTEGER NOT NULL CHECK (
                                typeof(invested) = 'integer' AND invested BETWEEN 0 AND 99999999999999
                            ),
                            current INTEGER NOT NULL CHECK (
                                typeof(current) = 'integer' AND current BETWEEN 0 AND 99999999999999
                            ),
                            PRIMARY KEY (user_id, year, month, asset)
                        )
                    """)
                    if self.connection.execute("SELECT COUNT(*) FROM monthly_finance_legacy").fetchone()[0]:
                        cursor = self.connection.execute(
                            "INSERT INTO users (name, name_key) VALUES (?, ?)", ("Existing data", "existing data")
                        )
                        self.connection.execute("""
                            INSERT INTO monthly_finance (user_id, year, month, asset, invested, current)
                            SELECT ?, year, month, asset, invested, current FROM monthly_finance_legacy
                        """, (cursor.lastrowid,))
                    self.connection.execute("DROP TABLE monthly_finance_legacy")
                if version < 4:
                    self.connection.execute("""
                        CREATE TABLE expense_categories (
                            id INTEGER PRIMARY KEY,
                            name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
                            name_key TEXT NOT NULL UNIQUE
                        )
                    """)
                    self.connection.execute("""
                        CREATE TABLE expense_subcategories (
                            id INTEGER PRIMARY KEY,
                            category_id INTEGER NOT NULL REFERENCES expense_categories(id),
                            name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
                            name_key TEXT NOT NULL,
                            UNIQUE (category_id, name_key)
                        )
                    """)
                    self.connection.execute("""
                        CREATE TABLE expenses (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL REFERENCES users(id),
                            year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 9999),
                            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
                            subcategory_id INTEGER NOT NULL REFERENCES expense_subcategories(id),
                            amount INTEGER NOT NULL CHECK (
                                typeof(amount) = 'integer' AND amount BETWEEN 1 AND 99999999999999
                            ),
                            description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 500)
                        )
                    """)
                    self.connection.execute("CREATE INDEX expense_scope ON expenses (user_id, year, month)")
                    self.connection.execute("CREATE INDEX expense_month ON expenses (year, month)")
                self.connection.execute("PRAGMA user_version = 4")
        except Exception:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()
