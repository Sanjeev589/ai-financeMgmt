"""Offline graph data and Tkinter Canvas rendering; no chart dependencies."""

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

from .finance import ASSETS, MONTHS, format_amount, month_label


METRICS = (
    ("invested", "Invested", (6, 3)),
    ("current", "Current", ()),
    ("invested_diff", "MoM invested", (2, 3)),
    ("current_diff", "MoM current", (7, 3, 2, 3)),
)
COLORS = {"stocks": "#2563eb", "mutual_funds": "#15803d", "fd": "#b45309", "rd": "#9333ea"}


@dataclass(frozen=True)
class GraphPoint:
    year: int
    month: int
    amount: int | None

    @property
    def ordinal(self):
        return self.year * 12 + self.month - 1


@dataclass(frozen=True)
class GraphSeries:
    key: str
    label: str
    color: str
    dash: tuple[int, ...]
    points: tuple[GraphPoint, ...]


def make_series(history, enabled):
    """Use only checked fields; preserve paise, year order, and unknown MoMs."""
    ordered = sorted(history, key=lambda row: (row.record.year, row.record.month))
    result = []
    for asset, label in ASSETS:
        for metric, title, dash in METRICS:
            key = f"{asset}_{metric}"
            if key not in enabled:
                continue
            points = []
            for row in ordered:
                change = next(change for change in row.changes if change.balance.asset == asset)
                value = getattr(change.balance, metric) if metric in ("invested", "current") else getattr(change, metric)
                points.append(GraphPoint(row.record.year, row.record.month, value))
            result.append(GraphSeries(key, f"{label} — {title}", COLORS[asset], dash, tuple(points)))
    return tuple(result)


def segments(points):
    """Break lines at absent calendar months or unknown values."""
    result = []
    current = []
    for point in points:
        if point.amount is None:
            if current:
                result.append(tuple(current))
            current = []
            continue
        if current and point.ordinal != current[-1].ordinal + 1:
            result.append(tuple(current))
            current = []
        current.append(point)
    if current:
        result.append(tuple(current))
    return tuple(result)


