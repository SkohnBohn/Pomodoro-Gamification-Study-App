import sqlite3
import json
import os
import config
from datetime import datetime
from config import LEVEL_THRESHOLDS, SKILLS, SKILL_EMOJIS

_SETTINGS_DEFAULTS = {
    "db":             "main",
    "timer_fills":    False,
    "pomo_max_mins":  90.0,
    "selected_skill": "TECH",
    "timer_mode":     "Pomodoro",
    "sound_click":    True,
    "sound_levelup":  True,
    "sound_finish":   True,
    "day_end_hour":   3,
    "hidden_tabs":    [],
    "known_tabs":     [],
    "hidden_stats_elements": [],
    "ambience_slots": [None] * 9,
}

def load_settings() -> dict:
    try:
        with open(config.SETTINGS_FILE, "r") as f:
            data = json.load(f)
        return {**_SETTINGS_DEFAULTS, **data}
    except FileNotFoundError:
        return dict(_SETTINGS_DEFAULTS)
    except Exception as e:
        import sys
        print(f"[settings] load failed: {e}", file=sys.stderr, flush=True)
        return dict(_SETTINGS_DEFAULTS)

def study_date(dt=None):
    """Return the 'study day' date for a datetime, shifted back if before day_end_hour."""
    from datetime import datetime as _dt, timedelta, date as _date
    if dt is None:
        dt = _dt.now()
    end_h = load_settings().get("day_end_hour", 3)
    if end_h and dt.hour < end_h:
        return (dt - timedelta(days=1)).date()
    return dt.date()


def save_settings(key: str, value) -> None:
    settings = load_settings()
    settings[key] = value
    path = config.SETTINGS_FILE
    dir_ = os.path.dirname(path)
    try:
        if dir_:
            os.makedirs(dir_, exist_ok=True)
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        import sys
        print(f"[settings] save failed ({path}): {e}", file=sys.stderr, flush=True)


def initialize_db():
    os.makedirs(os.path.dirname(config.DB_FILE), exist_ok=True)
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
    # Migrate: add pauses column (JSON) if it doesn't exist yet
    _ps_cols = [r[1] for r in c.execute("PRAGMA table_info(pomodoro_session)").fetchall()]
    if "pauses" not in _ps_cols:
        c.execute("ALTER TABLE pomodoro_session ADD COLUMN pauses TEXT")
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


