import sqlite3
import config
from datetime import datetime
from config import LEVEL_THRESHOLDS, SKILLS, SKILL_EMOJIS


def initialize_db():
    conn = sqlite3.connect(config.DB_FILE)
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
    # Migrate old notes table if it was created without an id autoincrement column
    note_cols = [r[1] for r in c.execute("PRAGMA table_info(notes)").fetchall()]
    if note_cols and "id" not in note_cols:
        c.execute("ALTER TABLE notes RENAME TO _notes_bak")
        c.execute('''
            CREATE TABLE notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, time TEXT, title TEXT, content TEXT
            )
        ''')
        try:
            common = [col for col in ["date", "time", "title", "content"]
                      if col in note_cols]
            cols_s = ", ".join(common)
            c.execute(f"INSERT INTO notes ({cols_s}) SELECT {cols_s} FROM _notes_bak")
        except Exception:
            pass
        c.execute("DROP TABLE IF EXISTS _notes_bak")
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS stat_confirmed_levels (
            stat TEXT PRIMARY KEY,
            confirmed_level INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()
    _seed_user_skills()


def _seed_user_skills():
    conn = sqlite3.connect(config.DB_FILE)
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
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT SUM(duration) FROM pomodoro_session")
    result = c.fetchone()[0]
    conn.close()
    return 0.0 if result is None else result / 60.0


def save_session(duration, intention, result, skill="Pomodoro"):
    now = datetime.now()
    conn = sqlite3.connect(config.DB_FILE)
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
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    row = c.execute("SELECT id FROM notes WHERE title=?", (title,)).fetchone()
    if row:
        c.execute(
            "UPDATE notes SET date=?, time=?, content=? WHERE id=?",
            (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), content, row[0]),
        )
    else:
        c.execute(
            "INSERT INTO notes (date, time, title, content) VALUES (?, ?, ?, ?)",
            (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), title, content),
        )
    conn.commit()
    conn.close()


def get_notes(limit: int = 50):
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT id, date, time, title, content FROM notes"
        " ORDER BY date DESC, time DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def delete_note(note_id: int):
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()


def rename_note(note_id: int, new_title: str):
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE notes SET title=? WHERE id=?", (new_title, note_id))
    conn.commit()
    conn.close()


# ── Skill level confirmation ───────────────────────────────────────────────────

def get_skill_confirmed_levels() -> dict:
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    rows = c.execute(
        "SELECT skill, confirmed_level FROM skill_confirmed_levels"
    ).fetchall()
    conn.close()
    return {sk: lv for sk, lv in rows}


def confirm_skill_level(skill: str, level: int):
    conn = sqlite3.connect(config.DB_FILE)
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
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    rows = c.execute("SELECT name FROM achievement_collected").fetchall()
    conn.close()
    return {r[0] for r in rows}


