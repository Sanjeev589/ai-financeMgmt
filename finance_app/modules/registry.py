"""Explicit module registration; no downloaded or dynamically loaded plugins."""

from dataclasses import dataclass
from typing import Callable

from .my_finance import build as build_my_finance


@dataclass(frozen=True)
class MenuModule:
    key: str
    title: str
    build: Callable


# Each user-described module gets an explicit entry here.
MODULES: tuple[MenuModule, ...] = (MenuModule("my_finance", "My Finance", build_my_finance),)
