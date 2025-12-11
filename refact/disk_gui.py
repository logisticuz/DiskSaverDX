import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pathlib import Path
from typing import Set, Optional
import json

from disk_core import (collect_and_analyse, copy_phase, cleanup_empty,
                       human, format_duration)

from gui_theme import setup_dark_theme
from gui_tooltip import ToolTip
from gui_utils import open_in_explorer, size_to_bytes, make_treeview_sortable