def mark_achievement_collected(name: str):
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO achievement_collected (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


# ── Badge unlock dates ─────────────────────────────────────────────────────────

def get_badge_unlock_date(level: int) -> str | None:
    return get_badge_unlock_info(level)[0]


def get_badge_unlock_info(level: int) -> tuple:
    """Return (date_str, cumulative_hours) when the badge was unlocked."""
    if level == 0:
        return ("Von Anfang an", 0.0)
    threshold_min = LEVEL_THRESHOLDS[level - 1] * 60
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date, duration FROM pomodoro_session ORDER BY sessions ASC")
    rows = c.fetchall()
    conn.close()
    total = 0.0
    for date_s, dur in rows:
        total += dur or 0
        if total >= threshold_min:
            return (date_s, total / 60.0)
    return (None, 0.0)


# ── User skills ────────────────────────────────────────────────────────────────

def get_user_skills() -> list:
    """Return [(name, emoji), ...] of all active skills."""
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    rows = c.execute(
        "SELECT name, emoji FROM user_skills WHERE active=1 ORDER BY sort_order"
    ).fetchall()
    conn.close()
    return rows


def add_user_skill(name: str, emoji: str):
    conn = sqlite3.connect(config.DB_FILE)
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
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE user_skills SET active=0 WHERE name=?", (name,))
    conn.commit()
    conn.close()


# ── Stat level confirmation ────────────────────────────────────────────────────

def get_stat_confirmed_levels() -> dict:
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    rows = c.execute(
        "SELECT stat, confirmed_level FROM stat_confirmed_levels"
    ).fetchall()
    conn.close()
    return {s: l for s, l in rows}


def confirm_stat_level(stat: str, level: int):
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute(
        """INSERT INTO stat_confirmed_levels (stat, confirmed_level) VALUES (?, ?)
           ON CONFLICT(stat) DO UPDATE SET confirmed_level = ?""",
        (stat, level, level),
    )
    conn.commit()
    conn.close()


# ── Chart data ─────────────────────────────────────────────────────────────────

def get_chart_data(skill: str = None) -> dict:
    """Return {date_str: hours} for bar chart, optionally filtered by skill."""
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    if skill and skill != "Alle":
        c.execute(
            "SELECT date, SUM(duration)/60.0 FROM pomodoro_session "
            "WHERE skill=? GROUP BY date ORDER BY date",
            (skill,),
        )
    else:
        c.execute(
            "SELECT date, SUM(duration)/60.0 FROM pomodoro_session "
            "GROUP BY date ORDER BY date"
        )
    rows = c.fetchall()
    conn.close()
    return {d: h for d, h in rows if d}


# ── First session date ─────────────────────────────────────────────────────────

def get_today_stats() -> dict:
    """All data needed for the Today tab in one DB connection."""
    from datetime import date as _date
    today = _date.today().isoformat()

    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()

    # Today's total and session list
    c.execute(
        "SELECT time, duration, skill FROM pomodoro_session"
        " WHERE date=? ORDER BY time",
        (today,),
    )
    today_rows = c.fetchall()
    total_min = sum(r[1] for r in today_rows if r[1])
    sessions  = len(today_rows)
    longest   = max((r[1] for r in today_rows), default=0)

    skill_breakdown: dict = {}
    for _, dur, sk in today_rows:
        if sk and dur:
            skill_breakdown[sk] = skill_breakdown.get(sk, 0) + dur

    timeline = [
        {"time": r[0], "duration": r[1], "skill": r[2]}
        for r in today_rows if r[0]
    ]

    # All days for percentile + average
    c.execute(
        "SELECT SUM(duration) FROM pomodoro_session"
        " WHERE date != ? AND date IS NOT NULL GROUP BY date",
        (today,),
    )
    other_days = [r[0] for r in c.fetchall() if r[0]]
    all_days   = sorted(other_days + ([total_min] if total_min > 0 else []), reverse=True)
    avg_min    = (sum(other_days) / len(other_days)) if other_days else 0

    # Best day ever
    c.execute(
        "SELECT MAX(daily) FROM"
        " (SELECT SUM(duration) as daily FROM pomodoro_session"
        "  WHERE date IS NOT NULL GROUP BY date)"
    )
    best_day_min = c.fetchone()[0] or 0

    conn.close()

    # Percentile: what % of days were worse than today
    if total_min > 0 and all_days:
        rank = sum(1 for d in all_days if d <= total_min)
        percentile = round(rank / len(all_days) * 100, 2)
    else:
        percentile = None

    return {
        "today":           today,
        "total_min":       total_min,
        "sessions":        sessions,
        "longest_min":     longest,
        "skill_breakdown": skill_breakdown,
        "timeline":        timeline,
        "best_day_min":    best_day_min,
        "avg_min":         avg_min,
        "percentile":      percentile,
    }


def get_last_session_duration() -> float | None:
    """Return duration (minutes) of the most recent session, or None."""
    conn = sqlite3.connect(config.DB_FILE)
    row = conn.execute(
        "SELECT duration FROM pomodoro_session ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_first_session_date() -> str | None:
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    row = c.execute("SELECT MIN(date) FROM pomodoro_session").fetchone()
    conn.close()
    return row[0] if row else None


# ── Heatmap data ───────────────────────────────────────────────────────────────

def get_heatmap_data() -> dict:
    """Return {date_str: total_minutes} for all dates with sessions."""
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date, SUM(duration) FROM pomodoro_session GROUP BY date")
    rows = c.fetchall()
    conn.close()
    return {d: m for d, m in rows if d}


def get_streak() -> int:
    """Return current consecutive-day streak (days with ≥1 session ending today or yesterday)."""
    from datetime import date, timedelta
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT DISTINCT date FROM pomodoro_session WHERE date IS NOT NULL ORDER BY date DESC")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    if not rows:
        return 0
    today = date.today()
    # Allow streak if last session was today or yesterday (don't break at midnight)
    try:
        last = date.fromisoformat(rows[0])
    except ValueError:
        return 0
    if last < today - timedelta(days=1):
        return 0
    streak = 0
    expected = last
    for ds in rows:
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            continue
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break
    return streak


# ── Records ────────────────────────────────────────────────────────────────────

def _skill_breakdown(conn, dates: list) -> dict:
    """Return {skill: minutes} for a list of date strings."""
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    c = conn.cursor()
    rows = c.execute(
        f"SELECT skill, SUM(duration) FROM pomodoro_session"
        f" WHERE date IN ({placeholders}) GROUP BY skill",
        dates,
    ).fetchall()
    return {sk: (m or 0) for sk, m in rows}


def get_best_periods(period: str = "day") -> list:
    """Return records sorted best-first.

    period: 'day' | 'week' | 'month'
    Each record: {label, total_min, breakdown: {skill: min}, dates: [date_str, ...]}
    """
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()

    if period == "day":
        c.execute(
            "SELECT date, SUM(duration) FROM pomodoro_session"
            " WHERE date IS NOT NULL GROUP BY date ORDER BY 2 DESC"
        )
        rows = c.fetchall()
        result = []
        for date_s, total in rows:
            bd = _skill_breakdown(conn, [date_s])
            cnt = c.execute(
                "SELECT COUNT(*) FROM pomodoro_session WHERE date=?",
                (date_s,)).fetchone()[0]
            try:
                from datetime import date as _date
                d = _date.fromisoformat(date_s)
                label = d.strftime("%a, %d %b %Y")
            except Exception:
                label = date_s
            result.append({"label": label, "total_min": total or 0,
                           "breakdown": bd, "dates": [date_s],
                           "session_count": cnt})

    elif period == "week":
        c.execute(
            "SELECT strftime('%Y-W%W', date) as wk, SUM(duration), MIN(date), MAX(date)"
            " FROM pomodoro_session WHERE date IS NOT NULL GROUP BY wk ORDER BY 2 DESC"
        )
        rows = c.fetchall()
        result = []
        for wk, total, dmin, dmax in rows:
            # collect all dates in that week
            c2 = conn.cursor()
            dates = [r[0] for r in c2.execute(
                "SELECT DISTINCT date FROM pomodoro_session"
                " WHERE strftime('%Y-W%W', date)=?", (wk,)
            ).fetchall()]
            bd = _skill_breakdown(conn, dates)
            ph = ",".join("?" * len(dates))
            cnt = c2.execute(
                f"SELECT COUNT(*) FROM pomodoro_session WHERE date IN ({ph})",
                dates).fetchone()[0]
            try:
                from datetime import date as _date
                d1 = _date.fromisoformat(dmin)
                d2 = _date.fromisoformat(dmax)
                label = f"{d1.strftime('%d %b')} – {d2.strftime('%d %b %Y')}"
            except Exception:
                label = wk
            result.append({"label": label, "total_min": total or 0,
                           "breakdown": bd, "dates": dates,
                           "session_count": cnt})

    else:  # month
        c.execute(
            "SELECT strftime('%Y-%m', date) as mo, SUM(duration), MIN(date)"
            " FROM pomodoro_session WHERE date IS NOT NULL GROUP BY mo ORDER BY 2 DESC"
        )
        rows = c.fetchall()
        result = []
        for mo, total, dmin in rows:
            c2 = conn.cursor()
            dates = [r[0] for r in c2.execute(
                "SELECT DISTINCT date FROM pomodoro_session"
                " WHERE strftime('%Y-%m', date)=?", (mo,)
            ).fetchall()]
            bd = _skill_breakdown(conn, dates)
            ph = ",".join("?" * len(dates))
            cnt = c2.execute(
                f"SELECT COUNT(*) FROM pomodoro_session WHERE date IN ({ph})",
                dates).fetchone()[0]
            try:
                from datetime import date as _date
                d = _date.fromisoformat(dmin)
                label = d.strftime("%B %Y")
            except Exception:
                label = mo
            result.append({"label": label, "total_min": total or 0,
                           "breakdown": bd, "dates": dates,
                           "session_count": cnt})

    conn.close()
    return result


def get_all_streaks() -> list:
    """Return all streaks sorted longest-first.
    Each: {length, start_date, end_date}
    """
    from datetime import date as _date, timedelta
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT DISTINCT date FROM pomodoro_session WHERE date IS NOT NULL ORDER BY date ASC")
    raw = [r[0] for r in c.fetchall()]
    conn.close()

    streaks = []
    if not raw:
        return streaks

    try:
        dates = sorted(_date.fromisoformat(d) for d in raw)
    except Exception:
        return streaks

    start = dates[0]
    length = 1
    for i in range(1, len(dates)):
        if dates[i] == dates[i - 1] + timedelta(days=1):
            length += 1
        else:
            streaks.append({"length": length,
                            "start_date": start.isoformat(),
                            "end_date": dates[i - 1].isoformat()})
            start = dates[i]
            length = 1
    streaks.append({"length": length,
                    "start_date": start.isoformat(),
                    "end_date": dates[-1].isoformat()})
    streaks.sort(key=lambda x: x["length"], reverse=True)
    return streaks


def get_best_days_for_skill(skill: str) -> list:
    """Return best days for a specific skill, sorted best-first.
    Each: {label, total_min, date_s}
    """
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT date, SUM(duration) FROM pomodoro_session"
        " WHERE skill=? AND date IS NOT NULL GROUP BY date ORDER BY 2 DESC",
        (skill,),
    )
    rows = c.fetchall()
    conn.close()
    result = []
    for date_s, total in rows:
        try:
            from datetime import date as _date
            d = _date.fromisoformat(date_s)
            label = d.strftime("%a, %d %b %Y")
        except Exception:
            label = date_s
        result.append({"label": label, "total_min": total or 0, "date_s": date_s})
    return result


# DB initialisieren beim Laden
initialize_db()
