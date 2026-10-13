# Mandatory project rules

- This is a fully offline desktop application. Never add networking, telemetry,
  upload, synchronization, remote assets, bank APIs, automatic updates, external
  processes, browser launching, or downloaded/dynamic plugins.
- All application data stays on the user's computer, outside this repository.
- GitHub is for source code, tests using synthetic data, and documentation only.
  Never commit real financial data, imports, exports, databases, backups, or logs.
- Keep the runtime offline audit hook enabled before loading UI/business modules.
- Use only Python standard-library dependencies; UI is Tkinter, storage is SQLite.
- Register new menu modules explicitly. Implement menus as described by the user.
- Store money as integer minor units or use Decimal, never binary floats.
- Use parameterized SQL. Apply versioned, transactional database migrations.
- Run `python -m unittest discover -s tests -v` before every source commit.
- Review the exact staged file list before committing and uploading source updates.
- No repository publishing code or GitHub credentials belong inside the application.
