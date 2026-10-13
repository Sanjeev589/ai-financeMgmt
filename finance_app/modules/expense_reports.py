"""Local calendar-period expense figures, stacked amount graphs, and pie charts."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
import sqlite3
import tkinter as tk
from tkinter import ttk

from .expenses import ExpenseStore, report_months
from .finance import MONTHS, format_amount, month_label
from .finance_graph import axis_range


PALETTE = ("#2563eb", "#15803d", "#b45309", "#9333ea", "#dc2626", "#0891b2", "#db2777", "#4f46e5", "#4d7c0f", "#475569")


@dataclass(frozen=True)
class TimeSeries:
    label: str
    values: tuple[int, ...]


def grouped_totals(summary, grouping):
    if grouping == "Overall":
        return (("Total expense", summary.total),) if summary.total else ()
    if grouping == "Category":
        return tuple((name, amount) for name, amount, count in summary.category_totals)
    if grouping == "Subcategory":
        return tuple((f"{category} / {name}", amount) for category, name, amount, count in summary.subcategory_totals)
    raise ValueError("Choose Overall, Category, or Subcategory.")


def time_series(summary, year, months, grouping):
    """One month uses calendar days; quarters/years use calendar months."""
    labels = tuple(str(day) for day in range(1, monthrange(year, months[0])[1] + 1)) if len(months) == 1 else tuple(f"{MONTHS[month - 1][:3]} {year}" for month in months)
    unknown = len(months) == 1 and any(expense.day is None for expense in summary.entries)
    if unknown:
        labels += ("Undated",)
    grouped_totals(summary, grouping)  # Validate the grouping, including empty reports.
    if grouping == "Overall":
        items = ((None, "Total expense"),) if summary.total else ()
    elif grouping == "Category":
        items = tuple((name, name) for name, amount, count in summary.category_totals)
    else:
        items = tuple(((category, name), f"{category} / {name}") for category, name, amount, count in summary.subcategory_totals)
    values = {key: [0] * len(labels) for key, label in items}
    for expense in summary.entries:
        group = None if grouping == "Overall" else expense.category if grouping == "Category" else (expense.category, expense.subcategory)
        index = (len(labels) - 1 if expense.day is None else expense.day - 1) if len(months) == 1 else months.index(expense.month)
        values[group][index] += expense.amount
    return labels, tuple(TimeSeries(label, tuple(values[key])) for key, label in items)


def percentage(amount, total):
    hundredths = amount * 10000 // total if total else 0
    return f"{hundredths // 100}.{hundredths % 100:02d}%"


class ExpenseReports:
    def __init__(self, parent, database, exclude_one_time):
        self.database = database
        self.store = ExpenseStore(database, None)
        self.exclude_one_time = exclude_one_time
        self.paused = False
        self.summary = None
        self.months = ()
        self.pending = None
        today = date.today()
        self.period = tk.StringVar(master=parent, value="Monthly")
        self.year = tk.StringVar(master=parent, value=str(today.year))
        self.month = tk.StringVar(master=parent, value=MONTHS[today.month - 1])
        self.quarter = tk.StringVar(master=parent, value=f"Q{(today.month - 1) // 3 + 1}")
        self.grouping = tk.StringVar(master=parent, value="Category")
        controls = ttk.Frame(parent)
        controls.pack(fill="x", pady=(0, 8))
        for period in ("Monthly", "Quarterly", "Yearly"):
            ttk.Radiobutton(controls, text=period, variable=self.period, value=period).pack(side="left", padx=(0, 12))
        dates = ttk.Frame(parent)
        dates.pack(fill="x", pady=(0, 8))
        ttk.Label(dates, text="Year").pack(side="left", padx=(0, 8))
        ttk.Spinbox(dates, textvariable=self.year, from_=1900, to=9999, width=6).pack(side="left", padx=(0, 12))
        self.month_box = ttk.Combobox(dates, textvariable=self.month, values=MONTHS, state="readonly", width=12)
        self.month_box.pack(side="left", padx=(0, 12))
        self.quarter_box = ttk.Combobox(dates, textvariable=self.quarter, values=("Q1", "Q2", "Q3", "Q4"), state="disabled", width=4)
        self.quarter_box.pack(side="left", padx=(0, 12))
        ttk.Label(dates, text="Breakdown").pack(side="left", padx=(0, 8))
        ttk.Combobox(dates, textvariable=self.grouping, values=("Overall", "Category", "Subcategory"), state="readonly", width=12).pack(side="left")
        self.heading = ttk.Label(parent, style="Heading.TLabel", wraplength=740)
        self.heading.pack(anchor="w", pady=(0, 6))
        self.status = ttk.Label(parent, wraplength=740)
        self.status.pack(anchor="w", pady=(0, 8))
        tabs = ttk.Notebook(parent)
        tabs.pack(fill="both", expand=True)
        figures, amounts, pie = (ttk.Frame(tabs, padding=8) for _ in range(3))
        tabs.add(figures, text="Figures")
        tabs.add(amounts, text="Amount graph")
        tabs.add(pie, text="Pie chart")
        self.figures = ttk.Treeview(figures, columns=("group", "count", "amount"), show="headings", height=8)
        for key, label, width in (("group", "Category / subcategory", 440), ("count", "Entries", 90), ("amount", "Expense (₹)", 200)):
            self.figures.heading(key, text=label)
            self.figures.column(key, width=width, minwidth=80, anchor="e" if key != "group" else "w")
        self.figures.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(figures, orient="vertical", command=self.figures.yview)
        scrollbar.pack(side="right", fill="y")
        self.figures.configure(yscrollcommand=scrollbar.set)
        self.amount_canvas = tk.Canvas(amounts, background="white", highlightthickness=0, height=260)
        self.amount_canvas.pack(fill="both", expand=True)
        self.pie_canvas = tk.Canvas(pie, background="white", highlightthickness=0, height=250)
        self.pie_canvas.pack(fill="both", expand=True)
        self.legend = ttk.Treeview(parent, columns=("name", "amount", "share"), show="headings", height=3, selectmode="none")
        for key, label, width in (("name", "Chart legend", 420), ("amount", "Amount (₹)", 200), ("share", "Share", 90)):
            self.legend.heading(key, text=label)
            self.legend.column(key, width=width, minwidth=70, anchor="w" if key == "name" else "e")
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(6, 0))
        self.legend.pack(in_=frame, side="left", fill="x", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.legend.yview)
        scroll.pack(side="right", fill="y")
        self.legend.configure(yscrollcommand=scroll.set)
        for canvas in (self.amount_canvas, self.pie_canvas):
            canvas.bind("<Configure>", self.schedule_draw)
            canvas.bind("<Destroy>", self.dispose)
        for variable in (self.period, self.year, self.month, self.quarter, self.grouping):
            variable.trace_add("write", self.refresh)

    def set_context(self, user_id, year, month):
        self.paused = True
        try:
            self.store = ExpenseStore(self.database, user_id)
            self.year.set(str(year))
            self.month.set(MONTHS[month - 1])
            self.quarter.set(f"Q{(month - 1) // 3 + 1}")
        finally:
            self.paused = False
        self.refresh()

    def refresh(self, *args):
        if self.paused:
            return
        period = self.period.get()
        self.month_box.configure(state="readonly" if period == "Monthly" else "disabled")
        self.quarter_box.configure(state="readonly" if period == "Quarterly" else "disabled")
        try:
            year = int(self.year.get())
            month = MONTHS.index(self.month.get()) + 1 if period == "Monthly" else None
            quarter = int(self.quarter.get()[1:]) if period == "Quarterly" else None
            months = report_months(year, period, month, quarter)
            self.summary = self.store.report(year, period, month=month, quarter=quarter, exclude_one_time=self.exclude_one_time.get())
            self.months = months
            self.report_year = year
            label = month_label(year, months[0]) if period == "Monthly" else f"Q{quarter} {year} ({MONTHS[months[0] - 1]}–{MONTHS[months[-1] - 1]})" if period == "Quarterly" else f"Year {year}"
            self.heading.configure(text=f"{self.store.user_name} • {label} • Total: {format_amount(self.summary.total)}")
            self.status.configure(text=f"{'One-time expenses excluded' if self.exclude_one_time.get() else 'All expenses included'} • {len(self.summary.entries)} entries. Monthly graphs use days; quarterly/yearly graphs use months. Undated entries remain included in totals.")
            self.render_figures()
        except (ValueError, sqlite3.Error) as error:
            self.summary = None
            self.status.configure(text=f"Cannot show report: {error}")
            self.heading.configure(text="Choose a valid report period")
            for tree in (self.figures, self.legend):
                for item in tree.get_children():
                    tree.delete(item)
        self.draw()

    def render_figures(self):
        for tree in (self.figures, self.legend):
            for item in tree.get_children():
                tree.delete(item)
        self.figures.insert("", "end", values=("OVERALL TOTAL", len(self.summary.entries), format_amount(self.summary.total)))
        for category, amount, count in self.summary.category_totals:
            self.figures.insert("", "end", values=(f"Category • {category}", count, format_amount(amount)))
        for category, subcategory, amount, count in self.summary.subcategory_totals:
            self.figures.insert("", "end", values=(f"Subcategory • {category} / {subcategory}", count, format_amount(amount)))
        for index, (label, amount) in enumerate(grouped_totals(self.summary, self.grouping.get())):
            tag = f"color{index}"
            self.legend.tag_configure(tag, foreground=PALETTE[index % len(PALETTE)])
            self.legend.insert("", "end", tags=(tag,), values=(label, format_amount(amount), percentage(amount, self.summary.total)))

    def schedule_draw(self, event=None):
        if self.pending is not None:
            self.amount_canvas.after_cancel(self.pending)
        self.pending = self.amount_canvas.after_idle(self.draw)

    def dispose(self, event=None):
        if self.pending is not None:
            self.amount_canvas.after_cancel(self.pending)
            self.pending = None

    def draw(self):
        self.dispose()
        for canvas in (self.amount_canvas, self.pie_canvas):
            canvas.delete("all")
        if self.summary is None or not self.summary.total:
            for canvas in (self.amount_canvas, self.pie_canvas):
                canvas.create_text(canvas.winfo_width() / 2, canvas.winfo_height() / 2, text="No expenses for the selected period and filters.", width=360, fill="#475569")
            return
        self.draw_amount()
        self.draw_pie()

    def draw_amount(self):
        canvas = self.amount_canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 240 or height < 170:
            return
        labels, series = time_series(self.summary, self.report_year, self.months, self.grouping.get())
        totals = [sum(line.values[index] for line in series) for index in range(len(labels))]
        low, high, step = axis_range(totals)
        left, right, top, bottom = 150, width - 24, 20, height - 64
        for amount in range(0, high + 1, step):
            y = bottom - amount * (bottom - top) / high
            canvas.create_line(left, y, right, y, fill="#e2e8f0")
            canvas.create_text(left - 8, y, anchor="e", text=format_amount(amount), font=("Arial", 9), fill="#475569")
        spacing = (right - left) / len(labels)
        for index, label in enumerate(labels):
            x = left + (index + 0.5) * spacing
            running = 0
            for group_index, line in enumerate(series):
                amount = line.values[index]
                if amount:
                    y0 = bottom - running * (bottom - top) / high
                    running += amount
                    y1 = bottom - running * (bottom - top) / high
                    canvas.create_rectangle(x - spacing * .36, y1, x + spacing * .36, y0, fill=PALETTE[group_index % len(PALETTE)], outline="")
            every = max(1, (len(labels) + 9) // 10)
            if index % every == 0 or index == len(labels) - 1:
                canvas.create_text(x, bottom + 14, text=label.replace(" ", "\n"), anchor="n", font=("Arial", 9), fill="#475569")
        canvas.create_text((left + right) / 2, height - 8, text="Day of month" if len(self.months) == 1 else "Month", fill="#475569", font=("Arial", 9))
        canvas.create_line(left, top, left, bottom, right, bottom, fill="#64748b")

    def draw_pie(self):
        canvas = self.pie_canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 180 or height < 160:
            return
        radius = min(width - 40, height - 40) / 2
        cx, cy = width / 2, height / 2
        bounds = (cx - radius, cy - radius, cx + radius, cy + radius)
        slices = grouped_totals(self.summary, self.grouping.get())
        angle = 90.0
        for index, (label, amount) in enumerate(slices):
            extent = 360 * amount / self.summary.total
            color = PALETTE[index % len(PALETTE)]
            if len(slices) == 1:
                canvas.create_oval(*bounds, fill=color, outline="white")
            else:
                canvas.create_arc(*bounds, start=angle, extent=extent, fill=color, outline="white", style="pieslice")
            angle += extent
