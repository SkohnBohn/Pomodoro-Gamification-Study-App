import os
import platform
import subprocess
from tkinter import messagebox
from config import LEVEL_THRESHOLDS

def open_file(filepath):
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.call(("open", filepath))
        elif system == "Windows":
            os.startfile(filepath)
        else:
            subprocess.call(("xdg-open", filepath))
    except Exception as e:
        messagebox.showerror("Fehler", f"Konnte Datei nicht öffnen: {e}")

def calculate_level(total_hours):
    level = 0
    for t in LEVEL_THRESHOLDS:
        if total_hours >= t:
            level += 1
    return level

def format_hours(hours: float) -> str:
    return f"{hours:.2f}h"
