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
from datetime import datetime, date, timedelta
from PIL import Image

from config import (
    DB_FILE, BADGE_DIR, LEVEL_THRESHOLDS, SKILL_THRESHOLDS, STAT_THRESHOLDS,
)
from data_manager import (
    calculate_total_time, save_session, initialize_db,
    save_note, get_notes, delete_note, rename_note,
    get_skill_confirmed_levels, confirm_skill_level,
    get_achievements_collected, mark_achievement_collected,
    get_badge_unlock_date,
    get_user_skills, add_user_skill, delete_user_skill,
    get_heatmap_data,
    get_stat_confirmed_levels, confirm_stat_level, get_chart_data,
    get_first_session_date,
)
from utils import calculate_level, format_hours
from audio_manager import play_sound, play_main_levelup, play_skill_levelup, play_stat_levelup

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

# (bg, border, text)  — one entry per level 0-15
_SKILL_CARD_PALETTE = [
    ("#fffbeb", "#d4b85a", DARK),   # 0  — Creme
    ("#fef9c3", "#ca8a04", DARK),   # 1
    ("#fef3c7", "#d97706", DARK),   # 2
    ("#fde68a", "#d97706", DARK),   # 3  — Gelb
    ("#fcd34d", "#b45309", DARK),   # 4
    ("#fbbf24", "#92400e", DARK),   # 5
    ("#fb923c", "#78350f", DARK),   # 6  — Orange
    ("#f97316", "#7c2d12", DARK),   # 7
    ("#ea580c", "#7c2d12", DARK),   # 8
    ("#fecdd3", "#f9a8b4", DARK),   # 9  — Rosa/Lachs
    ("#fda4af", "#f43f5e", DARK),   # 10
    ("#fb7185", "#e11d48", DARK),   # 11
    ("#f4a0a8", "#be123c", DARK),   # 12 — Ruby pastell
    ("#e8828e", "#9f1239", DARK),   # 13
    ("#d4606b", "#7f1d1d", "#fff8e7"),  # 14
    ("#c0444f", "#5c0a1c", "#fff8e7"),  # 15 — Prestige
]


def _skill_card_color(lvl: int):
    idx = max(0, min(lvl, len(_SKILL_CARD_PALETTE) - 1))
    return _SKILL_CARD_PALETTE[idx]


def _heatmap_color(minutes: float) -> str:
    if minutes == 0:   return CARD
    if minutes < 30:   return "#fbbf24"
    if minutes < 60:   return "#d97706"
    if minutes < 120:  return "#92400e"
    return DARK


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
    return ctk.CTkSegmentedButton(
        parent, values=values, variable=variable, command=command,
        selected_color=BORDER, selected_hover_color=DARK,
        unselected_color=CARD, unselected_hover_color=BORDER,
        text_color=TEXT, text_color_disabled=MUTED,
        font=ctk.CTkFont(size=12),
    )


def progress_bar(parent, color=DARK) -> ctk.CTkProgressBar:
    return ctk.CTkProgressBar(parent, height=6, corner_radius=3,
                               progress_color=color, fg_color=BORDER)


def icon_btn(parent, icon: str, command, size=14, **kw) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=icon, command=command,
        width=30, height=30, corner_radius=8,
        fg_color="transparent", hover_color=BORDER,
        text_color=MUTED, border_width=0,
        font=ctk.CTkFont(size=size), **kw,
    )


_ARROW_FG       = "#1e1c18"
_ARROW_FG_HOVER = "#5c4300"

