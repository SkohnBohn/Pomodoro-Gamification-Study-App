#böeghghggh#
# achievements.py
import tkinter as tk
from tkinter import messagebox
import sqlite3
from data_manager import calculate_total_time, save_session, DB_FILE


def show_achievements(root):
    total_hours = calculate_total_time()
    popup = tk.Toplevel(root)
    popup.title("Achievements")
    popup.geometry("300x450")  # etwas größer, weil mehr Balken

    # ---- Total Hours ----
    tk.Label(popup, text="Total Hours").pack(pady=(5, 0))
    hours_frame = tk.Frame(popup)
    hours_frame.pack(fill="x", padx=10)

    tk.Label(hours_frame, text="0").pack(side="left")
    tk.Label(hours_frame, text="200").pack(side="right")  # max_hours

    hours_canvas = tk.Canvas(hours_frame, height=20, bg="lightgray")
    hours_canvas.pack(fill="x", expand=True, side="left", padx=5)

    max_hours = 500
    hours_canvas.update_idletasks()
    fill_width = min(total_hours / max_hours, 1) * hours_canvas.winfo_width()
    hours_canvas.create_rectangle(0, 0, fill_width, 20, fill="green")
    tk.Label(popup, text=f"{total_hours:.2f} / {max_hours} h").pack(pady=2)


    # ---- Minuten ----
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT SUM(duration) FROM pomodoro_session")
        total_minutes = c.fetchone()[0] or 0  # duration ist in Minuten
        conn.close()
    except Exception as e:
        messagebox.showerror("Fehler", f"Fehler beim Laden der DB: {e}")
        total_minutes = 0

    tk.Label(popup, text="Total Minutes").pack(pady=(10,0))
    minutes_frame = tk.Frame(popup)
    minutes_frame.pack(fill="x", padx=10)

    tk.Label(minutes_frame, text="0").pack(side="left")
    tk.Label(minutes_frame, text="50000").pack(side="right")  # max_minutes

    minutes_canvas = tk.Canvas(minutes_frame, height=20, bg="lightgray")
    minutes_canvas.pack(fill="x", expand=True, side="left", padx=5)

    max_minutes = 50000
    minutes_canvas.update_idletasks()
    fill_width = min(total_minutes / max_minutes, 1.0) * minutes_canvas.winfo_width()
    minutes_canvas.create_rectangle(0, 0, fill_width, 20, fill="green")
    tk.Label(popup, text=f"{total_minutes} / {max_minutes} Minutes").pack(pady=(2,5))

        # ---- Sessions ----
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM pomodoro_session")
        session_count = c.fetchone()[0] or 0
    except Exception as e:
        messagebox.showerror("Fehler", f"Fehler beim Laden der DB: {e}")
        session_count = 0

    tk.Label(popup, text="Sessions").pack(pady=(10,0))
    sessions_frame = tk.Frame(popup)
    sessions_frame.pack(fill="x", padx=10)

    tk.Label(sessions_frame, text="0").pack(side="left")
    tk.Label(sessions_frame, text="2000").pack(side="right")  # max_sessions

    sessions_canvas = tk.Canvas(sessions_frame, height=20, bg="lightgray")
    sessions_canvas.pack(fill="x", expand=True, side="left", padx=5)

    max_sessions = 2000
    sessions_canvas.update_idletasks()
    session_fill = min(session_count / max_sessions, 1.0) * sessions_canvas.winfo_width()
    sessions_canvas.create_rectangle(0, 0, session_fill, 20, fill="green")
    tk.Label(popup, text=f"{session_count} / {max_sessions} Sessions").pack(pady=(2,5))
    
    # ---- Sessions >30min ----
    try:
        c.execute("SELECT COUNT(*) FROM pomodoro_session WHERE duration > 29.9")
        over_30_count = c.fetchone()[0] or 0
    except Exception as e:
        messagebox.showerror("Fehler", f"Fehler beim Laden der DB: {e}")
        over_30_count = 0

    tk.Label(popup, text="Sessions > 30 min").pack(pady=(10,0))
    over_30_frame = tk.Frame(popup)
    over_30_frame.pack(fill="x", padx=10)

    tk.Label(over_30_frame, text="0").pack(side="left")
    tk.Label(over_30_frame, text="1000").pack(side="right")  

    over_30_canvas = tk.Canvas(over_30_frame, height=20, bg="lightgray")
    over_30_canvas.pack(fill="x", expand=True, side="left", padx=5)
    max_sessions30 = 1000
    
    over_30_canvas.update_idletasks()
    over_30_fill = min(over_30_count / max_sessions30, 1.0) * over_30_canvas.winfo_width()
    over_30_canvas.create_rectangle(0, 0, over_30_fill, 20, fill="skyblue")
    tk.Label(popup, text=f"{over_30_count} / {max_sessions30} Sessions").pack(pady=(2,5))

    # ---- Sessions >50min ----
    try:
        c.execute("SELECT COUNT(*) FROM pomodoro_session WHERE duration > 49.9")
        over_50_count = c.fetchone()[0] or 0
        conn.close()
    except Exception as e:
        messagebox.showerror("Fehler", f"Fehler beim Laden der DB: {e}")
        over_50_count = 0

    tk.Label(popup, text="Sessions > 50 min").pack(pady=(10,0))
    over_50_frame = tk.Frame(popup)
    over_50_frame.pack(fill="x", padx=10)

    tk.Label(over_50_frame, text="0").pack(side="left")
    tk.Label(over_50_frame, text="500").pack(side="right")  
    max_sessions50 = 500

    over_50_canvas = tk.Canvas(over_50_frame, height=20, bg="lightgray")
    over_50_canvas.pack(fill="x", expand=True, side="left", padx=5)

    over_50_canvas.update_idletasks()
    over_50_fill = min(over_50_count / max_sessions50, 1.0) * over_50_canvas.winfo_width()
    over_50_canvas.create_rectangle(0, 0, over_50_fill, 20, fill="skyblue")
    tk.Label(popup, text=f"{over_50_count} / {max_sessions50} Sessions").pack(pady=(2,5))




