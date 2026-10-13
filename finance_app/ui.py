"""Desktop shell with explicit navigation and local database ownership."""

import tkinter as tk
from tkinter import ttk

from . import __version__
from .modules.registry import MODULES


class FinanceApp:
    def __init__(self, root, database):
        self.root = root
        self.database = database
        self.active_view = None
        root.title("Personal Finance — Offline")
        root.geometry("1120x760")
        root.minsize(960, 680)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Arial", 23, "bold"))
        style.configure("Heading.TLabel", font=("Arial", 12, "bold"))
        style.configure("TButton", padding=(12, 10))

        sidebar = ttk.Frame(root, padding=20)
        sidebar.pack(side="left", fill="y")
        ttk.Label(sidebar, text="PERSONAL\nFINANCE", style="Heading.TLabel").pack(anchor="w", pady=(0, 25))
        ttk.Button(sidebar, text="Home", command=self.home).pack(fill="x", pady=4)
        for module in MODULES:
            ttk.Button(sidebar, text=module.title, command=lambda m=module: self.open_module(m)).pack(fill="x", pady=4)
        ttk.Button(sidebar, text="Privacy & storage", command=self.privacy).pack(fill="x", pady=4)
        ttk.Button(sidebar, text="About", command=self.about).pack(fill="x", pady=4)
        ttk.Label(sidebar, text="Offline • Local storage").pack(side="bottom", anchor="w")

        self.content = ttk.Frame(root, padding=30)
        self.content.pack(side="right", fill="both", expand=True)
        self.home()

    def page(self, title):
        if self.active_view is not None and not self.active_view.can_discard_changes():
            return False
        self.active_view = None
        for child in self.content.winfo_children():
            child.destroy()
        ttk.Label(self.content, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, 25))
        return True

    def paragraph(self, text):
        ttk.Label(self.content, text=text, wraplength=610, justify="left").pack(anchor="w", pady=(0, 18))

    def home(self):
        if not self.page("Your finances, on your computer"):
            return
        self.paragraph("Welcome to your personal finance workspace. Your information is stored locally.")
        self.paragraph("Open My Finance to record monthly invested and current values for Stocks, Mutual Funds, FD, and RD.")
        self.paragraph("View saved months and month-over-month differences in All months. Use Graph to compare trends and show or hide any field. More menus will be added as they are defined.")

    def privacy(self):
        if not self.page("Privacy & storage"):
            return
        self.paragraph("The application has no cloud sync, telemetry, bank connections, web assets, or automatic updates. Network and external-process operations are blocked at runtime.")
        self.paragraph(f"Local database:\n{self.database.path}")
        self.paragraph("Data is stored outside the project folder. Databases, imported files, exports, and backups must never be included in Git commits.")
        self.paragraph("The local database is not encrypted. Protect this computer with your operating system account and disk encryption.")

    def about(self):
        if not self.page("About"):
            return
        self.paragraph(f"Personal Finance Management\nVersion {__version__}\nPython desktop application with SQLite local storage.")

    def open_module(self, module):
        if not self.page(module.title):
            return
        self.active_view = module.build(self.content, self.database)

    def close(self):
        if self.active_view is not None and not self.active_view.can_discard_changes():
            return
        self.database.close()
        self.root.destroy()
