import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import threading
import os
from PIL import Image, ImageTk
import sqlite3

from data_manager import calculate_total_time, save_session, DB_FILE
from utils import open_file, calculate_level, format_hours
from audio_manager import play_sound
from config import LEVEL_THRESHOLDS, BADGE_DIR
from achievements import show_achievements
from skilltree import show_skilltree


class PomodoroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pomodoro Timer")

        # quit on ctrl q 
        self.root.bind("<Control-q>", self.quit_app)
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

        self.running = False
        self.paused = False
        self.seconds_left = 0
        self.total_seconds = 0
        self.elapsed_seconds = 0
        self.intention_text = ""

        self.mode = tk.StringVar(value="Pomodoro")

        # ---- Frame für Dropdown + Settings Button ----
        top_frame = tk.Frame(root)
        top_frame.pack(fill="x", pady=5)

        self.mode_menu = tk.OptionMenu(top_frame, self.mode, "Pomodoro", "Offener Timer", command=self.switch_mode)
        self.mode_menu.pack(side="left", padx=5)

        self.settings_button = tk.Button(top_frame, text="⚙️", command=self.open_settings)
        self.settings_button.pack(side="right", padx=5)

        self.skilltree_button = tk.Button(top_frame, text="💠", command=lambda: show_skilltree(self.root))
        self.skilltree_button.pack(side="right", padx=5)

        self.duration_label = tk.Label(root, text="Dauer:")
        self.duration_label.pack()
        self.minutes_entry = tk.Entry(root)
        self.minutes_entry.pack()

        self.timer_label = tk.Label(root, text="00:00", font=("Helvetica", 32))
        self.timer_label.pack(pady=10)

        self.progress_width = 300
        self.progress_height = 25
        self.progress_canvas = tk.Canvas(root, width=self.progress_width, height=self.progress_height, bg="lightgray")
        self.progress_canvas.pack(pady=5)
        self.progress_bar = self.progress_canvas.create_rectangle(0, 0, 0, self.progress_height, fill="green")

        button_frame = tk.Frame(root)
        button_frame.pack(pady=5)
        self.start_button = tk.Button(button_frame, text="Start", command=self.ask_intention)
        self.start_button.pack(side="left", padx=5)
        self.pause_button = tk.Button(button_frame, text="Pause", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=5)
        self.stop_button = tk.Button(root, text="Stop", command=self.stop_open_timer)
        self.stop_button.pack_forget()

        self.badge_frame = tk.Frame(root, height=50)
        self.badge_frame.pack(pady=(0,0))
        self.badge_button = tk.Button(self.badge_frame, command=self.show_badge_gallery, borderwidth=0)
        self.badge_button.pack(pady=0)

        self.level_canvas = tk.Canvas(root, height=5, bg="lightgray", highlightthickness=0)
        self.level_canvas.pack(padx=10, pady=(5,0), fill="x")

        label_frame = tk.Frame(root)
        label_frame.pack(fill="x", padx=10, pady=(2,5))
        self.next_goal_label = tk.Label(label_frame, text="25h", font=("Helvetica", 12))
        self.next_goal_label.pack(side="left")
        self.total_time_label = tk.Label(label_frame, font=("Helvetica", 12))
        self.total_time_label.pack(side="left", expand=True)

        # Nach 100 ms (wenn alles geladen ist) den Text setzen, damit nicht weirder bug 
        self.root.after(100, self.update_total_time_label)
        self.level_label = tk.Label(label_frame, text="0", font=("Helvetica", 12))
        self.level_label.pack(side="right")

        self.current_level = calculate_level(calculate_total_time())
        self.update_side_progress()
        self.update_level_display()
        self.root.after(100, self.update_badge)

        self.notes_text = tk.Text(root, height=5, width=40, wrap="word")
        self.notes_text.pack(padx=10, pady=10, fill="both", expand=True)

        # ---- Stelle sicher, dass DB existiert ----
        self.ensure_db()

        # für updating total time auf main pomorodo gui 
    def update_total_time_label(self):
        total = calculate_total_time()
        self.total_time_label.config(text=f"Σ {format_hours(total)}")

    # ---- Datenbank Hilfsfunktion ----
    def ensure_db(self):
        """Erstellt Tabelle, falls sie nicht existiert."""
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS pomodoro_session (
                sessions INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                time TEXT,
                skill TEXT,
                duration REAL,
                total_time REAL,
                intention TEXT,
                result TEXT
            )
        """)
        conn.commit()
        conn.close()


    # ---- Timer-Logik ----
    def switch_mode(self, mode):
        self.reset_timer()
        if mode == "Pomodoro":
            self.duration_label.pack()
            self.minutes_entry.pack()
            self.progress_canvas.pack(pady=5)
            self.stop_button.pack_forget()
        else:
            self.duration_label.pack_forget()
            self.minutes_entry.pack_forget()
            self.progress_canvas.pack_forget()
            self.stop_button.pack(pady=5)
            self.stop_button.config(state="disabled")

    def ask_intention(self):
        if self.running:
            return
        popup = tk.Toplevel(self.root)
        popup.title("Intention")
        popup.geometry("300x180")
        
        tk.Label(popup, text="Was ist deine Intention für diese Session?").pack(pady=(10,0))
        entry = tk.Entry(popup, width=40)
        entry.pack(pady=(0,10))

        tk.Label(popup, text="Welcher Skill?").pack(pady=(5,0))
        skill_var = tk.StringVar(value="Pomodoro")  # Default-Wert
        skill_options = ["SOZ", "SUR", "MATH", "JOURNAL", "TECH", "UNI", "DESIGN"]
        skill_menu = tk.OptionMenu(popup, skill_var, *skill_options)
        skill_menu.pack(pady=(0,10))

        def confirm():
            text = entry.get().strip()
            skill = skill_var.get().strip()
            if not text:
                messagebox.showerror("Fehler", "Bitte eine Intention eingeben.")
                return
            self.intention_text = text
            self.selected_skill = skill
            popup.destroy()
            self.start_timer()

        tk.Button(popup, text="Starten", command=confirm).pack(pady=10)


        tk.Button(popup, text="Starten", command=confirm).pack(pady=10)

    def start_timer(self):
        self.running = True
        self.paused = False
        self.pause_button.config(state="normal")
        if self.mode.get() == "Pomodoro":
            try:
                minutes = float(self.minutes_entry.get())
                if minutes <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Fehler", "Bitte eine gültige Zahl > 0 eingeben.")
                self.running = False
                return
            self.total_seconds = int(minutes * 60)
            self.seconds_left = self.total_seconds
            self.update_timer()
        else:
            self.elapsed_seconds = 0
            self.stop_button.config(state="normal")
            self.update_open_timer()

    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        self.pause_button.config(text="Weiter" if self.paused else "Pause")
        if not self.paused:
            if self.mode.get() == "Pomodoro":
                self.update_timer()
            else:
                self.update_open_timer()

    def update_timer(self):
        if self.seconds_left > 0 and self.running and not self.paused:
            mins, secs = divmod(self.seconds_left, 60)
            self.timer_label.config(text=f"{mins:02d}:{secs:02d}")
            elapsed = self.total_seconds - self.seconds_left
            fill_width = (elapsed / self.total_seconds) * self.progress_width
            self.progress_canvas.coords(self.progress_bar, 0, 0, fill_width, self.progress_height)
            self.seconds_left -= 1
            self.root.after(1000, self.update_timer)
        elif self.seconds_left <= 0 and self.running:
            self.timer_label.config(text="00:00")
            self.progress_canvas.coords(self.progress_bar, 0, 0, self.progress_width, self.progress_height)
            self.running = False
            self.pause_button.config(state="disabled")
            threading.Thread(target=play_sound).start()
            self.show_result_popup(duration=self.total_seconds / 60)

    def update_open_timer(self):
        if self.running and not self.paused:
            mins, secs = divmod(self.elapsed_seconds, 60)
            self.timer_label.config(text=f"{mins:02d}:{secs:02d}")
            self.elapsed_seconds += 1
            self.root.after(1000, self.update_open_timer)

    def stop_open_timer(self):
        if self.mode.get() == "Offener Timer" and self.running:
            self.running = False
            self.pause_button.config(state="disabled")
            self.stop_button.config(state="disabled")
            self.show_result_popup(duration=self.elapsed_seconds / 60)

    # ---- Fortschritt / Level ----
    def update_side_progress(self):
        total_hours = calculate_total_time()
        current_level = calculate_level(total_hours)
        if current_level >= len(LEVEL_THRESHOLDS):
            max_val, val = 1, 1
        else:
            lower_bound = 0 if current_level == 0 else LEVEL_THRESHOLDS[current_level - 1]
            upper_bound = LEVEL_THRESHOLDS[current_level]
            max_val = upper_bound - lower_bound
            val = max(total_hours - lower_bound, 0)
        self.draw_gradient_bar(val, max_val)

    def draw_gradient_bar(self, value, maximum):
        self.level_canvas.delete("all")
        width = self.level_canvas.winfo_width()
        if width == 1:
            self.root.after(50, lambda: self.draw_gradient_bar(value, maximum))
            return
        height = self.level_canvas.winfo_height()
        fraction = min(max(value / maximum, 0), 1)
        steps = int(width)
        for i in range(steps):
            rel = i / steps
            if rel <= fraction:
                r = int(255 - 55 * rel)
                g = int(182 + 73 * rel)
                b = int(193 - 43 * rel)
                color = f"#{r:02x}{g:02x}{b:02x}"
                self.level_canvas.create_line(i, 0, i, height, fill=color)

    def update_badge(self):
        badge_path = os.path.join(BADGE_DIR, f"p{self.current_level}.png")
        if not os.path.exists(badge_path):
            return
        try: 
            img = Image.open(badge_path)
            img = img.resize((60, 60), Image.Resampling.LANCZOS)
            self.badge_image = ImageTk.PhotoImage(img)
            self.badge_button.config(image=self.badge_image)
        except Exception:
            pass

    def show_badge_gallery(self):
        gallery = tk.Toplevel(self.root)
        gallery.title("Freigeschaltete Badges")
        gallery.geometry("405x240")
        frame = tk.Frame(gallery)
        frame.pack(padx=10, pady=10, fill="x")
        images = []
        max_per_row = 5
        row = 0
        col = 0
        for i in range(self.current_level + 1):
            path = os.path.join(BADGE_DIR, f"p{i}.png")
            if os.path.exists(path):
                img = Image.open(path)
                img = img.resize((60, 60), Image.Resampling.LANCZOS)
                tk_img = ImageTk.PhotoImage(img)
                images.append(tk_img)
                lbl = tk.Label(frame, image=tk_img)
                lbl.image = tk_img  # Referenz halten!
                lbl.grid(row=row, column=col, padx=5, pady=5)
                col += 1
                if col >= max_per_row:
                    col = 0
                    row += 1
        if not images:
            tk.Label(frame, text="Keine Badges freigeschaltet.").pack()

    def show_leaderboard(self):
        def load_leaderboard(period="All Time"):
            sessions = []
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT duration, date, time FROM pomodoro_session")
                rows = c.fetchall()
                conn.close()
            except Exception:
                messagebox.showerror("Fehler", "Fehler beim Laden der DB.")
                return

            # ---- Zeitfilter vorbereiten ----
            now = datetime.now()
            filtered = []
            for dur, date_str, time_str in rows:
                try:
                    dur = float(dur)
                except:
                    dur = 0
                try:
                    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                except:
                    continue

                include = False
                if period == "All Time":
                    include = True
                elif period == "Today":
                    include = dt.date() == now.date()
                elif period == "This Week":
                    include = dt.isocalendar()[1] == now.isocalendar()[1] and dt.year == now.year
                elif period == "This Month":
                    include = dt.month == now.month and dt.year == now.year
                elif period == "This Year":
                    include = dt.year == now.year

                if include:
                    filtered.append((dur, dt))

            # ---- Anzeige aktualisieren ----
            for w in list(frame_inner.winfo_children()):
                w.destroy()

            # Summe berechnen und anzeigen
            total_minutes = sum(dur for dur, _ in filtered)
            sum_label.config(text=f"Summe: {total_minutes:.0f} min")

            tk.Label(
                frame_inner, text=f"Top 10 ({period})", font=("Helvetica", 12, "bold")
            ).pack(pady=5)

            colors = ["#b8860b", "silver", "#cd7f32"]  # Gold, Silber, Bronze
            emojis = ["🥇", "🥈", "🥉"] + [""] * 7

            if not filtered:
                tk.Label(frame_inner, text="Keine Einträge.").pack(pady=10)
                return

            # Sortierung: längste zuerst
            filtered.sort(reverse=True, key=lambda x: x[0])
            top10 = filtered[:10]

            for i, (dur, dt) in enumerate(top10):
                color = colors[i] if i < 3 else "black"
                emoji = emojis[i]
                ts = dt.strftime("%d.%m %H:%M")
                tk.Label(
                    frame_inner,
                    text=f"{emoji} {ts}: {dur:.0f} min",
                    fg=color,
                    font=("Helvetica", 10, "bold" if i < 3 else "normal")
                ).pack(anchor="w", padx=10)

        # ---- Popup erstellen ----
        popup = tk.Toplevel(self.root)
        popup.title("Leaderboard")
        popup.geometry("260x350")

        tk.Label(popup, text="", font=("Helvetica", 13, "bold")).pack(pady=5)

        # ---- Dropdown ----
        period_var = tk.StringVar(value="All Time")
        options = ["Today", "This Week", "This Month", "This Year", "All Time"]
        period_menu = tk.OptionMenu(popup, period_var, *options,
                                    command=lambda _: load_leaderboard(period_var.get()))
        period_menu.pack(pady=5)

        # ---- Label für Summe ----
        sum_label = tk.Label(popup, text="", font=("Helvetica", 10), fg="gray")
        sum_label.pack(pady=2)

        # ---- Frame für Ergebnisse ----
        frame_inner = tk.Frame(popup)
        frame_inner.pack(fill="both", expand=True)

        # ---- Initiales Laden ----
        load_leaderboard("All Time")

            
    def update_level_display(self):
        total_hours = calculate_total_time()
        level = calculate_level(total_hours)
        self.level_label.config(text=f"LVL {level}")
        next_threshold = next((t for t in LEVEL_THRESHOLDS if t > total_hours), None)
        if next_threshold:
            self.next_goal_label.config(text=f"{format_hours(next_threshold - total_hours)}")
        else:
            self.next_goal_label.config(text="Max Level!")
        self.current_level = level
        self.update_badge()

    # ---- Popup / Speicher ----
    def show_result_popup(self, duration=None):
        popup = tk.Toplevel(self.root)
        popup.title("Geschafft?")
        popup.geometry("300x120")
        tk.Label(popup, text="Hast du deine Aufgabe geschafft?").pack(pady=10)
        entry = tk.Entry(popup, width=40)
        entry.pack()

        def submit():
            result = entry.get().strip()
            if not result:
                messagebox.showerror("Fehler", "Bitte ein Ergebnis eintragen.")
                return
            dur = duration if duration is not None else 0
            save_session(dur, self.intention_text, result, skill=getattr(self, "selected_skill", "Pomodoro"))
            self.total_time_label.config(text=format_hours(calculate_total_time()))
            old_level = self.current_level
            self.update_side_progress()
            self.update_level_display()
            new_level = calculate_level(calculate_total_time())
            self.current_level = new_level
            if new_level > old_level:
                messagebox.showinfo("🎉 Glückwunsch!", f"Level Up! Du bist jetzt Level {new_level}!")
            messagebox.showinfo("Gespeichert", "Session wurde gespeichert.")
            self.reset_timer()
            popup.destroy()

        tk.Button(popup, text="Speichern", command=submit).pack(pady=10)

    def reset_timer(self):
        self.timer_label.config(text="00:00")
        self.minutes_entry.delete(0, tk.END)
        self.progress_canvas.coords(self.progress_bar, 0, 0, 0, self.progress_height)
        self.pause_button.config(text="Pause", state="disabled")
        self.stop_button.config(state="disabled")
        self.running = False
        self.paused = False
        self.intention_text = ""
        self.update_side_progress()
        self.update_level_display()

    # ---- Settings ----
    def open_log(self):
        if os.path.exists(DB_FILE):
            open_file(DB_FILE)
        else:
            messagebox.showinfo("Info", "DB existiert noch nicht.")

    def open_settings(self):
        popup = tk.Toplevel(self.root)
        popup.title("Settings")
        popup.geometry("200x150")
        tk.Button(popup, text="Log", width=15, command=lambda:[popup.destroy(), self.open_log()]).pack(pady=5)
        tk.Button(popup, text="Leaderboard", width=15, command=lambda:[popup.destroy(), self.show_leaderboard()]).pack(pady=5)
        tk.Button(popup, text="Achievements", width=15, command=lambda:[popup.destroy(), show_achievements(self.root)]).pack(pady=5)

    # quit on ctrl q 
    def quit_app(self, event=None):
        self.running = False
        self.root.destroy()

# ---- Start ----
if __name__ == "__main__":
    root = tk.Tk()
    app = PomodoroApp(root)
    root.mainloop()