def save_session(duration, intention, result, skill="POMO", pauses=None):
    import json as _json
    now = datetime.now()
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT MAX(sessions) FROM pomodoro_session")
    last_id = c.fetchone()[0] or 0
    c.execute("SELECT SUM(duration) FROM pomodoro_session")
    prev_total = c.fetchone()[0] or 0
    total_time = prev_total + duration
    pauses_json = _json.dumps(pauses) if pauses else None
    c.execute('''
        INSERT INTO pomodoro_session
            (sessions, date, time, skill, duration, total_time, intention, result, pauses)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (last_id + 1, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
          skill, round(duration, 2), round(total_time, 2), intention, result, pauses_json))
    conn.commit()
    conn.close()


def _parse_pauses(raw) -> list:
    if not raw:
        return []
    import json as _json
    try:
        return _json.loads(raw)
    except Exception:
        return []


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


def get_skill_log() -> list:
    """Return [(skill, session_count, last_date_str), ...] sorted by session count desc.

    last_date_str is ISO 'YYYY-MM-DD' or None.
    """
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT skill,
               COUNT(*)   AS cnt,
               MAX(date)  AS last_date
        FROM   pomodoro_session
        WHERE  skill IS NOT NULL AND skill != ''
        GROUP  BY skill
        ORDER  BY cnt DESC
        """
    ).fetchall()
    conn.close()
    return rows


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

def _normalized_sessions(skill: str = None, conn=None) -> list:
    """All sessions as (study_date_iso, duration, skill) — the stored
    wall-clock date shifted back a day for sessions before day_end_hour,
    so every date-bucketed stat in the app agrees on where a day starts.
    This is the one place that logic lives; every function that groups
    sessions by day/week/month/year should go through this."""
    from datetime import date as _date, timedelta as _td
    end_h = load_settings().get("day_end_hour", 3)
    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    if skill and skill != "Alle":
        c.execute(
            "SELECT date, time, duration, skill FROM pomodoro_session"
            " WHERE skill=? AND date IS NOT NULL",
            (skill,),
        )
    else:
        c.execute(
            "SELECT date, time, duration, skill FROM pomodoro_session"
            " WHERE date IS NOT NULL"
        )
    rows = c.fetchall()
    if own_conn:
        conn.close()
    out = []
    for ds, ts, dur, sk in rows:
        try:
            d = _date.fromisoformat(ds)
        except (ValueError, TypeError):
            continue
        if end_h and ts and ts < f"{end_h:02d}:00:00":
            d -= _td(days=1)
        out.append((d.isoformat(), dur or 0, sk))
    return out


def get_chart_data(skill: str = None) -> dict:
    """Return {date_str: hours} keyed by study date, optionally filtered by skill."""
    from datetime import date as _date, timedelta as _td
    end_h = load_settings().get("day_end_hour", 3)
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    if skill and skill != "Alle":
        c.execute(
            "SELECT date, time, duration FROM pomodoro_session "
            "WHERE skill=? AND date IS NOT NULL ORDER BY date",
            (skill,),
        )
    else:
        c.execute(
            "SELECT date, time, duration FROM pomodoro_session "
            "WHERE date IS NOT NULL ORDER BY date"
        )
    rows = c.fetchall()
    conn.close()
    result: dict = {}
    for ds, ts, dur in rows:
        if not ds or dur is None:
            continue
        try:
            d = _date.fromisoformat(ds)
            if end_h and ts and ts < f"{end_h:02d}:00:00":
                d -= _td(days=1)
            key = d.isoformat()
        except (ValueError, TypeError):
            key = ds
        result[key] = result.get(key, 0.0) + dur / 60.0
    return result


# ── First session date ─────────────────────────────────────────────────────────

def _study_day_where(target_date, end_h):
    """
    Returns (clause, params) for sessions belonging to a study day.
    All sessions use wall-clock dates. A study day owns:
      - sessions whose wall-clock date IS target_date AND time >= end_h
        (genuine daytime sessions on target_date)
      - sessions whose wall-clock date IS target_date+1 AND time < end_h
        (early-morning sessions on the next calendar day that still belong here)
    Crucially, target_date sessions with time < end_h are EXCLUDED — they
    belong to the PREVIOUS study day, preventing double-counting.
    """
    from datetime import timedelta as _td
    day_str      = target_date.isoformat()
    next_day_str = (target_date + _td(days=1)).isoformat()
    if end_h:
        end_time = f"{end_h:02d}:00:00"
        clause = "((date=? AND time >= ?) OR (date=? AND time < ?))"
        params = (day_str, end_time, next_day_str, end_time)
    else:
        clause = "date=?"
        params = (day_str,)
    return clause, params


def get_today_stats(target_date=None) -> dict:
    """All data needed for the Today tab in one DB connection."""
    from datetime import date as _date
    if target_date is None:
        target_date = study_date()
    day_str = target_date.isoformat()

    end_h = load_settings().get("day_end_hour", 3)
    day_clause, day_params = _study_day_where(target_date, end_h)

    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()

    # Target day's total and session list
    c.execute(
        f"SELECT time, duration, skill, pauses FROM pomodoro_session"
        f" WHERE {day_clause} ORDER BY time",
        day_params,
    )
    today_rows = c.fetchall()
    total_min = sum(r[1] for r in today_rows if r[1])
    sessions  = len(today_rows)
    longest   = max((r[1] for r in today_rows), default=0)

    skill_breakdown: dict = {}
    for _, dur, sk, _ in today_rows:
        if sk and dur:
            skill_breakdown[sk] = skill_breakdown.get(sk, 0) + dur

    timeline = [
        {"time": r[0], "duration": r[1], "skill": r[2], "pauses": _parse_pauses(r[3])}
        for r in today_rows if r[0]
    ]

    # Sessions that straddle the day boundary: they belong to tomorrow (end >= cutoff)
    # but started before the cutoff, so they visually overlap today's timeline too.
    timeline_next_overflow: list = []
    if end_h:
        from datetime import timedelta as _tdov
        _next_cal = (target_date + _tdov(days=1)).isoformat()
        _cutoff_str = f"{end_h:02d}:00:00"
        c.execute(
            "SELECT time, duration, skill, pauses FROM pomodoro_session"
            " WHERE date=? AND time >= ? ORDER BY time",
            (_next_cal, _cutoff_str),
        )
        for _r in c.fetchall():
            if not _r[0] or not _r[1]:
                continue
            try:
                _tp = _r[0].split(":")
                _end_min = int(_tp[0]) * 60 + int(_tp[1])
                _start_min = _end_min - _r[1]
            except Exception:
                continue
            if _start_min < end_h * 60:
                timeline_next_overflow.append(
                    {"time": _r[0], "duration": _r[1], "skill": _r[2],
                     "pauses": _parse_pauses(_r[3])}
                )

    # Study-date-normalized totals per day across all history — percentile,
    # average, best-day-ever and days-unbeaten are all derived from this so
    # they use the exact same day boundaries as the target day's own total.
    _sessions_all = _normalized_sessions(conn=conn)
    _day_totals_all: dict = {}
    for _ds, _dur, _sk in _sessions_all:
        _day_totals_all[_ds] = _day_totals_all.get(_ds, 0) + _dur

    other_days = [v for k, v in _day_totals_all.items() if k != day_str]
    all_days   = sorted(other_days + ([total_min] if total_min > 0 else []), reverse=True)
    avg_min    = (sum(other_days) / len(other_days)) if other_days else 0

    # Best day ever
    best_day_min = max(_day_totals_all.values()) if _day_totals_all else 0

    # Percentile + rank: what % of days were worse, and ordinal position from top
    if total_min > 0 and all_days:
        rank = sum(1 for d in all_days if d <= total_min)
        percentile = round(rank / len(all_days) * 100, 2)
        day_rank = sum(1 for d in all_days if d > total_min) + 1
        total_days = len(all_days)
    else:
        percentile = None
        day_rank = None
        total_days = len(all_days) if all_days else 0

    # Days unbeaten: consecutive past study-days (most recent first) with less total than today
    days_unbeaten = 0
    if total_min > 0:
        for k in sorted((k for k in _day_totals_all if k < day_str), reverse=True):
            if _day_totals_all[k] < total_min:
                days_unbeaten += 1
            else:
                break

    # Streak: normalize stored dates to study dates before counting
    from datetime import timedelta as _td
    _study_dates_seen: set = {_date.fromisoformat(ds) for ds, _dur, _sk in _sessions_all}
    _sd_rows = sorted(_study_dates_seen, reverse=True)

    streak = 0
    if _sd_rows:
        _anchor = None
        for _d in _sd_rows:
            if _d <= target_date:
                _anchor = _d
                break
        if _anchor is not None:
            _ok = (_anchor >= target_date - _td(days=1)) if target_date == study_date() \
                  else (_anchor == target_date)
            if _ok:
                _expected = _anchor
                for _d in _sd_rows:
                    if _d > target_date:
                        continue
                    if _d == _expected:
                        streak += 1
                        _expected -= _td(days=1)
                    elif _d < _expected:
                        break

    conn.close()

    # Thresholds: minutes needed to reach top X% of all days
    thresholds: dict = {}
    if other_days:
        asc = sorted(other_days)
        n = len(asc)
        for top_pct in [50, 20, 10, 5, 2, 1]:
            idx = min(int((100 - top_pct) / 100 * n), n - 1)
            thresholds[top_pct] = asc[idx]

    return {
        "today":           day_str,
        "total_min":       total_min,
        "sessions":        sessions,
        "longest_min":     longest,
        "skill_breakdown": skill_breakdown,
        "timeline":               timeline,
        "timeline_next_overflow": timeline_next_overflow,
        "best_day_min":    best_day_min,
        "avg_min":         avg_min,
        "percentile":      percentile,
        "day_rank":        day_rank,
        "total_days":      total_days,
        "thresholds":      thresholds,
        "days_unbeaten":   days_unbeaten,
        "streak":          streak,
    }


def get_period_bounds(unit: str, offset: int, today=None):
    """Calendar start/end dates for the week/month/year containing `today`,
    shifted by `offset` units (0 = current, -1 = previous, ...)."""
    from datetime import date as _date, timedelta as _td
    import calendar as _cal
    if today is None:
        today = study_date()
    if unit == "W":
        this_monday = today - _td(days=today.weekday())
        start = this_monday + _td(weeks=offset)
        end = start + _td(days=6)
    elif unit == "M":
        total = (today.year * 12 + (today.month - 1)) + offset
        y, m = divmod(total, 12)
        m += 1
        start = _date(y, m, 1)
        end = _date(y, m, _cal.monthrange(y, m)[1])
    elif unit == "Y":
        y = today.year + offset
        start = _date(y, 1, 1)
        end = _date(y, 12, 31)
    else:
        start = end = today + _td(days=offset)
    return start, end


def get_period_stats(unit: str, start_date, end_date) -> dict:
    """Aggregated stats for a week/month/year window — the period-level
    analogue of get_today_stats, summed over a date range instead of a
    single day."""
    from datetime import date as _date, timedelta as _td

    today = study_date()
    start_str, end_str = start_date.isoformat(), end_date.isoformat()

    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()

    # All sessions, study-date normalized — both the in-range totals and the
    # all-history period bucketing are derived from the same pass, so they
    # agree on where a day starts (consistent with get_today_stats).
    _sessions_all = _normalized_sessions(conn=conn)

    total_min = 0
    sessions = 0
    skill_breakdown: dict = {}
    day_totals: dict = {}
    day_skill_totals: dict = {}
    for ds, dur, sk in _sessions_all:
        if ds < start_str or ds > end_str:
            continue
        sessions += 1
        if not dur:
            continue
        total_min += dur
        day_totals[ds] = day_totals.get(ds, 0) + dur
        if sk:
            skill_breakdown[sk] = skill_breakdown.get(sk, 0) + dur
            day_skill_totals.setdefault(ds, {})
            day_skill_totals[ds][sk] = day_skill_totals[ds].get(sk, 0) + dur

    # All historical days, bucketed into periods of this unit, for
    # percentile / average / thresholds / best-period comparisons.
    def _period_key(d):
        if unit == "W":
            monday = d - _td(days=d.weekday())
            return monday.isoformat()
        elif unit == "M":
            return f"{d.year:04d}-{d.month:02d}"
        elif unit == "Y":
            return str(d.year)
        return d.isoformat()

    period_totals: dict = {}
    for ds, dur, _sk in _sessions_all:
        try:
            d = _date.fromisoformat(ds)
        except (ValueError, TypeError):
            continue
        key = _period_key(d)
        period_totals[key] = period_totals.get(key, 0) + dur

    this_key = _period_key(start_date)
    other_totals = [v for k, v in period_totals.items() if k != this_key]
    all_totals = sorted(other_totals + ([total_min] if total_min > 0 else []), reverse=True)
    avg_period_min = (sum(other_totals) / len(other_totals)) if other_totals else 0
    best_period_min = max(period_totals.values()) if period_totals else 0

    if total_min > 0 and all_totals:
        rank = sum(1 for v in all_totals if v <= total_min)
        percentile = round(rank / len(all_totals) * 100, 2)
        period_rank = sum(1 for v in all_totals if v > total_min) + 1
        total_periods = len(all_totals)
    else:
        percentile = None
        period_rank = None
        total_periods = len(all_totals) if all_totals else 0

    thresholds: dict = {}
    if other_totals:
        asc = sorted(other_totals)
        n = len(asc)
        for top_pct in [50, 20, 10, 5, 2, 1]:
            idx = min(int((100 - top_pct) / 100 * n), n - 1)
            thresholds[top_pct] = asc[idx]

    # Days worked vs. days in period (elapsed-so-far for the current,
    # still-in-progress period; full calendar length for past periods).
    days_worked = sum(1 for ds in day_totals if day_totals[ds] > 0)
    is_current = start_date <= today <= end_date
    if is_current:
        days_in_period = (min(end_date, today) - start_date).days + 1
    else:
        days_in_period = (end_date - start_date).days + 1

    # Period-level "unbeaten" streak: how many consecutive PRECEDING periods
    # (of this same unit, in chronological order — gaps with no data are
    # simply skipped over, same convention as the single-day version) had
    # strictly less total than this period's — i.e. how long this period's
    # total has stood unbeaten.
    period_unbeaten = 0
    if total_min > 0:
        sorted_keys = sorted(period_totals.keys())
        if this_key in sorted_keys:
            idx = sorted_keys.index(this_key)
            j = idx - 1
            while j >= 0:
                if period_totals[sorted_keys[j]] < total_min:
                    period_unbeaten += 1
                    j -= 1
                else:
                    break

    # Best streak HELD AT ANY POINT during this period: the global,
    # not-period-bounded running streak (same definition as get_today_stats'
    # single-day streak, extending backward past the period's start if that
    # streak was already running), evaluated as of each day in the period,
    # then taken as a max — "what was the highest streak you were holding
    # while inside this time frame," not a streak confined to the window.
    _study_dates_all = {_date.fromisoformat(ds) for ds, _dur, _sk in _sessions_all}
    all_worked_sorted = sorted(_study_dates_all)
    run_at: dict = {}
    run = 0
    prev = None
    for d in all_worked_sorted:
        run = run + 1 if (prev is not None and (d - prev).days == 1) else 1
        run_at[d] = run
        prev = d
    best_streak_in_period = max(
        (run_at[d] for d in all_worked_sorted if start_date <= d <= end_date),
        default=0,
    )

    conn.close()

    # Per-day series (date, total_min, skill_breakdown) for the bar chart —
    # callers bucket this into weeks themselves for the Y granularity.
    daily_series = []
    last = min(end_date, today) if is_current else end_date
    d = start_date
    while d <= last:
        ds = d.isoformat()
        daily_series.append((d, day_totals.get(ds, 0), day_skill_totals.get(ds, {})))
        d += _td(days=1)

    return {
        "total_min":                   total_min,
        "sessions":                    sessions,
        "skill_breakdown":             skill_breakdown,
        "best_period_min":             best_period_min,
        "avg_period_min":              avg_period_min,
        "percentile":                  percentile,
        "period_rank":                 period_rank,
        "total_periods":               total_periods,
        "thresholds":                  thresholds,
        "best_streak_in_period":       best_streak_in_period,
        "period_unbeaten":             period_unbeaten,
        "days_worked":                 days_worked,
        "days_in_period":              days_in_period,
        "days_in_period_full":         (end_date - start_date).days + 1,
        "daily_series":                daily_series,
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
    """Return {date_str: total_minutes} keyed by study date (not wall-clock date)."""
    from datetime import date as _date, timedelta as _td
    end_h = load_settings().get("day_end_hour", 3)
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date, time, duration FROM pomodoro_session WHERE date IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    result: dict = {}
    for ds, ts, dur in rows:
        if not ds or not dur:
            continue
        try:
            d = _date.fromisoformat(ds)
            if end_h and ts and ts < f"{end_h:02d}:00:00":
                d -= _td(days=1)
            key = d.isoformat()
        except (ValueError, TypeError):
            key = ds
        result[key] = result.get(key, 0.0) + dur
    return result


def get_streak(target_date=None) -> int:
    """Return consecutive-day streak ending on or before target_date (default: today)."""
    from datetime import date, timedelta
    if target_date is None:
        target_date = study_date()
    end_h = load_settings().get("day_end_hour", 3)
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date, time FROM pomodoro_session WHERE date IS NOT NULL ORDER BY date DESC, time DESC")
    # Normalize stored dates to study dates
    study_dates_seen: set = set()
    for ds, ts in c.fetchall():
        try:
            d = date.fromisoformat(ds)
            if end_h and ts and ts < f"{end_h:02d}:00:00":
                d -= timedelta(days=1)
            study_dates_seen.add(d)
        except (ValueError, TypeError):
            continue
    conn.close()
    rows = sorted(study_dates_seen, reverse=True)
    if not rows:
        return 0
    # Find the most recent study date <= target_date
    anchor = None
    for d in rows:
        if d <= target_date:
            anchor = d
            break
    if anchor is None:
        return 0
    # For today-view: allow streak if last session was today or yesterday
    # For past days: require the anchor to be exactly the target date
    if target_date == study_date():
        if anchor < target_date - timedelta(days=1):
            return 0
    else:
        if anchor != target_date:
            return 0
    streak = 0
    expected = anchor
    for d in rows:
        if d > target_date:
            continue
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break
    return streak


# ── Records ────────────────────────────────────────────────────────────────────

def get_best_periods(period: str = "day") -> list:
    """Return records sorted best-first.

    period: 'day' | 'week' | 'month'
    Each record: {label, total_min, breakdown: {skill: min}, dates: [date_str, ...]}
    """
    from datetime import date as _date, timedelta as _td

    sessions = _normalized_sessions()
    if not sessions:
        return []

    if period == "day":
        def key_fn(ds):
            return ds
    elif period == "week":
        def key_fn(ds):
            d = _date.fromisoformat(ds)
            monday = d - _td(days=d.weekday())
            return monday.isoformat()
    else:  # month
        def key_fn(ds):
            return ds[:7]

    groups: dict = {}
    for ds, dur, sk in sessions:
        key = key_fn(ds)
        g = groups.setdefault(key, {"total": 0, "dates": set(), "breakdown": {}, "count": 0})
        g["total"] += dur
        g["dates"].add(ds)
        g["count"] += 1
        if sk:
            g["breakdown"][sk] = g["breakdown"].get(sk, 0) + dur

    result = []
    for g in groups.values():
        dates_sorted = sorted(g["dates"])
        if period == "day":
            d = _date.fromisoformat(dates_sorted[0])
            label = d.strftime("%a, %d %b %Y")
        elif period == "week":
            d1 = _date.fromisoformat(dates_sorted[0])
            d2 = _date.fromisoformat(dates_sorted[-1])
            label = f"{d1.strftime('%d %b')} – {d2.strftime('%d %b %Y')}"
        else:
            d = _date.fromisoformat(dates_sorted[0])
            label = d.strftime("%B %Y")
        result.append({"label": label, "total_min": g["total"],
                       "breakdown": g["breakdown"], "dates": dates_sorted,
                       "session_count": g["count"]})

    result.sort(key=lambda r: r["total_min"], reverse=True)
    return result


def get_all_streaks() -> list:
    """Return all streaks sorted longest-first.
    Each: {length, start_date, end_date}
    """
    from datetime import date as _date, timedelta

    sessions = _normalized_sessions()
    streaks = []
    if not sessions:
        return streaks

    dates = sorted({_date.fromisoformat(ds) for ds, _dur, _sk in sessions})

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
    from datetime import date as _date

    sessions = _normalized_sessions(skill=skill)
    day_totals: dict = {}
    for ds, dur, _sk in sessions:
        day_totals[ds] = day_totals.get(ds, 0) + dur

    result = []
    for date_s, total in day_totals.items():
        try:
            d = _date.fromisoformat(date_s)
            label = d.strftime("%a, %d %b %Y")
        except Exception:
            label = date_s
        result.append({"label": label, "total_min": total or 0, "date_s": date_s})
    result.sort(key=lambda r: r["total_min"], reverse=True)
    return result


# DB initialisieren beim Laden
initialize_db()
