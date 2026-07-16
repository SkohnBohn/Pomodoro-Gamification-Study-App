import sqlite3
from datetime import datetime
from config import DB_FILE, LEVEL_THRESHOLDS, SKILLS, SKILL_EMOJIS


def initialize_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS pomodoro_session (
            sessions INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, time TEXT, skill TEXT,
            duration REAL, total_time REAL,
            intention TEXT, result TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, time TEXT, title TEXT, content TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS skill_confirmed_levels (
            skill TEXT PRIMARY KEY,
            confirmed_level INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS achievement_collected (
            name TEXT PRIMARY KEY
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_skills (
            name       TEXT PRIMARY KEY,
            emoji      TEXT DEFAULT '',
            active     INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()
    _seed_user_skills()


def _seed_user_skills():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if c.execute("SELECT COUNT(*) FROM user_skills").fetchone()[0] == 0:
        for i, sk in enumerate(SKILLS):
            c.execute(
                "INSERT OR IGNORE INTO user_skills (name, emoji, active, sort_order)"
                " VALUES (?, ?, 1, ?)",
                (sk, SKILL_EMOJIS.get(sk, ""), i),
            )
        conn.commit()
    conn.close()


# ── Sessions ───────────────────────────────────────────────────────────────────

def calculate_total_time():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT SUM(duration) FROM pomodoro_session")
    result = c.fetchone()[0]
    conn.close()
    return 0.0 if result is None else result / 60.0


def save_session(duration, intention, result, skill="Pomodoro"):
    now = datetime.now()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT MAX(sessions) FROM pomodoro_session")
    last_id = c.fetchone()[0] or 0
    c.execute("SELECT SUM(duration) FROM pomodoro_session")
    prev_total = c.fetchone()[0] or 0
    total_time = prev_total + duration
    c.execute('''
        INSERT INTO pomodoro_session
            (sessions, date, time, skill, duration, total_time, intention, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (last_id + 1, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
          skill, round(duration, 2), round(total_time, 2), intention, result))
    conn.commit()
    conn.close()


# ── Notes ──────────────────────────────────────────────────────────────────────

def save_note(title: str, content: str):
    now = datetime.now()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (date, time, title, content) VALUES (?, ?, ?, ?)",
        (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), title, content),
    )
    conn.commit()
    conn.close()


def get_notes(limit: int = 50):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT id, date, time, title, content FROM notes ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def delete_note(note_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()


def rename_note(note_id: int, new_title: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE notes SET title=? WHERE id=?", (new_title, note_id))
    conn.commit()
    conn.close()


# ── Skill level confirmation ───────────────────────────────────────────────────

def get_skill_confirmed_levels() -> dict:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    rows = c.execute(
        "SELECT skill, confirmed_level FROM skill_confirmed_levels"
    ).fetchall()
    conn.close()
    return {sk: lv for sk, lv in rows}


def confirm_skill_level(skill: str, level: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """INSERT INTO skill_confirmed_levels (skill, confirmed_level) VALUES (?, ?)
           ON CONFLICT(skill) DO UPDATE SET confirmed_level = ?""",
        (skill, level, level),
    )
    conn.commit()
    conn.close()


# ── Achievement collection ─────────────────────────────────────────────────────

def get_achievements_collected() -> set:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    rows = c.execute("SELECT name FROM achievement_collected").fetchall()
    conn.close()
    return {r[0] for r in rows}


def mark_achievement_collected(name: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO achievement_collected (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


# ── Badge unlock dates ─────────────────────────────────────────────────────────

def get_badge_unlock_date(level: int) -> str | None:
    if level == 0:
        return "Von Anfang an"
    threshold_min = LEVEL_THRESHOLDS[level - 1] * 60
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date, duration FROM pomodoro_session ORDER BY sessions ASC")
    rows = c.fetchall()
    conn.close()
    total = 0.0
    for date_s, dur in rows:
        total += dur or 0
        if total >= threshold_min:
            return date_s
    return None


# ── User skills ────────────────────────────────────────────────────────────────

def get_user_skills() -> list:
    """Return [(name, emoji), ...] of all active skills."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    rows = c.execute(
        "SELECT name, emoji FROM user_skills WHERE active=1 ORDER BY sort_order"
    ).fetchall()
    conn.close()
    return rows


def add_user_skill(name: str, emoji: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    max_order = c.execute("SELECT MAX(sort_order) FROM user_skills").fetchone()[0] or 0
    c.execute(
        "INSERT OR REPLACE INTO user_skills (name, emoji, active, sort_order)"
        " VALUES (?, ?, 1, ?)",
        (name.upper().strip(), emoji.strip(), max_order + 1),
    )
    conn.commit()
    conn.close()


def delete_user_skill(name: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE user_skills SET active=0 WHERE name=?", (name,))
    conn.commit()
    conn.close()


# ── Heatmap data ───────────────────────────────────────────────────────────────

def get_heatmap_data() -> dict:
    """Return {date_str: total_minutes} for all dates with sessions."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date, SUM(duration) FROM pomodoro_session GROUP BY date")
    rows = c.fetchall()
    conn.close()
    return {d: m for d, m in rows if d}


# DB initialisieren beim Laden
initialize_db()
