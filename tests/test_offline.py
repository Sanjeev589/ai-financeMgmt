import ast
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from finance_app.storage import Database


class StorageTests(unittest.TestCase):
    def test_schema_persists_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Database(folder)
            with database.connection:
                database.connection.execute("INSERT INTO app_settings VALUES (?, ?)", ("test", "synthetic"))
            database.close()
            database = Database(folder)
            self.assertEqual(database.connection.execute("SELECT value FROM app_settings WHERE key = ?", ("test",)).fetchone(), ("synthetic",))
            self.assertEqual(database.connection.execute("PRAGMA user_version").fetchone()[0], 3)
            database.close()

    def test_data_inside_repository_rejected(self):
        with self.assertRaises(ValueError):
            Database(Path(__file__).resolve().parents[1] / "data")

    def test_newer_schema_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "finance.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("PRAGMA user_version = 4")
            with self.assertRaises(RuntimeError):
                Database(folder)


class PrivacyTests(unittest.TestCase):
    def test_audit_hook_blocks_network_and_processes_but_allows_storage(self):
        # Isolate the permanent hook from the test runner. This subprocess is
        # test-only; application modules cannot create external processes.
        code = '''
import os, socket, sqlite3, subprocess, sys
from finance_app.privacy import enable_offline_policy
enable_offline_policy()
enable_offline_policy()
for operation in (
    lambda: socket.socket(),
    lambda: socket.getaddrinfo("localhost", 80),
    lambda: subprocess.run([sys.executable, "-V"]),
    lambda: os.system("echo forbidden"),
):
    try:
        operation()
    except PermissionError:
        pass
    else:
        raise AssertionError("Offline operation was not blocked")
with sqlite3.connect(":memory:") as connection:
    connection.execute("CREATE TABLE test (id INTEGER)")
'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_application_imports_are_explicit_and_local(self):
        allowed = {"sys", "os", "pathlib", "sqlite3", "tkinter", "dataclasses", "typing", "datetime", "re"}
        root = Path(__file__).resolve().parents[1] / "finance_app"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split(".")[0], allowed, str(path))
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn((node.module or "").split(".")[0], allowed, str(path))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"eval", "exec", "__import__"}, str(path))


if __name__ == "__main__":
    unittest.main()
