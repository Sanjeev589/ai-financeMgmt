from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from finance_app.modules.finance import (
    ASSETS, MAX_AMOUNT, FinanceStore, format_amount, month_label, parse_amount, previous_period,
)
from finance_app.storage import Database
from finance_app.modules.users import UserStore


def sample_values(invested=10000, current=12000):
    return {asset: (invested + index * 100, current + index * 100) for index, (asset, _) in enumerate(ASSETS)}


class MoneyTests(unittest.TestCase):
    def test_money_is_exact_and_accepts_zero(self):
        self.assertEqual(parse_amount("0"), 0)
        self.assertEqual(parse_amount(" 123.45 "), 12345)
        self.assertEqual(parse_amount("0.1"), 10)
        self.assertEqual(parse_amount("999999999999.99"), MAX_AMOUNT)
        self.assertEqual(format_amount(123456789), "₹1,234,567.89")
        self.assertEqual(format_amount(-12345, signed=True), "-₹123.45")
        self.assertEqual(format_amount(12345, signed=True), "+₹123.45")
        self.assertEqual(format_amount(None), "—")

    def test_invalid_amounts_are_rejected(self):
        for text in ("", "-1", "1.234", "1,000", "NaN", "Infinity", "1e3", "10abc", "1.", "1000000000000", "1" * 1000):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_amount(text)

    def test_calendar_labels_and_year_rollover(self):
        self.assertEqual(month_label(2026, 10), "October 2026")
        self.assertEqual(previous_period(2026, 1), (2025, 12))


