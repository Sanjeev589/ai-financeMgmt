# Personal Finance Management

An offline Python desktop application, built one user-defined menu at a time.
This initial version provides the desktop shell, local SQLite storage, an explicit
module registry, and privacy enforcement. Finance modules are not implemented yet.

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
