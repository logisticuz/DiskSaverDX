# gui_theme.py
import tkinter as tk
from tkinter import ttk

def setup_dark_theme(root: tk.Tk) -> None:
    """Simple dark mode styling for the entire Tkinter/ttk GUI."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    bg = "#1e1e1e"
    bg2 = "#252526"
    fg = "#f0f0f0"
    accent = "#0e639c"

    root.configure(bg=bg)

    style.configure(".", background=bg, foreground=fg, fieldbackground=bg)
    style.configure("TFrame", background=bg)
    style.configure("TLabelframe", background=bg, foreground=fg)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.configure("TButton", background="#2d2d30", foreground=fg, padding=4)
    style.map(
        "TButton",
        background=[("active", "#3e3e40")],
        foreground=[("disabled", "#888888")],
    )

    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=bg2,
        background=accent,
        bordercolor=bg2,
        lightcolor=accent,
        darkcolor=accent,
    )

    style.configure(
        "Treeview",
        background=bg2,
        foreground=fg,
        fieldbackground=bg2,
        bordercolor=bg,
        rowheight=22,
    )
    style.map(
        "Treeview",
        background=[("selected", "#094771")],
        foreground=[("selected", "#ffffff")],
    )

    style.configure(
        "Vertical.TScrollbar",
        background=bg2,
        troughcolor=bg,
        arrowcolor=fg,
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=bg2,
        troughcolor=bg,
        arrowcolor=fg,
    )

    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=bg2,
        foreground=fg,
        padding=(12, 4),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", "#3e3e40"), ("active", "#333333")],
        foreground=[("selected", "#ffffff"), ("!selected", fg)],
    )
