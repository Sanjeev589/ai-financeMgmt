import random
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from finance_app.modules.expenses import ExpenseCatalog, ExpenseStore
from finance_app.modules.expense_calculator import ExpenseCalculatorView
from finance_app.modules.finance import ASSETS, FinanceStore, format_amount, input_amount
from finance_app.modules.users import UserStore
from finance_app.storage import Database
from test_users import MemoryTree, NAMES


def calculator(database, tcl):
    view = ExpenseCalculatorView.__new__(ExpenseCalculatorView)
    view.parent, view.database = None, database
    view.catalog = ExpenseCatalog(database)
    view.store = ExpenseStore(database, None)
    view.user_choices = {user.name: user.id for user in UserStore(database).list_users()}
    view.category_choices = {category.name: category.id for category in view.catalog.categories()}
    view.subcategory_choices = {}
    for name, value in (("user", "ALL"), ("month", "October"), ("year", "2026"), ("amount", ""), ("category", ""), ("subcategory", ""), ("description", "")):
        setattr(view, name, tk.StringVar(master=tcl, value=value))
    view.loaded_scope = None
    view.day = tk.StringVar(master=tcl, value="1")
    view.one_time = tk.BooleanVar(master=tcl, value=False)
    view.exclude_one_time = tk.BooleanVar(master=tcl, value=False)
    view.reports = Mock()
    view.entries_by_id = {}
    view.original_values = view.form_values()
    for name in ("status", "heading", "add_button", "delete_button", "category_box", "subcategory_box", "amount_entry", "description_entry", "day_entry", "one_time_box", "total", "combined_total"):
        setattr(view, name, Mock())
    view.entries, view.category_totals, view.subcategory_totals = MemoryTree(), MemoryTree(), MemoryTree()
    return view


class ExpenseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(self.directory.name)
        self.users = [UserStore(self.database).add(name) for name in NAMES]
        self.catalog = ExpenseCatalog(self.database)
        self.categories = [self.catalog.add_category("Synthetic A"), self.catalog.add_category("Synthetic B")]
        self.subcategories = [self.catalog.add_subcategory(category.id, name) for category in self.categories for name in ("Synthetic child 1", "Synthetic child 2")]

    def tearDown(self):
        self.database.close()
        self.directory.cleanup()

    def add(self, user_id=None, amount=12345, year=2026, month=10):
        user_id = self.users[0].id if user_id is None else user_id
        sub = self.subcategories[0]
        return ExpenseStore(self.database, user_id).add(year, month, amount, sub.category_id, sub.id, "Synthetic description")

    def test_repeated_expenses_are_summed_per_category_and_month(self):
        self.add(amount=1025)
        self.add(amount=2075)
        self.add(amount=999, month=9)
        sub = self.subcategories[-1]
        ExpenseStore(self.database, self.users[0].id).add(2026, 10, 15000, sub.category_id, sub.id, "Other category")
        summary = ExpenseStore(self.database, self.users[0].id).summary(2026, 10)
        self.assertEqual(summary.total, 18100)
        self.assertEqual(summary.category_totals, (("Synthetic A", 3100, 2), ("Synthetic B", 15000, 1)))
        self.assertEqual(len(summary.entries), 3)

    def test_user_and_year_month_are_isolated_and_all_sums_users(self):
        self.add(self.users[0].id, 123)
        self.add(self.users[1].id, 456)
        self.add(self.users[0].id, 999, year=2025)
        self.assertEqual(ExpenseStore(self.database, self.users[0].id).summary(2026, 10).total, 123)
        self.assertEqual(ExpenseStore(self.database, self.users[1].id).summary(2026, 10).total, 456)
        self.assertEqual(ExpenseStore(self.database, None).summary(2026, 10).total, 579)

    def test_invalid_data_and_wrong_subcategory_parent_never_save(self):
        store = ExpenseStore(self.database, self.users[0].id)
        for amount in (0, -1, 1.5, True, 100000000000000):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                store.add(2026, 10, amount, self.categories[0].id, self.subcategories[0].id)
        for category_id, subcategory_id in ((self.categories[1].id, self.subcategories[0].id), (None, None), (999, 999)):
            with self.assertRaises(ValueError):
                store.add(2026, 10, 100, category_id, subcategory_id)
        for description in ("a" * 501, "bad\nline", None):
            with self.assertRaises(ValueError):
                store.add(2026, 10, 100, self.categories[0].id, self.subcategories[0].id, description)
        with self.assertRaises(ValueError):
            store.add(2026, 13, 100, self.categories[0].id, self.subcategories[0].id)
        self.assertEqual(store.summary(2026, 10).total, 0)

    def test_all_is_read_only_and_removal_requires_matching_user_and_month(self):
        expense_id = self.add()
        sub = self.subcategories[0]
        with self.assertRaises(ValueError):
            ExpenseStore(self.database, None).add(2026, 10, 100, sub.category_id, sub.id)
        with self.assertRaises(ValueError):
            ExpenseStore(self.database, None).delete(expense_id, 2026, 10)
        with self.assertRaises(ValueError):
            ExpenseStore(self.database, self.users[1].id).delete(expense_id, 2026, 10)
        store = ExpenseStore(self.database, self.users[0].id)
        with self.assertRaises(ValueError):
            store.delete(expense_id, 2026, 9)
        self.assertEqual(store.summary(2026, 10).total, 12345)
        store.delete(expense_id, 2026, 10)
        self.assertEqual(store.summary(2026, 10).total, 0)

    def test_catalog_duplicates_and_parent_specific_dropdowns(self):
        with self.assertRaises(ValueError):
            self.catalog.add_category(" synthetic a ")
        with self.assertRaises(ValueError):
            self.catalog.add_subcategory(self.categories[0].id, "Synthetic Child 1")
        with self.assertRaises(ValueError):
            self.catalog.add_subcategory(999, "Missing parent")
        self.assertEqual(len(self.catalog.subcategories(self.categories[0].id)), 2)
        view = calculator(self.database, tk.Tcl())
        view.store = ExpenseStore(self.database, self.users[0].id)
        view.category.set("Synthetic A")
        view.category_changed()
        self.assertEqual(set(view.subcategory_choices.values()), {sub.id for sub in self.subcategories[:2]})
        view.subcategory.set("Synthetic child 1")
        view.category.set("Synthetic B")
        view.category_changed()
        self.assertEqual(view.subcategory.get(), "")
        self.assertEqual(set(view.subcategory_choices.values()), {sub.id for sub in self.subcategories[2:]})

    def test_five_users_ui_entry_category_subcategory_and_grand_totals(self):
        view = calculator(self.database, tk.Tcl())
        rng = random.Random(51013)
        expected = {}
        for user in self.users:
            for month_name, month in (("September", 9), ("October", 10)):
                view.user.set(user.name)
                view.month.set(month_name)
                view.load_month(check_changes=False)
                for sub in self.subcategories:
                    for index in range(2):
                        amount = rng.randint(1, 2000000)
                        category = next(category for category in self.categories if category.id == sub.category_id)
                        view.category.set(category.name)
                        view.category_changed()
                        view.subcategory.set(sub.name)
                        view.amount.set(input_amount(amount))
                        view.description.set(f"Synthetic entry {index}")
                        view.add_expense()
                        expected.setdefault((user.id, month), []).append((category.name, sub.name, amount))
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 80)
        for name, user_id in [(user.name, user.id) for user in self.users] + [("ALL", None)]:
            for month_name, month in (("September", 9), ("October", 10)):
                view.user.set(name)
                view.month.set(month_name)
                view.load_month(check_changes=False)
                rows = [row for key, values in expected.items() if key[1] == month and (user_id is None or key[0] == user_id) for row in values]
                total = sum(row[2] for row in rows)
                self.assertIn(format_amount(total), view.total.configure.call_args.kwargs["text"])
                self.assertEqual(len(view.entries.rows), len(rows))
                for row in view.category_totals.rows.values():
                    category, count, amount = row["values"]
                    matching = [entry for entry in rows if entry[0] == category]
                    self.assertEqual((count, amount), (len(matching), format_amount(sum(entry[2] for entry in matching))))
                for row in view.subcategory_totals.rows.values():
                    category, subcategory, count, amount = row["values"]
                    matching = [entry for entry in rows if entry[:2] == (category, subcategory)]
                    self.assertEqual((count, amount), (len(matching), format_amount(sum(entry[2] for entry in matching))))
                combined = sum(entry[2] for key, values in expected.items() if key[1] == month for entry in values)
                self.assertIn(format_amount(combined), view.combined_total.configure.call_args.kwargs["text"])

    def test_changed_scope_blocks_ui_write_until_loading(self):
        view = calculator(self.database, tk.Tcl())
        view.user.set(self.users[0].name)
        view.load_month(check_changes=False)
        view.category.set("Synthetic A")
        view.category_changed()
        view.subcategory.set("Synthetic child 1")
        view.amount.set("100.25")
        view.user.set(self.users[1].name)
        view.scope_changed()
        view.add_button.state.assert_called_with(["disabled"])
        with patch("finance_app.modules.expense_calculator.messagebox.showerror") as error:
            view.add_expense()
        error.assert_called_once()
        self.assertEqual(ExpenseStore(self.database, None).summary(2026, 10).total, 0)

    def test_remove_ui_recalculates_category_and_total(self):
        expense_id = self.add(amount=1025)
        self.add(amount=2075)
        view = calculator(self.database, tk.Tcl())
        view.user.set(self.users[0].name)
        view.load_month(check_changes=False)
        view.entries.selection_set(str(expense_id))
        with patch("finance_app.modules.expense_calculator.messagebox.askyesno", return_value=True):
            view.remove_expense()
        self.assertIn("₹20.75", view.total.configure.call_args.kwargs["text"])
        self.assertEqual(len(view.entries.rows), 1)

    def test_cancelled_load_keeps_unsaved_expense_in_original_scope(self):
        view = calculator(self.database, tk.Tcl())
        view.user.set(self.users[0].name)
        view.load_month(check_changes=False)
        original_scope = view.loaded_scope
        view.amount.set("100")
        view.user.set(self.users[1].name)
        with patch("finance_app.modules.expense_calculator.messagebox.askyesno", return_value=False):
            view.load_month()
        self.assertEqual(view.loaded_scope, original_scope)
        self.assertEqual(view.amount.get(), "100")

    def test_persistence_and_blank_description(self):
        sub = self.subcategories[0]
        ExpenseStore(self.database, self.users[0].id).add(2026, 10, 101, sub.category_id, sub.id)
        self.database.close()
        self.database = Database(self.directory.name)
        summary = ExpenseStore(self.database, self.users[0].id).summary(2026, 10)
        self.assertEqual(summary.total, 101)
        self.assertEqual(summary.entries[0].description, "")

    def test_schema_upgrade_preserves_users_and_portfolio(self):
        finance = FinanceStore(self.database, self.users[0].id)
        finance.save_month(2026, 10, {asset: (12345, 23456) for asset, _ in ASSETS})
        with self.database.connection:
            self.database.connection.execute("DROP TABLE expenses")
            self.database.connection.execute("DROP TABLE expense_subcategories")
            self.database.connection.execute("DROP TABLE expense_categories")
            self.database.connection.execute("PRAGMA user_version = 3")
        self.database.close()
        self.database = Database(self.directory.name)
        self.assertEqual(len(UserStore(self.database).list_users()), 5)
        record = FinanceStore(self.database, self.users[0].id).get_month(2026, 10)
        self.assertTrue(all(balance.invested == 12345 for balance in record.balances))
        self.assertEqual(ExpenseCatalog(self.database).categories(), ())
        self.assertEqual(ExpenseStore(self.database, None).summary(2026, 10).total, 0)


