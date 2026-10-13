"""Monthly portfolio snapshots and exact comparisons, using local SQLite only."""

from dataclasses import dataclass
import re

from .users import UserStore


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
    user_ids: frozenset[int] = frozenset()


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
    def __init__(self, database, user_id):
        self.connection = database.connection
        # None means the read-only ALL scope. A named scope is mandatory to save.
        self.user_id = user_id
        self.user_name = "ALL" if user_id is None else UserStore(database).get(user_id).name

    def save_month(self, year, month, values):
        """Create or replace all four asset balances atomically for one month."""
        if self.user_id is None:
            raise ValueError("ALL is a combined, read-only view. Select a named user before saving.")
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
            rows.append((self.user_id, year, month, asset, *amounts))
        with self.connection:
            self.connection.executemany("""
                INSERT INTO monthly_finance (user_id, year, month, asset, invested, current)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, year, month, asset) DO UPDATE SET
                    invested = excluded.invested, current = excluded.current
            """, rows)

    @staticmethod
    def _record(year, month, rows, user_ids=frozenset()):
        values = {row[0]: Balance(*row) for row in rows}
        if set(values) != {asset for asset, _ in ASSETS}:
            raise RuntimeError("The saved month is incomplete; all four asset balances are required.")
        return MonthRecord(year, month, tuple(values[asset] for asset, _ in ASSETS), user_ids)

    def get_month(self, year, month):
        validate_period(year, month)
        records = self._records(year, month)
        return records.get((year, month))

    def _records(self, year=None, month=None):
        sql = "SELECT user_id, year, month, asset, invested, current FROM monthly_finance"
        clauses, parameters = [], []
        if self.user_id is not None:
            clauses.append("user_id = ?")
            parameters.append(self.user_id)
        if year is not None:
            clauses.append("year = ? AND month = ?")
            parameters.extend((year, month))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY year DESC, month DESC, user_id"
        grouped = {}
        for user_id, year, month, asset, invested, current in self.connection.execute(sql, parameters):
            grouped.setdefault((year, month, user_id), []).append((asset, invested, current))
        by_period = {}
        for (year, month, user_id), rows in grouped.items():
            record = self._record(year, month, rows, frozenset((user_id,)))
            by_period.setdefault((year, month), []).append(record)
        records = {}
        for period, contributors in by_period.items():
            # Python integers avoid SQLite SUM overflow when many users' values
            # are combined. No user's missing snapshot is silently stored as 0.
            totals = tuple(Balance(
                asset,
                sum(record.balances[index].invested for record in contributors),
                sum(record.balances[index].current for record in contributors),
            ) for index, (asset, _) in enumerate(ASSETS))
            user_ids = frozenset(user_id for record in contributors for user_id in record.user_ids)
            records[period] = MonthRecord(*period, totals, user_ids)
        return records

    def history(self):
        """Newest first; missing calendar months never become a zero baseline."""
        records = self._records()
        history = []
        for period, record in records.items():
            previous = records.get(previous_period(*period))
            # Combined MoM is known only when the same users have snapshots in
            # both months; otherwise sums of individual differences are unknown.
            baseline = {balance.asset: balance for balance in previous.balances} if previous and previous.user_ids == record.user_ids else {}
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
