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
            if version > 1:
                raise RuntimeError("This database requires a newer application version.")
            with self.connection:
                self.connection.execute(
                    "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                self.connection.execute("PRAGMA user_version = 1")
        except Exception:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()