def _arrow_btn(parent, direction: str, command,
               bg: str = PANEL, w: int = 32, h: int = 26) -> tk.Canvas:
    """Minimalist 2-stroke arrow button. direction: 'down'=save, 'up'=load."""
    c = tk.Canvas(parent, width=w, height=h,
                  bg=bg, highlightthickness=0)
    cx  = w // 2
    sx  = w / 32
    sy  = h / 26
    ow  = max(3, int(6 * sx))
    kw  = dict(fill=_ARROW_FG, width=max(1, int(2 * min(sx, sy))),
               capstyle="round", joinstyle="round")
    if direction == "down":
        c.create_line(cx, int(5*sy), cx, int(16*sy), **kw)
        c.create_line(cx-ow, int(12*sy), cx, int(20*sy), cx+ow, int(12*sy), **kw)
    else:
        c.create_line(cx-ow, int(14*sy), cx, int(6*sy), cx+ow, int(14*sy), **kw)
        c.create_line(cx, int(10*sy), cx, int(21*sy), **kw)

    def _recolor(col):
        c.itemconfigure("all", fill=col)

    c.bind("<Enter>",    lambda _: _recolor(_ARROW_FG_HOVER))
    c.bind("<Leave>",    lambda _: _recolor(_ARROW_FG))
    c.bind("<Button-1>", lambda _: command())
    return c


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
        self._skill_edit_mode = False

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

        # Header with settings gear
        hdr = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        hdr.pack(fill="x", padx=(20, 10), pady=(28, 30))
        mk_label(hdr, "Pomodoro", size=18, weight="bold", color=DARK).pack(side="left")
        icon_btn(hdr, "⚙", self._show_settings, size=15).pack(side="right")

        self._nav_btns: dict = {}
        for text, key in [
            ("Timer",         "timer"),
            ("Skilltree",     "skills"),
            ("Achievements",  "achievements"),
            ("Stats",         "stats"),
            ("Leaderboard",   "leaderboard"),
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
                "stats":        self._build_stats_view,
                "leaderboard":  self._build_leaderboard_view,
            }
            self._views[key] = builders[key]()

        self._views[key].pack(fill="both", expand=True)
        self._active_view = key

        if key == "skills":         self._refresh_skills()
        elif key == "achievements": self._refresh_achievements()
        elif key == "stats":        self._refresh_stats()
        elif key == "leaderboard":  self._refresh_leaderboard()

    # ── Settings popup ────────────────────────────────────────────────────────
    def _show_settings(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Einstellungen")
        dlg.geometry("260x130")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()
        mk_label(dlg, "Einstellungen", size=14, weight="bold",
                 color=DARK).pack(padx=20, pady=(18, 12), anchor="w")
        mk_btn(dlg, "Log öffnen", lambda: (self._open_log(), dlg.destroy()),
               width=200, height=36).pack(padx=20)

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

        self._dur_row = ctk.CTkFrame(left, fg_color="transparent")
        self._dur_row.pack()
        mk_label(self._dur_row, "Minuten:", color=MUTED).pack(side="left", padx=(0, 8))
        self.dur_entry = ctk.CTkEntry(
            self._dur_row, width=72, height=36, placeholder_text="25",
            corner_radius=10, fg_color=CARD, border_color=BORDER,
            text_color=TEXT, placeholder_text_color=DIM,
        )
        self.dur_entry.pack(side="left")

        self._brow = ctk.CTkFrame(left, fg_color="transparent")
        self._brow.pack(pady=(16, 28))

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

        # Skill section
        self._sk_card = mk_card(right)
        self._sk_card.pack(fill="x", pady=(0, 10))

        sk_hdr = ctk.CTkFrame(self._sk_card, fg_color="transparent")
        sk_hdr.pack(fill="x", padx=16, pady=(14, 6))
        mk_label(sk_hdr, "SKILL", size=10, color=MUTED).pack(side="left")
        icon_btn(sk_hdr, "✏", self._toggle_skill_edit, size=13).pack(side="right")

        self._sk_grid_frame = ctk.CTkFrame(self._sk_card, fg_color="transparent")
        self._sk_grid_frame.pack(padx=12, pady=(0, 14), fill="x")
        self._skill_btns: dict = {}
        self._build_skill_grid()

        # Intention
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

        # Notes
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
        _arrow_btn(note_btns, "up",   self._load_notes_dialog, bg=PANEL).pack(side="left")
        _arrow_btn(note_btns, "down", self._save_note,         bg=PANEL).pack(side="right")

        return view

    # ── Skill grid (normal + edit mode) ──────────────────────────────────────
    def _build_skill_grid(self):
        for w in self._sk_grid_frame.winfo_children():
            w.destroy()
        self._skill_btns = {}

        skills = get_user_skills()
        if not skills:
            return

        if self._skill_edit_mode:
            # Edit mode: list with × delete buttons + add button
            for name, emoji in skills:
                row = ctk.CTkFrame(self._sk_grid_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkButton(
                    row, text=f"{emoji} {name}", height=30, corner_radius=8,
                    fg_color=CARD, hover_color=BORDER, text_color=MUTED,
                    border_width=1, border_color=BORDER, font=ctk.CTkFont(size=12),
                    command=lambda s=name: self._pick_skill(s),
                ).pack(side="left", fill="x", expand=True)
                ctk.CTkButton(
                    row, text="×", width=30, height=30, corner_radius=8,
                    fg_color="transparent", hover_color=CARD, text_color=DANGER,
                    border_width=0, font=ctk.CTkFont(size=16),
                    command=lambda n=name: self._remove_skill(n),
                ).pack(side="right", padx=(4, 0))

            # Add skill row
            add_row = ctk.CTkFrame(self._sk_grid_frame, fg_color="transparent")
            add_row.pack(fill="x", pady=(6, 0))
            self._new_emoji = ctk.CTkEntry(
                add_row, width=36, height=28, placeholder_text="📌",
                corner_radius=8, fg_color=CARD, border_color=BORDER,
                text_color=TEXT, placeholder_text_color=DIM,
                font=ctk.CTkFont(size=13),
            )
            self._new_emoji.pack(side="left", padx=(0, 4))
            self._new_name = ctk.CTkEntry(
                add_row, height=28, placeholder_text="Skill name",
                corner_radius=8, fg_color=CARD, border_color=BORDER,
                text_color=TEXT, placeholder_text_color=DIM,
                font=ctk.CTkFont(size=12),
            )
            self._new_name.pack(side="left", fill="x", expand=True, padx=(0, 4))
            ctk.CTkButton(
                add_row, text="+", width=28, height=28, corner_radius=8,
                fg_color=DARK, hover_color=DARK2, text_color=BG,
                border_width=0, font=ctk.CTkFont(size=16, weight="bold"),
                command=self._add_skill,
            ).pack(side="right")
        else:
            # Normal mode: 3-col grid
            for i, (name, emoji) in enumerate(skills):
                b = ctk.CTkButton(
                    self._sk_grid_frame,
                    text=f"{emoji} {name}", width=82, height=32, corner_radius=8,
                    fg_color=CARD, hover_color=BORDER, text_color=MUTED,
                    border_width=1, border_color=BORDER, font=ctk.CTkFont(size=12),
                    command=lambda s=name: self._pick_skill(s),
                )
                b.grid(row=i // 3, column=i % 3, padx=3, pady=3, sticky="ew")
                self._sk_grid_frame.columnconfigure(i % 3, weight=1)
                self._skill_btns[name] = b

            # Re-highlight selected skill
            if self.selected_skill in self._skill_btns:
                self._pick_skill(self.selected_skill)
            elif skills:
                self._pick_skill(skills[0][0])

    def _toggle_skill_edit(self):
        self._skill_edit_mode = not self._skill_edit_mode
        self._build_skill_grid()

    def _add_skill(self):
        name  = self._new_name.get().strip()
        emoji = self._new_emoji.get().strip()
        if name:
            add_user_skill(name, emoji or "📌")
            self._build_skill_grid()

    def _remove_skill(self, name: str):
        delete_user_skill(name)
        if self.selected_skill == name:
            skills = get_user_skills()
            self.selected_skill = skills[0][0] if skills else "TECH"
        self._build_skill_grid()

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
            self._brow.pack_configure(pady=(16, 28))
        else:
            self._dur_row.pack_forget()
            self._brow.pack_configure(pady=(28, 28))

    # ── Notes ─────────────────────────────────────────────────────────────────
    def _save_note(self):
        content = self.notes_box.get("1.0", "end").strip()
        if not content:
            self.notes_box.configure(border_color=DANGER)
            self.after(900, lambda: self.notes_box.configure(border_color=BORDER))
            return

        auto_title = f"Note {len(get_notes(limit=10000)) + 1}"

        dlg = ctk.CTkToplevel(self)
        dlg.title("Speichern")
        dlg.geometry("360x156")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()
        dlg.resizable(False, False)

        mk_label(dlg, "Titel", size=12, color=MUTED).pack(
            padx=22, pady=(20, 4), anchor="w")
        entry = ctk.CTkEntry(
            dlg, height=38, fg_color=CARD, border_color=BORDER,
            text_color=TEXT, font=ctk.CTkFont(size=13),
        )
        entry.insert(0, auto_title)
        entry.pack(fill="x", padx=22, pady=(0, 14))
        entry.focus_set()
        entry.select_range(0, "end")

        def _do_save():
            title = entry.get().strip() or auto_title
            save_note(title, content)
            dlg.destroy()
            self.notes_box.configure(border_color=SUCCESS)
            self.after(900, lambda: self.notes_box.configure(border_color=BORDER))

        dlg.bind("<Return>", lambda _: _do_save())
        dlg.bind("<Escape>", lambda _: dlg.destroy())
        mk_btn(dlg, "Speichern", _do_save, height=36, primary=True).pack(
            fill="x", padx=22)

    def _load_notes_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Notizen")
        dlg.geometry("460x520")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()
        dlg.resizable(False, True)
        dlg.bind("<Escape>", lambda _: dlg.destroy())

        notes = get_notes(limit=200)

        if not notes:
            mk_label(dlg, "Noch nichts gespeichert.", size=13,
                     color=MUTED).pack(pady=60)
            return

        scroll = ctk.CTkScrollableFrame(
            dlg, fg_color="transparent",
            scrollbar_button_color=PANEL,
            scrollbar_button_hover_color=PANEL,
            scrollbar_fg_color=PANEL,
        )
        scroll.pack(fill="both", expand=True, padx=10, pady=(0, 14))

        _NOTE_HDR  = "#f6d955"   # slightly darker than CARD for header bar
        _NOTE_HOVER = "#fef3c7"  # card hover colour

        def _build_card(nid, date_s, time_s, title, content):
            # ── Outer row: card (left, expands) + side buttons (right) ──────
            outer = ctk.CTkFrame(scroll, fg_color="transparent")
            outer.pack(fill="x", pady=4, padx=2)

            # Card bg = header colour; content sits in a lighter inset frame
            card = ctk.CTkFrame(
                outer, fg_color=_NOTE_HDR, corner_radius=14,
                border_width=1, border_color=BORDER,
            )
            card.pack(side="left", fill="x", expand=True)

            # ── Title (sits on card's header bg) ─────────────────────────────
            title_lbl = mk_label(card, title, size=13, weight="bold", color=TEXT)
            title_lbl.pack(anchor="w", padx=12, pady=(7, 6))

            # ── Content inset (lighter, rounded) ─────────────────────────────
            body = ctk.CTkFrame(card, fg_color=CARD, corner_radius=10, height=100)
            body.pack(fill="x", padx=12, pady=(0, 12))
            body.pack_propagate(False)
            lines   = content.splitlines()
            preview = "\n".join(lines[:5]) + ("…" if len(lines) > 5 else "")
            prev_lbl = mk_label(body, preview, size=12, color=DIM,
                                wraplength=340, anchor="nw", justify="left")
            prev_lbl.pack(anchor="nw", padx=10, pady=(8, 0))

            # ── Side buttons (outside the card, to the right) ────────────────
            side = ctk.CTkFrame(outer, fg_color="transparent")
            side.pack(side="right", padx=(6, 0))

            def _rename(note_id=nid, lbl=title_lbl):
                rd = ctk.CTkToplevel(dlg)
                rd.title("Umbenennen")
                rd.geometry("340x128")
                rd.configure(fg_color=PANEL)
                rd.grab_set()
                rd.lift()
                rd.resizable(False, False)
                e = ctk.CTkEntry(rd, height=38, fg_color=CARD, border_color=BORDER,
                                 text_color=TEXT, font=ctk.CTkFont(size=13))
                e.insert(0, lbl.cget("text"))
                e.pack(fill="x", padx=20, pady=(20, 12))
                e.focus_set()
                e.select_range(0, "end")
                def _ok():
                    t = e.get().strip()
                    if t:
                        rename_note(note_id, t)
                        lbl.configure(text=t)
                    rd.destroy()
                e.bind("<Return>", lambda _: _ok())
                e.bind("<Escape>", lambda _: rd.destroy())
                mk_btn(rd, "OK", _ok, primary=True, height=34).pack(
                    fill="x", padx=20)

            o_lbl = mk_label(side, "○", size=13, color=MUTED)
            o_lbl.pack(pady=(4, 10))
            o_lbl.bind("<Button-1>", lambda _: _rename())
            o_lbl.bind("<Enter>", lambda _, l=o_lbl: l.configure(text_color=DARK))
            o_lbl.bind("<Leave>", lambda _, l=o_lbl: l.configure(text_color=MUTED))

            x_lbl = mk_label(side, "✕", size=12, color=MUTED)
            x_lbl.pack(pady=(0, 10))
            x_lbl.bind("<Button-1>", lambda _, o=outer, i=nid: (
                delete_note(i), o.destroy()))
            x_lbl.bind("<Enter>", lambda _, l=x_lbl: l.configure(text_color=DARK))
            x_lbl.bind("<Leave>", lambda _, l=x_lbl: l.configure(text_color=MUTED))

            def _load(c=content):
                self.notes_box.delete("1.0", "end")
                self.notes_box.insert("1.0", c)
                dlg.destroy()

            _arrow_btn(side, "up", _load, bg=PANEL, w=18, h=16).pack()

        for nid, date_s, time_s, title, content in notes:
            _build_card(nid, date_s, time_s, title, content)

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
        dlg.title("")
        dlg.geometry("360x200")
        dlg.resizable(False, False)
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()

        mk_label(dlg, f"{duration:.0f} min  ·  {self.selected_skill}",
                 size=15, weight="bold", color=DARK).pack(pady=(22, 2))
        mk_label(dlg, "Was hast du erreicht?", size=12,
                 color=MUTED).pack()

        ctk.CTkFrame(dlg, height=1, fg_color=BORDER).pack(
            fill="x", padx=22, pady=(12, 8))

        res = ctk.CTkEntry(
            dlg, height=36, placeholder_text="Ergebnis …",
            corner_radius=10, fg_color=CARD, border_color=BORDER,
            text_color=TEXT, placeholder_text_color=DIM,
            font=ctk.CTkFont(size=13),
        )
        res.pack(fill="x", padx=22, pady=(0, 14))
        res.focus()

        def _discard():
            dlg.destroy()
            self._reset_timer()

        def _save():
            result = res.get().strip()
            if not result:
                res.configure(border_color=DANGER)
                self.after(1400, lambda: res.configure(border_color=BORDER))
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
                play_main_levelup()
                self._levelup_dialog(new_lvl)

        res.bind("<Return>", lambda _: _save())
        dlg.bind("<Escape>", lambda _: _discard())

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(padx=22)

        ctk.CTkButton(
            btn_row, text="✕", command=_discard,
            width=56, height=48, corner_radius=12,
            fg_color=CARD, hover_color=BORDER, text_color=MUTED,
            border_width=1, border_color=BORDER,
            font=ctk.CTkFont(size=20),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="✓", command=_save,
            width=220, height=48, corner_radius=12,
            fg_color=DARK, hover_color=DARK2, text_color=BG,
            border_width=0,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left")

    def _levelup_dialog(self, level: int):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Level Up!")
        dlg.geometry("360x230")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()
        mk_label(dlg, "✨ ⭐ ✨", size=32, color=DARK).pack(pady=(30, 4))
        mk_label(dlg, f"Level {level} erreicht!", size=18, weight="bold",
                 color=DARK).pack()
        mk_btn(dlg, "✨  Weiter", dlg.destroy,
               width=180, height=44, primary=True).pack(pady=24)

    def _skill_levelup_dialog(self, skill: str, level: int):
        nature = ["🌸", "🌿", "🌱", "⭐", "🌟", "✨", "🍀", "🌈", "💫", "🌺"]
        pick = nature[level % len(nature)]
        skills = {name: emoji for name, emoji in get_user_skills()}
        emoji = skills.get(skill, "")

        dlg = ctk.CTkToplevel(self)
        dlg.title("Skill Level Up!")
        dlg.geometry("340x230")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()
        mk_label(dlg, f"{pick}  {pick}  {pick}", size=30, color=DARK).pack(pady=(26, 4))
        mk_label(dlg, f"{emoji}  {skill}", size=18, weight="bold", color=DARK).pack()
        mk_label(dlg, f"Level {level}!", size=14, color=MUTED).pack(pady=(2, 8))
        mk_btn(dlg, f"{pick}  Super!", dlg.destroy,
               width=160, height=40, primary=True).pack(pady=12)

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
        for i, col in enumerate([DARK, BORDER, DARK, BORDER, orig]):
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

        active = {name: emoji for name, emoji in get_user_skills()}
        skill_hours: dict = {name: 0.0 for name in active}
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
            emoji    = active.get(skill, "")
            at_cap   = lvl >= len(SKILL_THRESHOLDS)
            conf_lvl = confirmed.get(skill, 0)
            next_collect = conf_lvl + 1
            has_uncollected = lvl >= next_collect and not at_cap

            card_bg, card_border, card_text = _skill_card_color(conf_lvl)
            c = mk_card(self._sk_scroll, bg=card_bg, border=card_border)
            c.pack(fill="x", pady=5, padx=6)
            inner = ctk.CTkFrame(c, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=14)

            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            mk_label(top, f"{emoji}  {skill}", size=15, weight="bold",
                     color=card_text).pack(side="left")
            cap_label = "MAX ⭐" if at_cap else f"LVL {lvl}"
            mk_label(top, cap_label, size=14, weight="bold",
                     color=card_text).pack(side="right")

            bar = progress_bar(inner, color=card_text)
            bar.pack(fill="x", pady=(8, 4))
            bar.set(1.0 if at_cap else max(0.0, frac))

            stat = ctk.CTkFrame(inner, fg_color="transparent")
            stat.pack(fill="x")
            mk_label(stat, f"{hours:.1f}h", color=card_text, size=12).pack(side="left")
            if not at_cap:
                mk_label(stat, f"→ {next_t}h für LVL {lvl + 1}",
                         color=card_text, size=12).pack(side="right")

            if has_uncollected:
                def _collect(sk=skill, lv=next_collect, card=c):
                    play_skill_levelup()
                    self._animate_collect(card)
                    confirm_skill_level(sk, lv)
                    self.after(600, self._refresh_skills)
                    self.after(650, lambda s=sk, l=lv: self._skill_levelup_dialog(s, l))

                ctk.CTkButton(
                    inner, text=f"⭐  LVL {next_collect} einsammeln!",
                    height=36, corner_radius=10,
                    fg_color=DARK, hover_color=DARK2, text_color=BG,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    command=_collect,
                ).pack(fill="x", pady=(10, 0))

        ctk.CTkFrame(self._sk_scroll, height=1, fg_color=BORDER).pack(
            fill="x", padx=6, pady=14)
        mk_label(self._sk_scroll, f"Gesamt: {total_all:.1f} Stunden",
                 color=MUTED, size=13).pack(pady=2)

        # ── Level colour legend ───────────────────────────────────────────────
        leg_wrap = ctk.CTkFrame(self._sk_scroll, fg_color="transparent")
        leg_wrap.pack(fill="x", padx=6, pady=(12, 8))
        # number row
        num_row = ctk.CTkFrame(leg_wrap, fg_color="transparent")
        num_row.pack(fill="x")
        for i in range(16):
            lbl = mk_label(num_row, str(i) if i % 3 == 0 else "",
                           size=9, color=MUTED)
            lbl.pack(side="left", expand=True)
        # colour strip
        strip = ctk.CTkFrame(leg_wrap, fg_color="transparent", height=16)
        strip.pack(fill="x")
        strip.pack_propagate(False)
        for col, border, _tc in _SKILL_CARD_PALETTE:
            sq = ctk.CTkFrame(strip, fg_color=col, corner_radius=3,
                              border_width=1, border_color=border, height=16)
            sq.pack(side="left", fill="both", expand=True, padx=1)
        if last:
            dur_min, sk = last
            emoji = active.get(sk, "")
            mk_label(self._sk_scroll,
                     f"Letzte Session: {emoji}  +{dur_min:.0f} min in {sk}",
                     color=DARK, size=13).pack(pady=4)

    # ── Stats View (was Achievements) ─────────────────────────────────────────
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
            cur.execute("SELECT COUNT(*) FROM pomodoro_session WHERE duration > 59.9")
            over60 = cur.fetchone()[0] or 0
            conn.close()
        except Exception:
            total_min = sessions = over30 = over60 = 0

        stat_confirmed = get_stat_confirmed_levels()
        lvl = calculate_level(total_h)

        # ── Badges ────────────────────────────────────────────────────────────
        if lvl > 0:
            bc = mk_card(self._ach_scroll)
            bc.pack(fill="x", pady=5, padx=6)
            mk_label(bc, "Freigeschaltete Badges", size=13, weight="bold",
                     color=TEXT).pack(anchor="w", padx=16, pady=(14, 8))
            badge_frame = ctk.CTkFrame(bc, fg_color="transparent")
            badge_frame.pack(padx=14, pady=(0, 14), fill="x")
            self._ach_badge_imgs = []
            badge_btns = []

            for i in range(min(lvl + 1, 20)):
                p = os.path.join(BADGE_DIR, f"p{i}.png")
                if not os.path.exists(p):
                    continue
                try:
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

                    btn = ctk.CTkButton(
                        badge_frame, image=ci, text="", width=64, height=64,
                        corner_radius=12, fg_color=CARD, hover_color=BORDER,
                        border_width=1, border_color=BORDER, command=_on_badge,
                    )
                    badge_btns.append(btn)
                except Exception:
                    pass

            def _layout_badges(event=None):
                w = badge_frame.winfo_width()
                per_row = max(1, (w - 8) // 72) if w > 10 else 5
                for j, b in enumerate(badge_btns):
                    b.grid(row=j // per_row, column=j % per_row, padx=4, pady=4)

            badge_frame.bind("<Configure>", _layout_badges)
            badge_frame.after(100, _layout_badges)

        # ── Stat level bars ───────────────────────────────────────────────────
        def _lvl_prog_stat(val, thresholds):
            for i, t in enumerate(thresholds):
                if val < t:
                    lo = 0 if i == 0 else thresholds[i - 1]
                    return i, (val - lo) / (t - lo), t
            return len(thresholds), 1.0, thresholds[-1]

        stats = [
            ("Total Stunden",     "hours",    total_h,   STAT_THRESHOLDS["hours"],    "h"),
            ("Total Minuten",     "minutes",  total_min, STAT_THRESHOLDS["minutes"],  " min"),
            ("Sessions",          "sessions", sessions,  STAT_THRESHOLDS["sessions"], ""),
            ("Sessions > 30 min", "over30",   over30,    STAT_THRESHOLDS["over30"],   ""),
            ("Sessions > 60 min", "over60",   over60,    STAT_THRESHOLDS["over60"],   ""),
        ]

        for name, key, val, thresholds, unit in stats:
            lvl_s, frac, next_t = _lvl_prog_stat(val, thresholds)
            at_cap          = lvl_s >= len(thresholds)
            conf_lvl        = stat_confirmed.get(key, 0)
            next_collect    = conf_lvl + 1
            has_uncollected = lvl_s >= next_collect and not at_cap

            c = mk_card(self._ach_scroll)
            c.pack(fill="x", pady=5, padx=6)
            inner = ctk.CTkFrame(c, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=14)

            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            mk_label(top, name, size=14, weight="bold", color=TEXT).pack(side="left")
            cap_label = "MAX ⭐" if at_cap else f"LVL {lvl_s}"
            lvl_col   = DARK if has_uncollected else MUTED
            mk_label(top, cap_label, size=14, weight="bold",
                     color=lvl_col).pack(side="right")

            bar = progress_bar(inner, color=SUCCESS)
            bar.pack(fill="x", pady=(8, 4))
            bar.set(1.0 if at_cap else max(0.0, frac))

            val_row = ctk.CTkFrame(inner, fg_color="transparent")
            val_row.pack(fill="x")
            val_s = (f"{val:.1f}" if isinstance(val, float) and val != int(val)
                     else str(int(val)))
            mk_label(val_row, f"{val_s}{unit}", color=MUTED, size=12).pack(side="left")
            if not at_cap:
                next_s = str(int(next_t)) if next_t == int(next_t) else f"{next_t:.0f}"
                mk_label(val_row, f"→ {next_s}{unit} für LVL {lvl_s + 1}",
                         color=MUTED, size=12).pack(side="right")

            if has_uncollected:
                def _collect_stat(k=key, lv=next_collect, n=name, card=c):
                    play_stat_levelup()
                    confirm_stat_level(k, lv)
                    self._animate_collect(card)
                    self.after(600, self._refresh_achievements)
                    self.after(650, lambda nn=n, ll=lv: self._stat_levelup_dialog(nn, ll))

                ctk.CTkButton(
                    inner, text=f"⭐  LVL {next_collect} einsammeln!",
                    height=36, corner_radius=10,
                    fg_color=DARK, hover_color=DARK2, text_color=BG,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    command=_collect_stat,
                ).pack(fill="x", pady=(10, 0))

    # ── Heatmap ───────────────────────────────────────────────────────────────
    def _draw_heatmap(self, parent):
        CELL, GAP = 11, 2
        STEP = CELL + GAP
        LM, TM = 26, 18

        today_d = date.today()
        past_d  = today_d - timedelta(days=364)
        past_d -= timedelta(days=past_d.weekday())  # snap to Monday

        data = get_heatmap_data()

        # Count columns
        d = past_d
        num_cols = 0
        while d <= today_d:
            d += timedelta(weeks=1)
            num_cols += 1

        canvas_w = LM + num_cols * STEP + CELL + 4
        canvas_h = TM + 7 * STEP + 4

        canvas = tk.Canvas(parent, width=canvas_w, height=canvas_h,
                           bg=PANEL, highlightthickness=0)
        canvas.pack(padx=14, pady=(0, 6))

        # Day labels (Mon/Mi/Fr/So)
        for r, label in enumerate(["Mo", "", "Mi", "", "Fr", "", "So"]):
            if label:
                canvas.create_text(
                    LM - 4, TM + r * STEP + CELL // 2,
                    text=label, anchor="e",
                    fill=MUTED, font=("Helvetica", 7),
                )

        # Draw weeks
        d = past_d
        col = 0
        prev_month = None
        cell_map: dict = {}   # (col, row) → (date_str, minutes)

        while d <= today_d:
            month = d.strftime("%b")
            if month != prev_month:
                canvas.create_text(
                    LM + col * STEP, TM - 4,
                    text=month, anchor="sw",
                    fill=MUTED, font=("Helvetica", 7),
                )
                prev_month = month

            for r in range(7):
                cur = d + timedelta(days=r)
                if cur > today_d:
                    break
                ds   = cur.strftime("%Y-%m-%d")
                mins = data.get(ds, 0)
                x0   = LM + col * STEP
                y0   = TM + r * STEP
                canvas.create_rectangle(x0, y0, x0 + CELL, y0 + CELL,
                                        fill=_heatmap_color(mins), outline="")
                cell_map[(col, r)] = (ds, mins)

            d   += timedelta(weeks=1)
            col += 1

        # Tooltip label below canvas
        tip = mk_label(parent, "", size=11, color=MUTED)
        tip.pack(anchor="w", padx=14, pady=(0, 10))

        def _hover(event):
            c = (event.x - LM) // STEP
            r = (event.y - TM) // STEP
            info = cell_map.get((c, r))
            if info:
                ds, mins = info
                if mins:
                    h, m = divmod(int(mins), 60)
                    ts = f"{h}h {m}min" if h else f"{m}min"
                    tip.configure(text=f"{ds}  ·  {ts}")
                else:
                    tip.configure(text=f"{ds}  ·  kein Eintrag")
            else:
                tip.configure(text="")

        canvas.bind("<Motion>", _hover)
        canvas.bind("<Leave>", lambda _: tip.configure(text=""))

        # Legend
        leg = ctk.CTkFrame(parent, fg_color="transparent")
        leg.pack(anchor="w", padx=14, pady=(0, 14))
        mk_label(leg, "Wenig", size=10, color=MUTED).pack(side="left", padx=(0, 4))
        for col_val in [CARD, "#fbbf24", "#d97706", "#92400e", DARK]:
            c = tk.Canvas(leg, width=CELL, height=CELL, bg=col_val,
                          highlightthickness=0)
            c.pack(side="left", padx=1)
        mk_label(leg, "Viel", size=10, color=MUTED).pack(side="left", padx=(4, 0))

    # ── Stat level-up dialog ─────────────────────────────────────────────────
    def _stat_levelup_dialog(self, stat_name: str, level: int):
        nature = ["🌸", "🌿", "🌱", "⭐", "🌟", "✨", "🍀", "🌈", "💫", "🌺"]
        pick = nature[level % len(nature)]
        dlg = ctk.CTkToplevel(self)
        dlg.title("Level Up!")
        dlg.geometry("340x230")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        dlg.lift()
        mk_label(dlg, f"{pick}  {pick}  {pick}", size=30, color=DARK).pack(pady=(26, 4))
        mk_label(dlg, stat_name, size=16, weight="bold", color=DARK).pack()
        mk_label(dlg, f"Level {level}!", size=14, color=MUTED).pack(pady=(2, 8))
        mk_btn(dlg, f"{pick}  Super!", dlg.destroy,
               width=160, height=40, primary=True).pack(pady=12)

    # ── Bar chart ─────────────────────────────────────────────────────────────
    def _draw_bar_chart(self, parent):
        ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(14, 6))
        mk_label(ctrl, "Verlauf (letzte 60 Tage)", size=13, weight="bold",
                 color=TEXT).pack(side="left")

        skills_list = ["Alle"] + [name for name, _ in get_user_skills()]
        chart_skill = ctk.StringVar(value="Alle")
        opt = ctk.CTkOptionMenu(
            ctrl, values=skills_list, variable=chart_skill,
            width=130, height=28, corner_radius=8,
            fg_color=CARD, button_color=BORDER, button_hover_color=DARK,
            text_color=TEXT, dropdown_fg_color=CARD,
            dropdown_text_color=TEXT, dropdown_hover_color=BORDER,
            font=ctk.CTkFont(size=12),
        )
        opt.pack(side="right")

        canvas = tk.Canvas(parent, height=170, bg=PANEL, highlightthickness=0)
        canvas.pack(fill="x", padx=16, pady=(0, 4))

        tip = mk_label(parent, "", size=11, color=MUTED)
        tip.pack(anchor="w", padx=16, pady=(0, 12))

        def _redraw(*_):
            w = canvas.winfo_width()
            if w < 50:
                return
            self._draw_bars(canvas, chart_skill.get(), w, tip)

        canvas.bind("<Configure>", lambda _: _redraw())
        chart_skill.trace_add("write", lambda *_: _redraw())

    def _draw_bars(self, canvas, skill: str, canvas_w: int, tip_lbl):
        canvas.delete("all")
        canvas_h = 170
        LM, BM, TM, RM = 44, 32, 10, 10
        draw_w = canvas_w - LM - RM
        draw_h = canvas_h - TM - BM

        data = get_chart_data(skill if skill != "Alle" else None)

        today_d = date.today()
        days    = [(today_d - timedelta(days=59 - i)) for i in range(60)]
        values  = [data.get(d.strftime("%Y-%m-%d"), 0.0) for d in days]

        max_h = max(values) if any(v > 0 for v in values) else 0.0
        if max_h == 0:
            canvas.create_text(canvas_w // 2, canvas_h // 2,
                               text="Keine Daten", fill=MUTED,
                               font=("Helvetica", 13))
            return

        # Nice Y-axis ceiling
        if max_h <= 1:   nice_max = 1
        elif max_h <= 2: nice_max = 2
        elif max_h <= 5: nice_max = 5
        elif max_h <= 10: nice_max = 10
        else:            nice_max = math.ceil(max_h / 5) * 5

        # Axes
        canvas.create_line(LM, TM, LM, TM + draw_h, fill=BORDER, width=1)
        canvas.create_line(LM, TM + draw_h, LM + draw_w, TM + draw_h,
                          fill=BORDER, width=1)

        # Y-axis ticks
        for frac in [0.0, 0.5, 1.0]:
            y = TM + draw_h - frac * draw_h
            canvas.create_line(LM - 3, y, LM, y, fill=MUTED, width=1)
            label = f"{nice_max * frac:.0f}h"
            canvas.create_text(LM - 5, y, text=label,
                               anchor="e", fill=MUTED, font=("Helvetica", 8))

        # Bars
        bar_total_w = draw_w / 60
        bar_w = max(2.0, bar_total_w * 0.75)

        for i, (d, val) in enumerate(zip(days, values)):
            if val <= 0:
                continue
            x_center = LM + (i + 0.5) * bar_total_w
            bar_h = (val / nice_max) * draw_h
            x0 = x_center - bar_w / 2
            y1 = TM + draw_h
            y0 = max(TM + 1.0, y1 - bar_h)
            ratio = val / max_h
            fill = DARK if ratio >= 0.75 else (DARK2 if ratio >= 0.4 else BORDER)
            canvas.create_rectangle(x0, y0, x0 + bar_w, y1, fill=fill, outline="")

        # X-axis date labels every 10 days
        for i, d in enumerate(days):
            if i % 10 == 0:
                x = LM + (i + 0.5) * bar_total_w
                canvas.create_text(x, TM + draw_h + 6, text=d.strftime("%d.%m"),
                                  fill=MUTED, font=("Helvetica", 8), anchor="n")

        # Hover
        btw = bar_total_w

        def _hover(event):
            idx = int((event.x - LM) / btw)
            if 0 <= idx < len(days):
                d = days[idx]
                val = values[idx]
                ds = d.strftime("%Y-%m-%d")
                tip_lbl.configure(
                    text=f"{ds}  ·  {val:.2f}h" if val > 0
                    else f"{ds}  ·  kein Eintrag"
                )
            else:
                tip_lbl.configure(text="")

        canvas.bind("<Motion>", _hover)
        canvas.bind("<Leave>", lambda _: tip_lbl.configure(text=""))

    # ── Stats View ────────────────────────────────────────────────────────────
    def _build_stats_view(self) -> ctk.CTkFrame:
        view = ctk.CTkFrame(self.content, fg_color=BG)
        mk_label(view, "Stats", size=22, weight="bold",
                 color=DARK).pack(anchor="w", padx=28, pady=(24, 14))
        self._stats_scroll = ctk.CTkScrollableFrame(
            view, fg_color=BG,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=DARK,
        )
        self._stats_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        return view

    def _refresh_stats(self):
        if not hasattr(self, "_stats_scroll"):
            return
        for w in self._stats_scroll.winfo_children():
            w.destroy()

        # ── Heatmap ───────────────────────────────────────────────────────────
        hm_card = mk_card(self._stats_scroll)
        hm_card.pack(fill="x", pady=5, padx=6)
        mk_label(hm_card, "Aktivität", size=13, weight="bold",
                 color=TEXT).pack(anchor="w", padx=16, pady=(14, 6))
        self._draw_heatmap(hm_card)

        # ── Bar chart (last 60 days) ───────────────────────────────────────────
        bar_card = mk_card(self._stats_scroll)
        bar_card.pack(fill="x", pady=5, padx=6)
        self._draw_bar_chart(bar_card)

        # ── Line graph (all time) ──────────────────────────────────────────────
        line_card = mk_card(self._stats_scroll)
        line_card.pack(fill="x", pady=5, padx=6)
        self._draw_line_graph(line_card)

    # ── Line graph ────────────────────────────────────────────────────────────
    def _draw_line_graph(self, parent):
        ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(14, 6))
        mk_label(ctrl, "Verlauf (gesamt)", size=13, weight="bold",
                 color=TEXT).pack(side="left")

        skills_list = ["Alle"] + [name for name, _ in get_user_skills()]
        line_skill = ctk.StringVar(value="Alle")
        opt = ctk.CTkOptionMenu(
            ctrl, values=skills_list, variable=line_skill,
            width=130, height=28, corner_radius=8,
            fg_color=CARD, button_color=BORDER, button_hover_color=DARK,
            text_color=TEXT, dropdown_fg_color=CARD,
            dropdown_text_color=TEXT, dropdown_hover_color=BORDER,
            font=ctk.CTkFont(size=12),
        )
        opt.pack(side="right")

        canvas = tk.Canvas(parent, height=180, bg=PANEL, highlightthickness=0)
        canvas.pack(fill="x", padx=16, pady=(0, 4))

        tip = mk_label(parent, "", size=11, color=MUTED)
        tip.pack(anchor="w", padx=16, pady=(0, 12))

        def _redraw(*_):
            w = canvas.winfo_width()
            if w < 50:
                return
            self._draw_lines(canvas, line_skill.get(), w, tip)

        canvas.bind("<Configure>", lambda _: _redraw())
        line_skill.trace_add("write", lambda *_: _redraw())

    def _draw_lines(self, canvas, skill: str, canvas_w: int, tip_lbl):
        canvas.delete("all")
        canvas_h = 180
        LM, BM, TM, RM = 44, 32, 10, 10
        draw_w = canvas_w - LM - RM
        draw_h = canvas_h - TM - BM

        first = get_first_session_date()
        if not first:
            canvas.create_text(canvas_w // 2, canvas_h // 2,
                               text="Keine Daten", fill=MUTED,
                               font=("Helvetica", 13))
            return

        data = get_chart_data(skill if skill != "Alle" else None)

        start_d = datetime.strptime(first, "%Y-%m-%d").date()
        today_d = date.today()
        num_days = (today_d - start_d).days + 1
        if num_days < 1:
            num_days = 1

        days = [start_d + timedelta(days=i) for i in range(num_days)]

        # Build cumulative hours
        cumulative = []
        running = 0.0
        for d in days:
            running += data.get(d.strftime("%Y-%m-%d"), 0.0)
            cumulative.append(running)

        total_h = cumulative[-1]
        if total_h == 0:
            canvas.create_text(canvas_w // 2, canvas_h // 2,
                               text="Keine Daten", fill=MUTED,
                               font=("Helvetica", 13))
            return

        if total_h <= 10:    nice_max = math.ceil(total_h)
        elif total_h <= 50:  nice_max = math.ceil(total_h / 5) * 5
        elif total_h <= 200: nice_max = math.ceil(total_h / 10) * 10
        elif total_h <= 500: nice_max = math.ceil(total_h / 50) * 50
        else:                nice_max = math.ceil(total_h / 100) * 100

        # Axes
        canvas.create_line(LM, TM, LM, TM + draw_h, fill=BORDER, width=1)
        canvas.create_line(LM, TM + draw_h, LM + draw_w, TM + draw_h,
                           fill=BORDER, width=1)

        # Y-axis ticks
        for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = TM + draw_h - frac * draw_h
            canvas.create_line(LM - 3, y, LM, y, fill=MUTED, width=1)
            label = f"{nice_max * frac:.0f}h"
            canvas.create_text(LM - 5, y, text=label,
                               anchor="e", fill=MUTED, font=("Helvetica", 8))

        def _x(i):
            if num_days == 1:
                return LM + draw_w // 2
            return LM + i * draw_w / (num_days - 1)

        def _y(val):
            return TM + draw_h - (val / nice_max) * draw_h

        # Continuous line across all days
        coords = []
        for i, v in enumerate(cumulative):
            coords.append(_x(i))
            coords.append(_y(v))
        if len(coords) >= 4:
            canvas.create_line(*coords, fill=DARK2, width=1.5, smooth=False)

        # X-axis month labels
        prev_month = None
        for i, d in enumerate(days):
            if d.day == 1:
                m = d.strftime("%b %y")
                if m != prev_month:
                    canvas.create_text(
                        _x(i), TM + draw_h + 6,
                        text=d.strftime("%b '%y") if d.month == 1 else d.strftime("%b"),
                        fill=MUTED, font=("Helvetica", 8), anchor="n",
                    )
                    prev_month = m

        # Hover: show cumulative total at nearest day
        def _hover(event):
            if num_days < 2:
                return
            frac = (event.x - LM) / draw_w
            idx  = max(0, min(num_days - 1, round(frac * (num_days - 1))))
            d    = days[idx]
            val  = cumulative[idx]
            tip_lbl.configure(text=f"{d.strftime('%Y-%m-%d')}  ·  {val:.1f}h gesamt")

        canvas.bind("<Motion>", _hover)
        canvas.bind("<Leave>", lambda _: tip_lbl.configure(text=""))

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
            date_filter = f"WHERE date = '{now.strftime('%Y-%m-%d')}'"
        elif period == "This Month":
            date_filter = f"WHERE date LIKE '{now.strftime('%Y-%m')}%'"
        elif period == "This Year":
            date_filter = f"WHERE date LIKE '{now.strftime('%Y')}%'"
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
            text=f"Σ {total / 60:.1f} h · {len(filtered)} Sessions")

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
            mk_label(self._lb_scroll, "Keine Einträge für diesen Zeitraum.",
                     color=MUTED, size=14).pack(pady=40)
        elif shown < len(filtered):
            mk_btn(
                self._lb_scroll,
                f"Mehr laden  ({len(filtered) - shown} weitere)",
                command=lambda: self._refresh_leaderboard(shown + 10),
                width=220, height=36,
            ).pack(pady=14)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
