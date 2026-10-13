# Personal Finance Management

An offline Python desktop application, built one user-defined menu at a time.
Version 0.5 provides named users, My Finance monthly entry and graphs, an Expense
Calculator with monthly category totals, local SQLite storage, and privacy enforcement.

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

1. Open **Users**, enter a **Name**, and click **Add user**. Names are the only
   profile field. Blank names and case-insensitive duplicates are rejected;
   `ALL` is reserved for the combined view. Names and financial records stay local.
2. Open **My Finance** and select the user name from the dropdown above the tabs.
   This selector also applies to **All months** and **Graph**, so every financial
   view clearly belongs to that user. Select **ALL** to view combined data.
3. In **Monthly entry**, the month and year default to the current
   month on your computer. To choose another month/year, select it and click
   **Load month** before entering values. All eight entry values belong to this
   loaded user/month/year. The save button names the user and exact period and is disabled
   whenever the month/year selection changes until you load that period.
4. Enter **Invested** and **Current value** for **Stocks**, **Mutual Funds**,
   **FD** (fixed deposits), and **RD** (recurring deposits). Values are monthly
   snapshots of total invested capital and current value, not just contributions
   made during that month. Amounts use INR with up to two decimal places, without
   commas. Enter `0` for assets you do not hold; all eight amounts are required.
5. Click **Save month**. Loading a saved month allows updating it after confirmation;
   there is exactly one snapshot per user and month, containing all four asset balances.
   Switching users loads that user's values and warns before discarding unsaved input.
   The **ALL** entry form is read-only; select an actual user to save financial data.
6. Open **All months**. Each row starts with its month/year (for example,
   **October 2026**), followed by invested, current, MoM invested difference, and
   MoM current difference for each asset. Horizontal/vertical scrolling shows
   the selected user's full history. Select a row for a breakdown of all four assets.
   Highlighted **ALL** rows at the bottom sum each asset's invested/current values
   and show both automatic MoM differences for that month across users. **ALL • Total**
   sums all four assets. A note shows how many users have saved data for that month.
7. Choose **Edit selected month**, or double-click a history row, to load its entry.
   Combined ALL records cannot be edited.
8. Open **Graph** to compare the selected user's saved months in calendar order.
   Choose a different name, or **ALL**, in the same dropdown before viewing graphs.
   ALL graphs use the same summed amounts and differences as the combined table.
   Each asset has
   separate checkboxes for invested, current, MoM invested, and MoM current.
   Uncheck any field to hide it without changing saved data. **Balances** selects
   the eight entered-value series; **MoM changes** selects the calculated
   differences. **Show all** and **Hide all** control every series at once.
   Colors identify assets and line styles identify fields. Hover over a point
   for its exact month/year, field, and INR amount. Graphs refresh after saves.

The graph uses a local Tkinter Canvas, with no external chart packages or web
resources. The horizontal axis includes month and year; the vertical axis is INR.
Missing months and unknown MoM values break lines rather than being plotted as
zero. A single saved month is displayed with points. All amount calculations
remain in integer paise; floating point is used only for drawing pixel positions.

### Combined totals and missing data

**ALL** sums users' saved snapshots for each individual calendar month; it does
not add balances from different months together. A user without data for that
month is excluded, and the reporting-user count makes this visible. If the same
users have data in two adjacent months, combined MoM is the sum of their individual
differences. If the reporting users differ, combined MoM is `—` until the missing
records are entered. Missing user snapshots are never assumed to be zero.
All MoM fields are calculated automatically and cannot be entered manually.

**MoM invested difference** = this month's invested amount − previous calendar
month's invested amount, for the same asset. **MoM current difference** uses the
current values in the same way. This applies to Stocks, Mutual Funds, FD, and RD.
January compares to December of the preceding year. Missing previous-month data
shows `—`, not zero or a comparison to an earlier non-adjacent month. Entering or
updating a prior month automatically recalculates affected comparisons. Differences
are amounts in INR, not percentage returns; a change in current value includes
both contributions/withdrawals and valuation changes.

Money is stored as integer paise to avoid floating-point rounding. Existing
earlier databases are upgraded transactionally without losing settings or
financial records. Pre-user finance records are placed under a named **Existing data**
profile, so they remain accessible without guessing who owned them. A fresh or empty
database starts with no profiles; add them in Users.
Unsaved edits require confirmation before switching users or months, leaving the module,
or closing the application.

## Expense Calculator

1. Open **Expense Calculator**, select a named user, choose the **Month** and
   **Year**, and click **Load month**. Each expense belongs to that user and month.
   **ALL** shows combined expenses across users for the selected month and is read-only.
2. Enter a positive **Amount** in INR (up to two decimal places, without commas),
   choose **Category** and **Subcategory** from the dropdowns, and optionally enter
   a **Description** of up to 500 characters. Subcategory choices are filtered by
   the selected category. Changing category clears the old subcategory selection.
3. Click **Add expense**. You can add multiple entries in the same category and
   month. Each is a separate expense, so identical values are counted separately.
   The entry list and totals update immediately after saving.
4. Open **Category totals** for sums and entry counts by category and subcategory.
   The selected user's **monthly total expense** appears at the bottom, with the
   **ALL users combined** monthly total below it. Amounts from different months or
   years are never mixed.
5. To correct an entry, select it, click **Remove selected expense**, confirm,
   and add the corrected expense. Removal is restricted to the loaded user/month.

**Dropdown definitions are awaiting the user's category/subcategory list.** No
guessed categories are installed in real databases. Until values are configured,
the UI shows this status and expense entry is disabled. The service supports
local category definitions through `ExpenseCatalog`; adding the supplied values
will populate these dependent dropdowns. Synthetic test definitions never enter
the application's real database.

Expense totals use exact integer paise. Saving is blocked if the user/month/year
selection changes until that scope is loaded. Unsaved expense input requires
confirmation before loading another scope or leaving the menu. The database
upgrade preserves existing users, portfolio data, and settings.

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

The regression suite includes five deterministic randomly selected synthetic
names, 12 months per user, and all eight input fields: **60 monthly snapshots,
240 asset records, and 480 entered amounts**. It checks every per-user/ALL value,
automatic MoM field, graph series, combined summary, persistence, profile isolation,
and migration. Headless UI callback tests exercise user creation, financial entry,
user selection, summaries, and the real graph drawing path with a recording Canvas;
desktop font/layout verification still requires a display. Test records are temporary
and are never preloaded into the application or uploaded as databases.

Expense tests additionally enter **80 synthetic expenses** through the entry UI
callbacks for five users across two months. They verify every category/subcategory
sum, entry count, per-user and ALL monthly total, dependent dropdowns, removal,
persistence, schema upgrade, validation, and operation with networking blocked.

New menus live under `finance_app/modules/` and are registered in
`finance_app/modules/registry.py`. Each builder receives the content frame and
local database. There is no dynamic plugin loading.

Only source code and synthetic tests may be published to GitHub. Publishing is
a developer action outside the application; the application contains no GitHub
integration. Review the staged file list before every commit. Git ignore rules
are a safeguard, not protection against manually forcing data into Git.

See `docs/ROADMAP.md` for incremental module work and `AGENTS.md` for project rules.
