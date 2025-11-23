#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DiskSaverDX – Diskräddare v2.4 (refaktorerad och optimerad version + datum-sortering)

Funktioner
──────────
1.  Effektiviserad med en enda genomsökning av källan
2.  Interaktiv meny med föranalys- och räddningsläge
3.  Föranalys:
    • totalsiffror
    • kategorifördelning
    • topp 5-mappar per kategori
    • filtypsöversikt per ändelse (ext_stats)
4.  Direktkopiering med
    • hash-baserad dubblettkontroll (SHA-256)
    • progressbar, timer & ETA (uppdateras var 0,2 s)
    • gruppering efter toppmapp (från_<mappnamn>)
    • valbar hantering av dolda filer, exkluderade filtyper, maxstorlek
    • datum-mappar (ÅR/ÅR-MÅNAD)
    • val om toppmapp före filtyp eller tvärtom
5.  Auto-cleanup av tomma mappar (frågas efter kopiering)
6.  Loggar: logg.txt, dubbletter.txt, dolda.txt, fel.txt, rensning.txt
7.  Admin-påminnelse – kör via starter_disk_auth.bat för skyddade mappar (UAC).
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

# --------------  KONSTANTER  --------------
HIDDEN_PREFIX = "."
BAR_WIDTH      = 30
HASH_CHUNK     = 1 << 20
REFRESH_RATE   = 0.2

FILE_TYPES: Dict[str, List[str]] = {
    "Videos": [
        ".mp4", ".avi", ".mov", ".mpg", ".mpeg",
        ".wmv", ".flv", ".mkv", ".qt",
    ],
    "Bilder": [
        ".jpg", ".jpeg", ".bmp", ".gif", ".png", ".tiff",
        ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".dng",
    ],
    "Audio": [
        ".mp3", ".wav", ".wma", ".aac", ".ogg", ".mid",
    ],
    "Dokument": [
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".pdf", ".txt", ".rtf", ".odt", ".csv",
    ],
    "Installationsfiler": [
        ".exe", ".msi", ".iso", ".zip", ".rar", ".7z", ".tar", ".gz",
    ],
    "Torrents": [".torrent"],
}

ADMIN_HINT = (
    "🛡  Kör via starter_disk_auth.bat om du behöver åtkomst till "
    "skyddade mappar (UAC).\n"
)
print(ADMIN_HINT)


# ───────────────────  I/O-hjälpare  ───────────────────

def ask_path(prompt: str) -> Path:
    while True:
        p = Path(input(prompt).strip().strip('"\'')).resolve()
        if p.exists():
            return p
        print("❌  Sökvägen finns inte. Försök igen.")

def ask_yes(question: str) -> bool:
    return input(f"{question} (j/n): ").strip().lower() == "j"