class ExpenseOfflineTests(unittest.TestCase):
    def test_real_catalog_is_empty_until_user_supplies_values(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(directory)
            try:
                self.assertEqual(ExpenseCatalog(database).categories(), ())
                view = calculator(database, tk.Tcl())
                view.load_month(check_changes=False)
                self.assertIn("awaiting your list", view.status.configure.call_args.kwargs["text"])
                view.add_button.state.assert_called_with(["disabled"])
            finally:
                database.close()

    def test_expense_module_operates_with_network_blocked(self):
        code = '''
import tempfile
from finance_app.privacy import enable_offline_policy
enable_offline_policy()
from finance_app.storage import Database
from finance_app.modules.users import UserStore
from finance_app.modules.expenses import ExpenseStore, ExpenseCatalog
from finance_app.modules.registry import MODULES
assert any(module.title == "Expense Calculator" for module in MODULES)
with tempfile.TemporaryDirectory() as directory:
    database = Database(directory)
    user = UserStore(database).add("Synthetic offline user")
    catalog = ExpenseCatalog(database)
    category = catalog.add_category("Synthetic category")
    subcategory = catalog.add_subcategory(category.id, "Synthetic subcategory")
    store = ExpenseStore(database, user.id)
    store.add(2026, 10, 1025, category.id, subcategory.id)
    assert store.summary(2026, 10).total == 1025
    assert ExpenseStore(database, None).summary(2026, 10).total == 1025
    database.close()
'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
