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


class DiskraddareGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Diskräddare v2.4 – GUI")

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

        ttk.Button(frame_buttons, text="🔍 Föranalys", command=self.run_analysis).grid(row=0, column=0, **pad)
        ttk.Button(frame_buttons, text="🚀 Starta räddning", command=self.run_recovery).grid(row=0, column=1, **pad)
        ttk.Button(frame_buttons, text="💾 Exportera analys (CSV)", command=self.export_csv).grid(row=0, column=2, **pad)
        ttk.Button(frame_buttons, text="💾 Exportera analys (JSON)", command=self.export_json).grid(row=0, column=3, **pad)

        # Logg / textutskrift
        frame_log = ttk.LabelFrame(self.root, text="Logg / status")
        frame_log.grid(row=4, column=0, sticky="nsew", **pad)
        self.root.rowconfigure(4, weight=1)
        frame_log.rowconfigure(0, weight=1)
        frame_log.columnconfigure(0, weight=1)

        self.log_text = tk.Text(frame_log, height=12)
        self.log_text.grid(row=0, column=0, sticky="nsew", **pad)
        scroll = ttk.Scrollbar(frame_log, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text["yscrollcommand"] = scroll.set

        # Progressbar + label längst ner
        frame_prog = ttk.Frame(self.root)
        frame_prog.grid(row=5, column=0, sticky="ew", padx=5, pady=5)
        frame_prog.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(frame_prog, mode="indeterminate")
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=5, pady=2)

        self.progress_label = ttk.Label(frame_prog, text="Ingen pågående process.")
        self.progress_label.grid(row=1, column=0, sticky="w", padx=5, pady=2)

        self._append_log("Välkommen till Diskräddare GUI.\n")

        # initial UI state
        self._on_group_top_change()
        self._on_use_hash_change()

    # ----------- Hjälpfunktioner / UI-logik -----------

    def _append_log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _on_group_top_change(self):
        # Om man inte har toppmapp-gruppering spelar ordningen ingen roll
        if not self.group_top_var.get():
            self.top_before_type_var.set(False)

    def _on_use_hash_change(self):
        if not self.use_hash_var.get():
            self.hash_only_var.set(False)

    def _start_progress(self, text: str):
        if self.progress_bar is not None:
            self.progress_bar.start(10)  # 10 ms per steg (indeterminate)
        if self.progress_label is not None:
            self.progress_label.config(text=text)

    def _stop_progress(self, text: str = "Klar."):
        if self.progress_bar is not None:
            self.progress_bar.stop()
        if self.progress_label is not None:
            self.progress_label.config(text=text)

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
                self.analysis_results = res
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

        # start progress och thread
        self._start_progress("Föranalys pågår...")
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
                if self.analysis_results is None:
                    self._append_log("Ingen föranalys cachead – samlar filer först...")
                    analysis_results = collect_and_analyse(src, incl_hidden=True)
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

                self._append_log(
                    f"Bearbetar {len(files_to_process)} filer "
                    f"(dolda med: {'Ja' if include_hidden else 'Nej'})..."
                )

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

        self._start_progress("Räddning pågår...")
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
            filetypes=[("CSV-filer", "*.csv"), ("Alla filer", "*.*")]
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
            filetypes=[("JSON-filer", "*.json"), ("Alla filer", "*.*")]
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
    app = DiskraddareGUI(root)
    root.geometry("900x650")
    root.mainloop()


if __name__ == "__main__":
    main()