def axis_range(values):
    """Round integer paise to useful ticks; include zero and negative changes."""
    low, high = min(0, min(values)), max(0, max(values))
    if low == high:
        high = 100
    target = max(1, (high - low + 4) // 5)
    magnitude = 1
    while magnitude * 10 <= target:
        magnitude *= 10
    step = next(factor * magnitude for factor in (1, 2, 5, 10) if factor * magnitude >= target)
    low = (low // step) * step
    high = ((high + step - 1) // step) * step
    return low, high, step


class FinanceGraph:
    def __init__(self, parent):
        self.history = ()
        self.enabled = {}
        self.hit_points = []
        self.pending_redraw = None
        self.heading = ttk.Label(parent, text="Compare monthly finances", style="Heading.TLabel")
        self.heading.pack(anchor="w", pady=(0, 6))
        self.scope_name = "ALL"
        ttk.Label(parent, text="Check or uncheck any field to show or hide its line. All amounts are in INR.\nDashed: invested • Solid: current • Dotted: MoM invested • Dash-dot: MoM current", wraplength=660).pack(anchor="w", pady=(0, 8))
        controls = ttk.Frame(parent)
        controls.pack(fill="x")
        for row, (asset, label) in enumerate(ASSETS):
            ttk.Label(controls, text=label, foreground=COLORS[asset]).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            for column, (metric, title, _) in enumerate(METRICS, start=1):
                variable = tk.BooleanVar(master=parent, value=metric in ("invested", "current"))
                self.enabled[f"{asset}_{metric}"] = variable
                ttk.Checkbutton(controls, text=title, variable=variable, command=self.draw).grid(row=row, column=column, sticky="w", padx=(0, 10))
        presets = ttk.Frame(parent)
        presets.pack(fill="x", pady=(6, 8))
        for text, metrics in (("Balances", ("invested", "current")), ("MoM changes", ("invested_diff", "current_diff")), ("Show all", tuple(metric for metric, _, _ in METRICS)), ("Hide all", ())):
            ttk.Button(presets, text=text, command=lambda selected=metrics: self.select_metrics(selected)).pack(side="left", padx=(0, 6))
        self.canvas = tk.Canvas(parent, background="#ffffff", highlightthickness=1, highlightbackground="#d1d5db", height=240)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.schedule_redraw)
        self.canvas.bind("<Destroy>", self.dispose)
        self.canvas.bind("<Motion>", self.hover)
        self.canvas.bind("<Leave>", lambda event: self.hover_text.set(self.hint))
        self.hint = "Hover over a point for its exact value. Only saved months are plotted; gaps are not joined."
        self.hover_text = tk.StringVar(master=parent, value=self.hint)
        ttk.Label(parent, textvariable=self.hover_text, wraplength=660).pack(anchor="w", pady=(6, 0))

    def set_history(self, history):
        self.history = tuple(history)
        self.draw()

    def set_scope(self, name):
        self.scope_name = name
        self.heading.configure(text=f"{name} — monthly finance graph")

    def select_metrics(self, metrics):
        for asset, _ in ASSETS:
            for metric, _, _ in METRICS:
                self.enabled[f"{asset}_{metric}"].set(metric in metrics)
        self.draw()

    def schedule_redraw(self, event=None):
        if self.pending_redraw is not None:
            self.canvas.after_cancel(self.pending_redraw)
        self.pending_redraw = self.canvas.after_idle(self.draw)

    def dispose(self, event=None):
        if self.pending_redraw is not None:
            self.canvas.after_cancel(self.pending_redraw)
            self.pending_redraw = None

    def draw(self):
        if self.pending_redraw is not None:
            self.canvas.after_cancel(self.pending_redraw)
            self.pending_redraw = None
        canvas = self.canvas
        canvas.delete("all")
        self.hit_points = []
        self.hover_text.set(self.hint)
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 200 or height < 160:
            return
        enabled = {key for key, variable in self.enabled.items() if variable.get()}
        series = make_series(self.history, enabled)
        amounts = [point.amount for line in series for point in line.points if point.amount is not None]
        if not self.history or not series or not amounts:
            text = "Save your first monthly entry to see the graph." if not self.history else "Select at least one field above." if not series else "No previous-month data is available for the selected MoM fields."
            canvas.create_text(width / 2, height / 2, text=text, width=width - 60, fill="#475569", font=("Arial", 11))
            return

        left, right, top, bottom = 150, width - 30, 20, height - 60
        low, high, step = axis_range(amounts)
        ordinals = sorted({point.ordinal for line in series for point in line.points})
        first, last = ordinals[0], ordinals[-1]

        def position(point):
            # Floating-point values are used only for pixel coordinates. All
            # financial values, comparisons, and axis ticks remain integer paise.
            x = (left + right) / 2 if first == last else left + (point.ordinal - first) * (right - left) / (last - first)
            y = bottom - (point.amount - low) * (bottom - top) / (high - low)
            return x, y

        for value in range(low, high + 1, step):
            y = bottom - (value - low) * (bottom - top) / (high - low)
            canvas.create_line(left, y, right, y, fill="#94a3b8" if value == 0 else "#e2e8f0")
            canvas.create_text(left - 10, y, text=format_amount(value), anchor="e", fill="#475569", font=("Arial", 9))
        canvas.create_line(left, top, left, bottom, fill="#64748b")
        canvas.create_line(left, bottom, right, bottom, fill="#64748b")
        tick_count = max(2, min(6, (right - left) // 100))
        ticks = {first, last}
        ticks.update(first + index * (last - first) // (tick_count - 1) for index in range(tick_count))
        for ordinal in sorted(ticks):
            year, zero_month = divmod(ordinal, 12)
            x = (left + right) / 2 if first == last else left + (ordinal - first) * (right - left) / (last - first)
            canvas.create_text(x, bottom + 16, text=f"{MONTHS[zero_month][:3]}\n{year}", anchor="n", fill="#475569", font=("Arial", 9))
        for line in series:
            for segment in segments(line.points):
                coordinates = [coordinate for point in segment for coordinate in position(point)]
                if len(segment) > 1:
                    canvas.create_line(*coordinates, fill=line.color, width=2, dash=line.dash)
                for point in segment:
                    x, y = position(point)
                    canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=line.color, outline=line.color)
                    self.hit_points.append((x, y, line.label, point))

    def hover(self, event):
        nearby = [((x - event.x) ** 2 + (y - event.y) ** 2, label, point) for x, y, label, point in self.hit_points]
        if not nearby:
            self.hover_text.set(self.hint)
            return
        distance, label, point = min(nearby, key=lambda item: item[0])
        self.hover_text.set(f"{self.scope_name} • {month_label(point.year, point.month)} • {label}: {format_amount(point.amount)}" if distance <= 144 else self.hint)
