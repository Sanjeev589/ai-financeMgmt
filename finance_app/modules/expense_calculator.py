"""Offline monthly expense entry and category/subcategory totals UI."""

from datetime import date
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from .expenses import ExpenseCatalog, ExpenseStore
from .finance import MONTHS, format_amount, month_label, parse_amount, validate_period
from .users import UserStore


class ExpenseCalculatorView:
    def __init__(self, parent, database):
        self.parent, self.database = parent, database
        self.catalog = ExpenseCatalog(database)
        self.store = ExpenseStore(database, None)
        self.user_choices = {user.name: user.id for user in UserStore(database).list_users()}
        self.category_choices = {category.name: category.id for category in self.catalog.categories()}
        self.subcategory_choices = {}
        self.loaded_scope = None
        self.entries_by_id = {}
        self.user = tk.StringVar(master=parent, value="ALL")
        today = date.today()
        self.month = tk.StringVar(master=parent, value=MONTHS[today.month - 1])
        self.year = tk.StringVar(master=parent, value=str(today.year))
        self.amount = tk.StringVar(master=parent)
        self.category = tk.StringVar(master=parent)
        self.subcategory = tk.StringVar(master=parent)
        self.description = tk.StringVar(master=parent)
        self.original_values = self.form_values()
        self._build()
        self.load_month(check_changes=False)
        for variable in (self.user, self.month, self.year):
            variable.trace_add("write", self.scope_changed)

    def _build(self):
        selector = ttk.LabelFrame(self.parent, text="Monthly expenses — select user, month, and year", padding=12)
        selector.pack(fill="x", pady=(0, 12))
        ttk.Label(selector, text="User").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Combobox(selector, textvariable=self.user, values=("ALL", *self.user_choices), state="readonly", width=28).grid(row=0, column=1, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(selector, text="ALL = combined, read-only").grid(row=0, column=4, padx=(12, 0), pady=(0, 8))
        ttk.Label(selector, text="Month").grid(row=1, column=0, padx=(0, 8))
        ttk.Combobox(selector, textvariable=self.month, values=MONTHS, state="readonly", width=13).grid(row=1, column=1, padx=(0, 12))
        ttk.Label(selector, text="Year").grid(row=1, column=2, padx=(0, 8))
        ttk.Spinbox(selector, textvariable=self.year, from_=1900, to=9999, width=6).grid(row=1, column=3)
        ttk.Button(selector, text="Load month", command=self.load_month).grid(row=1, column=4, padx=(12, 0))
        self.heading = ttk.Label(self.parent, style="Heading.TLabel", wraplength=720)
        self.heading.pack(anchor="w", pady=(0, 8))

        tabs = ttk.Notebook(self.parent)
        tabs.pack(fill="both", expand=True)
        entry_tab, totals_tab = ttk.Frame(tabs, padding=12), ttk.Frame(tabs, padding=12)
        tabs.add(entry_tab, text="Monthly entries")
        tabs.add(totals_tab, text="Category totals")
        form = ttk.LabelFrame(entry_tab, text="Add an expense", padding=12)
        form.pack(fill="x", pady=(0, 8))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        ttk.Label(form, text="Amount (₹)").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.amount_entry = ttk.Entry(form, textvariable=self.amount, width=20)
        self.amount_entry.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=4)
        ttk.Label(form, text="Category").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        self.category_box = ttk.Combobox(form, textvariable=self.category, values=tuple(self.category_choices), state="readonly", width=22)
        self.category_box.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=4)
        self.category_box.bind("<<ComboboxSelected>>", self.category_changed)
        ttk.Label(form, text="Subcategory").grid(row=1, column=2, sticky="w", padx=(0, 10), pady=4)
        self.subcategory_box = ttk.Combobox(form, textvariable=self.subcategory, state="disabled", width=22)
        self.subcategory_box.grid(row=1, column=3, sticky="ew", pady=4)
        ttk.Label(form, text="Description").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        self.description_entry = ttk.Entry(form, textvariable=self.description)
        self.description_entry.grid(row=2, column=1, columnspan=3, sticky="ew", pady=4)
        ttk.Label(form, text="Amount, category, and subcategory are required. Description is optional. No commas in amounts.", wraplength=680).grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 4))
        self.add_button = ttk.Button(form, text="Add expense", command=self.add_expense)
        self.add_button.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.status = ttk.Label(entry_tab, wraplength=700)
        self.status.pack(anchor="w", pady=(0, 8))
        self.entries = self._table(entry_tab, (("user", "User", 120), ("category", "Category", 140), ("subcategory", "Subcategory", 140), ("description", "Description", 240), ("amount", "Amount (₹)", 140)), height=8)
        self.delete_button = ttk.Button(entry_tab, text="Remove selected expense", command=self.remove_expense)
        self.delete_button.pack(anchor="w", pady=(8, 0))

        ttk.Label(totals_tab, text="Sum by category", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        self.category_totals = self._table(totals_tab, (("category", "Category", 300), ("count", "Entries", 100), ("amount", "Total (₹)", 200)), height=5)
        ttk.Label(totals_tab, text="Sum by subcategory", style="Heading.TLabel").pack(anchor="w", pady=(12, 8))
        self.subcategory_totals = self._table(totals_tab, (("category", "Category", 200), ("subcategory", "Subcategory", 220), ("count", "Entries", 80), ("amount", "Total (₹)", 160)), height=5)
        self.total = ttk.Label(self.parent, style="Heading.TLabel")
        self.total.pack(anchor="w", pady=(12, 0))
        self.combined_total = ttk.Label(self.parent, wraplength=700)
        self.combined_total.pack(anchor="w", pady=(6, 0))

    @staticmethod
    def _table(parent, columns, height):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=tuple(key for key, _, _ in columns), show="headings", height=height, selectmode="browse")
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=70, anchor="e" if key in ("amount", "count") else "w")
        tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        return tree

    def selected_scope(self):
        name = self.user.get()
        if name != "ALL" and name not in self.user_choices:
            raise ValueError("Select a valid user. Create names in Users first.")
        try:
            year, month = int(self.year.get()), MONTHS.index(self.month.get()) + 1
            validate_period(year, month)
        except ValueError:
            raise ValueError("Choose a valid month and a year from 1900 to 9999.") from None
        return None if name == "ALL" else self.user_choices[name], year, month

    def form_values(self):
        return tuple(variable.get() for variable in (self.amount, self.category, self.subcategory, self.description))

    def can_discard_changes(self):
        return self.form_values() == self.original_values or messagebox.askyesno("Unsaved expense", "Discard the expense that has not been added?", parent=self.parent)

    def scope_changed(self, *args):
        self.add_button.state(["disabled"])
        self.delete_button.state(["disabled"])
        self.status.configure(text="Selection changed. Click Load month before entering or removing expenses.")
        try:
            if self.selected_scope() == self.loaded_scope:
                self._set_controls()
        except ValueError:
            pass

    def _set_controls(self):
        editable = self.store.user_id is not None
        self.amount_entry.state(["!readonly"] if editable else ["readonly"])
        self.description_entry.state(["!readonly"] if editable else ["readonly"])
        self.category_box.configure(state="readonly" if editable and self.category_choices else "disabled")
        self.subcategory_box.configure(state="readonly" if editable and self.subcategory_choices else "disabled")
        self.add_button.state(["!disabled"] if editable and self.category_choices else ["disabled"])
        self.delete_button.state(["!disabled"] if editable else ["disabled"])
        if not self.category_choices:
            text = "Category and subcategory values are awaiting your list. Expense entry will be enabled when those dropdown values are configured."
        elif not editable:
            text = "ALL is read-only. Select a named user and click Load month to add expenses."
        else:
            text = "Enter an expense for the user and month shown above. Totals update after every entry."
        self.status.configure(text=text)

    def category_changed(self, event=None):
        self.subcategory.set("")
        category_id = self.category_choices.get(self.category.get())
        self.subcategory_choices = {subcategory.name: subcategory.id for subcategory in self.catalog.subcategories(category_id)} if category_id is not None else {}
        self.subcategory_box.configure(values=tuple(self.subcategory_choices), state="readonly" if self.subcategory_choices and self.store.user_id is not None else "disabled")

    def load_month(self, check_changes=True):
        try:
            scope = self.selected_scope()
            if check_changes and not self.can_discard_changes():
                return
            store = ExpenseStore(self.database, scope[0])
            summary = store.summary(*scope[1:])
            combined = ExpenseStore(self.database, None).summary(*scope[1:])
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Cannot load expenses", str(error), parent=self.parent)
            return
        self.store, self.loaded_scope = store, scope
        for variable in (self.amount, self.category, self.subcategory, self.description):
            variable.set("")
        self.category_changed()
        self.original_values = self.form_values()
        self.heading.configure(text=f"{self.store.user_name} — {month_label(*scope[1:])}")
        self._set_controls()
        self.render_summary(summary, combined)

    def render_summary(self, summary, combined):
        for tree in (self.entries, self.category_totals, self.subcategory_totals):
            for item in tree.get_children():
                tree.delete(item)
        self.entries_by_id = {str(expense.id): expense for expense in summary.entries}
        for expense in summary.entries:
            self.entries.insert("", "end", iid=str(expense.id), values=(expense.user_name, expense.category, expense.subcategory, expense.description, format_amount(expense.amount)))
        for category, amount, count in summary.category_totals:
            self.category_totals.insert("", "end", values=(category, count, format_amount(amount)))
        for category, subcategory, amount, count in summary.subcategory_totals:
            self.subcategory_totals.insert("", "end", values=(category, subcategory, count, format_amount(amount)))
        label = month_label(*self.loaded_scope[1:])
        self.total.configure(text=f"{self.store.user_name} • {label} • Total expense: {format_amount(summary.total)} ({len(summary.entries)} entries)")
        self.combined_total.configure(text=f"ALL users combined • {label}: {format_amount(combined.total)}")

    def require_loaded_user(self):
        scope = self.selected_scope()
        if scope != self.loaded_scope:
            raise ValueError("The selection changed. Click Load month before adding or removing expenses.")
        if self.store.user_id is None:
            raise ValueError("ALL is read-only. Select a named user and click Load month.")
        return scope

    def refresh_totals(self):
        period = self.loaded_scope[1:]
        self.render_summary(self.store.summary(*period), ExpenseStore(self.database, None).summary(*period))

    def add_expense(self):
        try:
            scope = self.require_loaded_user()
            category_id = self.category_choices.get(self.category.get())
            subcategory_id = self.subcategory_choices.get(self.subcategory.get())
            if category_id is None or subcategory_id is None:
                raise ValueError("Choose a category and its subcategory. Dropdown values must be configured first.")
            self.store.add(*scope[1:], parse_amount(self.amount.get()), category_id, subcategory_id, self.description.get())
            self.amount.set("")
            self.description.set("")
            self.original_values = self.form_values()
            self.refresh_totals()
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Cannot add expense", str(error), parent=self.parent)
            return
        self.status.configure(text="Expense saved locally. Category totals and monthly total updated.")

    def remove_expense(self):
        try:
            scope = self.require_loaded_user()
            selected = self.entries.selection()
            if not selected or selected[0] not in self.entries_by_id:
                raise ValueError("Select an expense to remove.")
            expense = self.entries_by_id[selected[0]]
            if not messagebox.askyesno("Remove expense", f"Remove {format_amount(expense.amount)} for {expense.category} from {self.store.user_name} — {month_label(*scope[1:])}?", parent=self.parent):
                return
            self.store.delete(expense.id, *scope[1:])
            self.refresh_totals()
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Cannot remove expense", str(error), parent=self.parent)
            return
        self.status.configure(text="Expense removed. Monthly totals updated.")


def build(parent, database):
    return ExpenseCalculatorView(parent, database)
