# Personal Finance Management

An offline Python desktop application, built one user-defined menu at a time.
Version 0.2 provides the My Finance monthly entry and history module, local SQLite
storage, an explicit module registry, and privacy enforcement.

## Run

Install Python 3.10 or newer with Tcl/Tk support, copy this project to your
computer, open a terminal in the project folder, and run:

```sh
python -m finance_app
```

On Windows, `py -m finance_app` also works. Python's Windows installer normally
includes Tcl/Tk. Linux may require an OS-provided Tkinter package installed
beforehand. No pip install, browser, server, account, or internet connection is
needed to run the application once Python and Tcl/Tk are available.

## My Finance

1. Open **My Finance → Monthly entry**. The month and year default to the current
   month on your computer. To choose another month/year, select it and click
   **Load month** before entering values.
2. Enter **Invested** and **Current value** for **Stocks**, **Mutual Funds**,
   **FD** (fixed deposits), and **RD** (recurring deposits). Values are monthly
   snapshots of total invested capital and current value, not just contributions
   made during that month. Amounts use INR with up to two decimal places, without
   commas. Enter `0` for assets you do not hold; all eight amounts are required.
3. Click **Save month**. Loading a saved month allows updating it after confirmation;
   there is exactly one snapshot per month, containing all four asset balances.
4. Open **All months**. Each row starts with its month/year (for example,
   **October 2026**), followed by invested, current, MoM invested difference, and
   MoM current difference for each asset. Horizontal/vertical scrolling shows
   the full history. Select a row for a compact breakdown of all four assets.
5. Choose **Edit selected month**, or double-click a history row, to load its entry.

**MoM invested difference** = this month's invested amount − previous calendar
month's invested amount, for the same asset. **MoM current difference** uses the
current values in the same way. This applies to Stocks, Mutual Funds, FD, and RD.
January compares to December of the preceding year. Missing previous-month data
shows `—`, not zero or a comparison to an earlier non-adjacent month. Entering or
updating a prior month automatically recalculates affected comparisons. Differences
are amounts in INR, not percentage returns; a change in current value includes
both contributions/withdrawals and valuation changes.

Money is stored as integer paise to avoid floating-point rounding. Existing
version-0.1 databases are upgraded transactionally without losing settings.
Unsaved edits require confirmation before switching months, leaving the module,
or closing the application.

## Data and privacy

- SQLite data stays outside the source folder:
  - Windows: `%LOCALAPPDATA%\OfflineFinance\finance.sqlite3`
  - macOS: `~/Library/Application Support/OfflineFinance/finance.sqlite3`
  - Linux: `~/.local/share/OfflineFinance/finance.sqlite3`
- No network clients, telemetry, cloud sync, remote resources, bank connections,
  automatic updates, or uploading code exist in the application.
- A Python audit hook denies socket/network and external-process activity.
- Runtime data, imports, exports, backups, and logs are excluded from Git.
- The database is not encrypted. Local filesystem/disk security remains the
  operating system's responsibility. Avoid cloud-synced application data folders.
- The runtime hook and source checks protect the maintained code, but do not
  replace an OS sandbox against arbitrary malicious future code changes. Future
  commits must keep the offline policy and pass review and regression tests.

## Development

```sh
python -m unittest discover -s tests -v
```

New menus live under `finance_app/modules/` and are registered in
`finance_app/modules/registry.py`. Each builder receives the content frame and
local database. There is no dynamic plugin loading.

Only source code and synthetic tests may be published to GitHub. Publishing is
a developer action outside the application; the application contains no GitHub
integration. Review the staged file list before every commit. Git ignore rules
are a safeguard, not protection against manually forcing data into Git.

See `docs/ROADMAP.md` for incremental module work and `AGENTS.md` for project rules.
