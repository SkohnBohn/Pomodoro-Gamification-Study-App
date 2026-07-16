#!/usr/bin/env python3
"""Pomodoro Gamification App — Yellow Mode (CustomTkinter)"""

import customtkinter as ctk
import tkinter as tk
import sqlite3
import threading
import math
import os
import platform
import subprocess
from datetime import datetime
from PIL import Image

from config import (
    DB_FILE, BADGE_DIR, LEVEL_THRESHOLDS,
    SKILLS, SKILL_EMOJIS, SKILL_THRESHOLDS,
)
from data_manager import (
    calculate_total_time, save_session, initialize_db,
    save_note, get_notes,
    get_skill_confirmed_levels, confirm_skill_level,
    get_achievements_collected, mark_achievement_collected,
    get_badge_unlock_date,
)
from utils import calculate_level, format_hours
from audio_manager import play_sound

# ── Palette ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

BG      = "#f7c90f"
PANEL   = "#f9d340"
CARD    = "#fce380"
BORDER  = "#ddb800"
DARK    = "#1a1200"
DARK2   = "#3d3000"
MUTED   = "#5c4300"
DIM     = "#7a5f00"
TEXT    = "#1a1200"
SUCCESS = "#14532d"
DANGER  = "#991b1b"

# Skill card colors keyed by level bracket
_SKILL_CARD_PALETTE = [
    (PANEL,     BORDER),      # LVL 0        — base yellow
    ("#fef3c7", "#d97706"),   # LVL 1–2      — light amber
    ("#fde68a", "#b45309"),   # LVL 3–5      — medium amber
    ("#fbbf24", "#92400e"),   # LVL 6–9      — deep amber
    ("#f59e0b", "#78350f"),   # LVL 10+      — rich amber
]


def _skill_card_color(lvl: int):
    if lvl == 0: return _SKILL_CARD_PALETTE[0]
    if lvl <= 2: return _SKILL_CARD_PALETTE[1]
    if lvl <= 5: return _SKILL_CARD_PALETTE[2]
    if lvl <= 9: return _SKILL_CARD_PALETTE[3]
    return _SKILL_CARD_PALETTE[4]


# ── Circular Timer Canvas ──────────────────────────────────────────────────────
class RingTimer(tk.Canvas):
    SIZE = 300

    def __init__(self, parent, **kw):
        super().__init__(
            parent, width=self.SIZE, height=self.SIZE,
            bg=PANEL, highlightthickness=0, **kw,
        )
        self._draw(0.0, "00:00", "")

    def update_ring(self, fraction: float, time_str: str, sub: str = ""):
        self._draw(fraction, time_str, sub)

    def _draw(self, fraction: float, time_str: str, sub: str):
        self.delete("all")
        cx = cy = self.SIZE // 2
        pad, w = 14, 20

        self._arc(pad, w, BORDER, 359.99)
        if fraction > 0.001:
            self._arc(pad, w, DARK, fraction * 359.99)
        if 0.001 < fraction < 0.999:
            angle = math.radians(90 - fraction * 360)
            r = (self.SIZE - pad * 2) / 2
            dx = cx + r * math.cos(angle)
            dy = cy - r * math.sin(angle)
            self.create_oval(dx - w // 2, dy - w // 2,
                             dx + w // 2, dy + w // 2,
                             fill=DARK2, outline="")

        self.create_text(cx, cy - (14 if sub else 0),
                         text=time_str, fill=TEXT,
                         font=("Helvetica", 42, "bold"))
        if sub:
            self.create_text(cx, cy + 28, text=sub,
                             fill=MUTED, font=("Helvetica", 13))

    def _arc(self, pad, width, color, extent):
        self.create_arc(
            pad, pad, self.SIZE - pad, self.SIZE - pad,
            start=90, extent=-extent,
            style="arc", outline=color, width=width,
        )


# ── Helpers ────────────────────────────────────────────────────────────────────
def mk_card(parent, bg=PANEL, border=BORDER, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=bg, corner_radius=18,
                        border_width=1, border_color=border, **kw)


def mk_label(parent, text, size=13, weight="normal", color=TEXT, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=ctk.CTkFont(size=size, weight=weight), **kw)


def mk_btn(parent, text, command, width=120, height=40,
           primary=False, danger=False, **kw) -> ctk.CTkButton:
    if primary:
        fg, hover, tc = DARK, DARK2, BG
    elif danger:
        fg, hover, tc = CARD, CARD, DANGER
    else:
        fg, hover, tc = CARD, BORDER, MUTED
    return ctk.CTkButton(
        parent, text=text, command=command,
        width=width, height=height, corner_radius=12,
        fg_color=fg, hover_color=hover, text_color=tc,
        border_width=1, border_color=BORDER,
        font=ctk.CTkFont(size=13, weight="bold"), **kw,
    )


