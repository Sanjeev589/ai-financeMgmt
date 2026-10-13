"""Local named user profiles. Names identify profiles; no online accounts."""

from dataclasses import dataclass
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk


@dataclass(frozen=True)
class User:
    id: int
    name: str


class UserStore:
    def __init__(self, database):
        self.connection = database.connection

    def list_users(self):
        return tuple(User(*row) for row in self.connection.execute("SELECT id, name FROM users ORDER BY name_key, id"))

    def get(self, user_id):
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("Select a valid named user.")
        row = self.connection.execute("SELECT id, name FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("This user does not exist. Create a user in Users first.")
        return User(*row)

    def add(self, name):
        if not isinstance(name, str) or any(ord(character) < 32 or ord(character) == 127 for character in name):
            raise ValueError("Enter a name without control characters.")
        name = " ".join(name.split())
        if not 1 <= len(name) <= 100:
            raise ValueError("Enter a name between 1 and 100 characters.")
        key = name.casefold()
        if key == "all":
            raise ValueError("ALL is reserved for the combined finance view. Choose another name.")
        try:
            with self.connection:
                cursor = self.connection.execute("INSERT INTO users (name, name_key) VALUES (?, ?)", (name, key))
        except sqlite3.IntegrityError:
            raise ValueError("A user with this name already exists.") from None
        return User(cursor.lastrowid, name)


class UsersView:
    def __init__(self, parent, database):
        self.parent = parent
        self.store = UserStore(database)
        ttk.Label(parent, text="Create a user by name. Then select that name in My Finance.", wraplength=650).pack(anchor="w", pady=(0, 16))
        form = ttk.Frame(parent)
        form.pack(fill="x", pady=(0, 12))
        ttk.Label(form, text="Name").pack(side="left", padx=(0, 12))
        self.name = tk.StringVar(master=parent)
        entry = ttk.Entry(form, textvariable=self.name, width=32)
        entry.pack(side="left", padx=(0, 12))
        entry.bind("<Return>", lambda event: self.add_user())
        ttk.Button(form, text="Add user", command=self.add_user).pack(side="left")
        self.status = ttk.Label(parent, wraplength=650)
        self.status.pack(anchor="w", pady=(0, 12))
        self.list = ttk.Treeview(parent, columns=("name",), show="headings", selectmode="none", height=12)
        self.list.heading("name", text="Users")
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        self.list.pack(in_=frame, side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.list.yview)
        scrollbar.pack(side="right", fill="y")
        self.list.configure(yscrollcommand=scrollbar.set)
        self.refresh()

    def refresh(self):
        for item in self.list.get_children():
            self.list.delete(item)
        for user in self.store.list_users():
            self.list.insert("", "end", iid=str(user.id), values=(user.name,))

    def add_user(self):
        try:
            user = self.store.add(self.name.get())
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Cannot create user", str(error), parent=self.parent)
            return
        self.name.set("")
        self.status.configure(text=f"Created {user.name}. Open My Finance and select this user to enter data.")
        self.refresh()

    def can_discard_changes(self):
        return not self.name.get().strip() or messagebox.askyesno(
            "Unsaved name", "Discard the name that has not been added?", parent=self.parent
        )


def build(parent, database):
    return UsersView(parent, database)