def ask_size() -> int | None:
    raw = input("Max filstorlek (ex 2GB, 500MB) – Enter för ingen: ").lower().strip()
    if not raw:
        return None
    num = ''.join(c for c in raw if c.isdigit() or c == '.')
    unit = ''.join(c for c in raw if c.isalpha())
    try:
        val = float(num)
    except ValueError:
        print("❌  Ogiltigt tal.")
        return ask_size()
    fac = {"kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}.get(unit)
    if not fac:
        print("❌  Ogiltig enhet (använd KB, MB, GB eller TB).")
        return ask_size()
    return int(val * fac)

def ask_excl() -> set[str]:
    raw = input("Filändelser att exkludera (.exe,.zip) – Enter för inga: ")
    return {e.strip().lower() for e in raw.split(',') if e.strip()} if raw else set()


# ───────────────────  Utils  ───────────────────

def human(b: int | None) -> str:
    if b is None:
        return "0 B"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB":
            return f"{b:.1f} {u}"
        b /= 1024

def sha256(fp: Path) -> str:
    h = hashlib.sha256()
    with fp.open('rb') as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()

def category(ext: str) -> str:
    ext = ext.lower()
    return next((c for c, exts in FILE_TYPES.items() if ext in exts), "Övrigt")


# ───────────────────────── Insamling och Analys ─────────────────────────

def collect_and_analyse(src: Path, incl_hidden: bool) -> dict[str, Any]:
    """
    Skannar källan rekursivt och samlar statistik:

    - all_files: list[Path]
    - hidden_files: list[Path]
    - tot_size: int (bytes)
    - cats: kategori → {n, s, paths, folders}
    - ext_stats: ändelse → {n, s, cat}
    - dup_hint: ungefärligt antal dubbletter baserat på (filnamn, storlek)
    """
    print("\n🔎   Genomsöker källa och analyserar filer. Detta kan ta en stund...")
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
        # Ny: filtypsstatistik per ändelse
        "ext_stats": defaultdict(lambda: {
            "n": 0,
            "s": 0,
            "cat": "Övrigt",
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

        # Kategoristatistik
        cat_entry = stats["cats"][cat_name]
        cat_entry["n"] += 1
        cat_entry["s"] += sz
        cat_entry["paths"].append(p)

        parent_folder = p.parent
        folder_entry = cat_entry["folders"][parent_folder]
        folder_entry["n"] += 1
        folder_entry["s"] += sz

        # Filtypsstatistik per ändelse
        ext_entry = stats["ext_stats"][ext if ext else "<ingen>"]
        ext_entry["n"] += 1
        ext_entry["s"] += sz
        ext_entry["cat"] = cat_name

        # Grov dubblettindikator baserat på (namn, storlek)
        dup_counter[(p.name, sz)] += 1

    stats["dup_hint"] = sum(c - 1 for c in dup_counter.values() if c > 1)
    return stats


def print_analysis(res: dict):
    print("\n── Föranalys ─────────────")
    print(f"Totalt {len(res['all_files'])} filer hittade | {human(res['tot_size'])}")
    print(f"Dolda filer: {len(res['hidden_files'])} | Dublett-indikation: {res['dup_hint']}")
    print("\nKategoriöversikt (sorterat på storlek):")

    sorted_cats = sorted(res['cats'].items(), key=lambda item: item[1]['s'], reverse=True)

    for c, d in sorted_cats:
        print(f"    {c:<18} {d['n']:>8} | {human(d['s'])}")
    print()

    # Topp 5-mappar per kategori
    for c, d in sorted_cats:
        if not d['n']:
            continue

        top = sorted(
            d['folders'].items(),
            key=lambda item: item[1]['s'],
            reverse=True
        )[:5]

        print(f"📂   Topp 5 mappar – {c}:")
        for fld, s in top:
            print(f"    {fld} — {s['n']} filer, {human(s['s'])}")
        print()

    # Ny: filtypsöversikt
    if "ext_stats" in res:
        print("Filtypsöversikt (topp 20 efter storlek):")
        exts_sorted = sorted(
            res["ext_stats"].items(),
            key=lambda item: item[1]["s"],
            reverse=True
        )[:20]

        for ext, d in exts_sorted:
            ext_label = ext or "<ingen>"
            print(
                f"    {ext_label:<10} {d['n']:>8} | {human(d['s']):>10} | {d['cat']}"
            )
        print()


# ───────────────────────── Progress-utskrifter ─────────────────────────

class Progress:
    def __init__(self, total: int,
                 callback: Optional[Callable[[int, int, int, int, Optional[Path]], None]] = None):
        self.t0 = time.time()
        self.total = total
        self.done = 0
        self._lock = threading.Lock()
        self._last_update = 0.0
        self._cb = callback  # för GUI

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

                # CLI-progress
                sys.stdout.write(
                    f"\r📦 [{bar}] {pct*100:5.1f}% {self.done}/{self.total} "
                    f"| ⏱ {elapsed}s | ETA {eta}s "
                )
                sys.stdout.flush()
                if self.done == self.total:
                    print()

                # GUI-callback (om satt)
                if self._cb is not None:
                    try:
                        self._cb(self.done, self.total, elapsed, eta, current_path)
                    except Exception:
                        pass


# ───────────────────────── Kopierings-logik ─────────────────────────

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

    prog = Progress(len(files_to_copy), callback=progress_cb)
    hashes: dict[str, Path] = {}
    copied = dups = fails = skipped = 0

    with (
        open('logg.txt', 'w', encoding='utf-8') as log,
        open('dubbletter.txt', 'w', encoding='utf-8') as dlog,
        open('fel.txt', 'w', encoding='utf-8') as elog,
        open('dolda.txt', 'w', encoding='utf-8') as dolda_log
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
                top_folder_name = rel_parts[0] if len(rel_parts) > 1 else "roten"

                dest_dir = dst

                if use_date_folders:
                    ts = fp.stat().st_mtime
                    dt = datetime.fromtimestamp(ts)
                    year = str(dt.year)
                    period = f"{dt.year}-{dt.month:02d}"
                    dest_dir = dest_dir / year / period

                if group_top and top_before_type:
                    dest_dir = dest_dir / f"från_{top_folder_name}"

                dest_dir = dest_dir / cat_name

                if group_top and not top_before_type:
                    dest_dir = dest_dir / f"från_{top_folder_name}"

                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / fp.name

                if dest_path.exists() or (h and h in hashes):
                    copy_dir = dest_dir / "Kopior"
                    copy_dir.mkdir(parents=True, exist_ok=True)
                    i = 1
                    while True:
                        new_name = f"{fp.stem}_dubblett{i}{fp.suffix}"
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

    print(f"Hoppade över {skipped} filer p.g.a. filter.")
    return copied, dups, fails


# ───────────────────  Cleanup tomma mappar  ───────────────────

def cleanup_empty(dst: Path) -> None:
    removed = 0
    for d, _, _ in os.walk(dst, topdown=False):
        p = Path(d)
        try:
            if not any(p.iterdir()):
                p.rmdir()
                removed += 1
        except OSError:
            continue
    with open("rensning.txt", "a", encoding="utf-8") as f:
        f.write(f"Removed {removed} dirs {datetime.now()}\n")
    print(f"🧹  Tog bort {removed} tomma mappar\n")


# ───────────────────  Ctrl-C  ───────────────────

def abort(sig, frame):
    print("\n⛔  Avbrutet av användaren – loggar sparade, men processen slutfördes inte.")
    sys.exit(1)

signal.signal(signal.SIGINT, abort)


# ───────────────────────── Meny (CLI) ─────────────────────────

def main():
    print("\n🎛️   DiskSaverDX – Diskräddare v2.4")
    print("1. 🔍   Föranalys och sedan ev. räddning")
    print("2. 🚀   Direkt räddning (utan föranalys)")
    print("3. ❌   Avsluta")
    choice = input("Val (1/2/3): ").strip()

    if choice == '3':
        sys.exit()
    if choice not in ('1', '2'):
        print("Ogiltigt val.")
        return

    src = ask_path("📂   Källa: ")

    analysis_results = collect_and_analyse(src, incl_hidden=True)

    if choice == '1':
        print_analysis(analysis_results)
        if not ask_yes("Fortsätt till räddning?"):
            sys.exit()

    print("\n⚙️   Inställningar för räddning:")
    dst = ask_path("📁   Destination: ")

    incl_hidden = ask_yes("Inkludera dolda filer i kopieringen?")
    max_sz = ask_size()
    excl = ask_excl()

    group_top = ask_yes("Gruppera efter toppmapp (från_<mappnamn>)?")

    top_before_type = False
    if group_top:
        top_before_type = ask_yes(
            "📂 Toppmapp före filtyp? "
            "(j = ÅR/ÅR-MÅNAD/från_<mapp>/Bilder, "
            "n = ÅR/ÅR-MÅNAD/Bilder/från_<mapp>)"
        )

    use_date_folders = ask_yes("📅 Sortera filer i datum-mappar (ÅR/ÅR-MÅNAD)?")
    use_hash = ask_yes("Aktivera hash-dubblettkontroll (långsammare men säkrare)?")
    hash_only = False
    if use_hash:
        hash_only = ask_yes("Endast dubblettanalys (ingen kopiering)?")

    if incl_hidden:
        files_to_process = analysis_results['all_files']
    else:
        hidden_set = set(analysis_results['hidden_files'])
        files_to_process = [f for f in analysis_results['all_files'] if f not in hidden_set]

    print("\n─── Sammanfattning före start ───")
    print(f"Källa: {src}")
    print(f"Destination: {dst}")
    print(f"Antal filer att bearbeta: {len(files_to_process)}")
    print(f"Inkludera dolda: {'Ja' if incl_hidden else 'Nej'}")
    print(f"Max filstorlek: {human(max_sz) if max_sz is not None else 'Obegränsad'}")
    print(f"Exkluderade filtyper: {excl if excl else 'Inga'}")
    print(f"Hash-kontroll: {'Ja' if use_hash else 'Nej'}")
    print(f"Datum-mappar: {'Ja' if use_date_folders else 'Nej'}")
    print(f"Toppmapp före filtyp: {'Ja' if (group_top and top_before_type) else 'Nej'}")
    if not ask_yes("\nÄr du redo att starta processen?"):
        print("Avbryter.")
        sys.exit()

    print("\n🚀   Startar processen...")
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
        progress_cb=None,  # CLI använder bara text-progress
    )

    print("\n✨   Processen är klar!")
    if not hash_only:
        print(f"Kopierade: {copied}")
    print(f"Dubbletter hittade: {dups}")
    print(f"Fel: {fails}")

    if not hash_only and copied > 0 and ask_yes("\nVill du köra en städning av tomma mappar i destinationen?"):
        cleanup_empty(dst)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAvbrutet av användaren. Hej då!")
        sys.exit(0)
