# gui_utils.py
from __future__ import annotations

from pathlib import Path
import os
import sys
import subprocess
from tkinter import messagebox
from tkinter import ttk

def open_in_explorer(path: Path) -> None:
    """Open a folder or file in the system file explorer."""
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        messagebox.showerror(
            "Open folder",
            f"Could not open:\n{path}\n\n{e}",
        )

def size_to_bytes(s: str) -> float:
    s = s.strip()
    if not s:
        return 0.0
    parts = s.split()
    try:
        value = float(parts[0])
    except ValueError:
        return 0.0
    unit = parts[1].upper() if len(parts) > 1 else "B"
    factors = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }
    return value * factors.get(unit, 1)

def make_treeview_sortable(tree: ttk.Treeview, column_types: dict[str, str], size_parser=size_to_bytes) -> None:
    """Attach clickable headers that sort the rows."""

    def sort_by(column: str, reverse: bool):
        data = []
        for iid in tree.get_children(""):
            text = tree.set(iid, column)
            col_type = column_types.get(column, "str")
            if col_type == "int":
                try:
                    key = int(text)
                except ValueError:
                    key = 0
            elif col_type == "size":
                key = size_parser(text)
            else:
                key = text.lower()
            data.append((key, iid))

        data.sort(reverse=reverse)

        for index, (_key, iid) in enumerate(data):
            tree.move(iid, "", index)

        tree.heading(
            column,
            command=lambda c=column, r=not reverse: sort_by(c, r),
        )

    for col in tree["columns"]:
        tree.heading(
            col,
            command=lambda c=col: sort_by(c, False),
        )
