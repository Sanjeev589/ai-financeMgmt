"""Monthly portfolio snapshots and exact comparisons, using local SQLite only."""

from dataclasses import dataclass
import re


ASSETS = (("stocks", "Stocks"), ("mutual_funds", "Mutual Funds"), ("fd", "FD"), ("rd", "RD"))
MONTHS = (
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
)
MAX_AMOUNT = 99999999999999  # paise; keeps input and SQLite integer arithmetic bounded.


def validate_period(year, month):
    if type(year) is not int or not 1900 <= year <= 9999:
        raise ValueError("Year must be a whole number from 1900 to 9999.")
    if type(month) is not int or not 1 <= month <= 12:
        raise ValueError("Choose a month from January to December.")


def previous_period(year, month):
    validate_period(year, month)
    return (year - 1, 12) if month == 1 else (year, month - 1)


def month_label(year, month):
    validate_period(year, month)
    return f"{MONTHS[month - 1]} {year}"


def parse_amount(text):
    """Convert a rupee input to integer paise without floating-point rounding."""
    if not isinstance(text, str):
        raise ValueError("Enter an amount as digits with up to two decimal places.")
    text = text.strip()
    if len(text) > 16 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
        raise ValueError("Enter a non-negative amount, without commas, with up to two decimal places.")
    whole, _, fraction = text.partition(".")
    amount = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    if amount > MAX_AMOUNT:
        raise ValueError("Amount must not exceed 999999999999.99.")
    return amount


def input_amount(amount):
    whole, fraction = divmod(amount, 100)
    return f"{whole}.{fraction:02d}"


def format_amount(amount, signed=False):
    if amount is None:
        return "—"
    prefix = "-" if amount < 0 else "+" if signed and amount > 0 else ""
    whole, fraction = divmod(abs(amount), 100)
    return f"{prefix}₹{whole:,}.{fraction:02d}"


@dataclass(frozen=True)
class Balance:
    asset: str
    invested: int
    current: int


@dataclass(frozen=True)
class MonthRecord:
    year: int
    month: int
    balances: tuple[Balance, ...]


@dataclass(frozen=True)
class AssetChange:
    balance: Balance
    invested_diff: int | None
    current_diff: int | None


@dataclass(frozen=True)
class HistoryRow:
    record: MonthRecord
    changes: tuple[AssetChange, ...]


class FinanceStore:
    def __init__(self, database):
        self.connection = database.connection

    def save_month(self, year, month, values):
        """Create or replace all four asset balances atomically for one month."""
        validate_period(year, month)
        if set(values) != {asset for asset, _ in ASSETS}:
            raise ValueError("Enter invested and current values for all four assets.")
        rows = []
        for asset, label in ASSETS:
            amounts = values[asset]
            if not isinstance(amounts, (tuple, list)) or len(amounts) != 2:
                raise ValueError(f"{label}: invested and current values are required.")
            if any(type(amount) is not int or not 0 <= amount <= MAX_AMOUNT for amount in amounts):
                raise ValueError(f"{label}: amounts must be non-negative integer paise within the supported limit.")
            rows.append((year, month, asset, *amounts))
        with self.connection:
            self.connection.executemany("""
                INSERT INTO monthly_finance (year, month, asset, invested, current)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(year, month, asset) DO UPDATE SET
                    invested = excluded.invested, current = excluded.current
            """, rows)

    @staticmethod
    def _record(year, month, rows):
        values = {row[0]: Balance(*row) for row in rows}
        if set(values) != {asset for asset, _ in ASSETS}:
            raise RuntimeError("The saved month is incomplete; all four asset balances are required.")
        return MonthRecord(year, month, tuple(values[asset] for asset, _ in ASSETS))

    def get_month(self, year, month):
        validate_period(year, month)
        rows = self.connection.execute(
            "SELECT asset, invested, current FROM monthly_finance WHERE year = ? AND month = ?",
            (year, month),
        ).fetchall()
        return self._record(year, month, rows) if rows else None

    def history(self):
        """Newest first; missing calendar months never become a zero baseline."""
        groups = {}
        rows = self.connection.execute(
            "SELECT year, month, asset, invested, current FROM monthly_finance ORDER BY year DESC, month DESC"
        ).fetchall()
        for year, month, asset, invested, current in rows:
            groups.setdefault((year, month), []).append((asset, invested, current))
        records = {period: self._record(*period, rows) for period, rows in groups.items()}
        history = []
        for period, record in records.items():
            previous = records.get(previous_period(*period))
            baseline = {balance.asset: balance for balance in previous.balances} if previous else {}
            changes = tuple(
                AssetChange(
                    balance,
                    balance.invested - baseline[balance.asset].invested if baseline else None,
                    balance.current - baseline[balance.asset].current if baseline else None,
                )
                for balance in record.balances
            )
            history.append(HistoryRow(record, changes))
        return tuple(history)
