"""Entry point: activate offline policy before creating the desktop application."""

from .privacy import enable_offline_policy


def main():
    enable_offline_policy()
    import tkinter as tk
    from .storage import Database
    from .ui import FinanceApp

    root = tk.Tk()
    try:
        database = Database()
        FinanceApp(root, database)
    except Exception:
        root.destroy()
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
