"""Tkinter monthly finance entry and history views. No external resources."""

from datetime import date
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from .finance import ASSETS, MONTHS, FinanceStore, format_amount, input_amount, month_label, parse_amount, validate_period


class MyFinanceView:
    def __init__(self, parent, database):
        self.parent = parent
        self.store = FinanceStore(database)
        self.loaded_period = None
        self.original_values = ()
        self.history_rows = {}
        self.fields = {}

        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill="both", expand=True)
        self.entry_tab = ttk.Frame(self.tabs, padding=16)
        self.history_tab = ttk.Frame(self.tabs, padding=16)
        self.tabs.add(self.entry_tab, text="Monthly entry")
        self.tabs.add(self.history_tab, text="All months")
        self._build_entry()
        self._build_history()
        today = date.today()
        self.month.set(MONTHS[today.month - 1])
        self.year.set(str(today.year))
        self.load_month(check_changes=False)
        self.refresh_history()

    def _build_entry(self):
        selector = ttk.Frame(self.entry_tab)
        selector.pack(fill="x", pady=(0, 16))
        ttk.Label(selector, text="Month").grid(row=0, column=0, padx=(0, 8))
        self.month = tk.StringVar(master=self.parent)
        ttk.Combobox(selector, textvariable=self.month, values=MONTHS, state="readonly", width=13).grid(row=0, column=1)
        ttk.Label(selector, text="Year").grid(row=0, column=2, padx=(16, 8))
        self.year = tk.StringVar(master=self.parent)
        ttk.Spinbox(selector, textvariable=self.year, from_=1900, to=9999, width=6).grid(row=0, column=3)
        ttk.Button(selector, text="Load month", command=self.load_month).grid(row=0, column=4, padx=(16, 0))

        self.entry_heading = ttk.Label(self.entry_tab, style="Heading.TLabel")
        self.entry_heading.pack(anchor="w", pady=(0, 12))
        ttk.Label(self.entry_tab, text="Enter total invested and current value in INR for this month.\nUse 0 for an asset you do not hold. Up to two decimal places; no commas.", wraplength=570).pack(anchor="w", pady=(0, 12))

        grid = ttk.Frame(self.entry_tab)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=1)
        for column, title in enumerate(("Asset", "Invested (₹)", "Current value (₹)")):
            ttk.Label(grid, text=title, style="Heading.TLabel").grid(row=0, column=column, sticky="w", padx=(0, 12), pady=(0, 8))
        for row, (asset, label) in enumerate(ASSETS, start=1):
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", padx=(0, 18), pady=6)
            variables = []
            for column in (1, 2):
                variable = tk.StringVar(master=self.parent)
                ttk.Entry(grid, textvariable=variable, width=19).grid(row=row, column=column, sticky="ew", padx=(0, 12), pady=6)
                variables.append(variable)
            self.fields[asset] = tuple(variables)

        ttk.Button(self.entry_tab, text="Save month", command=self.save_month).pack(anchor="w", pady=(16, 8))
        self.status = ttk.Label(self.entry_tab, wraplength=580)
        self.status.pack(anchor="w")
        ttk.Label(self.entry_tab, text="MoM differences are calculated automatically in All months.", wraplength=580).pack(anchor="w", pady=(12, 0))

    def _build_history(self):
        self.history_heading = ttk.Label(self.history_tab, text="Monthly finance history", style="Heading.TLabel")
        self.history_heading.pack(anchor="w", pady=(0, 6))
        ttk.Label(self.history_tab, text="Each row is headed by month and year. Scroll horizontally for all assets.\nMoM = this month minus the previous calendar month; — means the previous month has no data.", wraplength=590).pack(anchor="w", pady=(0, 8))

        frame = ttk.Frame(self.history_tab)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        columns = tuple(f"{asset}_{field}" for asset, _ in ASSETS for field in ("invested", "current", "invested_diff", "current_diff"))
        self.history = ttk.Treeview(frame, columns=columns, show="tree headings", height=6, selectmode="browse")
        self.history.heading("#0", text="Month / year")
        self.history.column("#0", width=155, minwidth=155, stretch=False)
        for asset, label in ASSETS:
            for field, heading in (("invested", "Invested"), ("current", "Current"), ("invested_diff", "MoM invested Δ"), ("current_diff", "MoM current Δ")):
                column = f"{asset}_{field}"
                self.history.heading(column, text=f"{label}: {heading}")
                self.history.column(column, width=165, minwidth=140, stretch=False, anchor="e")
        self.history.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.history.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.history.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.history.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.history.bind("<<TreeviewSelect>>", self.show_selected)
        self.history.bind("<Double-1>", self.edit_selected)

        self.detail_heading = ttk.Label(self.history_tab, text="Select a month to see its breakdown", style="Heading.TLabel")
        self.detail_heading.pack(anchor="w", pady=(12, 6))
        self.details = ttk.Treeview(self.history_tab, columns=("asset", "invested", "current", "invested_diff", "current_diff"), show="headings", height=4, selectmode="none")
        for field, title, width in (("asset", "Asset", 95), ("invested", "Invested (₹)", 120), ("current", "Current (₹)", 120), ("invested_diff", "MoM invested Δ", 140), ("current_diff", "MoM current Δ", 140)):
            self.details.heading(field, text=title)
            self.details.column(field, width=width, minwidth=75, anchor="w" if field == "asset" else "e")
        self.details.pack(fill="x")
        ttk.Button(self.history_tab, text="Edit selected month", command=self.edit_selected).pack(anchor="w", pady=(8, 0))

    def selected_period(self):
        try:
            year = int(self.year.get())
            month = MONTHS.index(self.month.get()) + 1
            validate_period(year, month)
            return year, month
        except ValueError:
            raise ValueError("Choose a valid month and a year from 1900 to 9999.") from None

    def field_values(self):
        return tuple(variable.get() for asset, _ in ASSETS for variable in self.fields[asset])

    def can_discard_changes(self):
        return self.field_values() == self.original_values or messagebox.askyesno(
            "Unsaved changes", "Discard the unsaved entry values?", parent=self.parent
        )

    def load_month(self, check_changes=True):
        try:
            period = self.selected_period()
            if check_changes and not self.can_discard_changes():
                return
            record = self.store.get_month(*period)
        except (ValueError, sqlite3.Error, RuntimeError) as error:
            messagebox.showerror("Cannot load month", str(error), parent=self.parent)
            return
        values = {balance.asset: (balance.invested, balance.current) for balance in record.balances} if record else {}
        for asset, _ in ASSETS:
            for index, variable in enumerate(self.fields[asset]):
                variable.set(input_amount(values[asset][index]) if record else "")
        self.loaded_period = period
        self.original_values = self.field_values()
        self.entry_heading.configure(text=f"Monthly entry — {month_label(*period)}")
        self.status.configure(text="Saved month loaded. You can update these values." if record else "New month. Enter all eight amounts, using 0 where applicable.")

    def save_month(self):
        try:
            period = self.selected_period()
            if period != self.loaded_period:
                raise ValueError("The month selection changed. Click Load month before entering or saving its values.")
            values = {}
            for asset, label in ASSETS:
                try:
                    values[asset] = tuple(parse_amount(variable.get()) for variable in self.fields[asset])
                except ValueError as error:
                    raise ValueError(f"{label}: {error}") from None
            existing = self.store.get_month(*period)
            if existing and not messagebox.askyesno("Update saved month", f"Replace the saved values for {month_label(*period)}?", parent=self.parent):
                return
            self.store.save_month(*period, values)
        except (ValueError, sqlite3.Error, RuntimeError) as error:
            messagebox.showerror("Cannot save month", str(error), parent=self.parent)
            return
        self.original_values = self.field_values()
        self.status.configure(text=f"Saved {month_label(*period)} on this computer. Open All months to view it.")
        self.refresh_history(period)

    def refresh_history(self, preferred_period=None):
        for tree in (self.history, self.details):
            for item in tree.get_children():
                tree.delete(item)
        self.history_rows = {}
        self.detail_heading.configure(text="Select a month to see its breakdown")
        try:
            rows = self.store.history()
        except (sqlite3.Error, RuntimeError) as error:
            messagebox.showerror("Cannot read history", str(error), parent=self.parent)
            return
        for row in rows:
            period = (row.record.year, row.record.month)
            item = f"{period[0]}-{period[1]:02d}"
            self.history_rows[item] = row
            values = tuple(value for change in row.changes for value in (
                format_amount(change.balance.invested), format_amount(change.balance.current),
                format_amount(change.invested_diff, signed=True), format_amount(change.current_diff, signed=True),
            ))
            self.history.insert("", "end", iid=item, text=month_label(*period), values=values)
        self.history_heading.configure(text="Monthly finance history" if rows else "No saved months yet — add your first monthly entry")
        if rows:
            item = f"{preferred_period[0]}-{preferred_period[1]:02d}" if preferred_period else next(iter(self.history_rows))
            if item in self.history_rows:
                self.history.selection_set(item)
                self.history.see(item)
                self.show_selected()

    def show_selected(self, event=None):
        selected = self.history.selection()
        if not selected or selected[0] not in self.history_rows:
            return
        row = self.history_rows[selected[0]]
        self.detail_heading.configure(text=f"{month_label(row.record.year, row.record.month)} — all assets")
        for item in self.details.get_children():
            self.details.delete(item)
        labels = dict(ASSETS)
        for change in row.changes:
            self.details.insert("", "end", values=(
                labels[change.balance.asset], format_amount(change.balance.invested),
                format_amount(change.balance.current), format_amount(change.invested_diff, signed=True),
                format_amount(change.current_diff, signed=True),
            ))

    def edit_selected(self, event=None):
        selected = self.history.selection()
        if not selected or selected[0] not in self.history_rows:
            return
        if not self.can_discard_changes():
            return
        record = self.history_rows[selected[0]].record
        self.month.set(MONTHS[record.month - 1])
        self.year.set(str(record.year))
        self.load_month(check_changes=False)
        self.tabs.select(self.entry_tab)


def build(parent, database):
    return MyFinanceView(parent, database)
