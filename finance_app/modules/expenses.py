"""Local monthly expenses and category totals in integer paise."""

from dataclasses import dataclass
import sqlite3

from .finance import MAX_AMOUNT, validate_period
from .users import UserStore


@dataclass(frozen=True)
class Category:
    id: int
    name: str


@dataclass(frozen=True)
class Subcategory:
    id: int
    category_id: int
    name: str


class ExpenseCatalog:
    """Dropdown definitions. No assumed categories are seeded into real data."""
    def __init__(self, database):
        self.connection = database.connection

    @staticmethod
    def clean_name(name):
        if not isinstance(name, str) or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError("Enter a name without control characters.")
        name = " ".join(name.split())
        if not 1 <= len(name) <= 80:
            raise ValueError("Category names must contain 1 to 80 characters.")
        return name

    def categories(self):
        return tuple(Category(*row) for row in self.connection.execute("SELECT id, name FROM expense_categories ORDER BY name_key"))

    def subcategories(self, category_id):
        return tuple(Subcategory(*row) for row in self.connection.execute(
            "SELECT id, category_id, name FROM expense_subcategories WHERE category_id = ? ORDER BY name_key", (category_id,)
        ))

    def add_category(self, name):
        name = self.clean_name(name)
        try:
            with self.connection:
                cursor = self.connection.execute("INSERT INTO expense_categories (name, name_key) VALUES (?, ?)", (name, name.casefold()))
        except sqlite3.IntegrityError:
            raise ValueError("This category already exists.") from None
        return Category(cursor.lastrowid, name)

    def add_subcategory(self, category_id, name):
        if type(category_id) is not int or not self.connection.execute("SELECT 1 FROM expense_categories WHERE id = ?", (category_id,)).fetchone():
            raise ValueError("Select an existing category.")
        name = self.clean_name(name)
        try:
            with self.connection:
                cursor = self.connection.execute("INSERT INTO expense_subcategories (category_id, name, name_key) VALUES (?, ?, ?)", (category_id, name, name.casefold()))
        except sqlite3.IntegrityError:
            raise ValueError("This subcategory already exists in the category.") from None
        return Subcategory(cursor.lastrowid, category_id, name)


@dataclass(frozen=True)
class Expense:
    id: int
    user_id: int
    user_name: str
    year: int
    month: int
    category_id: int
    category: str
    subcategory_id: int
    subcategory: str
    amount: int
    description: str


@dataclass(frozen=True)
class ExpenseSummary:
    entries: tuple[Expense, ...]
    category_totals: tuple[tuple[str, int, int], ...]
    subcategory_totals: tuple[tuple[str, str, int, int], ...]
    total: int


class ExpenseStore:
    def __init__(self, database, user_id):
        self.connection = database.connection
        self.user_id = user_id
        self.user_name = "ALL" if user_id is None else UserStore(database).get(user_id).name

    def add(self, year, month, amount, category_id, subcategory_id, description=""):
        if self.user_id is None:
            raise ValueError("Select a named user before adding an expense. ALL is read-only.")
        validate_period(year, month)
        if type(amount) is not int or not 1 <= amount <= MAX_AMOUNT:
            raise ValueError("Amount must be greater than zero, with at most two decimal places.")
        if type(category_id) is not int or type(subcategory_id) is not int:
            raise ValueError("Select a category and subcategory from the dropdowns.")
        valid = self.connection.execute(
            "SELECT 1 FROM expense_subcategories WHERE id = ? AND category_id = ?", (subcategory_id, category_id)
        ).fetchone()
        if valid is None:
            raise ValueError("Select a subcategory belonging to the selected category.")
        if not isinstance(description, str) or len(description) > 500 or any(ord(char) < 32 or ord(char) == 127 for char in description):
            raise ValueError("Description must be at most 500 characters, without control characters.")
        with self.connection:
            cursor = self.connection.execute("""
                INSERT INTO expenses (user_id, year, month, subcategory_id, amount, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (self.user_id, year, month, subcategory_id, amount, description.strip()))
        return cursor.lastrowid

    def summary(self, year, month):
        validate_period(year, month)
        sql = """
            SELECT e.id, e.user_id, u.name, e.year, e.month, c.id, c.name, s.id, s.name, e.amount, e.description
            FROM expenses e JOIN users u ON u.id = e.user_id
            JOIN expense_subcategories s ON s.id = e.subcategory_id
            JOIN expense_categories c ON c.id = s.category_id
            WHERE e.year = ? AND e.month = ?
        """
        parameters = [year, month]
        if self.user_id is not None:
            sql += " AND e.user_id = ?"
            parameters.append(self.user_id)
        sql += " ORDER BY e.id DESC"
        entries = tuple(Expense(*row) for row in self.connection.execute(sql, parameters))
        categories, subcategories = {}, {}
        for expense in entries:
            for mapping, key in ((categories, expense.category), (subcategories, (expense.category, expense.subcategory))):
                amount, count = mapping.get(key, (0, 0))
                mapping[key] = (amount + expense.amount, count + 1)
        # Sum in Python: combined totals may exceed a single SQLite INTEGER.
        category_totals = tuple((name, *categories[name]) for name in sorted(categories, key=str.casefold))
        subcategory_totals = tuple((*names, *subcategories[names]) for names in sorted(subcategories, key=lambda names: (names[0].casefold(), names[1].casefold())))
        return ExpenseSummary(entries, category_totals, subcategory_totals, sum(expense.amount for expense in entries))

    def delete(self, expense_id, year, month):
        if self.user_id is None:
            raise ValueError("ALL is read-only. Select the expense's named user to remove it.")
        validate_period(year, month)
        if type(expense_id) is not int or expense_id <= 0:
            raise ValueError("Select an expense to remove.")
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM expenses WHERE id = ? AND user_id = ? AND year = ? AND month = ?",
                (expense_id, self.user_id, year, month),
            )
            if cursor.rowcount != 1:
                raise ValueError("This expense does not belong to the selected user and month.")
