#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pathlib import Path
from typing import Set, Optional

# Import your backend
from disk_core import (
    collect_and_analyse,
    copy_phase,
    cleanup_empty,
    human,
    format_duration,
)


def setup_dark_theme(root: tk.Tk):
    """Simple dark mode styling for the entire Tkinter/ttk GUI."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        # fall back to default if clam is missing
        pass

    bg = "#1e1e1e"
    bg2 = "#252526"
    fg = "#f0f0f0"
    accent = "#0e639c"

    root.configure(bg=bg)

    # Base
    style.configure(".", background=bg, foreground=fg, fieldbackground=bg)

    # Specific widgets
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

    # ---- NEW: clearer tabs for notebooks ----
    style.configure(
        "TNotebook",
        background=bg,
        borderwidth=0,
    )
    style.configure(
        "TNotebook.Tab",
        background=bg2,     # mörkare bakgrund
        foreground=fg,      # ljus text
        padding=(12, 4),    # lite mer luft runt texten
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", "#3e3e40"),   # tydligt vald tab
            ("active", "#333333"),
        ],
        foreground=[
            ("selected", "#ffffff"),   # ren vit text på vald tab
            ("!selected", fg),
        ]
    )



class ToolTip:
    """Simple tooltip for Tkinter widgets."""

    def __init__(self, widget: tk.Widget, text: str, *, delay: int = 400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._id = None
        self._tip_window: tk.Toplevel | None = None

        self.widget.bind("<Enter>", self._on_enter)
        self.widget.bind("<Leave>", self._on_leave)
        self.widget.bind("<ButtonPress>", self._on_leave)

    def _on_enter(self, _event=None):
        self._schedule()

    def _on_leave(self, _event=None):
        self._unschedule()
        self._hide()

    def _schedule(self):
        self._unschedule()
        self._id = self.widget.after(self.delay, self._show)

    def _unschedule(self):
        if self._id is not None:
            self.widget.after_cancel(self._id)
            self._id = None

    def _show(self):
        if self._tip_window is not None or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self._tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#333333",
            foreground="#ffffff",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=3,
            wraplength=300,
        )
        label.pack(ipadx=1)

    def _hide(self):
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None


class DiskraddareGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.columnconfigure(0, weight=1)
        root.title("DiskSaverDX – DiskSaver (Dark Mode)")

        # ---- Variables ----
        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar()

        self.include_hidden_var = tk.BooleanVar(value=True)
        self.group_top_var = tk.BooleanVar(value=True)
        self.top_before_type_var = tk.BooleanVar(value=True)
        self.use_date_var = tk.BooleanVar(value=True)
        self.use_hash_var = tk.BooleanVar(value=False)
        self.hash_only_var = tk.BooleanVar(value=False)
        self.cleanup_var = tk.BooleanVar(value=False)

        self.max_size_var = tk.StringVar()       # e.g. "2GB" or empty
        self.excl_exts_var = tk.StringVar()      # e.g. ".exe,.zip"

        self.log_text: tk.Text | None = None
        self.analysis_results = None  # cache for latest pre-analysis

        self.progress_bar: ttk.Progressbar | None = None
        self.progress_label: ttk.Label | None = None
        self.current_file_label: ttk.Label | None = None  # shows current file

        # analysis tables
        self.analysis_tree: ttk.Treeview | None = None    # categories
        self.ext_tree: ttk.Treeview | None = None         # file types
        self.top_folders_tree: ttk.Treeview | None = None # top folders

        # Top folders view mode: "per_cat" or "global"
        self.top_folders_view_var = tk.StringVar(value="per_cat")

        # Pause / resume
        self._pause_event = threading.Event()
        self._pause_event.set()          # not paused at start
        self._is_running = False
        self.pause_button: ttk.Button | None = None

        self._build_ui()

    # ----------- UI construction -----------

    def _build_ui(self):
        pad = {"padx": 5, "pady": 5}

        # Source / destination
        frame_paths = ttk.LabelFrame(self.root, text="Paths")
        frame_paths.grid(row=0, column=0, sticky="ew", **pad)
        frame_paths.columnconfigure(1, weight=1)

        ttk.Label(frame_paths, text="Source:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frame_paths, textvariable=self.src_var).grid(
            row=0, column=1, sticky="ew", **pad
        )
        ttk.Button(frame_paths, text="Browse", command=self.choose_src).grid(
            row=0, column=2, **pad
        )

        ttk.Label(frame_paths, text="Destination:").grid(
            row=1, column=0, sticky="w", **pad
        )
        ttk.Entry(frame_paths, textvariable=self.dst_var).grid(
            row=1, column=1, sticky="ew", **pad
        )
        ttk.Button(frame_paths, text="Browse", command=self.choose_dst).grid(
            row=1, column=2, **pad
        )

        # ---------- OPTIONS NOTEBOOK ----------
        frame_opts = ttk.LabelFrame(self.root, text="Options")
        frame_opts.grid(row=1, column=0, sticky="ew", **pad)
        frame_opts.columnconfigure(0, weight=1)

        options_notebook = ttk.Notebook(frame_opts)
        options_notebook.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # --- Basic tab ---
        tab_basic = ttk.Frame(options_notebook)
        options_notebook.add(tab_basic, text="Basic")
        tab_basic.columnconfigure(0, weight=1)
        tab_basic.columnconfigure(1, weight=1)

        include_hidden_cb = ttk.Checkbutton(
            tab_basic,
            text="Include hidden files",
            variable=self.include_hidden_var,
        )
        include_hidden_cb.grid(row=0, column=0, sticky="w", **pad)

        group_top_cb = ttk.Checkbutton(
            tab_basic,
            text="Group by top folder (from_<folder>)",
            variable=self.group_top_var,
            command=self._on_group_top_change,
        )
        group_top_cb.grid(row=1, column=0, sticky="w", **pad)

        date_cb = ttk.Checkbutton(
            tab_basic,
            text="Use date folders (YEAR/YEAR-MONTH)",
            variable=self.use_date_var,
        )
        date_cb.grid(row=0, column=1, sticky="w", **pad)

        cleanup_cb = ttk.Checkbutton(
            tab_basic,
            text="Clean up empty folders afterwards",
            variable=self.cleanup_var,
        )
        cleanup_cb.grid(row=1, column=1, sticky="w", **pad)

        # --- Advanced tab ---
        tab_advanced = ttk.Frame(options_notebook)
        options_notebook.add(tab_advanced, text="Advanced")
        tab_advanced.columnconfigure(0, weight=1)
        tab_advanced.columnconfigure(1, weight=1)

        top_before_cb = ttk.Checkbutton(
            tab_advanced,
            text="Top folder before file type",
            variable=self.top_before_type_var,
        )
        top_before_cb.grid(row=0, column=0, sticky="w", **pad)

        use_hash_cb = ttk.Checkbutton(
            tab_advanced,
            text="Hash duplicate check",
            variable=self.use_hash_var,
            command=self._on_use_hash_change,
        )
        use_hash_cb.grid(row=0, column=1, sticky="w", **pad)

        hash_only_cb = ttk.Checkbutton(
            tab_advanced,
            text="Duplicates analysis only (no copying)",
            variable=self.hash_only_var,
        )
        hash_only_cb.grid(row=1, column=1, sticky="w", **pad)

        # --- Filters tab ---
        tab_filters = ttk.Frame(options_notebook)
        options_notebook.add(tab_filters, text="Filters")
        tab_filters.columnconfigure(1, weight=1)

        ttk.Label(tab_filters, text="Max file size (e.g. 2GB, 500MB):").grid(
            row=0, column=0, sticky="w", **pad
        )
        ttk.Entry(tab_filters, textvariable=self.max_size_var).grid(
            row=0, column=1, sticky="ew", **pad
        )

        ttk.Label(tab_filters, text="Exclude extensions (.exe,.zip):").grid(
            row=1, column=0, sticky="w", **pad
        )
        ttk.Entry(tab_filters, textvariable=self.excl_exts_var).grid(
            row=1, column=1, sticky="ew", **pad
        )

        # Tooltips for options
        ToolTip(
            include_hidden_cb,
            "If enabled, also include files and folders that are marked as hidden by the operating system.",
        )
        ToolTip(
            group_top_cb,
            "If enabled, copied files are grouped under from_<folder> based on the top-level folder they came from.",
        )
        ToolTip(
            top_before_cb,
            "Controls whether the from_<folder> level is placed before or after the category (e.g. Images, Videos).",
        )
        ToolTip(
            date_cb,
            "If enabled, files are organized into YEAR/YEAR-MONTH folders based on each file's modification time.",
        )
        ToolTip(
            use_hash_cb,
            "Calculates a SHA-256 hash for each file to detect real duplicates. Safer but slower, especially on large files.",
        )
        ToolTip(
            hash_only_cb,
            "Only performs duplicate analysis and logging. No files are copied when this option is enabled.",
        )
        ToolTip(
            cleanup_cb,
            "After recovery, remove any empty folders that were created in the destination.",
        )

        # ---------- BUTTONS ----------
        frame_buttons = ttk.Frame(self.root)
        frame_buttons.grid(row=2, column=0, sticky="ew", **pad)

        ttk.Button(
            frame_buttons, text="🔍 Scan & analyze", command=self.run_analysis
        ).grid(row=0, column=0, **pad)
        ttk.Button(
            frame_buttons, text="🚀 Run recovery", command=self.run_recovery
        ).grid(row=0, column=1, **pad)
        ttk.Button(
            frame_buttons, text="📄 Export report (CSV)", command=self.export_csv
        ).grid(row=0, column=2, **pad)
        ttk.Button(
            frame_buttons, text="📄 Export report (JSON)", command=self.export_json
        ).grid(row=0, column=3, **pad)

        # ---------- ANALYSIS / NOTEBOOK + LOG ----------
        frame_log = ttk.LabelFrame(self.root, text="Analysis, file types & log")
        frame_log.grid(row=3, column=0, sticky="nsew", **pad)
        self.root.rowconfigure(3, weight=1)
        frame_log.rowconfigure(0, weight=1)
        frame_log.rowconfigure(1, weight=1)
        frame_log.columnconfigure(0, weight=1)

        notebook = ttk.Notebook(frame_log)
        notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # --- Categories tab ---
        tab_cats = ttk.Frame(notebook)
        notebook.add(tab_cats, text="Categories")
        tab_cats.rowconfigure(0, weight=1)
        tab_cats.columnconfigure(0, weight=1)

        cat_columns = ("category", "count", "size")
        self.analysis_tree = ttk.Treeview(
            tab_cats,
            columns=cat_columns,
            show="headings",
            selectmode="browse",
            height=5,
        )
        self.analysis_tree.heading("category", text="Category")
        self.analysis_tree.heading("count", text="Files")
        self.analysis_tree.heading("size", text="Size")
        self.analysis_tree.column("category", width=200, anchor="w")
        self.analysis_tree.column("count", width=80, anchor="e")
        self.analysis_tree.column("size", width=120, anchor="e")
        self.analysis_tree.grid(row=0, column=0, sticky="nsew")

        cat_scroll = ttk.Scrollbar(
            tab_cats, orient="vertical", command=self.analysis_tree.yview
        )
        cat_scroll.grid(row=0, column=1, sticky="ns")
        self.analysis_tree.configure(yscrollcommand=cat_scroll.set)

        # --- File types tab ---
        tab_exts = ttk.Frame(notebook)
        notebook.add(tab_exts, text="File types")
        tab_exts.rowconfigure(0, weight=1)
        tab_exts.columnconfigure(0, weight=1)

        ext_columns = ("ext", "count", "size", "cat")
        self.ext_tree = ttk.Treeview(
            tab_exts,
            columns=ext_columns,
            show="headings",
            selectmode="browse",
            height=5,
        )
        self.ext_tree.heading("ext", text="Extension")
        self.ext_tree.heading("count", text="Files")
        self.ext_tree.heading("size", text="Size")
        self.ext_tree.heading("cat", text="Category")
        self.ext_tree.column("ext", width=90, anchor="w")
        self.ext_tree.column("count", width=80, anchor="e")
        self.ext_tree.column("size", width=110, anchor="e")
        self.ext_tree.column("cat", width=140, anchor="w")
        self.ext_tree.grid(row=0, column=0, sticky="nsew")

        ext_scroll = ttk.Scrollbar(
            tab_exts, orient="vertical", command=self.ext_tree.yview
        )
        ext_scroll.grid(row=0, column=1, sticky="ns")
        self.ext_tree.configure(yscrollcommand=ext_scroll.set)

        # --- Top folders tab ---
        tab_top = ttk.Frame(notebook)
        notebook.add(tab_top, text="Top folders")
        tab_top.rowconfigure(1, weight=1)
        tab_top.columnconfigure(0, weight=1)

        # View mode radio buttons
        view_frame = ttk.Frame(tab_top)
        view_frame.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))

        ttk.Label(view_frame, text="View:").grid(row=0, column=0, padx=(0, 5))

        rb_per_cat = ttk.Radiobutton(
            view_frame,
            text="Per category (Top 5 each)",
            variable=self.top_folders_view_var,
            value="per_cat",
            command=self._refresh_top_folders_view,
        )
        rb_per_cat.grid(row=0, column=1, padx=(0, 10))

        rb_global = ttk.Radiobutton(
            view_frame,
            text="Global (Top 100 overall)",
            variable=self.top_folders_view_var,
            value="global",
            command=self._refresh_top_folders_view,
        )
        rb_global.grid(row=0, column=2)

        top_columns = ("folder", "files", "size", "category")
        self.top_folders_tree = ttk.Treeview(
            tab_top,
            columns=top_columns,
            show="headings",
            selectmode="browse",
            height=5,
        )
        self.top_folders_tree.heading("folder", text="Folder")
        self.top_folders_tree.heading("files", text="Files")
        self.top_folders_tree.heading("size", text="Size")
        self.top_folders_tree.heading("category", text="Category")
        self.top_folders_tree.column("folder", width=300, anchor="w")
        self.top_folders_tree.column("files", width=70, anchor="e")
        self.top_folders_tree.column("size", width=110, anchor="e")
        self.top_folders_tree.column("category", width=120, anchor="w")
        self.top_folders_tree.grid(row=1, column=0, sticky="nsew", padx=0, pady=(5, 0))

        top_scroll = ttk.Scrollbar(
            tab_top, orient="vertical", command=self.top_folders_tree.yview
        )
        top_scroll.grid(row=1, column=1, sticky="ns", pady=(5, 0))
        self.top_folders_tree.configure(yscrollcommand=top_scroll.set)

        # Text log under notebook
        self.log_text = tk.Text(frame_log, height=6, wrap="word")
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))
        log_scroll = ttk.Scrollbar(frame_log, command=self.log_text.yview)
        log_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 5))
        self.log_text["yscrollcommand"] = log_scroll.set

        # Adjust text widget to dark mode
        self.log_text.configure(
            bg="#1e1e1e",
            fg="#f0f0f0",
            insertbackground="#ffffff",
            relief="flat",
        )

        # Progress bar + labels at the bottom
        frame_prog = ttk.Frame(self.root)
        frame_prog.grid(row=4, column=0, sticky="ew", padx=5, pady=5)
        frame_prog.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(frame_prog, mode="indeterminate")
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=5, pady=2)

        self.progress_label = ttk.Label(frame_prog, text="No active process.")
        self.progress_label.grid(row=1, column=0, sticky="w", padx=5, pady=2)

        self.current_file_label = ttk.Label(frame_prog, text="File: -")
        self.current_file_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)

        self.pause_button = ttk.Button(
            frame_prog,
            text="⏸ Pause",
            command=self.toggle_pause,
            state="disabled",
        )
        self.pause_button.grid(row=3, column=0, sticky="e", padx=5, pady=2)

        self._append_log("Welcome to DiskSaverDX GUI.\n")

        # Make tables sortable
        self._make_treeview_sortable(
            self.analysis_tree,
            {"category": "str", "count": "int", "size": "size"},
        )
        self._make_treeview_sortable(
            self.ext_tree,
            {"ext": "str", "count": "int", "size": "size", "cat": "str"},
        )
        self._make_treeview_sortable(
            self.top_folders_tree,
            {"folder": "str", "files": "int", "size": "size", "category": "str"},
        )

        # Initial UI state
        self._on_group_top_change()
        self._on_use_hash_change()

    # ----------- Helper / UI logic -----------

    def _append_log(self, msg: str):
        if self.log_text is not None:
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")

    def _on_group_top_change(self):
        # If top-folder grouping is disabled, the ordering flag is irrelevant
        if not self.group_top_var.get():
            self.top_before_type_var.set(False)

    def _on_use_hash_change(self):
        if not self.use_hash_var.get():
            self.hash_only_var.set(False)

    # ---- Tree sorting helpers ----

    def _size_to_bytes(self, s: str) -> float:
        """Best-effort: parse '283.0 MB', '6.5 GB', '0.0 B' to bytes."""
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

    def _make_treeview_sortable(self, tree: ttk.Treeview, column_types: dict[str, str]):
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
                    key = self._size_to_bytes(text)
                else:
                    key = text.lower()
                data.append((key, iid))

            data.sort(reverse=reverse)

            for index, (_key, iid) in enumerate(data):
                tree.move(iid, "", index)

            # Toggle reverse next click
            tree.heading(
                column,
                command=lambda c=column, r=not reverse: sort_by(c, r),
            )

        # initial bindings (ascending first)
        for col in tree["columns"]:
            tree.heading(
                col,
                command=lambda c=col: sort_by(c, False),
            )

    def _start_progress(self, text: str, pausable: bool = False):
        """Start a 'working...' indicator (indeterminate)."""
        if self.progress_bar is not None:
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(10)
        if self.progress_label is not None:
            self.progress_label.config(text=text)
        if self.current_file_label is not None:
            self.current_file_label.config(text="File: -")

        self._is_running = True
        self._pause_event.set()

        if self.pause_button is not None:
            if pausable:
                self.pause_button.config(state="normal", text="⏸ Pause")
            else:
                self.pause_button.config(state="disabled", text="⏸ Pause")

    def _setup_copy_progress(self, total: int):
        """Switch progress bar to determinate mode when we know total files."""
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.config(
                style="Horizontal.TProgressbar",
                mode="determinate",
                maximum=total,
                value=0,
            )
        if self.progress_label is not None:
            self.progress_label.config(
                text=f"Recovery in progress... 0/{total} files"
            )
        if self.current_file_label is not None:
            self.current_file_label.config(text="File: -")

    def _stop_progress(self, text: str = "No active process."):
        if self.progress_bar is not None:
            self.progress_bar.stop()
        if self.progress_label is not None:
            self.progress_label.config(text=text)

        self._is_running = False
        self._pause_event.set()

        if self.pause_button is not None:
            self.pause_button.config(state="disabled", text="⏸ Pause")

    def toggle_pause(self):
        """Pause or resume ongoing recovery."""
        if not self._is_running or self.pause_button is None:
            return

        if self._pause_event.is_set():
            self._pause_event.clear()
            self.pause_button.config(text="▶ Resume")
            self._append_log(
                "⏸ Pausing recovery (waiting for current file to finish)..."
            )
        else:
            self._pause_event.set()
            self.pause_button.config(text="⏸ Pause")
            self._append_log("▶ Resuming recovery...")

    def _progress_callback(
        self,
        done: int,
        total: int,
        elapsed: int,
        eta: int,
        current_path: Optional[Path],
    ):
        """Callback from copy_phase (worker thread)."""

        self._pause_event.wait()

        def updater():
            if self.progress_bar is None or self.progress_label is None:
                return

            pct = (done / total * 100) if total else 100.0
            self.progress_bar["value"] = done

            elapsed_str = format_duration(elapsed)
            eta_str = format_duration(eta)

            self.progress_label.config(
                text=(
                    f"{done}/{total} files "
                    f"({pct:5.1f} %) – ⏱ {elapsed_str} – ETA {eta_str}"
                )
            )

            if self.current_file_label is not None:
                if current_path is not None:
                    self.current_file_label.config(text=f"File: {current_path.name}")
                else:
                    self.current_file_label.config(text="File: -")

        self.root.after(0, updater)

    # ----------- Analysis table updates -----------

    def _update_analysis_tree(self, res: dict):
        """Fill the table views with results from collect_and_analyse."""
        self.analysis_results = res

        # ----- Category table -----
        if self.analysis_tree is not None:
            for row in self.analysis_tree.get_children():
                self.analysis_tree.delete(row)

            cats_sorted = sorted(
                res["cats"].items(),
                key=lambda item: item[1]["s"],
                reverse=True,
            )

            for cat, data in cats_sorted:
                count = data["n"]
                size = data["s"]
                self.analysis_tree.insert(
                    "",
                    "end",
                    values=(cat, count, human(size)),
                )

        # ----- File types table -----
        if self.ext_tree is not None:
            for row in self.ext_tree.get_children():
                self.ext_tree.delete(row)

            ext_stats = res.get("ext_stats", {})
            exts_sorted = sorted(
                ext_stats.items(),
                key=lambda item: item[1]["s"],
                reverse=True,
            )

            for ext, d in exts_sorted:
                ext_label = ext or "<none>"
                count = d["n"]
                size = d["s"]
                cat = d.get("cat", "Other")
                self.ext_tree.insert(
                    "",
                    "end",
                    values=(ext_label, count, human(size), cat),
                )

        # ----- Top folders table -----
        self._update_top_folders()

    def _update_top_folders(self):
        """Refresh Top folders tab based on view mode and analysis_results."""
        if self.top_folders_tree is None or self.analysis_results is None:
            return

        for row in self.top_folders_tree.get_children():
            self.top_folders_tree.delete(row)

        cats = self.analysis_results["cats"]
        view = self.top_folders_view_var.get()

        if view == "global":
            # Flatten all folders across categories and sort globally
            all_folders = []
            for cat_name, data in cats.items():
                for folder_path, info in data["folders"].items():
                    all_folders.append(
                        (folder_path, info["n"], info["s"], cat_name)
                    )

            all_folders.sort(key=lambda item: item[2], reverse=True)
            top_n = all_folders[:100]

            for folder_path, count, size, cat_name in top_n:
                self.top_folders_tree.insert(
                    "",
                    "end",
                    values=(str(folder_path), count, human(size), cat_name),
                )
        else:
            # Per category – top 5 per category
            for cat_name, data in cats.items():
                folders = data["folders"]
                sorted_folders = sorted(
                    folders.items(), key=lambda item: item[1]["s"], reverse=True
                )[:5]

                for folder_path, info in sorted_folders:
                    self.top_folders_tree.insert(
                        "",
                        "end",
                        values=(
                            str(folder_path),
                            info["n"],
                            human(info["s"]),
                            cat_name,
                        ),
                    )

    def _refresh_top_folders_view(self):
        """Called when the radiobutton for view mode changes."""
        if self.analysis_results is not None:
            self._update_top_folders()

    # ----------- Path choosers -----------

    def choose_src(self):
        path = filedialog.askdirectory(title="Select source folder")
        if path:
            self.src_var.set(path)

    def choose_dst(self):
        path = filedialog.askdirectory(title="Select destination folder")
        if path:
            self.dst_var.set(path)

    # ----------- Business logic wrappers -----------

    def _parse_size(self, raw: str) -> Optional[int]:
        raw = raw.strip().lower()
        if not raw:
            return None
        num = "".join(c for c in raw if c.isdigit() or c == ".")
        unit = "".join(c for c in raw if c.isalpha())
        try:
            val = float(num)
        except ValueError:
            return None
        factors = {"kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
        fac = factors.get(unit)
        if not fac:
            return None
        return int(val * fac)

    def _parse_excl(self, raw: str) -> Set[str]:
        raw = raw.strip()
        if not raw:
            return set()
        return {e.strip().lower() for e in raw.split(",") if e.strip()}

    # ----------- Pre-analysis -----------

    def run_analysis(self):
        src = Path(self.src_var.get())
        if not src.exists():
            messagebox.showerror("Error", "Invalid source path.")
            return

        include_hidden = self.include_hidden_var.get()

        def worker():
            try:
                self._append_log("🔍 Running pre-analysis...")
                res = collect_and_analyse(src, incl_hidden=include_hidden)
                self.root.after(0, self._update_analysis_tree, res)
                msg = (
                    f"Total files: {len(res['all_files'])}\n"
                    f"Total size: {human(res['tot_size'])}\n"
                    f"Hidden files: {len(res['hidden_files'])}\n"
                    f"Duplicate hint: {res['dup_hint']}"
                )
                self._append_log(msg)
                messagebox.showinfo("Pre-analysis complete", msg)
            except Exception as e:
                self._append_log(f"Error during pre-analysis: {e}")
                messagebox.showerror("Error", str(e))
            finally:
                self.root.after(0, self._stop_progress, "No active process.")

        self._start_progress("Pre-analysis in progress...", pausable=False)
        threading.Thread(target=worker, daemon=True).start()

    # ----------- Recovery -----------

    def run_recovery(self):
        src = Path(self.src_var.get())
        dst = Path(self.dst_var.get())
        if not src.exists():
            messagebox.showerror("Error", "Invalid source path.")
            return
        if not dst.exists():
            messagebox.showerror("Error", "Invalid destination path.")
            return

        include_hidden = self.include_hidden_var.get()
        max_sz = self._parse_size(self.max_size_var.get())
        excl = self._parse_excl(self.excl_exts_var.get())
        group_top = self.group_top_var.get()
        top_before_type = self.top_before_type_var.get()
        use_date = self.use_date_var.get()
        use_hash = self.use_hash_var.get()
        hash_only = self.hash_only_var.get()

        def worker():
            try:
                self._append_log("🚀 Starting recovery...")

                if self.analysis_results is None:
                    self._append_log(
                        "No cached pre-analysis – collecting files first..."
                    )
                    analysis_results = collect_and_analyse(src, incl_hidden=True)
                    self.root.after(
                        0, self._update_analysis_tree, analysis_results
                    )
                else:
                    analysis_results = self.analysis_results

                if include_hidden:
                    files_to_process = analysis_results["all_files"]
                else:
                    hidden_set = set(analysis_results["hidden_files"])
                    files_to_process = [
                        f
                        for f in analysis_results["all_files"]
                        if f not in hidden_set
                    ]

                total_files = len(files_to_process)

                self._append_log(
                    f"Processing {total_files} files "
                    f"(include hidden: {'Yes' if include_hidden else 'No'})..."
                )

                self.root.after(0, self._setup_copy_progress, total_files)

                copied, dups, fails = copy_phase(
                    files_to_copy=files_to_process,
                    src=src,
                    dst=dst,
                    max_sz=max_sz,
                    excl=excl,
                    use_hash=use_hash,
                    hash_only=hash_only,
                    group_top=group_top,
                    use_date_folders=use_date,
                    top_before_type=top_before_type,
                    progress_cb=self._progress_callback,
                )

                msg = (
                    f"Copied: {copied}\n"
                    f"Duplicates: {dups}\n"
                    f"Errors: {fails}"
                )
                self._append_log(msg)
                messagebox.showinfo("Recovery complete", msg)

                if not hash_only and copied > 0 and self.cleanup_var.get():
                    self._append_log("🧹 Cleaning up empty folders...")
                    cleanup_empty(dst)
                    self._append_log("Cleanup complete.")
            except Exception as e:
                self._append_log(f"Error during recovery: {e}")
                messagebox.showerror("Error", str(e))
            finally:
                self.root.after(0, self._stop_progress, "No active process.")

        self._start_progress("Preparing recovery...", pausable=True)
        threading.Thread(target=worker, daemon=True).start()

    # ----------- Export functions -----------

    def export_csv(self):
        import csv

        if self.analysis_results is None:
            messagebox.showerror("No analysis", "Run pre-analysis first.")
            return

        path = filedialog.asksaveasfilename(
            title="Save analysis as CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        res = self.analysis_results
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Category", "File count", "Total size (bytes)"])
                for cat, d in res["cats"].items():
                    writer.writerow([cat, d["n"], d["s"]])
            self._append_log(f"Analysis exported to CSV: {path}")
            messagebox.showinfo("Export complete", f"Analysis exported to:\n{path}")
        except Exception as e:
            self._append_log(f"Error during CSV export: {e}")
            messagebox.showerror("Export error", str(e))

    def export_json(self):
        import json

        if self.analysis_results is None:
            messagebox.showerror("No analysis", "Run pre-analysis first.")
            return

        path = filedialog.asksaveasfilename(
            title="Save analysis as JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        res = self.analysis_results
        serializable = {
            "total_files": len(res["all_files"]),
            "total_size": res["tot_size"],
            "hidden_files": len(res["hidden_files"]),
            "dup_hint": res["dup_hint"],
            "categories": {},
            "extensions": {},
        }
        for cat, d in res["cats"].items():
            serializable["categories"][cat] = {
                "count": d["n"],
                "size": d["s"],
                "folders": [
                    {
                        "path": str(folder),
                        "count": stats["n"],
                        "size": stats["s"],
                    }
                    for folder, stats in d["folders"].items()
                ],
            }

        ext_stats = res.get("ext_stats", {})
        for ext, d in ext_stats.items():
            serializable["extensions"][ext] = {
                "count": d["n"],
                "size": d["s"],
                "category": d.get("cat", "Other"),
            }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            self._append_log(f"Analysis exported to JSON: {path}")
            messagebox.showinfo("Export complete", f"Analysis exported to:\n{path}")
        except Exception as e:
            self._append_log(f"Error during JSON export: {e}")
            messagebox.showerror("Export error", str(e))


def main():
    root = tk.Tk()
    setup_dark_theme(root)

    # Try to set icon if disksaverdx.ico exists in the same folder
    icon_path = Path(__file__).with_name("disksaverdx.ico")
    try:
        if icon_path.exists():
            root.iconbitmap(icon_path)
    except Exception:
        pass

    app = DiskraddareGUI(root)

    root.update_idletasks()
    root.columnconfigure(0, weight=1)
    root.minsize(root.winfo_width(), root.winfo_height())

    root.mainloop()


if __name__ == "__main__":
    main()