def sec_title(parent, text):
    mk_label(parent, text.upper(), size=10, color=MUTED).pack(
        anchor="w", padx=16, pady=(14, 6))


def seg_btn(parent, values, variable=None, command=None) -> ctk.CTkSegmentedButton:
    # selected_color=BORDER so TEXT (dark) stays readable on both states
    return ctk.CTkSegmentedButton(
        parent, values=values, variable=variable, command=command,
        selected_color=BORDER, selected_hover_color=DARK,
        unselected_color=CARD, unselected_hover_color=BORDER,
        text_color=TEXT,
        text_color_disabled=MUTED,
        font=ctk.CTkFont(size=12),
    )


def progress_bar(parent, color=DARK) -> ctk.CTkProgressBar:
    return ctk.CTkProgressBar(parent, height=6, corner_radius=3,
                               progress_color=color, fg_color=BORDER)


# ── Main Application ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Pomodoro")
        self.geometry("1120x740")
        self.minsize(920, 660)
        self.configure(fg_color=BG)
        self.bind("<Control-q>", lambda _: self.destroy())

        initialize_db()

        self.running        = False
        self.paused         = False
        self.seconds_left   = 0
        self.total_seconds  = 0
        self.elapsed_secs   = 0
        self.intention_text = ""
        self.selected_skill = "TECH"
        self.timer_mode     = "Pomodoro"

        self._views: dict = {}
        self._active_view = ""

        self._build_ui()
        self._nav("timer")
        self.after(100, self._refresh_sidebar)

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=196, fg_color=PANEL,
                                    corner_radius=0, border_width=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        mk_label(self.sidebar, "Pomodoro", size=18, weight="bold",
                 color=DARK).pack(pady=(28, 30), padx=20, anchor="w")

        self._nav_btns: dict = {}
        for text, key in [
            ("Timer",        "timer"),
            ("Skilltree",    "skills"),
            ("Achievements", "achievements"),
            ("Leaderboard",  "leaderboard"),
        ]:
            b = ctk.CTkButton(
                self.sidebar, text=text, anchor="w",
                height=42, corner_radius=10,
                fg_color="transparent", hover_color=BORDER,
                text_color=MUTED, border_width=0,
                font=ctk.CTkFont(size=14),
                command=lambda k=key: self._nav(k),
            )
            b.pack(padx=10, pady=2, fill="x")
            self._nav_btns[key] = b

        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=14, pady=20)

        ctk.CTkFrame(footer, height=1, fg_color=BORDER).pack(fill="x", pady=(0, 14))

        self._badge_lbl = ctk.CTkLabel(footer, text="")
        self._badge_lbl.pack()

        self._level_lbl = mk_label(footer, "LVL 0", size=15, weight="bold", color=DARK)
        self._level_lbl.pack(pady=(6, 2))

        self._total_lbl = mk_label(footer, "0.0h gesamt", size=12, color=TEXT)
        self._total_lbl.pack(pady=(0, 2))

        self._next_lbl = mk_label(footer, "", size=11, color=MUTED)
        self._next_lbl.pack()

        self._lvl_bar = progress_bar(footer)
        self._lvl_bar.pack(fill="x", pady=(8, 12))
        self._lvl_bar.set(0)

        mk_btn(footer, "Log öffnen", self._open_log,
               width=168, height=32).pack()

        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.pack(side="right", fill="both", expand=True)

    def _nav(self, key: str):
        for k, b in self._nav_btns.items():
            if k == key:
                b.configure(fg_color=BORDER, text_color=TEXT)
            else:
                b.configure(fg_color="transparent", text_color=MUTED)

        if self._active_view and self._active_view in self._views:
            self._views[self._active_view].pack_forget()

        if key not in self._views:
            builders = {
                "timer":        self._build_timer_view,
                "skills":       self._build_skills_view,
                "achievements": self._build_achievements_view,
                "leaderboard":  self._build_leaderboard_view,
            }
            self._views[key] = builders[key]()

        self._views[key].pack(fill="both", expand=True)
        self._active_view = key

        if key == "skills":         self._refresh_skills()
        elif key == "achievements": self._refresh_achievements()
        elif key == "leaderboard":  self._refresh_leaderboard()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    def _refresh_sidebar(self):
        total = calculate_total_time()
        level = calculate_level(total)
        self._level_lbl.configure(text=f"LVL {level}")
        self._total_lbl.configure(text=f"{total:.1f}h gesamt")

        if level >= len(LEVEL_THRESHOLDS):
            self._lvl_bar.set(1)
            self._next_lbl.configure(text="MAX LEVEL ⭐")
        else:
            lower = LEVEL_THRESHOLDS[level - 1] if level > 0 else 0
            upper = LEVEL_THRESHOLDS[level]
            frac  = max(0.0, min((total - lower) / (upper - lower), 1.0))
            self._lvl_bar.set(frac)
            self._next_lbl.configure(
                text=f"{format_hours(upper - total)} bis LVL {level + 1}")

        badge_path = os.path.join(BADGE_DIR, f"p{level}.png")
        if os.path.exists(badge_path):
            try:
                img = Image.open(badge_path).resize((60, 60), Image.Resampling.LANCZOS)
                self._badge_img = ctk.CTkImage(img, size=(60, 60))
                self._badge_lbl.configure(image=self._badge_img, text="")
            except Exception:
                pass

    # ── Timer View ────────────────────────────────────────────────────────────
    def _build_timer_view(self) -> ctk.CTkFrame:
        view = ctk.CTkFrame(self.content, fg_color=BG)

        hdr = ctk.CTkFrame(view, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(22, 0))
        mk_label(hdr, "Timer", size=22, weight="bold", color=DARK).pack(side="left")

        self.mode_seg = seg_btn(hdr, ["Pomodoro", "Open Timer"],
                                command=self._on_mode_change)
        self.mode_seg.set("Pomodoro")
        self.mode_seg.pack(side="right")

        body = ctk.CTkFrame(view, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=18)

        # ── Left ─────────────────────────────────────────────────────────────
        left = mk_card(body)
        left.pack(side="left", fill="both", expand=True, padx=(8, 10))

        self.ring = RingTimer(left)
        self.ring.pack(pady=(28, 8))

        # Duration row (Pomodoro only)
        self._dur_row = ctk.CTkFrame(left, fg_color="transparent")
        self._dur_row.pack()
        mk_label(self._dur_row, "Minuten:", color=MUTED).pack(side="left", padx=(0, 8))
        self.dur_entry = ctk.CTkEntry(
            self._dur_row, width=72, height=36, placeholder_text="25",
            corner_radius=10, fg_color=CARD, border_color=BORDER,
            text_color=TEXT, placeholder_text_color=DIM,
        )
        self.dur_entry.pack(side="left")

        # Preset buttons (Pomodoro only)
        self._pre_row = ctk.CTkFrame(left, fg_color="transparent")
        self._pre_row.pack(pady=(8, 16))
        for m in (15, 25, 45, 60):
            ctk.CTkButton(
                self._pre_row, text=f"{m}m", width=52, height=28, corner_radius=8,
                fg_color=CARD, hover_color=BORDER, text_color=MUTED,
                border_width=1, border_color=BORDER, font=ctk.CTkFont(size=12),
                command=lambda v=m: self._set_dur(v),
            ).pack(side="left", padx=3)

        self._brow = ctk.CTkFrame(left, fg_color="transparent")
        self._brow.pack(pady=(0, 28))

        self.start_btn = ctk.CTkButton(
            self._brow, text="▶  Start", width=120, height=46, corner_radius=14,
            fg_color=DARK, hover_color=DARK2, text_color=BG,
            border_width=0, font=ctk.CTkFont(size=15, weight="bold"),
            command=self._on_start,
        )
        self.start_btn.pack(side="left", padx=5)

        self.pause_btn = mk_btn(self._brow, "⏸  Pause", self._on_pause,
                                width=100, height=46, state="disabled")
        self.pause_btn.pack(side="left", padx=5)

        self.stop_btn = mk_btn(self._brow, "⏹  Stop", self._on_stop,
                               width=100, height=46, danger=True, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        # ── Right ─────────────────────────────────────────────────────────────
        right = ctk.CTkFrame(body, fg_color="transparent", width=290)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        sk_card = mk_card(right)
        sk_card.pack(fill="x", pady=(0, 10))
        sec_title(sk_card, "Skill")

        g = ctk.CTkFrame(sk_card, fg_color="transparent")
        g.pack(padx=12, pady=(0, 14), fill="x")
        self._skill_btns: dict = {}
        for i, sk in enumerate(SKILLS):
            emoji = SKILL_EMOJIS.get(sk, "")
            b = ctk.CTkButton(
                g, text=f"{emoji} {sk}", width=82, height=32, corner_radius=8,
                fg_color=CARD, hover_color=BORDER, text_color=MUTED,
                border_width=1, border_color=BORDER, font=ctk.CTkFont(size=12),
                command=lambda s=sk: self._pick_skill(s),
            )
            b.grid(row=i // 3, column=i % 3, padx=3, pady=3, sticky="ew")
            g.columnconfigure(i % 3, weight=1)
            self._skill_btns[sk] = b
        self._pick_skill("TECH")

        int_card = mk_card(right)
        int_card.pack(fill="x", pady=(0, 10))
        sec_title(int_card, "Intention")
        self.intention_entry = ctk.CTkEntry(
            int_card, height=38, placeholder_text="",
            corner_radius=10, fg_color=CARD, border_color=BORDER,
            text_color=TEXT, placeholder_text_color=DIM,
            font=ctk.CTkFont(size=13),
        )
        self.intention_entry.pack(fill="x", padx=12, pady=(0, 14))

        notes_card = mk_card(right)
        notes_card.pack(fill="both", expand=True)
        sec_title(notes_card, "Notizen")
        self.notes_box = ctk.CTkTextbox(
            notes_card, corner_radius=10, fg_color=CARD,
            text_color=TEXT, font=ctk.CTkFont(size=13),
            border_color=BORDER, border_width=1,
        )
        self.notes_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        note_btns = ctk.CTkFrame(notes_card, fg_color="transparent")
        note_btns.pack(fill="x", padx=12, pady=(0, 12))
        mk_btn(note_btns, "Speichern", self._save_note,
               width=90, height=28).pack(side="left", padx=(0, 6))
        mk_btn(note_btns, "Laden", self._load_notes_dialog,
               width=90, height=28).pack(side="left")

        return view

    def _set_dur(self, m: int):
        self.dur_entry.delete(0, "end")
        self.dur_entry.insert(0, str(m))

    def _pick_skill(self, skill: str):
        self.selected_skill = skill
        for sk, b in self._skill_btns.items():
            if sk == skill:
                b.configure(fg_color=DARK, text_color=BG, border_color=DARK)
            else:
                b.configure(fg_color=CARD, text_color=MUTED, border_color=BORDER)

    def _on_mode_change(self, mode: str):
        self.timer_mode = mode
        self._reset_timer()
        if mode == "Pomodoro":
            self._dur_row.pack(after=self.ring)
            self._pre_row.pack(after=self._dur_row, pady=(8, 16))
            self._brow.pack_configure(pady=(0, 28))
        else:
            self._dur_row.pack_forget()
            self._pre_row.pack_forget()
            self._brow.pack_configure(pady=(24, 28))

    # ── Notes ─────────────────────────────────────────────────────────────────
    def _save_note(self):
        content = self.notes_box.get("1.0", "end").strip()
        if not content:
            return
        title = f"{self.selected_skill} · {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        save_note(title, content)
        self.notes_box.configure(border_color=SUCCESS)
        self.after(900, lambda: self.notes_box.configure(border_color=BORDER))

    def _load_notes_dialog(self):
        notes = get_notes()
        if not notes:
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Gespeicherte Notizen")
        dlg.geometry("500x440")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()

        mk_label(dlg, "Gespeicherte Notizen", size=16, weight="bold",
                 color=DARK).pack(padx=24, pady=(20, 10), anchor="w")

        scroll = ctk.CTkScrollableFrame(dlg, fg_color=BG,
                                        scrollbar_button_color=BORDER,
                                        scrollbar_button_hover_color=DARK)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        for _nid, _date, _time, title, content in notes:
            row = mk_card(scroll)
            row.pack(fill="x", pady=4, padx=4)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=14, pady=10)
            mk_label(inner, title, size=12, weight="bold", color=TEXT).pack(anchor="w")
            preview = content[:90] + ("…" if len(content) > 90 else "")
            mk_label(inner, preview, size=11, color=MUTED).pack(anchor="w")

            def _load(c=content, d=dlg):
                self.notes_box.delete("1.0", "end")
                self.notes_box.insert("1.0", c)
                d.destroy()

            mk_btn(inner, "Laden", _load, width=70, height=26).pack(
                anchor="e", pady=(6, 0))

    # ── Timer logic ───────────────────────────────────────────────────────────
    def _on_start(self):
        if self.running:
            return
        intention = self.intention_entry.get().strip()
        if not intention:
            self.intention_entry.configure(border_color=DANGER)
            self.after(1800, lambda: self.intention_entry.configure(border_color=BORDER))
            return
        self.intention_text = intention

        if self.timer_mode == "Pomodoro":
            try:
                mins = float(self.dur_entry.get() or "25")
                if mins <= 0:
                    raise ValueError
            except ValueError:
                self.dur_entry.configure(border_color=DANGER)
                self.after(1800, lambda: self.dur_entry.configure(border_color=BORDER))
                return
            self.total_seconds = int(mins * 60)
            self.seconds_left  = self.total_seconds
            self.running = True
            self.paused  = False
            self._btns_running()
            self._tick_pomodoro()
        else:
            self.elapsed_secs = 0
            self.running = True
            self.paused  = False
            self._btns_running()
            self._tick_open()

    def _on_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        self.pause_btn.configure(text="▶  Weiter" if self.paused else "⏸  Pause")
        if not self.paused:
            if self.timer_mode == "Pomodoro":
                self._tick_pomodoro()
            else:
                self._tick_open()

    def _on_stop(self):
        if not self.running:
            return
        self.running = False
        elapsed = (
            (self.total_seconds - self.seconds_left) / 60
            if self.timer_mode == "Pomodoro"
            else self.elapsed_secs / 60
        )
        self._btns_idle()
        if elapsed >= 0.5:
            self._result_dialog(elapsed)
        else:
            self._reset_timer()

    def _tick_pomodoro(self):
        if not self.running or self.paused:
            return
        if self.seconds_left > 0:
            m, s  = divmod(self.seconds_left, 60)
            frac  = (self.total_seconds - self.seconds_left) / self.total_seconds
            self.ring.update_ring(
                frac, f"{m:02d}:{s:02d}",
                f"{self.total_seconds // 60} min · {self.selected_skill}",
            )
            self.seconds_left -= 1
            self.after(1000, self._tick_pomodoro)
        else:
            self.ring.update_ring(1.0, "00:00", "Fertig! 🎉")
            self.running = False
            self._btns_idle()
            threading.Thread(target=play_sound, daemon=True).start()
            self._result_dialog(self.total_seconds / 60)

    def _tick_open(self):
        if not self.running or self.paused:
            return
        m, s = divmod(self.elapsed_secs, 60)
        h, m = divmod(m, 60)
        ts   = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        self.ring.update_ring(0, ts, self.selected_skill)
        self.elapsed_secs += 1
        self.after(1000, self._tick_open)

    def _btns_running(self):
        self.start_btn.configure(state="disabled", fg_color=CARD, text_color=DIM,
                                  border_color=BORDER, border_width=1)
        self.pause_btn.configure(state="normal", text_color=TEXT, text="⏸  Pause")
        self.stop_btn.configure(state="normal")

    def _btns_idle(self):
        self.start_btn.configure(state="normal", fg_color=DARK, text_color=BG,
                                  border_width=0)
        self.pause_btn.configure(state="disabled", text_color=MUTED, text="⏸  Pause")
        self.stop_btn.configure(state="disabled")

    def _reset_timer(self):
        self.running = False
        self.paused  = False
        self.ring.update_ring(0, "00:00")
        self._btns_idle()

    # ── Result dialog ─────────────────────────────────────────────────────────
    def _result_dialog(self, duration: float):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Session beendet")
        dlg.geometry("420x290")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()

        mk_label(dlg, "Session beendet 🎉", size=20, weight="bold",
                 color=DARK).pack(pady=(28, 4))
        mk_label(dlg, f"{duration:.0f} min · {self.selected_skill}",
                 color=MUTED).pack()
        ctk.CTkFrame(dlg, height=1, fg_color=BORDER).pack(fill="x", padx=24, pady=18)
        mk_label(dlg, "Was hast du erreicht?", color=TEXT).pack(anchor="w", padx=24)

        res = ctk.CTkEntry(
            dlg, height=40, placeholder_text="Ergebnis …",
            corner_radius=10, fg_color=CARD, border_color=BORDER,
            text_color=TEXT, placeholder_text_color=DIM,
            font=ctk.CTkFont(size=14),
        )
        res.pack(fill="x", padx=24, pady=8)
        res.focus()

        def save():
            result = res.get().strip()
            if not result:
                res.configure(border_color=DANGER)
                return
            old_lvl = calculate_level(calculate_total_time())
            save_session(duration, self.intention_text, result,
                         skill=self.selected_skill)
            new_lvl = calculate_level(calculate_total_time())
            dlg.destroy()
            self._reset_timer()
            self.intention_entry.delete(0, "end")
            self._refresh_sidebar()
            if new_lvl > old_lvl:
                self._levelup_dialog(new_lvl)

        res.bind("<Return>", lambda _: save())
        ctk.CTkButton(
            dlg, text="Speichern", height=44, corner_radius=12,
            fg_color=DARK, hover_color=DARK2, text_color=BG,
            font=ctk.CTkFont(size=14, weight="bold"), command=save,
        ).pack(fill="x", padx=24, pady=(4, 28))

    def _levelup_dialog(self, level: int):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Level Up!")
        dlg.geometry("360x230")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()
        mk_label(dlg, "⬆  LEVEL UP!", size=28, weight="bold", color=DARK).pack(
            pady=(36, 8))
        mk_label(dlg, f"Du bist jetzt Level {level}!", size=16, color=TEXT).pack()
        mk_btn(dlg, "🎉  Weiter", dlg.destroy,
               width=180, height=44, primary=True).pack(pady=28)

    def _skill_levelup_dialog(self, skill: str, level: int):
        emoji = SKILL_EMOJIS.get(skill, "")
        dlg = ctk.CTkToplevel(self)
        dlg.title("Skill Level Up!")
        dlg.geometry("360x230")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()
        mk_label(dlg, f"⬆  {emoji} {skill} LVL {level}!", size=22,
                 weight="bold", color=DARK).pack(pady=(36, 8))
        mk_label(dlg, "Skill aufgestiegen!", size=14, color=TEXT).pack()
        mk_btn(dlg, "💪  Let's go!", dlg.destroy,
               width=180, height=44, primary=True).pack(pady=28)

    # ── Open log ──────────────────────────────────────────────────────────────
    def _open_log(self):
        if not os.path.exists(DB_FILE):
            return
        try:
            plat = platform.system()
            if plat == "Darwin":
                subprocess.call(("open", DB_FILE))
            elif plat == "Windows":
                os.startfile(DB_FILE)
            else:
                subprocess.call(("xdg-open", DB_FILE))
        except Exception:
            pass

    # ── Collect animation ─────────────────────────────────────────────────────
    def _animate_collect(self, card: ctk.CTkFrame):
        orig = card.cget("fg_color")
        flashes = [DARK, BORDER, DARK, BORDER, orig]
        for i, col in enumerate(flashes):
            self.after(i * 110, lambda c=col: card.configure(fg_color=c))

    # ── Skills View ───────────────────────────────────────────────────────────
    def _build_skills_view(self) -> ctk.CTkFrame:
        view = ctk.CTkFrame(self.content, fg_color=BG)
        mk_label(view, "Skilltree", size=22, weight="bold",
                 color=DARK).pack(anchor="w", padx=28, pady=(24, 14))
        self._sk_scroll = ctk.CTkScrollableFrame(
            view, fg_color=BG,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=DARK,
        )
        self._sk_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        return view

    def _refresh_skills(self):
        if not hasattr(self, "_sk_scroll"):
            return
        for w in self._sk_scroll.winfo_children():
            w.destroy()

        skill_hours: dict = {s: 0.0 for s in SKILLS}
        total_all = 0.0
        last      = None
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute(
                "SELECT skill, SUM(duration) FROM pomodoro_session GROUP BY skill")
            for sk, mins in cur.fetchall():
                if sk in skill_hours and mins:
                    skill_hours[sk] = mins / 60.0
            cur.execute("SELECT SUM(duration) FROM pomodoro_session")
            r = cur.fetchone()[0] or 0
            total_all = r / 60.0
            cur.execute(
                "SELECT duration, skill FROM pomodoro_session "
                "ORDER BY sessions DESC LIMIT 1")
            last = cur.fetchone()
            conn.close()
        except Exception:
            pass

        confirmed = get_skill_confirmed_levels()

        def lvl_prog(hours):
            for i, t in enumerate(SKILL_THRESHOLDS):
                if hours < t:
                    lo = 0 if i == 0 else SKILL_THRESHOLDS[i - 1]
                    return i, (hours - lo) / (t - lo), t
            return len(SKILL_THRESHOLDS), 1.0, SKILL_THRESHOLDS[-1]

        for skill, hours in sorted(skill_hours.items(),
                                    key=lambda x: x[1], reverse=True):
            lvl, frac, next_t = lvl_prog(hours)
            emoji    = SKILL_EMOJIS.get(skill, "")
            at_cap   = lvl >= len(SKILL_THRESHOLDS)
            conf_lvl = confirmed.get(skill, 0)
            # Show collect button for the next uncollected level only
            next_to_collect = conf_lvl + 1
            has_uncollected = lvl >= next_to_collect and not at_cap

            card_bg, card_border = _skill_card_color(lvl)
            c = mk_card(self._sk_scroll, bg=card_bg, border=card_border)
            c.pack(fill="x", pady=5, padx=6)
            inner = ctk.CTkFrame(c, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=14)

            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            mk_label(top, f"{emoji}  {skill}", size=15, weight="bold",
                     color=TEXT).pack(side="left")
            cap_label = "MAX ⭐" if at_cap else f"LVL {lvl}"
            lvl_col   = MUTED if (not has_uncollected or at_cap) else DARK
            mk_label(top, cap_label, size=14, weight="bold",
                     color=lvl_col).pack(side="right")

            bar = progress_bar(inner, color=DARK if not at_cap else MUTED)
            bar.pack(fill="x", pady=(8, 4))
            bar.set(1.0 if at_cap else max(0.0, frac))

            stat = ctk.CTkFrame(inner, fg_color="transparent")
            stat.pack(fill="x")
            mk_label(stat, f"{hours:.1f}h", color=MUTED, size=12).pack(side="left")
            if not at_cap:
                mk_label(stat, f"→ {next_t}h für LVL {lvl + 1}",
                         color=MUTED, size=12).pack(side="right")

            if has_uncollected:
                def _collect(sk=skill, lv=next_to_collect, card=c):
                    self._animate_collect(card)
                    confirm_skill_level(sk, lv)
                    self.after(600, self._refresh_skills)
                    self.after(650, lambda s=sk, l=lv: self._skill_levelup_dialog(s, l))

                ctk.CTkButton(
                    inner,
                    text=f"⬆  LVL {next_to_collect} einsammeln!",
                    height=36, corner_radius=10,
                    fg_color=DARK, hover_color=DARK2, text_color=BG,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    command=_collect,
                ).pack(fill="x", pady=(10, 0))

        ctk.CTkFrame(self._sk_scroll, height=1, fg_color=BORDER).pack(
            fill="x", padx=6, pady=14)
        mk_label(self._sk_scroll, f"Gesamt: {total_all:.1f} Stunden",
                 color=MUTED, size=13).pack(pady=2)
        if last:
            dur_min, sk = last
            emoji = SKILL_EMOJIS.get(sk, "")
            mk_label(self._sk_scroll,
                     f"Letzte Session: {emoji}  +{dur_min:.0f} min in {sk}",
                     color=DARK, size=13).pack(pady=4)

    # ── Achievements View ──────────────────────────────────────────────────────
    def _build_achievements_view(self) -> ctk.CTkFrame:
        view = ctk.CTkFrame(self.content, fg_color=BG)
        mk_label(view, "Achievements", size=22, weight="bold",
                 color=DARK).pack(anchor="w", padx=28, pady=(24, 14))
        self._ach_scroll = ctk.CTkScrollableFrame(
            view, fg_color=BG,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=DARK,
        )
        self._ach_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        return view

    def _refresh_achievements(self):
        if not hasattr(self, "_ach_scroll"):
            return
        for w in self._ach_scroll.winfo_children():
            w.destroy()

        total_h = calculate_total_time()
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("SELECT SUM(duration) FROM pomodoro_session")
            total_min = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM pomodoro_session")
            sessions = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM pomodoro_session WHERE duration > 29.9")
            over30 = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM pomodoro_session WHERE duration > 49.9")
            over50 = cur.fetchone()[0] or 0
            conn.close()
        except Exception:
            total_min = sessions = over30 = over50 = 0

        collected_ach = get_achievements_collected()
        lvl = calculate_level(total_h)

        # ── Badge gallery ──────────────────────────────────────────────────────
        if lvl > 0:
            bc = mk_card(self._ach_scroll)
            bc.pack(fill="x", pady=5, padx=6)
            mk_label(bc, "Freigeschaltete Badges", size=14, weight="bold",
                     color=TEXT).pack(anchor="w", padx=16, pady=(14, 8))

            badge_frame = ctk.CTkFrame(bc, fg_color="transparent")
            badge_frame.pack(padx=14, pady=(0, 14), fill="x")
            self._ach_badge_imgs = []
            col = 0
            row_f = None
            for i in range(min(lvl + 1, 20)):
                p = os.path.join(BADGE_DIR, f"p{i}.png")
                if not os.path.exists(p):
                    continue
                try:
                    if col % 5 == 0:
                        row_f = ctk.CTkFrame(badge_frame, fg_color="transparent")
                        row_f.pack(fill="x", pady=2)
                    img = Image.open(p).resize((56, 56), Image.Resampling.LANCZOS)
                    ci  = ctk.CTkImage(img, size=(56, 56))
                    self._ach_badge_imgs.append(ci)

                    def _on_badge(badge_i=i):
                        date_s = get_badge_unlock_date(badge_i)
                        d = ctk.CTkToplevel(self)
                        d.title(f"Badge {badge_i}")
                        d.geometry("320x190")
                        d.configure(fg_color=PANEL)
                        d.grab_set()
                        d.lift()
                        mk_label(d, f"Badge LVL {badge_i}", size=18,
                                 weight="bold", color=DARK).pack(pady=(28, 8))
                        date_text = (f"Freigeschaltet am {date_s}"
                                     if date_s else "Datum unbekannt")
                        mk_label(d, date_text, size=13, color=MUTED).pack()
                        mk_btn(d, "Schließen", d.destroy,
                               width=130, height=36, primary=True).pack(pady=20)

                    ctk.CTkButton(
                        row_f, image=ci, text="", width=64, height=64,
                        corner_radius=12, fg_color=CARD, hover_color=BORDER,
                        border_width=1, border_color=BORDER, command=_on_badge,
                    ).pack(side="left", padx=4)
                    col += 1
                except Exception:
                    pass

        # ── Stat bars ──────────────────────────────────────────────────────────
        stats = [
            ("Total Stunden",     "hours",    total_h,   500,   "h"),
            ("Total Minuten",     "minutes",  total_min, 50000, " min"),
            ("Sessions",          "sessions", sessions,  2000,  ""),
            ("Sessions > 30 min", "over30",   over30,    1000,  ""),
            ("Sessions > 50 min", "over50",   over50,    500,   ""),
        ]
        for name, key, val, max_val, unit in stats:
            frac = min(val / max_val, 1.0) if max_val else 0
            is_full = frac >= 1.0
            already_done = key in collected_ach

            c = mk_card(self._ach_scroll)
            c.pack(fill="x", pady=5, padx=6)
            inner = ctk.CTkFrame(c, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=14)

            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            mk_label(top, name, size=14, weight="bold", color=TEXT).pack(side="left")
            val_s = (f"{val:.1f}" if isinstance(val, float) and val != int(val)
                     else str(int(val)))
            mk_label(top, f"{val_s}{unit} / {int(max_val)}{unit}",
                     color=MUTED, size=13).pack(side="right")

            bar = progress_bar(inner, color=SUCCESS)
            bar.pack(fill="x", pady=(8, 0))
            bar.set(frac)

            if is_full and not already_done:
                def _collect_ach(k=key, card=c):
                    mark_achievement_collected(k)
                    self._animate_collect(card)
                    self.after(600, self._refresh_achievements)

                ctk.CTkButton(
                    inner, text="🏆  Einsammeln!",
                    height=34, corner_radius=10,
                    fg_color=DARK, hover_color=DARK2, text_color=BG,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    command=_collect_ach,
                ).pack(fill="x", pady=(10, 0))
            elif is_full and already_done:
                mk_label(inner, "✓ Eingesammelt", size=12,
                         color=SUCCESS).pack(anchor="e", pady=(6, 0))

    # ── Leaderboard View ──────────────────────────────────────────────────────
    def _build_leaderboard_view(self) -> ctk.CTkFrame:
        view = ctk.CTkFrame(self.content, fg_color=BG)
        mk_label(view, "Leaderboard", size=22, weight="bold",
                 color=DARK).pack(anchor="w", padx=28, pady=(24, 12))

        f = ctk.CTkFrame(view, fg_color="transparent")
        f.pack(padx=28, pady=(0, 8), fill="x")
        self._lb_period = ctk.StringVar(value="All Time")
        seg_btn(
            f,
            ["Today", "This Week", "This Month", "This Year", "All Time"],
            variable=self._lb_period,
            command=lambda _: self._refresh_leaderboard(),
        ).pack(side="left")

        self._lb_sum = mk_label(view, "", color=MUTED, size=13)
        self._lb_sum.pack(anchor="w", padx=28, pady=(0, 6))

        self._lb_scroll = ctk.CTkScrollableFrame(
            view, fg_color=BG,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=DARK,
        )
        self._lb_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        return view

    def _refresh_leaderboard(self, shown: int = 10):
        if not hasattr(self, "_lb_scroll"):
            return
        for w in self._lb_scroll.winfo_children():
            w.destroy()

        period = self._lb_period.get() if hasattr(self, "_lb_period") else "All Time"
        now = datetime.now()

        if period == "Today":
            date_filter = f"AND date = '{now.strftime('%Y-%m-%d')}'"
        elif period == "This Month":
            date_filter = f"AND date LIKE '{now.strftime('%Y-%m')}%'"
        elif period == "This Year":
            date_filter = f"AND date LIKE '{now.strftime('%Y')}%'"
        else:
            date_filter = ""

        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute(
                f"SELECT duration, date, time, skill, intention "
                f"FROM pomodoro_session {date_filter}")
            rows = cur.fetchall()
            conn.close()
        except Exception:
            rows = []

        filtered = []
        for dur, date_s, time_s, skill, intention in rows:
            try:
                dur = float(dur)
                dt  = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            if period == "This Week":
                iso = dt.isocalendar()
                if not (iso[1] == now.isocalendar()[1] and dt.year == now.year):
                    continue
            filtered.append((dur, dt, skill or "", intention or ""))

        total = sum(d for d, *_ in filtered)
        self._lb_sum.configure(
            text=f"Σ {total:.0f} Minuten · {len(filtered)} Sessions")

        filtered.sort(key=lambda x: x[0], reverse=True)
        medals  = ["🥇", "🥈", "🥉"]
        mcolors = ["#92700a", "#555555", "#7a4500"]

        for i, (dur, dt, skill, intention) in enumerate(filtered[:shown]):
            c = mk_card(self._lb_scroll)
            c.pack(fill="x", pady=4, padx=6)
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=12)

            rank_s = medals[i]  if i < 3 else f"# {i + 1}"
            rank_c = mcolors[i] if i < 3 else MUTED
            mk_label(row, rank_s, size=17, color=rank_c, width=34).pack(side="left")
            mk_label(row, f"{dur:.0f} min", size=16, weight="bold",
                     color=rank_c if i < 3 else TEXT).pack(side="left", padx=(0, 14))

            det = ctk.CTkFrame(row, fg_color="transparent")
            det.pack(side="left", fill="x", expand=True)
            mk_label(det, intention, size=12, color=MUTED).pack(anchor="w")
            mk_label(det, f"{dt.strftime('%d.%m.%Y %H:%M')}  ·  {skill}",
                     size=11, color=DIM).pack(anchor="w")

        if not filtered:
            mk_label(self._lb_scroll,
                     "Keine Einträge für diesen Zeitraum.",
                     color=MUTED, size=14).pack(pady=40)
        elif shown < len(filtered):
            remaining = len(filtered) - shown
            mk_btn(
                self._lb_scroll,
                f"Mehr laden  ({remaining} weitere)",
                command=lambda: self._refresh_leaderboard(shown + 10),
                width=220, height=36,
            ).pack(pady=14)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
