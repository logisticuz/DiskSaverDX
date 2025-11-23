#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pathlib import Path
from typing import Set, Optional

# Importera din backend
from disk_core import (
    collect_and_analyse,
    copy_phase,
    cleanup_empty,
    human,
)


def setup_dark_theme(root: tk.Tk):
    """Enkel dark mode-stil för hela Tkinter/ttk GUI."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        # fall back på default om clam saknas
        pass

    bg = "#1e1e1e"
    bg2 = "#252526"
    fg = "#f0f0f0"
    accent = "#0e639c"

    root.configure(bg=bg)

    # Bas
    style.configure(".", background=bg, foreground=fg, fieldbackground=bg)

    # Specifika widgets
    style.configure("TFrame", background=bg)
    style.configure("TLabelframe", background=bg, foreground=fg)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)

    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.configure("TButton", background="#2d2d30", foreground=fg, padding=4)
    style.map(
        "TButton",
        background=[("active", "#3e3e40")],
        foreground=[("disabled", "#888888")]
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


class DiskraddareGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("DiskSaverDX – Diskräddare (Dark Mode)")

        # ---- Variabler ----
        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar()

        self.include_hidden_var = tk.BooleanVar(value=True)
        self.group_top_var = tk.BooleanVar(value=True)
        self.top_before_type_var = tk.BooleanVar(value=True)
        self.use_date_var = tk.BooleanVar(value=True)
        self.use_hash_var = tk.BooleanVar(value=False)
        self.hash_only_var = tk.BooleanVar(value=False)
        self.cleanup_var = tk.BooleanVar(value=False)

        self.max_size_var = tk.StringVar()       # t.ex. "2GB" eller tom
        self.excl_exts_var = tk.StringVar()      # t.ex. ".exe,.zip"

        self.log_text: tk.Text | None = None
        self.analysis_results = None  # cache för senaste föranalys

        self.progress_bar: ttk.Progressbar | None = None
        self.progress_label: ttk.Label | None = None
        self.current_file_label: ttk.Label | None = None  # visar aktuell fil

        self.analysis_tree: ttk.Treeview | None = None    # tabellvy för kategorier
        self.ext_tree: ttk.Treeview | None = None         # tabellvy för filtyper

        # För paus/fortsätt
        self._pause_event = threading.Event()
        self._pause_event.set()          # inte pausad från start
        self._is_running = False
        self.pause_button: ttk.Button | None = None

        self._build_ui()

    # ----------- UI-bygge -----------

    def _build_ui(self):
        pad = {"padx": 5, "pady": 5}

        # Källa
        frame_paths = ttk.LabelFrame(self.root, text="Sökvägar")
        frame_paths.grid(row=0, column=0, sticky="ew", **pad)
        frame_paths.columnconfigure(1, weight=1)

        ttk.Label(frame_paths, text="Källa:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frame_paths, textvariable=self.src_var).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frame_paths, text="Bläddra", command=self.choose_src).grid(row=0, column=2, **pad)

        ttk.Label(frame_paths, text="Destination:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frame_paths, textvariable=self.dst_var).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frame_paths, text="Bläddra", command=self.choose_dst).grid(row=1, column=2, **pad)

        # Inställningar
        frame_opts = ttk.LabelFrame(self.root, text="Inställningar")
        frame_opts.grid(row=1, column=0, sticky="ew", **pad)
        frame_opts.columnconfigure(0, weight=1)
        frame_opts.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            frame_opts,
            text="Inkludera dolda filer",
            variable=self.include_hidden_var
        ).grid(row=0, column=0, sticky="w", **pad)

        ttk.Checkbutton(
            frame_opts,
            text="Gruppera efter toppmapp (från_<mapp>)",
            variable=self.group_top_var,
            command=self._on_group_top_change
        ).grid(row=1, column=0, sticky="w", **pad)

        ttk.Checkbutton(
            frame_opts,
            text="Toppmapp före filtyp",
            variable=self.top_before_type_var
        ).grid(row=2, column=0, sticky="w", **pad)

        ttk.Checkbutton(
            frame_opts,
            text="Datum-mappar (ÅR/ÅR-MÅNAD)",
            variable=self.use_date_var
        ).grid(row=0, column=1, sticky="w", **pad)

        ttk.Checkbutton(
            frame_opts,
            text="Hash-dubblettkontroll",
            variable=self.use_hash_var,
            command=self._on_use_hash_change
        ).grid(row=1, column=1, sticky="w", **pad)

        ttk.Checkbutton(
            frame_opts,
            text="Endast dubblettanalys (ingen kopiering)",
            variable=self.hash_only_var
        ).grid(row=2, column=1, sticky="w", **pad)

        ttk.Checkbutton(
            frame_opts,
            text="Rensa tomma mappar efteråt",
            variable=self.cleanup_var
        ).grid(row=3, column=0, sticky="w", **pad)

        # Max storlek / exkludera
        frame_filters = ttk.LabelFrame(self.root, text="Filter")
        frame_filters.grid(row=2, column=0, sticky="ew", **pad)
        frame_filters.columnconfigure(1, weight=1)

        ttk.Label(frame_filters, text="Max filstorlek (ex 2GB, 500MB):").grid(
            row=0, column=0, sticky="w", **pad
        )
        ttk.Entry(frame_filters, textvariable=self.max_size_var).grid(
            row=0, column=1, sticky="ew", **pad
        )

        ttk.Label(frame_filters, text="Exkludera ändelser (.exe,.zip):").grid(
            row=1, column=0, sticky="w", **pad
        )
        ttk.Entry(frame_filters, textvariable=self.excl_exts_var).grid(
            row=1, column=1, sticky="ew", **pad
        )

        # Knapp-rad
        frame_buttons = ttk.Frame(self.root)
        frame_buttons.grid(row=3, column=0, sticky="ew", **pad)

        ttk.Button(frame_buttons, text="🔍 Skanna & analysera", command=self.run_analysis).grid(row=0, column=0, **pad)
        ttk.Button(frame_buttons, text="🚀 Kör räddning", command=self.run_recovery).grid(row=0, column=1, **pad)
        ttk.Button(frame_buttons, text="📄 Exportera rapport (CSV)", command=self.export_csv).grid(row=0, column=2, **pad)
        ttk.Button(frame_buttons, text="📄 Exportera rapport (JSON)", command=self.export_json).grid(row=0, column=3, **pad)

        # Logg + tabellvy
        frame_log = ttk.LabelFrame(self.root, text="Analys, filtyper & logg")
        frame_log.grid(row=4, column=0, sticky="nsew", **pad)
        self.root.rowconfigure(4, weight=1)
        frame_log.rowconfigure(0, weight=1)
        frame_log.rowconfigure(1, weight=1)
        frame_log.rowconfigure(2, weight=1)
        frame_log.columnconfigure(0, weight=1)

        # Tabell (Treeview) för kategorier
        cat_columns = ("category", "count", "size")
        self.analysis_tree = ttk.Treeview(
            frame_log,
            columns=cat_columns,
            show="headings",
            selectmode="browse",
            height=5,
        )
        self.analysis_tree.heading("category", text="Kategori")
        self.analysis_tree.heading("count", text="Antal filer")
        self.analysis_tree.heading("size", text="Storlek")
        self.analysis_tree.column("category", width=180, anchor="w")
        self.analysis_tree.column("count", width=90, anchor="e")
        self.analysis_tree.column("size", width=120, anchor="e")
        self.analysis_tree.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 0))

        cat_scroll = ttk.Scrollbar(
            frame_log, orient="vertical", command=self.analysis_tree.yview
        )
        cat_scroll.grid(row=0, column=1, sticky="ns", pady=(5, 0))
        self.analysis_tree.configure(yscrollcommand=cat_scroll.set)

        # Ny tabell (Treeview) för filtyper
        ext_columns = ("ext", "count", "size", "cat")
        self.ext_tree = ttk.Treeview(
            frame_log,
            columns=ext_columns,
            show="headings",
            selectmode="browse",
            height=5,
        )
        self.ext_tree.heading("ext", text="Filändelse")
        self.ext_tree.heading("count", text="Antal")
        self.ext_tree.heading("size", text="Storlek")
        self.ext_tree.heading("cat", text="Kategori")
        self.ext_tree.column("ext", width=90, anchor="w")
        self.ext_tree.column("count", width=80, anchor="e")
        self.ext_tree.column("size", width=110, anchor="e")
        self.ext_tree.column("cat", width=140, anchor="w")
        self.ext_tree.grid(row=1, column=0, sticky="nsew", padx=5, pady=(5, 0))

        ext_scroll = ttk.Scrollbar(
            frame_log, orient="vertical", command=self.ext_tree.yview
        )
        ext_scroll.grid(row=1, column=1, sticky="ns", pady=(5, 0))
        self.ext_tree.configure(yscrollcommand=ext_scroll.set)

        # Textlogg under tabellerna
        self.log_text = tk.Text(frame_log, height=6, wrap="word")
        self.log_text.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        log_scroll = ttk.Scrollbar(frame_log, command=self.log_text.yview)
        log_scroll.grid(row=2, column=1, sticky="ns", pady=5)
        self.log_text["yscrollcommand"] = log_scroll.set

        # Anpassa text-widgeten till dark mode
        self.log_text.configure(
            bg="#1e1e1e",
            fg="#f0f0f0",
            insertbackground="#ffffff",
            relief="flat",
        )

        # Progressbar + labels längst ner
        frame_prog = ttk.Frame(self.root)
        frame_prog.grid(row=5, column=0, sticky="ew", padx=5, pady=5)
        frame_prog.columnconfigure(0, weight=1)

        # default: indeterminate, används för "jobbar..." (analys, förberedelse)
        self.progress_bar = ttk.Progressbar(frame_prog, mode="indeterminate")
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=5, pady=2)

        self.progress_label = ttk.Label(frame_prog, text="Ingen pågående process.")
        self.progress_label.grid(row=1, column=0, sticky="w", padx=5, pady=2)

        # aktuell fil under räddning
        self.current_file_label = ttk.Label(frame_prog, text="Fil: -")
        self.current_file_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)

        # Paus/Fortsätt-knapp (aktiveras bara under räddning)
        self.pause_button = ttk.Button(
            frame_prog,
            text="⏸ Pausa",
            command=self.toggle_pause,
            state="disabled",
        )
        self.pause_button.grid(row=3, column=0, sticky="e", padx=5, pady=2)

        self._append_log("Välkommen till DiskSaverDX GUI.\n")

        # initial UI state
        self._on_group_top_change()
        self._on_use_hash_change()

    # ----------- Hjälpfunktioner / UI-logik -----------

    def _append_log(self, msg: str):
        if self.log_text is not None:
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")

    def _on_group_top_change(self):
        # Om man inte har toppmapp-gruppering spelar ordningen ingen roll
        if not self.group_top_var.get():
            self.top_before_type_var.set(False)

    def _on_use_hash_change(self):
        if not self.use_hash_var.get():
            self.hash_only_var.set(False)

    def _start_progress(self, text: str, pausable: bool = False):
        """Starta en 'jobbar...' indikator (indeterminate)."""
        if self.progress_bar is not None:
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(10)  # 10 ms per steg
        if self.progress_label is not None:
            self.progress_label.config(text=text)
        if self.current_file_label is not None:
            self.current_file_label.config(text="Fil: -")

        # startar en ny process
        self._is_running = True
        self._pause_event.set()  # inte pausad

        # Paus-knappen bara aktiv om processen är pauserbar (räddning)
        if self.pause_button is not None:
            if pausable:
                self.pause_button.config(state="normal", text="⏸ Pausa")
            else:
                self.pause_button.config(state="disabled", text="⏸ Pausa")

    def _setup_copy_progress(self, total: int):
        """
        Körs på main-tråden (via root.after) när vi vet hur många filer som ska
        bearbetas. Ställer om progressbaren till determinate-läge.
        """
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.config(
                style="Horizontal.TProgressbar",
                mode="determinate",
                maximum=total,
                value=0,
            )
        if self.progress_label is not None:
            self.progress_label.config(text=f"Räddning pågår... 0/{total} filer")
        if self.current_file_label is not None:
            self.current_file_label.config(text="Fil: -")

    def _stop_progress(self, text: str = "Klar."):
        if self.progress_bar is not None:
            self.progress_bar.stop()
        if self.progress_label is not None:
            self.progress_label.config(text=text)
        # current_file_label lämnas som den är (senaste fil)

        self._is_running = False
        self._pause_event.set()  # så ingen hänger i wait()

        if self.pause_button is not None:
            self.pause_button.config(state="disabled", text="⏸ Pausa")

    def toggle_pause(self):
        """Pausa / fortsätt pågående räddning."""
        if not self._is_running or self.pause_button is None:
            return

        if self._pause_event.is_set():
            # GÅR TILL PAUS
            self._pause_event.clear()
            self.pause_button.config(text="▶ Fortsätt")
            self._append_log("⏸ Pausar räddning (väntar färdigt på aktuell fil)...")
        else:
            # FORTSÄTT
            self._pause_event.set()
            self.pause_button.config(text="⏸ Pausa")
            self._append_log("▶ Fortsätter räddning...")

    def _progress_callback(
        self,
        done: int,
        total: int,
        elapsed: int,
        eta: int,
        current_path: Optional[Path],
    ):
        """
        Callback som kommer från copy_phase (i worker-thread).
        Vi får INTE röra Tk direkt här, så vi schemalägger en uppdatering
        på main-tråden med root.after(0, ...).
        """

        # Blockera här om paus-läge är aktivt.
        # Detta pausar worker-tråden mellan filerna men lämnar GUI responsivt.
        self._pause_event.wait()

        def updater():
            if self.progress_bar is None or self.progress_label is None:
                return

            pct = (done / total * 100) if total else 100.0
            self.progress_bar["value"] = done

            self.progress_label.config(
                text=(
                    f"{done}/{total} filer "
                    f"({pct:5.1f} %) – ⏱ {elapsed}s – ETA {eta}s"
                )
            )

            if self.current_file_label is not None:
                if current_path is not None:
                    self.current_file_label.config(text=f"Fil: {current_path.name}")
                else:
                    self.current_file_label.config(text="Fil: -")

        # se till att UI-uppdatering sker på main-tråden
        self.root.after(0, updater)

    def _update_analysis_tree(self, res: dict):
        """Fyll tabellvyerna med resultat från collect_and_analyse."""
        self.analysis_results = res

        # ----- Kategoritabell -----
        if self.analysis_tree is not None:
            for row in self.analysis_tree.get_children():
                self.analysis_tree.delete(row)

            cats = sorted(
                res["cats"].items(),
                key=lambda item: item[1]["s"],
                reverse=True,
            )

            for cat, data in cats:
                count = data["n"]
                size = data["s"]
                self.analysis_tree.insert(
                    "",
                    "end",
                    values=(cat, count, human(size)),
                )

        # ----- Filtyps-tabell -----
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
                ext_label = ext or "<ingen>"
                count = d["n"]
                size = d["s"]
                cat = d.get("cat", "Övrigt")
                self.ext_tree.insert(
                    "",
                    "end",
                    values=(ext_label, count, human(size), cat),
                )

    def choose_src(self):
        path = filedialog.askdirectory(title="Välj källmapp")
        if path:
            self.src_var.set(path)

    def choose_dst(self):
        path = filedialog.askdirectory(title="Välj destination")
        if path:
            self.dst_var.set(path)

    # ----------- Businesslogik-wrapper -----------

    def _parse_size(self, raw: str) -> Optional[int]:
        raw = raw.strip().lower()
        if not raw:
            return None
        num = ''.join(c for c in raw if c.isdigit() or c == '.')
        unit = ''.join(c for c in raw if c.isalpha())
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

    # ----------- Föranalys -----------

    def run_analysis(self):
        src = Path(self.src_var.get())
        if not src.exists():
            messagebox.showerror("Fel", "Ogiltig källa.")
            return

        include_hidden = self.include_hidden_var.get()

        def worker():
            try:
                self._append_log("🔍 Kör föranalys...")
                res = collect_and_analyse(src, incl_hidden=include_hidden)
                # uppdatera tabellvyer
                self.root.after(0, self._update_analysis_tree, res)
                msg = (
                    f"Totalt: {len(res['all_files'])} filer\n"
                    f"Storlek: {human(res['tot_size'])}\n"
                    f"Dolda filer: {len(res['hidden_files'])}\n"
                    f"Dublett-indikation: {res['dup_hint']}"
                )
                self._append_log(msg)
                messagebox.showinfo("Föranalys klar", msg)
            except Exception as e:
                self._append_log(f"Fel vid föranalys: {e}")
                messagebox.showerror("Fel", str(e))
            finally:
                # stop progress i main-thread
                self.root.after(0, self._stop_progress, "Ingen pågående process.")

        # start progress och thread (ej pauserbar)
        self._start_progress("Föranalys pågår...", pausable=False)
        threading.Thread(target=worker, daemon=True).start()

    # ----------- Räddning -----------

    def run_recovery(self):
        src = Path(self.src_var.get())
        dst = Path(self.dst_var.get())
        if not src.exists():
            messagebox.showerror("Fel", "Ogiltig källa.")
            return
        if not dst.exists():
            messagebox.showerror("Fel", "Ogiltig destination.")
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
                self._append_log("🚀 Startar räddning...")

                # Säkerställ att vi har analysdata
                if self.analysis_results is None:
                    self._append_log("Ingen föranalys cachead – samlar filer först...")
                    analysis_results = collect_and_analyse(src, incl_hidden=True)
                    # uppdatera tabellvyer med denna analys
                    self.root.after(0, self._update_analysis_tree, analysis_results)
                else:
                    analysis_results = self.analysis_results

                if include_hidden:
                    files_to_process = analysis_results["all_files"]
                else:
                    hidden_set = set(analysis_results["hidden_files"])
                    files_to_process = [
                        f for f in analysis_results["all_files"]
                        if f not in hidden_set
                    ]

                total_files = len(files_to_process)

                self._append_log(
                    f"Bearbetar {total_files} filer "
                    f"(dolda med: {'Ja' if include_hidden else 'Nej'})..."
                )

                # konfigurera determinate-progress på main-tråden
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
                    progress_cb=self._progress_callback,  # kopplad progress + paus
                )

                msg = (
                    f"Kopierade: {copied}\n"
                    f"Dubbletter: {dups}\n"
                    f"Fel: {fails}"
                )
                self._append_log(msg)
                messagebox.showinfo("Räddning klar", msg)

                if not hash_only and copied > 0 and self.cleanup_var.get():
                    self._append_log("🧹 Rensar tomma mappar...")
                    cleanup_empty(dst)
                    self._append_log("Rensning klar.")
            except Exception as e:
                self._append_log(f"Fel vid räddning: {e}")
                messagebox.showerror("Fel", str(e))
            finally:
                # stop progress i main-thread
                self.root.after(0, self._stop_progress, "Ingen pågående process.")

        # start progress och thread (den här är pauserbar)
        self._start_progress("Förbereder räddning...", pausable=True)
        threading.Thread(target=worker, daemon=True).start()

    # ----------- Exportfunktioner -----------

    def export_csv(self):
        import csv
        if self.analysis_results is None:
            messagebox.showerror("Ingen analys", "Kör föranalys först.")
            return

        path = filedialog.asksaveasfilename(
            title="Spara analys som CSV",
            defaultextension=".csv",
            filetypes=[("CSV-filer", "*.csv"), ("Alla filer", "*.*")],
        )
        if not path:
            return

        res = self.analysis_results
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Kategori", "Antal filer", "Total storlek (bytes)"])
                for cat, d in res["cats"].items():
                    writer.writerow([cat, d["n"], d["s"]])
            self._append_log(f"Analys exporterad till CSV: {path}")
            messagebox.showinfo("Export klar", f"Analys exporterad till:\n{path}")
        except Exception as e:
            self._append_log(f"Fel vid CSV-export: {e}")
            messagebox.showerror("Fel vid export", str(e))

    def export_json(self):
        import json
        if self.analysis_results is None:
            messagebox.showerror("Ingen analys", "Kör föranalys först.")
            return

        path = filedialog.asksaveasfilename(
            title="Spara analys som JSON",
            defaultextension=".json",
            filetypes=[("JSON-filer", "*.json"), ("Alla filer", "*.*")],
        )
        if not path:
            return

        res = self.analysis_results
        # Gör en JSON-vänlig version
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

        # Lägg till ext_stats om det finns
        ext_stats = res.get("ext_stats", {})
        for ext, d in ext_stats.items():
            serializable["extensions"][ext] = {
                "count": d["n"],
                "size": d["s"],
                "category": d.get("cat", "Övrigt"),
            }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            self._append_log(f"Analys exporterad till JSON: {path}")
            messagebox.showinfo("Export klar", f"Analys exporterad till:\n{path}")
        except Exception as e:
            self._append_log(f"Fel vid JSON-export: {e}")
            messagebox.showerror("Fel vid export", str(e))


def main():
    root = tk.Tk()
    setup_dark_theme(root)

    # Försök sätta ikon om disksaverdx.ico finns i samma mapp
    icon_path = Path(__file__).with_name("disksaverdx.ico")
    try:
        if icon_path.exists():
            root.iconbitmap(icon_path)
    except Exception:
        # ikon är nice-to-have; ignorera fel om något strular
        pass

    app = DiskraddareGUI(root)
    root.geometry("950x700")
    root.mainloop()


if __name__ == "__main__":
    main()
