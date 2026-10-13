from calendar import monthrange
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock

from finance_app.modules.expenses import ExpenseCatalog, ExpenseStore, report_months
from finance_app.modules.expense_reports import ExpenseReports, grouped_totals, time_series
from finance_app.modules.finance import format_amount
from finance_app.modules.users import UserStore
from finance_app.storage import Database
from test_expenses import calculator
from test_users import MemoryTree, NAMES


class LegendTree(MemoryTree):
    def tag_configure(self, tag, **options):
        pass


def report_panel(database, user_id):
    tcl = tk.Tcl()
    panel = ExpenseReports.__new__(ExpenseReports)
    panel.database = database
    panel.store = ExpenseStore(database, user_id)
    panel.exclude_one_time = tk.BooleanVar(master=tcl, value=False)
    panel.paused = False
    panel.summary = None
    panel.months = ()
    panel.pending = None
    for name, value in (("period", "Monthly"), ("year", "2026"), ("month", "January"), ("quarter", "Q1"), ("grouping", "Category")):
        setattr(panel, name, tk.StringVar(master=tcl, value=value))
    for name in ("heading", "status", "month_box", "quarter_box", "amount_canvas", "pie_canvas"):
        setattr(panel, name, Mock())
    for canvas in (panel.amount_canvas, panel.pie_canvas):
        canvas.winfo_width.return_value = 900
        canvas.winfo_height.return_value = 360
    panel.figures, panel.legend = MemoryTree(), LegendTree()
    return panel


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(self.directory.name)
        self.users = [UserStore(self.database).add(name) for name in NAMES]
        catalog = ExpenseCatalog(self.database)
        self.categories = [catalog.add_category("Synthetic A"), catalog.add_category("Synthetic B")]
        self.subcategories = [catalog.add_subcategory(category.id, name) for category in self.categories for name in ("Child 1", "Child 2")]
        self.data = []
        rng = random.Random(20261013)
        for user in self.users:
            for year in (2025, 2026):
                for month in range(1, 13):
                    for index, sub in enumerate(self.subcategories):
                        amount = rng.randint(1, 5000000)
                        day = None if index == 3 else 1 if index == 0 else monthrange(year, month)[1]
                        one_time = index == 2
                        ExpenseStore(self.database, user.id).add(year, month, amount, sub.category_id, sub.id, "Synthetic expense", day=day, one_time=one_time)
                        self.data.append((user.id, year, month, sub.id, amount, day, one_time))

    def tearDown(self):
        self.database.close()
        self.directory.cleanup()

    def expected_rows(self, user_id, year, months, excluded):
        return [row for row in self.data if (user_id is None or row[0] == user_id) and row[1] == year and row[2] in months and not (excluded and row[-1])]

    def test_five_users_and_all_match_every_month_quarter_year_with_and_without_one_time(self):
        for user_id in [user.id for user in self.users] + [None]:
            for year in (2025, 2026):
                for period, selections in (("Monthly", range(1, 13)), ("Quarterly", range(1, 5)), ("Yearly", (None,))):
                    for selection in selections:
                        options = {"month": selection} if period == "Monthly" else {"quarter": selection} if period == "Quarterly" else {}
                        months = report_months(year, period, **options)
                        for excluded in (False, True):
                            with self.subTest(user=user_id, year=year, period=period, selection=selection, excluded=excluded):
                                summary = ExpenseStore(self.database, user_id).report(year, period, exclude_one_time=excluded, **options)
                                expected = self.expected_rows(user_id, year, months, excluded)
                                self.assertEqual(summary.total, sum(row[4] for row in expected))
                                self.assertEqual(len(summary.entries), len(expected))
                                self.assertEqual(sum(row[1] for row in summary.category_totals), summary.total)
                                self.assertEqual(sum(row[2] for row in summary.subcategory_totals), summary.total)
                                for category, amount, count in summary.category_totals:
                                    category_id = next(item.id for item in self.categories if item.name == category)
                                    sub_ids = {item.id for item in self.subcategories if item.category_id == category_id}
                                    matching = [row for row in expected if row[3] in sub_ids]
                                    self.assertEqual((amount, count), (sum(row[4] for row in matching), len(matching)))
                                for grouping in ("Overall", "Category", "Subcategory"):
                                    self.assertEqual(sum(amount for label, amount in grouped_totals(summary, grouping)), summary.total)
                                    labels, series = time_series(summary, year, months, grouping)
                                    self.assertEqual(sum(sum(line.values) for line in series), summary.total)
                                    self.assertEqual(len(labels), monthrange(year, months[0])[1] + 1 if period == "Monthly" else len(months))

    def test_daily_graph_unknown_day_and_month_totals_are_exact(self):
        store = ExpenseStore(self.database, None)
        summary = store.summary(2026, 1)
        labels, series = time_series(summary, 2026, (1,), "Overall")
        self.assertEqual(labels[-1], "Undated")
        self.assertEqual(series[0].values[0], sum(row[4] for row in self.data if row[1:3] == (2026, 1) and row[5] == 1))
        self.assertEqual(series[0].values[-1], sum(row[4] for row in self.data if row[1:3] == (2026, 1) and row[5] is None))
        quarter = store.report(2026, "Quarterly", quarter=1)
        labels, series = time_series(quarter, 2026, (1, 2, 3), "Overall")
        self.assertEqual(labels, ("Jan 2026", "Feb 2026", "Mar 2026"))
        self.assertEqual(series[0].values, tuple(sum(row[4] for row in self.data if row[1] == 2026 and row[2] == month) for month in (1, 2, 3)))

    def test_report_ui_figures_and_graphs_and_pie_obey_exclusion(self):
        for user_id in [user.id for user in self.users] + [None]:
            panel = report_panel(self.database, user_id)
            for period in ("Monthly", "Quarterly", "Yearly"):
                panel.period.set(period)
                for grouping in ("Overall", "Category", "Subcategory"):
                    panel.grouping.set(grouping)
                    for excluded in (False, True):
                        panel.exclude_one_time.set(excluded)
                        panel.amount_canvas.reset_mock()
                        panel.pie_canvas.reset_mock()
                        panel.refresh()
                        months = report_months(2026, period, month=1, quarter=1)
                        total = sum(row[4] for row in self.expected_rows(user_id, 2026, months, excluded))
                        self.assertEqual(panel.summary.total, total)
                        self.assertEqual(next(iter(panel.figures.rows.values()))["values"][2], format_amount(total))
                        self.assertEqual(len(panel.legend.rows), len(grouped_totals(panel.summary, grouping)))
                        self.assertGreater(panel.amount_canvas.create_rectangle.call_count, 0)
                        arcs = panel.pie_canvas.create_arc.call_args_list
                        if len(panel.legend.rows) == 1:
                            panel.pie_canvas.create_oval.assert_called_once()
                        else:
                            self.assertEqual(len(arcs), len(panel.legend.rows))
                            self.assertAlmostEqual(sum(call.kwargs["extent"] for call in arcs), 360)
                        for call in panel.amount_canvas.create_rectangle.call_args_list:
                            x0, y0, x1, y1 = call.args
                            self.assertTrue(150 <= x0 < x1 <= 876)
                            self.assertTrue(20 <= y0 < y1 <= 296)

    def test_monthly_entry_flag_filter_and_reset_after_save(self):
        view = calculator(self.database, tk.Tcl())
        view.user.set(self.users[0].name)
        view.month.set("October")
        view.load_month(check_changes=False)
        view.category.set("Synthetic A")
        view.category_changed()
        view.subcategory.set("Child 1")
        view.amount.set("100.25")
        view.day.set("7")
        view.one_time.set(True)
        before = ExpenseStore(self.database, self.users[0].id).summary(2026, 10).total
        view.add_expense()
        latest = ExpenseStore(self.database, self.users[0].id).summary(2026, 10).entries[0]
        self.assertTrue(latest.one_time)
        self.assertEqual(latest.day, 7)
        self.assertFalse(view.one_time.get())
        view.exclude_one_time.set(True)
        view.filter_changed()
        expected = sum(row[4] for row in self.expected_rows(self.users[0].id, 2026, (10,), True))
        self.assertIn(format_amount(expected), view.total.configure.call_args.kwargs["text"])
        self.assertEqual(ExpenseStore(self.database, self.users[0].id).summary(2026, 10).total, before + 10025)
        self.assertTrue(all(row["values"][5] == "No" for row in view.entries.rows.values()))

    def test_filtering_never_deletes_or_changes_stored_expenses(self):
        count = self.database.connection.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        store = ExpenseStore(self.database, None)
        before = store.report(2026, "Yearly")
        self.assertLess(store.report(2026, "Yearly", exclude_one_time=True).total, before.total)
        self.assertEqual(store.report(2026, "Yearly"), before)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], count)

    def test_empty_filtered_report_has_no_chart_division_by_zero(self):
        panel = report_panel(self.database, self.users[0].id)
        panel.year.set("2030")
        panel.refresh()
        self.assertEqual(panel.summary.total, 0)
        panel.pie_canvas.create_arc.assert_not_called()
        self.assertIn("No expenses", panel.pie_canvas.create_text.call_args.kwargs["text"])
        panel.year.set("invalid")
        panel.refresh()
        self.assertIsNone(panel.summary)
        self.assertEqual(panel.legend.rows, {})

    def test_calendar_quarters_and_invalid_periods(self):
        self.assertEqual(report_months(2026, "Quarterly", quarter=4), (10, 11, 12))
        self.assertEqual(report_months(2026, "Yearly"), tuple(range(1, 13)))
        for period, options in (("Quarterly", {"quarter": 0}), ("Quarterly", {"quarter": 5}), ("Monthly", {"month": 13}), ("Bad", {})):
            with self.assertRaises(ValueError):
                report_months(2026, period, **options)

    def test_leap_year_dates_and_invalid_flags(self):
        store = ExpenseStore(self.database, self.users[0].id)
        sub = self.subcategories[0]
        store.add(2024, 2, 100, sub.category_id, sub.id, day=29, one_time=True)
        self.assertEqual(store.summary(2024, 2).entries[0].day, 29)
        for year, month, day in ((2025, 2, 29), (2026, 4, 31), (2026, 1, 0), (2026, 1, True)):
            with self.assertRaises(ValueError):
                store.add(year, month, 100, sub.category_id, sub.id, day=day)
        with self.assertRaises(ValueError):
            store.add(2026, 1, 100, sub.category_id, sub.id, one_time="yes")

    def test_flag_and_day_persist_after_reopening(self):
        before = ExpenseStore(self.database, self.users[0].id).report(2026, "Yearly")
        self.database.close()
        self.database = Database(self.directory.name)
        self.assertEqual(ExpenseStore(self.database, self.users[0].id).report(2026, "Yearly"), before)


