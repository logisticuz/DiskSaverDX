#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DiskSaverDX – DiskSaver v2.5 (refactored version with date sorting)

Features
────────
1.  Single pass scan of the source folder
2.  Interactive CLI menu with pre-analysis and recovery modes
3.  Pre-analysis:
    • total counts
    • per-category distribution
    • top 5 folders per category
    • file type overview per extension (ext_stats)
4.  Direct copy with:
    • hash-based duplicate detection (SHA-256)
    • progress bar, timer & ETA (updated every 0.2 s)
    • grouping by top folder (from_<folder_name>)
    • configurable handling of hidden files, excluded extensions, max size
    • date folders (YEAR/YEAR-MONTH)
    • choice of top folder before/after category
5.  Auto-cleanup of empty folders (optional after copy)
6.  Logs: log.txt, duplicates.txt, hidden.txt, errors.txt, cleanup.txt
7.  Admin reminder – run via starter_disk_auth.bat for protected folders (UAC).
"""

from __future__ import annotations

import os
import sys
import shutil
import hashlib
import time
import signal
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Callable
from collections import defaultdict, Counter
from datetime import datetime

# --------------  CONSTANTS  --------------
HIDDEN_PREFIX = "."
BAR_WIDTH = 30
HASH_CHUNK = 1 << 20
REFRESH_RATE = 0.2

FILE_TYPES: Dict[str, List[str]] = {
    "Videos": [
        ".mp4", ".avi", ".mov", ".mpg", ".mpeg",
        ".wmv", ".flv", ".mkv", ".qt",
    ],
    "Images": [
        ".jpg", ".jpeg", ".bmp", ".gif", ".png", ".tiff",
        ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".dng",
    ],
    "Audio": [
        ".mp3", ".wav", ".wma", ".aac", ".ogg", ".mid",
    ],
    "Documents": [
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".pdf", ".txt", ".rtf", ".odt", ".csv",
    ],
    "Installers": [
        ".exe", ".msi", ".iso", ".zip", ".rar", ".7z", ".tar", ".gz",
    ],
    "Torrents": [".torrent"],
}

ADMIN_HINT = (
    "🛡  Tip: run via starter_disk_auth.bat if you need access to "
    "protected folders (UAC).\n"
)
print(ADMIN_HINT)


# ───────────────────  I/O HELPERS  ───────────────────

def ask_path(prompt: str) -> Path:
    """Ask for an existing path on disk."""
    while True:
        p = Path(input(prompt).strip().strip('"\'')).resolve()
        if p.exists():
            return p
        print("❌  Path does not exist. Try again.")


def ask_yes(question: str) -> bool:
    """Simple yes/no question, expects y/n."""
    return input(f"{question} (y/n): ").strip().lower() == "y"


def ask_size() -> int | None:
    """Ask for a maximum file size like '2GB' or '500MB'. Empty for no limit."""
    raw = input("Max file size (e.g. 2GB, 500MB) – press Enter for no limit: ").lower().strip()
    if not raw:
        return None
    num = ''.join(c for c in raw if c.isdigit() or c == '.')
    unit = ''.join(c for c in raw if c.isalpha())
    try:
        val = float(num)
    except ValueError:
        print("❌  Invalid number.")
        return ask_size()
    fac = {"kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}.get(unit)
    if not fac:
        print("❌  Invalid unit (use KB, MB, GB or TB).")
        return ask_size()
    return int(val * fac)


def ask_excl() -> set[str]:
    """Ask for extensions to exclude, e.g. '.exe,.zip'."""
    raw = input("Extensions to exclude (.exe,.zip) – press Enter for none: ")
    return {e.strip().lower() for e in raw.split(',') if e.strip()} if raw else set()


# ───────────────────  UTILS  ───────────────────

def human(b: int | None) -> str:
    """Format bytes as a human readable string."""
    if b is None:
        return "0 B"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB":
            return f"{b:.1f} {u}"
        b /= 1024


def format_duration(seconds: int | None) -> str:
    """Format seconds as '45s', '3m 20s', '1h 12m' etc."""
    if seconds is None or seconds <= 0:
        return "0s"
    mins, sec = divmod(int(seconds), 60)
    if mins == 0:
        return f"{sec}s"
    hours, mins = divmod(mins, 60)
    if hours == 0:
        return f"{mins}m {sec}s"
    return f"{hours}h {mins}m"


def sha256(fp: Path) -> str:
    """Calculate SHA-256 hash for a file."""
    h = hashlib.sha256()
    with fp.open('rb') as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def category(ext: str) -> str:
    """Map file extension to a logical category."""
    ext = ext.lower()
    return next((c for c, exts in FILE_TYPES.items() if ext in exts), "Other")


# ───────────────────────── COLLECTION & ANALYSIS ─────────────────────────

def collect_and_analyse(src: Path, incl_hidden: bool) -> dict[str, Any]:
    """
    Recursively scan the source folder and collect statistics:

    - all_files: list[Path]
    - hidden_files: list[Path]
    - tot_size: int (bytes)
    - cats: category → {n, s, paths, folders}
    - ext_stats: extension → {n, s, cat}
    - dup_hint: rough duplicate count based on (filename, size)
    """
    print("\n🔎   Scanning source and analyzing files. This may take a while...")
    stats: dict[str, Any] = {
        "all_files": [],
        "hidden_files": [],
        "tot_size": 0,
        "cats": defaultdict(lambda: {
            "n": 0,
            "s": 0,
            "paths": [],
            "folders": defaultdict(lambda: {"n": 0, "s": 0}),
        }),
        # File type statistics per extension
        "ext_stats": defaultdict(lambda: {
            "n": 0,
            "s": 0,
            "cat": "Other",
        }),
    }
    dup_counter: Counter = Counter()

    for p in src.rglob('*'):
        if not p.is_file():
            continue

        is_hidden = any(part.startswith(HIDDEN_PREFIX) for part in p.parts)
        if is_hidden:
            stats["hidden_files"].append(p)
            if not incl_hidden:
                continue

        try:
            sz = p.stat().st_size
        except FileNotFoundError:
            continue

        stats["all_files"].append(p)
        stats["tot_size"] += sz

        ext = p.suffix.lower()
        cat_name = category(ext)

        # Per-category statistics
        cat_entry = stats["cats"][cat_name]
        cat_entry["n"] += 1
        cat_entry["s"] += sz
        cat_entry["paths"].append(p)

        parent_folder = p.parent
        folder_entry = cat_entry["folders"][parent_folder]
        folder_entry["n"] += 1
        folder_entry["s"] += sz

        # File type statistics per extension
        ext_key = ext if ext else "<none>"
        ext_entry = stats["ext_stats"][ext_key]
        ext_entry["n"] += 1
        ext_entry["s"] += sz
        ext_entry["cat"] = cat_name

        # Rough duplicate indicator based on (name, size)
        dup_counter[(p.name, sz)] += 1

    stats["dup_hint"] = sum(c - 1 for c in dup_counter.values() if c > 1)
    return stats


def print_analysis(res: dict):
    """Pretty-print the collected analysis to the CLI."""
    print("\n── Pre-analysis ─────────────")
    print(f"Total files: {len(res['all_files'])} | {human(res['tot_size'])}")
    print(f"Hidden files: {len(res['hidden_files'])} | Duplicate hint: {res['dup_hint']}")
    print("\nCategory overview (sorted by size):")

    sorted_cats = sorted(res['cats'].items(), key=lambda item: item[1]['s'], reverse=True)

    for c, d in sorted_cats:
        print(f"    {c:<18} {d['n']:>8} | {human(d['s'])}")
    print()

    # Top 5 folders per category
    for c, d in sorted_cats:
        if not d['n']:
            continue

        top = sorted(
            d['folders'].items(),
            key=lambda item: item[1]['s'],
            reverse=True
        )[:5]

        print(f"📂   Top 5 folders – {c}:")
        for fld, s in top:
            print(f"    {fld} — {s['n']} files, {human(s['s'])}")
        print()

    # File type overview
    if "ext_stats" in res:
        print("File type overview (top 20 by size):")
        exts_sorted = sorted(
            res["ext_stats"].items(),
            key=lambda item: item[1]["s"],
            reverse=True
        )[:20]

        for ext, d in exts_sorted:
            ext_label = ext or "<none>"
            print(
                f"    {ext_label:<10} {d['n']:>8} | {human(d['s']):>10} | {d['cat']}"
            )
        print()


# ───────────────────────── PROGRESS PRINTING ─────────────────────────

class Progress:
    """Simple CLI progress bar with elapsed time and ETA, plus optional callback."""

    def __init__(
        self,
        total: int,
        callback: Optional[Callable[[int, int, int, int, Optional[Path]], None]] = None
    ):
        self.t0 = time.time()
        self.total = total
        self.done = 0
        self._lock = threading.Lock()
        self._last_update = 0.0
        self._cb = callback  # for GUI progress callback

    def step(self, current_path: Optional[Path] = None):
        with self._lock:
            self.done += 1
            now = time.time()
            if now - self._last_update >= REFRESH_RATE or self.done == self.total:
                self._last_update = now
                pct = self.done / self.total if self.total else 1
                filled = int(BAR_WIDTH * pct)
                bar = "█" * filled + "░" * (BAR_WIDTH - filled)
                elapsed = int(now - self.t0)
                spd = self.done / elapsed if elapsed else 0
                eta = int((self.total - self.done) / spd) if spd else 0

                elapsed_str = format_duration(elapsed)
                eta_str = format_duration(eta)

                # CLI progress
                sys.stdout.write(
                    f"\r📦 [{bar}] {pct*100:5.1f}% {self.done}/{self.total} "
                    f"| ⏱ {elapsed_str} | ETA {eta_str} "
                )
                sys.stdout.flush()
                if self.done == self.total:
                    print()

                # GUI callback (if set)
                if self._cb is not None:
                    try:
                        self._cb(self.done, self.total, elapsed, eta, current_path)
                    except Exception:
                        # GUI errors should not kill CLI run
                        pass


# ───────────────────────── COPY LOGIC ─────────────────────────

def copy_phase(
    files_to_copy: List[Path],
    src: Path,
    dst: Path,
    max_sz: int | None,
    excl: set[str],
    use_hash: bool,
    hash_only: bool,
    group_top: bool,
    use_date_folders: bool,
    top_before_type: bool,
    progress_cb: Optional[Callable[[int, int, int, int, Optional[Path]], None]] = None,
) -> Tuple[int, int, int]:
    """
    Core copy phase.

    Returns:
        (copied, duplicates, failures)
    """

    prog = Progress(len(files_to_copy), callback=progress_cb)
    hashes: dict[str, Path] = {}
    copied = dups = fails = skipped = 0

    with (
        open('log.txt', 'w', encoding='utf-8') as log,
        open('duplicates.txt', 'w', encoding='utf-8') as dlog,
        open('errors.txt', 'w', encoding='utf-8') as elog,
        open('hidden.txt', 'w', encoding='utf-8') as hidden_log
    ):
        for fp in files_to_copy:
            try:
                ext = fp.suffix.lower()

                if ext in excl:
                    skipped += 1
                    continue
                if max_sz and fp.stat().st_size > max_sz:
                    skipped += 1
                    continue

                h = sha256(fp) if use_hash else None
                if h and h in hashes:
                    dups += 1
                    dlog.write(f"{fp} == {hashes[h]}\n")
                    if hash_only:
                        prog.step(current_path=fp)
                        continue

                if hash_only:
                    prog.step(current_path=fp)
                    continue

                cat_name = category(ext)

                rel_parts = fp.relative_to(src).parts
                top_folder_name = rel_parts[0] if len(rel_parts) > 1 else "root"

                dest_dir = dst

                if use_date_folders:
                    ts = fp.stat().st_mtime
                    dt = datetime.fromtimestamp(ts)
                    year = str(dt.year)
                    period = f"{dt.year}-{dt.month:02d}"
                    dest_dir = dest_dir / year / period

                if group_top and top_before_type:
                    dest_dir = dest_dir / f"from_{top_folder_name}"

                dest_dir = dest_dir / cat_name

                if group_top and not top_before_type:
                    dest_dir = dest_dir / f"from_{top_folder_name}"

                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / fp.name

                if dest_path.exists() or (h and h in hashes):
                    copy_dir = dest_dir / "Copies"
                    copy_dir.mkdir(parents=True, exist_ok=True)
                    i = 1
                    while True:
                        new_name = f"{fp.stem}_duplicate{i}{fp.suffix}"
                        candidate = copy_dir / new_name
                        if not candidate.exists():
                            dest_path = candidate
                            break
                        i += 1

                shutil.copy2(fp, dest_path)
                copied += 1
                log.write(f"{fp} → {dest_path}\n")

                if h:
                    hashes[h] = fp

            except Exception as e:
                fails += 1
                elog.write(f"❌ {fp} → {e}\n")
            finally:
                prog.step(current_path=fp)

    print(f"Skipped {skipped} files due to filters.")
    return copied, dups, fails


# ───────────────────  CLEANUP EMPTY FOLDERS  ───────────────────

def cleanup_empty(dst: Path) -> None:
    """Remove all empty folders under dst and log the result."""
    removed = 0
    for d, _, _ in os.walk(dst, topdown=False):
        p = Path(d)
        try:
            if not any(p.iterdir()):
                p.rmdir()
                removed += 1
        except OSError:
            continue
    with open("cleanup.txt", "a", encoding="utf-8") as f:
        f.write(f"Removed {removed} dirs {datetime.now()}\n")
    print(f"🧹  Removed {removed} empty folders\n")


# ───────────────────  CTRL-C HANDLING  ───────────────────

def abort(sig, frame):
    print("\n⛔  Aborted by user – logs are saved, but the process did not complete.")
    sys.exit(1)


signal.signal(signal.SIGINT, abort)


# ───────────────────────── CLI MENU ─────────────────────────

def main():
    print("\n🎛️   DiskSaverDX – DiskSaver v2.5")
    print("1. 🔍   Pre-analysis and then optional recovery")
    print("2. 🚀   Direct recovery (without pre-analysis)")
    print("3. ❌   Exit")
    choice = input("Choice (1/2/3): ").strip()

    if choice == '3':
        sys.exit()
    if choice not in ('1', '2'):
        print("Invalid choice.")
        return

    src = ask_path("📂   Source: ")

    # Always collect analysis once (even for direct mode),
    # so we can reuse its file list.
    analysis_results = collect_and_analyse(src, incl_hidden=True)

    if choice == '1':
        print_analysis(analysis_results)
        if not ask_yes("Continue to recovery?"):
            sys.exit()

    print("\n⚙️   Recovery settings:")
    dst = ask_path("📁   Destination: ")

    incl_hidden = ask_yes("Include hidden files in recovery?")
    max_sz = ask_size()
    excl = ask_excl()

    group_top = ask_yes("Group by top folder (from_<folder_name>)?")

    top_before_type = False
    if group_top:
        top_before_type = ask_yes(
            "📂 Top folder before category? "
            "(y = YEAR/YEAR-MONTH/from_<folder>/Images, "
            "n = YEAR/YEAR-MONTH/Images/from_<folder>)"
        )

    use_date_folders = ask_yes("📅 Sort files into date folders (YEAR/YEAR-MONTH)?")
    use_hash = ask_yes("Enable hash-based duplicate check (slower but safer)?")
    hash_only = False
    if use_hash:
        hash_only = ask_yes("Duplicates analysis only (no copying)?")

    if incl_hidden:
        files_to_process = analysis_results['all_files']
    else:
        hidden_set = set(analysis_results['hidden_files'])
        files_to_process = [f for f in analysis_results['all_files'] if f not in hidden_set]

    print("\n─── Summary before start ───")
    print(f"Source: {src}")
    print(f"Destination: {dst}")
    print(f"Files to process: {len(files_to_process)}")
    print(f"Include hidden: {'Yes' if incl_hidden else 'No'}")
    print(f"Max file size: {human(max_sz) if max_sz is not None else 'Unlimited'}")
    print(f"Excluded extensions: {excl if excl else 'None'}")
    print(f"Hash check: {'Yes' if use_hash else 'No'}")
    print(f"Date folders: {'Yes' if use_date_folders else 'No'}")
    print(f"Top folder before category: {'Yes' if (group_top and top_before_type) else 'No'}")
    if not ask_yes("\nReady to start the process?"):
        print("Aborting.")
        sys.exit()

    print("\n🚀   Starting process...")
    copied, dups, fails = copy_phase(
        files_to_copy=files_to_process,
        src=src,
        dst=dst,
        max_sz=max_sz,
        excl=excl,
        use_hash=use_hash,
        hash_only=hash_only,
        group_top=group_top,
        use_date_folders=use_date_folders,
        top_before_type=top_before_type,
        progress_cb=None,  # CLI uses text progress only
    )

    print("\n✨   Process completed!")
    if not hash_only:
        print(f"Copied: {copied}")
    print(f"Duplicates found: {dups}")
    print(f"Errors: {fails}")

    if not hash_only and copied > 0 and ask_yes("\nRun cleanup of empty folders in destination?"):
        cleanup_empty(dst)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user. Bye!")
        sys.exit(0)
