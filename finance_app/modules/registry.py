"""Explicit module registration; no downloaded or dynamically loaded plugins."""

from dataclasses import dataclass
from typing import Callable

from .my_finance import build as build_my_finance
from .users import build as build_users
from .expense_calculator import build as build_expense_calculator


@dataclass(frozen=True)
class MenuModule:
    key: str
    title: str
    build: Callable


# Each user-described module gets an explicit entry here.
MODULES: tuple[MenuModule, ...] = (
    MenuModule("my_finance", "My Finance", build_my_finance),
    MenuModule("users", "Users", build_users),
    MenuModule("expense_calculator", "Expense Calculator", build_expense_calculator),
)
