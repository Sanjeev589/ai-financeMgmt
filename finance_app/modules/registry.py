"""Explicit module registration; no downloaded or dynamically loaded plugins."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MenuModule:
    key: str
    title: str
    build: Callable


# Each user-described module gets an explicit entry here.
MODULES: tuple[MenuModule, ...] = ()
