from pathlib import Path
import random
import sqlite3
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from finance_app.modules.finance import ASSETS, FinanceStore, format_amount, input_amount
from finance_app.modules.finance_graph import FinanceGraph, METRICS, make_series
from finance_app.modules.my_finance import MyFinanceView
from finance_app.modules.users import UserStore, UsersView
from finance_app.storage import Database


NAMES = random.Random(20261013).sample(
    ("Aarav Mehta", "Priya Nair", "Kabir Shah", "Ananya Rao", "Rohan Das",
     "Meera Joshi", "Vikram Iyer", "Nisha Sen", "Ishaan Kapoor", "Kavya Menon"), 5
)
PERIODS = ((2025, 12),) + tuple((2026, month) for month in range(1, 12))
ALL_FIELDS = {f"{asset}_{metric}" for asset, _ in ASSETS for metric, _, _ in METRICS}


class MemoryTree:
    """Record real UI callback outputs without requiring a display server."""
    def __init__(self):
        self.rows = {}
        self.selected = ()
        self.counter = 0

    def get_children(self):
        return tuple(self.rows)

    def delete(self, item):
        self.rows.pop(item)
        self.selected = tuple(key for key in self.selected if key != item)

    def insert(self, parent, position, iid=None, **row):
        self.counter += 1
        iid = iid or str(self.counter)
        self.rows[iid] = row
        return iid

    def selection(self):
        return self.selected

    def selection_set(self, item):
        self.selected = (item,)

    def see(self, item):
        pass


def headless_view(database, tcl):
    view = MyFinanceView.__new__(MyFinanceView)
    view.parent = None
    view.database = database
    view.users = UserStore(database)
    view.store = FinanceStore(database, None)
    view.combined_store = FinanceStore(database, None)
    view.user_choices = {user.name: user.id for user in view.users.list_users()}
    view.user_choice = tk.StringVar(master=tcl, value="ALL")
    view.loaded_period = None
    view.loaded_user_id = None
    view.month = tk.StringVar(master=tcl, value="November")
    view.year = tk.StringVar(master=tcl, value="2026")
    view.fields = {asset: tuple(tk.StringVar(master=tcl) for _ in range(2)) for asset, _ in ASSETS}
    view.entry_widgets = [Mock() for _ in range(8)]
    view.original_values = view.field_values()
    view.history_rows = {}
    view.combined_rows = {}
    for field in ("save_button", "status", "entry_heading", "history_heading", "detail_heading", "combined_status", "edit_button"):
        setattr(view, field, Mock())
    view.history, view.details = MemoryTree(), MemoryTree()
    graph = FinanceGraph.__new__(FinanceGraph)
    graph.canvas = Mock()
    graph.canvas.winfo_width.return_value = 1000
    graph.canvas.winfo_height.return_value = 320
    graph.pending_redraw = None
    graph.hit_points = []
    graph.history = ()
    graph.hint = "Hover for details"
    graph.scope_name = "ALL"
    graph.heading = Mock()
    graph.hover_text = tk.StringVar(master=tcl)
    graph.enabled = {key: tk.BooleanVar(master=tcl, value=True) for key in ALL_FIELDS}
    view.graph = graph
    return view


class UserValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(self.directory.name)
        self.users = UserStore(self.database)

    def tearDown(self):
        self.database.close()
        self.directory.cleanup()

    def test_names_are_required_unique_and_all_is_reserved(self):
        user = self.users.add("  Test   Person  ")
        self.assertEqual(user.name, "Test Person")
        for name in ("", "   ", "ALL", "all", " Test Person ", "test person", "a" * 101, "Bad\nName"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.users.add(name)
        self.assertEqual(len(self.users.list_users()), 1)

    def test_sql_like_name_and_unicode_are_stored_literally(self):
        names = ("O'Neil; DROP TABLE users;", "संजय कुमार")
        for name in names:
            self.users.add(name)
        self.assertEqual({user.name for user in self.users.list_users()}, set(names))

    def test_user_is_mandatory_and_all_cannot_save(self):
        with self.assertRaises(ValueError):
            FinanceStore(self.database, 999)
        with self.assertRaises(ValueError):
            FinanceStore(self.database, True)
        values = {asset: (100, 200) for asset, _ in ASSETS}
        with self.assertRaises(ValueError):
            FinanceStore(self.database, None).save_month(2026, 10, values)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("INSERT INTO monthly_finance VALUES (?, ?, ?, ?, ?, ?)", (999, 2026, 10, "stocks", 100, 100))


class FiveUserTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(self.directory.name)
        self.users = [UserStore(self.database).add(name) for name in NAMES]
        rng = random.Random(589)
        self.data = {}
        for user in self.users:
            self.data[user.id] = {}
            for period in PERIODS:
                values = {asset: (rng.randint(0, 20000000), rng.randint(0, 20000000)) for asset, _ in ASSETS}
                self.data[user.id][period] = values
                FinanceStore(self.database, user.id).save_month(*period, values)

    def tearDown(self):
        self.database.close()
        self.directory.cleanup()

    def expected(self, user_id, period, asset):
        if user_id is None:
            return tuple(sum(self.data[user.id][period][asset][column] for user in self.users) for column in (0, 1))
        return self.data[user_id][period][asset]

    def verify_scope(self, user_id):
        store = FinanceStore(self.database, user_id)
        history = store.history()
        self.assertEqual(len(history), 12)
        for row in history:
            period = (row.record.year, row.record.month)
            index = PERIODS.index(period)
            self.assertEqual(len(row.record.user_ids), 5 if user_id is None else 1)
            for change in row.changes:
                expected = self.expected(user_id, period, change.balance.asset)
                self.assertEqual((change.balance.invested, change.balance.current), expected)
                differences = (None, None) if index == 0 else tuple(expected[column] - self.expected(user_id, PERIODS[index - 1], change.balance.asset)[column] for column in (0, 1))
                self.assertEqual((change.invested_diff, change.current_diff), differences)
        lines = make_series(history, ALL_FIELDS)
        self.assertEqual(len(lines), 16)
        for line in lines:
            self.assertEqual(len(line.points), 12)
            asset = next(asset for asset, _ in ASSETS if line.key.startswith(asset + "_"))
            metric = line.key[len(asset) + 1:]
            column = 0 if metric in ("invested", "invested_diff") else 1
            for index, point in enumerate(line.points):
                expected = self.expected(user_id, PERIODS[index], asset)[column]
                if metric.endswith("_diff"):
                    expected = None if index == 0 else expected - self.expected(user_id, PERIODS[index - 1], asset)[column]
                self.assertEqual(point.amount, expected)

    def test_all_entered_fields_differences_and_graph_values_for_five_users_and_all(self):
        for user_id in [user.id for user in self.users] + [None]:
            with self.subTest(user_id=user_id):
                self.verify_scope(user_id)

    def test_edit_one_user_does_not_change_others_and_all_recalculates(self):
        first, second = self.users[:2]
        original = FinanceStore(self.database, second.id).get_month(*PERIODS[-1])
        values = {asset: (12345, 23456) for asset, _ in ASSETS}
        FinanceStore(self.database, first.id).save_month(*PERIODS[-1], values)
        self.data[first.id][PERIODS[-1]] = values
        self.assertEqual(FinanceStore(self.database, second.id).get_month(*PERIODS[-1]), original)
        self.verify_scope(first.id)
        self.verify_scope(None)

    def test_data_persists_for_all_five_users_after_reopening(self):
        self.database.close()
        self.database = Database(self.directory.name)
        self.assertEqual({user.name for user in UserStore(self.database).list_users()}, set(NAMES))
        for user in self.users:
            self.verify_scope(user.id)
        self.verify_scope(None)

    def test_changed_reporting_users_make_combined_mom_unknown_until_backfilled(self):
        user = self.users[-1]
        with self.database.connection:
            self.database.connection.execute("DELETE FROM monthly_finance WHERE user_id = ? AND year = ? AND month = ?", (user.id, *PERIODS[-1]))
        combined = FinanceStore(self.database, None).history()[0]
        self.assertEqual(len(combined.record.user_ids), 4)
        self.assertTrue(all(change.invested_diff is None and change.current_diff is None for change in combined.changes))
        FinanceStore(self.database, user.id).save_month(*PERIODS[-1], self.data[user.id][PERIODS[-1]])
        self.verify_scope(None)

    def test_ui_modules_create_five_users_enter_all_fields_and_render_every_scope(self):
        # Exercise Users.add_user, MyFinance.save_month/load/history/combined
        # summary, and the real Canvas renderer callbacks using synthetic data.
        with tempfile.TemporaryDirectory() as directory:
            database = Database(directory)
            try:
                tcl = tk.Tcl()
                users_view = UsersView.__new__(UsersView)
                users_view.parent = None
                users_view.store = UserStore(database)
                users_view.name = tk.StringVar(master=tcl)
                users_view.status = Mock()
                users_view.list = MemoryTree()
                for name in NAMES:
                    users_view.name.set(name)
                    users_view.add_user()
                self.assertEqual({user.name for user in users_view.store.list_users()}, set(NAMES))
                self.assertEqual(len(users_view.list.rows), 5)
                view = headless_view(database, tcl)
                for user in self.users:
                    view.user_choice.set(user.name)
                    view.user_changed()
                    for period in PERIODS:
                        from finance_app.modules.finance import MONTHS
                        view.month.set(MONTHS[period[1] - 1])
                        view.year.set(str(period[0]))
                        view.load_month(check_changes=False)
                        for asset, _ in ASSETS:
                            for column in (0, 1):
                                view.fields[asset][column].set(input_amount(self.data[user.id][period][asset][column]))
                        view.save_month()
                self.assertEqual(database.connection.execute("SELECT COUNT(*) FROM monthly_finance").fetchone()[0], 240)
                for name in [user.name for user in self.users] + ["ALL"]:
                    view.user_choice.set(name)
                    view.user_changed()
                    self.assertEqual(len(view.history_rows), 12)
                    self.assertEqual(view.graph.scope_name, name)
                    self.assertEqual(len(view.graph.hit_points), 184)  # 16 fields × 12 months minus 8 unknown first MoMs.
                    self.assertTrue(all(150 <= x <= 970 and 20 <= y <= 260 for x, y, _, _ in view.graph.hit_points))
                    user_id = None if name == "ALL" else view.user_choices[name]
                    for _, _, label, point in view.graph.hit_points:
                        asset = next(asset for asset, title in ASSETS if label.startswith(title + " — "))
                        title = label.split(" — ", 1)[1]
                        column = 0 if title in ("Invested", "MoM invested") else 1
                        period = (point.year, point.month)
                        expected = self.expected(user_id, period, asset)[column]
                        if title.startswith("MoM"):
                            expected -= self.expected(user_id, PERIODS[PERIODS.index(period) - 1], asset)[column]
                        self.assertEqual(point.amount, expected)
                    summary = [row for row in view.details.rows.values() if "combined" in row.get("tags", ())]
                    self.assertEqual(len(summary), 5)
                    for row, (asset, _) in zip(summary[:4], ASSETS):
                        values = self.expected(None, PERIODS[-1], asset)
                        previous = self.expected(None, PERIODS[-2], asset)
                        self.assertEqual(row["values"][1:], (format_amount(values[0]), format_amount(values[1]), format_amount(values[0] - previous[0], True), format_amount(values[1] - previous[1], True)))
                with patch("finance_app.modules.my_finance.messagebox.showerror") as error:
                    view.save_month()  # ALL must remain read-only, including through its UI callback.
                error.assert_called_once()
            finally:
                database.close()

    def test_cancelled_user_switch_keeps_unsaved_values_with_original_user(self):
        view = headless_view(self.database, tk.Tcl())
        view.user_choice.set(self.users[0].name)
        view.user_changed()
        view.fields["stocks"][0].set("123.45")
        view.user_choice.set(self.users[1].name)
        with patch("finance_app.modules.my_finance.messagebox.askyesno", return_value=False):
            view.user_changed()
        self.assertEqual(view.store.user_id, self.users[0].id)
        self.assertEqual(view.user_choice.get(), self.users[0].name)
        self.assertEqual(view.fields["stocks"][0].get(), "123.45")


class UserMigrationTests(unittest.TestCase):
    def test_pre_user_finance_is_preserved_in_existing_data_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finance.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute("INSERT INTO app_settings VALUES ('synthetic', 'kept')")
                connection.execute("CREATE TABLE monthly_finance (year INTEGER, month INTEGER, asset TEXT, invested INTEGER, current INTEGER, PRIMARY KEY(year, month, asset))")
                connection.executemany("INSERT INTO monthly_finance VALUES (?, ?, ?, ?, ?)", [(2026, 9, asset, 1000, 2000) for asset, _ in ASSETS])
                connection.execute("PRAGMA user_version = 2")
            database = Database(directory)
            try:
                users = UserStore(database).list_users()
                self.assertEqual(len(users), 1)
                self.assertEqual(users[0].name, "Existing data")
                record = FinanceStore(database, users[0].id).get_month(2026, 9)
                self.assertTrue(all(balance.invested == 1000 and balance.current == 2000 for balance in record.balances))
                self.assertEqual(database.connection.execute("SELECT value FROM app_settings").fetchone()[0], "kept")
                self.assertEqual(database.connection.execute("PRAGMA user_version").fetchone()[0], 4)
            finally:
                database.close()

    def test_empty_database_does_not_create_an_unrequested_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(directory)
            try:
                self.assertEqual(UserStore(database).list_users(), ())
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
