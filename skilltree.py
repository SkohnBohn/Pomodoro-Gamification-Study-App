# skilltree.py
import tkinter as tk
from tkinter import messagebox
import sqlite3
import math

from data_manager import calculate_total_time, DB_FILE

def show_skilltree(root):
    """
    Zeigt das Skilltree-Popup an.
    'root' ist das Tkinter-Hauptfenster der App.
    """

    skills = ["SOZ", "SUR", "MATH", "JOURNAL", "TECH", "UNI", "DESIGN"]
    skill_totals = {skill: 0.0 for skill in skills}
    SKILL_THRESHOLDS = [5, 10, 20, 35, 55, 80, 110, 145, 185, 230, 280, 335]  # Stunden pro Skill-Level
    SKILL_EMOJIS = {
        "SOZ": "🧠",
        "SUR": "🎨",
        "MATH": "📐",
        "JOURNAL": "📝",
        "TECH": "💻",
        "UNI": "🎓",
        "DESIGN": "🎨"
    }

    # ---- DB abfragen ----
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT skill, SUM(duration) FROM pomodoro_session GROUP BY skill")
        for skill, total_min in c.fetchall():
            if skill in skill_totals and total_min:
                skill_totals[skill] = total_min / 60.0

        c.execute("SELECT SUM(duration) FROM pomodoro_session")
        total_all_min = c.fetchone()[0] or 0
        total_all = total_all_min / 60.0

        c.execute("SELECT duration, skill FROM pomodoro_session ORDER BY Sessions DESC LIMIT 1")
        last = c.fetchone()
        conn.close()
    except Exception as e:
        messagebox.showerror("Fehler", f"Fehler beim Laden der DB: {e}")
        return

    # ---- Hilfsfunktion Level und Fortschritt ----
    def get_level_and_progress(hours):
        for i, t in enumerate(SKILL_THRESHOLDS):
            if hours < t:
                lower = 0 if i == 0 else SKILL_THRESHOLDS[i - 1]
                upper = t
                return i, (hours - lower) / (upper - lower), upper
        return len(SKILL_THRESHOLDS), 1.0, SKILL_THRESHOLDS[-1]

    # ---- Farbverlauf & Glow ----
    def get_color(level_ratio, glow=0.0):
        # Pastellfarben Gradient: Blau → Grün → Gelb
        if level_ratio < 0.5:
            r = int(135 * (1 - level_ratio*2) + 144 * (level_ratio*2))
            g = int(206 * (1 - level_ratio*2) + 238 * (level_ratio*2))
            b = int(250 * (1 - level_ratio*2) + 144 * (level_ratio*2))
        else:
            r = int(144 + (255-144) * (level_ratio-0.5)*2)
            g = int(238 + (215-238) * (level_ratio-0.5)*2)
            b = int(144 + (0-144) * (level_ratio-0.5)*2)

        r = min(int(r * (1 + glow)), 255)
        g = min(int(g * (1 + glow)), 255)
        b = min(int(b * (1 + glow)), 255)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ---- Popup & Layout ----
    popup = tk.Toplevel(root)
    popup.title("Skilltree")
    popup.geometry("460x420")
    popup.configure(bg="#fdfdfd")  # hell

    tk.Label(popup, text="🎯 Skilltree", font=("Helvetica", 16, "bold"),
             bg="#fdfdfd", fg="#333333").pack(pady=8)

    # ---- Canvas + Scrollbar ----
    canvas = tk.Canvas(popup, bg="#fdfdfd", highlightthickness=0)
    scrollbar = tk.Scrollbar(popup, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas, bg="#fdfdfd")

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # ---- Skill-Balken ----
    sorted_skills = sorted(skill_totals.items(), key=lambda x: x[1], reverse=True)
    bar_length = 260

    for idx, (skill, hours) in enumerate(sorted_skills):
        level, progress_ratio, next_level_goal = get_level_and_progress(hours)
        glow = 0.05 + 0.05*math.sin(progress_ratio*math.pi*2)
        color = get_color(min(level / len(SKILL_THRESHOLDS), 1.0), glow=glow)

        frame = tk.Frame(scroll_frame, bg="#fdfdfd")
        frame.pack(fill="x", pady=6)

        # Spalte 0: Skillname
        tk.Label(frame, text=f"{SKILL_EMOJIS.get(skill,'')} {skill}", font=("Helvetica", 11, "bold"),
                 bg="#fdfdfd", fg="#333333", width=10, anchor="w").grid(row=0, column=0, sticky="w", padx=(8,4))

        # Spalte 1: Balken
        bar_canvas = tk.Canvas(frame, width=bar_length, height=24, bg="#e0e0e0",
                               highlightthickness=1, highlightbackground="#cccccc")
        bar_canvas.grid(row=0, column=1, sticky="w")
        fill_width = progress_ratio * bar_length
        bar_canvas.create_rectangle(0, 0, fill_width, 24, fill=color, outline="#888888", width=1)
        bar_canvas.create_text(bar_length/2, 12, text=f"LVL {level}", fill="#333333", font=("Helvetica", 10, "bold"))

        # Spalte 2: Stunden-Text
        tk.Label(frame, text=f"{hours:.1f} / {next_level_goal}h" if level < len(SKILL_THRESHOLDS) else f"{hours:.1f}h ⭐",
                 font=("Helvetica", 12), bg="#fdfdfd", fg="#333333").grid(row=0, column=2, sticky="w", padx=(8,0))

    # ---- Gesamtzeit ----
    tk.Label(
        scroll_frame,
        text=f"Gesamtzeit: {total_all:.2f} h",
        font=("Helvetica", 11, "italic"),
        bg="#fdfdfd",
        fg="#555555"
    ).pack(pady=10)

    # ---- Letzte Session ----
    if last:
        last_duration, last_skill = last
        last_duration_min = last_duration     # already in minutes
        last_duration_h = last_duration_min / 60  # only for color scaling
        emoji = SKILL_EMOJIS.get(last_skill, "")
        
        # Text zeigt jetzt die Dauer in Minuten
        last_text = f"{emoji} +{last_duration_min}min in {last_skill}"

        glow = 0.1
        color = get_color(min(last_duration_h / 5.0, 1.0), glow=glow)

        last_frame = tk.Frame(scroll_frame, bg="#fdfdfd")
        last_frame.pack(pady=(8, 18))
        
        tk.Label(last_frame, text="Letzte Session:", font=("Helvetica", 11, "bold"),
                 bg="#fdfdfd", fg="#333333").pack()
        tk.Label(last_frame, text=last_text, font=("Helvetica", 12, "bold"),
                 fg=color, bg="#fdfdfd").pack(pady=3)

        # Progress bar in MINUTEN
        progress_canvas = tk.Canvas(last_frame, width=240, height=10, bg="#e0e0e0",
                                    highlightthickness=1, highlightbackground="#cccccc")
        progress_canvas.pack()

             # --- Fortschritt relativ zur Level-Grenze des Skills ---
        skill_hours = skill_totals.get(last_skill, 0)
        level, progress_ratio, next_level_goal = get_level_and_progress(skill_hours)

        # Differenz zwischen aktuellem Level-Lowerbound und Upperbound
        lower = 0 if level == 0 else SKILL_THRESHOLDS[level - 1]
        upper = next_level_goal

        level_span_minutes = (upper - lower) * 60  # in Minuten

        # Wie viel der Session passt relativ in diese Levelspanne?
        fill_ratio = min(last_duration_min / level_span_minutes, 1.0)
        fill_width = fill_ratio * 240

        progress_canvas.create_rectangle(0, 0, fill_width, 10,
                                         fill=color, outline="#888888", width=1)

        if last_duration_h >= 5:
            tk.Label(last_frame, text="⭐ LEVEL UP!", font=("Helvetica", 11, "bold"), fg="#ffbb00", bg="#fdfdfd").pack(pady=2)

# ich möchte den code verbessern um es more satisfying zu machen. dafür möchte ich es belohnen, 
# wenn ein balken im skill tree voll ist. Dafür soll, wenn einer voll ist, auf dem balken oder daneben
# oder so mach wei du meinst, ein button sein, denn man drücken kann, wo dann kommt "level up" und erst
# dann sieht man wieder wie weit man sit. Baue das in diesen code ein, das ist mein skilltree modeul