import sqlite3
from datetime import datetime
from config import DB_FILE

def initialize_db():
    """Erstellt die Tabelle, falls sie noch nicht existiert."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
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
    ''')
    conn.commit()
    conn.close()

def calculate_total_time():
    """Summiert alle gespeicherten Sitzungen (duration) in Minuten und gibt Stunden zurück."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT SUM(duration) FROM pomodoro_session")
    result = c.fetchone()[0]
    conn.close()
    if result is None:
        return 0.0
    return result / 60.0  # Stunden

def save_session(duration, intention, result, skill="Pomodoro"):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Nächste Session-Nummer berechnen
    c.execute("SELECT MAX(sessions) FROM pomodoro_session")
    last_id = c.fetchone()[0] or 0
    session_number = last_id + 1

    # Gesamtdauer bisher
    c.execute("SELECT SUM(duration) FROM pomodoro_session")
    prev_total = c.fetchone()[0] or 0
    total_time = prev_total + duration

    # Einfügen
    c.execute('''
        INSERT INTO pomodoro_session (sessions, date, time, skill, duration, total_time, intention, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session_number, date_str, time_str, skill, round(duration, 2), round(total_time, 2), intention, result))

    conn.commit()
    conn.close()


# DB initialisieren beim Laden
initialize_db()
