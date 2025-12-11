# DiskSaverDX – Advanced File Recovery & Disk Cleanup Tool 🔍⚡

DiskSaverDX is a modern, high-performance tool for **rescuing files**,
**organizing chaotic storage**, and **cleaning up disk clutter** on Windows.

Designed for power-users and everyday people alike, DiskSaverDX offers:

- Smart backup (“Saver Mode”)
- Safe cleanup (“Städläge”)
- Deep disk analysis
- Duplicate detection (hash-based)
- A full GUI with dark mode
- A fast, single-pass scan engine

Whether you're rescuing old CD backups, cleaning Downloads/Desktop, or organizing thousands of photos — DiskSaverDX helps you bring order to chaos.

---

## 🚀 Key Features

### 🔎 Powerful Disk Analysis
- Scans entire drives or folders
- Categorizes files (Bilder, Videos, Audio, Dokument, etc.)
- Summaries per category & filetype
- Top folders by size
- Hidden file detection
- Duplicate hints

### 💾 Saver Mode (Backup)
Automatically organizes rescued files by:
- optional **date structure** (YEAR/YEAR-MONTH)
- **category** (Images, Videos, Documents, etc.)
- optional **source top folder** (`från_<mapp>`)
- optional size limits
- excludable filetypes

Perfect for external drive backups, old PCs, USB drives, SD cards, cameras, etc.

### 🧹 Städläge (Cleanup Mode)
Preset optimized for cleaning messy locations like Desktop, Downloads, Temp folders.

Includes:
- temp/system ignore
- size filters
- safe category-based sorting
- duplicate detection
- option to remove empty folders after cleanup

### 🔐 Hash-Based Duplicate Detection (Optional)
- SHA-256 exact duplicate matching
- “Only duplicate analysis” mode
- Logs all duplicates to `dubbletter.txt`

### 🖥 Modern Dark-Mode GUI
- Progress bars (determinate + indeterminate)
- ETA display
- Pause/Resume during file rescue
- Live “current file” indicator
- Two analysis tables (categories + filetypes)
- Export to CSV or JSON

### 📄 Detailed Logs
DiskSaverDX generates:
```
logg.txt           – all copy actions
dubbletter.txt     – hash duplicates (when enabled)
dolda.txt          – hidden files discovered
fel.txt            – files that failed to copy (with reason)
rensning.txt       – removed empty directories
```

---

## 🧠 Project Structure

```
/src
   disk_core.py       → core engine (analysis, copy, hashing, cleanup)
   disk_gui.py        → full GUI (tkinter, dark mode, progress, presets)
/logs                 → generated logs (ignored by Git)
/README.md
/LICENSE
```

---

## 📦 Installation

### 1. Clone the repo
```bash
git clone https://github.com/<your-user>/DiskSaverDX.git
cd DiskSaverDX
```

### 2. Create a venv (recommended)
```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies
(Currently standard library only — no external deps required)

### 4. Run the GUI
```bash
python src/disk_gui.py
```

### Run CLI version (optional)
```bash
python src/disk_core.py
```

---

## 🧪 Testing (planned)
```bash
pytest tests/
```

---

# 🗺 Roadmap

## ✔ v2.x (Current Capabilities)
- GUI (dark mode)
- Analysis engine (categories + filetypes)
- Powerful backup mode (Saver Mode)
- Cleanup presets (Städläge)
- Hash duplicate detection (optional)
- Pause/Resume for long operations
- Date-folder sorting (optional)
- Top-folder grouping (optional)
- CSV/JSON export
- Extensive logging

---

## 🚧 v3.0 (In Progress)
### ✨ UX / Quality Improvements
- Human-readable ETA (minutes / hours)
- Improved window layout + auto-sizing
- Smarter tooltips / explanations
- Pre-warnings (e.g. “You are about to sort a full user profile by month”)

### 📊 Post-Run Error Visualizer
A full GUI page showing:
- What failed to copy
- Why it failed
- Grouped by error type
- Insights (e.g. “98% of failures came from AppData/Local/Temp”)
- Exportable report

### 🔥 Smart Filters
- “Ignore system folders” preset
- Auto-detection of Temp/AppData
- Excluding system-protected files
- Path-too-long warnings/fixes

---

## 🌟 Future Versions (v3.x+)
- Plugin system
- Scheduled cleanup
- Cloud backup integration
- Photo/Video management mode
- Performance visualizations
- Premium/Pro tier
- File system monitoring

---

## 🔒 Privacy & Data Handling

DiskSaverDX **collects zero user data**.
All logs remain 100% local.
Future optional telemetry (opt-in only) may be added using open-source tools like Plausible.

---

## 🤝 Contributing

Pull requests are welcome!

1. Fork repo
2. Create feature branch
3. Make changes
4. Submit PR

Feedback, ideas, and issues are appreciated.

---

## 📄 License
This project is licensed under **MIT**.
See `LICENSE` for details.