class ReportMigrationTests(unittest.TestCase):
    def test_old_expenses_are_preserved_as_undated_and_regular(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finance.sqlite3"
            database = Database(directory)
            user = UserStore(database).add("Legacy synthetic user")
            catalog = ExpenseCatalog(database)
            category = catalog.add_category("Legacy category")
            sub = catalog.add_subcategory(category.id, "Legacy subcategory")
            with database.connection:
                database.connection.execute("DROP TABLE expenses")
                database.connection.execute("CREATE TABLE expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, year INTEGER, month INTEGER, subcategory_id INTEGER, amount INTEGER, description TEXT)")
                database.connection.execute("INSERT INTO expenses VALUES (1, ?, 2026, 10, ?, 12345, 'Preserved')", (user.id, sub.id))
                database.connection.execute("PRAGMA user_version = 4")
            database.close()
            database = Database(directory)
            try:
                summary = ExpenseStore(database, user.id).summary(2026, 10)
                self.assertEqual(summary.total, 12345)
                self.assertIsNone(summary.entries[0].day)
                self.assertFalse(summary.entries[0].one_time)
                self.assertEqual(summary.entries[0].description, "Preserved")
                labels, lines = time_series(summary, 2026, (10,), "Overall")
                self.assertEqual(labels[-1], "Undated")
                self.assertEqual(lines[0].values[-1], 12345)
            finally:
                database.close()

    def test_reports_and_pie_data_work_with_network_blocked(self):
        code = '''
import tempfile
from finance_app.privacy import enable_offline_policy
enable_offline_policy()
from finance_app.storage import Database
from finance_app.modules.users import UserStore
from finance_app.modules.expenses import ExpenseCatalog, ExpenseStore
from finance_app.modules.expense_reports import grouped_totals, time_series
with tempfile.TemporaryDirectory() as directory:
    database = Database(directory)
    user = UserStore(database).add("Offline report user")
    catalog = ExpenseCatalog(database)
    category = catalog.add_category("Synthetic category")
    sub = catalog.add_subcategory(category.id, "Synthetic subcategory")
    store = ExpenseStore(database, user.id)
    store.add(2026, 1, 100, category.id, sub.id, day=2)
    store.add(2026, 2, 900, category.id, sub.id, day=3, one_time=True)
    summary = store.report(2026, "Quarterly", quarter=1, exclude_one_time=True)
    assert summary.total == 100
    assert grouped_totals(summary, "Category")[0][1] == 100
    assert sum(time_series(summary, 2026, (1, 2, 3), "Overall")[1][0].values) == 100
    database.close()
'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