class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(self.temp.name)
        self.user = UserStore(self.database).add("Synthetic user")
        self.store = FinanceStore(self.database, self.user.id)

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_save_reload_and_persist_all_assets(self):
        self.assertIsNone(self.store.get_month(2026, 10))
        self.store.save_month(2026, 10, sample_values())
        self.database.close()
        self.database = Database(self.temp.name)
        self.store = FinanceStore(self.database, self.user.id)
        record = self.store.get_month(2026, 10)
        self.assertEqual([balance.asset for balance in record.balances], [asset for asset, _ in ASSETS])
        self.assertEqual((record.balances[0].invested, record.balances[0].current), (10000, 12000))

    def test_mom_increases_and_decreases_for_every_asset(self):
        self.store.save_month(2026, 9, sample_values(10000, 12000))
        self.store.save_month(2026, 10, sample_values(10550, 11025))
        newest, oldest = self.store.history()
        for change in newest.changes:
            self.assertEqual((change.invested_diff, change.current_diff), (550, -975))
        for change in oldest.changes:
            self.assertIsNone(change.invested_diff)
            self.assertIsNone(change.current_diff)

    def test_january_compares_to_december(self):
        self.store.save_month(2025, 12, sample_values(10000, 12000))
        self.store.save_month(2026, 1, sample_values(15000, 18000))
        change = self.store.history()[0].changes[0]
        self.assertEqual((change.invested_diff, change.current_diff), (5000, 6000))

    def test_gap_is_unknown_and_backfill_recalculates(self):
        self.store.save_month(2026, 8, sample_values())
        self.store.save_month(2026, 10, sample_values(15000, 20000))
        self.assertIsNone(self.store.history()[0].changes[0].current_diff)
        self.store.save_month(2026, 9, sample_values(11000, 13000))
        self.assertEqual(self.store.history()[0].changes[0].current_diff, 7000)

    def test_update_is_not_duplicate_and_recalculates_next_month(self):
        self.store.save_month(2026, 9, sample_values())
        self.store.save_month(2026, 10, sample_values(15000, 20000))
        self.store.save_month(2026, 9, sample_values(12000, 16000))
        self.assertEqual(len(self.store.history()), 2)
        self.assertEqual(self.store.history()[0].changes[0].current_diff, 4000)
        count = self.database.connection.execute("SELECT COUNT(*) FROM monthly_finance").fetchone()[0]
        self.assertEqual(count, 8)

    def test_zero_baseline_and_zero_change_are_not_missing(self):
        zero = {asset: (0, 0) for asset, _ in ASSETS}
        self.store.save_month(2026, 9, zero)
        self.store.save_month(2026, 10, zero)
        self.assertEqual(self.store.history()[0].changes[0].current_diff, 0)

    def test_invalid_save_leaves_existing_values_intact(self):
        self.store.save_month(2026, 10, sample_values())
        invalid = sample_values(99999, 99999)
        invalid["rd"] = (-1, 1)
        with self.assertRaises(ValueError):
            self.store.save_month(2026, 10, invalid)
        self.assertEqual(self.store.get_month(2026, 10).balances[0].invested, 10000)
        for year, month in ((2026, 0), (2026, 13), (1899, 1), (10000, 1), (True, 1)):
            with self.subTest(year=year, month=month), self.assertRaises(ValueError):
                self.store.save_month(year, month, sample_values())
        missing = sample_values()
        del missing["rd"]
        with self.assertRaises(ValueError):
            self.store.save_month(2026, 10, missing)
        noninteger = sample_values()
        noninteger["rd"] = (1.25, 0)
        with self.assertRaises(ValueError):
            self.store.save_month(2026, 10, noninteger)

    def test_database_failure_rolls_back_all_four_assets(self):
        self.store.save_month(2026, 10, sample_values())
        self.database.connection.execute("""
            CREATE TRIGGER simulate_failure BEFORE UPDATE ON monthly_finance
            WHEN NEW.asset = 'rd' BEGIN SELECT RAISE(ABORT, 'test failure'); END
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_month(2026, 10, sample_values(99999, 99999))
        self.assertEqual(self.store.get_month(2026, 10).balances[0].invested, 10000)

    def test_incomplete_record_is_not_silently_treated_as_zero(self):
        self.database.connection.execute(
            "INSERT INTO monthly_finance VALUES (?, ?, ?, ?, ?, ?)", (self.user.id, 2026, 10, "stocks", 100, 100)
        )
        with self.assertRaises(RuntimeError):
            self.store.history()


class MigrationTests(unittest.TestCase):
    def test_old_settings_survive_upgrade_to_current_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            with sqlite3.connect(Path(directory) / "finance.sqlite3") as connection:
                connection.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute("INSERT INTO app_settings VALUES ('test', 'synthetic')")
                connection.execute("PRAGMA user_version = 1")
            database = Database(directory)
            try:
                self.assertEqual(database.connection.execute("SELECT value FROM app_settings").fetchone()[0], "synthetic")
                user = UserStore(database).add("Synthetic user")
                FinanceStore(database, user.id).save_month(2026, 10, sample_values())
                self.assertEqual(database.connection.execute("PRAGMA user_version").fetchone()[0], 3)
            finally:
                database.close()

    def test_migration_failure_keeps_old_schema_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finance.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute("CREATE TABLE monthly_finance (existing TEXT)")
                connection.execute("PRAGMA user_version = 1")
            with self.assertRaises(sqlite3.OperationalError):
                Database(directory)
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_full_finance_workflow_runs_with_network_blocked(self):
        code = '''
import tempfile
from finance_app.privacy import enable_offline_policy
enable_offline_policy()
from finance_app.storage import Database
from finance_app.modules.finance import ASSETS, FinanceStore
from finance_app.modules.users import UserStore
from finance_app.modules.registry import MODULES
assert MODULES[0].title == "My Finance"
with tempfile.TemporaryDirectory() as directory:
    database = Database(directory)
    user = UserStore(database).add("Offline user")
    store = FinanceStore(database, user.id)
    store.save_month(2026, 10, {asset: (100, 200) for asset, _ in ASSETS})
    assert store.history()[0].changes[0].balance.current == 200
    assert FinanceStore(database, None).history()[0].changes[0].balance.current == 200
    database.close()
'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
