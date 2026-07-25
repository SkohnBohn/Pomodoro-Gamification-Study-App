import os

BASE_DIR    = os.path.expanduser("~/Desktop/Pomodoro/NEWUI")

DB_NEWUI = os.path.expanduser("~/Desktop/Pomodoro/NEWUI/DB/pomodoro_sessions.db")
DB_MAIN  = os.path.expanduser("~/Desktop/Pomodoro/DB/pomodoro_sessions.db")

DB_FILE       = DB_MAIN  # active DB — reassigned at runtime by _switch_db()
BADGE_DIR     = os.path.expanduser("~/Desktop/Pomodoro/badges")
SETTINGS_FILE = "/Users/sky/Desktop/Pomodoro/global_settings"

SOUNDS_DIR    = os.path.join(os.path.dirname(__file__), "sounds")
SOUND_CLICK   = os.path.join(SOUNDS_DIR, "click.mp3")
ALARM_SOUND = os.path.join(BASE_DIR, "alarm.mp3")

LEVEL_THRESHOLDS = [
    25, 30, 40, 55, 75, 100, 130, 165, 205, 250,
    300, 355, 415, 480, 550, 630, 720, 820, 930, 1050,
]

SKILLS = ["SOZ", "SUR", "MATH", "JOURNAL", "TECH", "UNI", "DESIGN", "ORGA"]
SKILL_EMOJIS = {
    "SOZ": "🧠", "SUR": "🎨", "MATH": "📐",
    "JOURNAL": "📝", "TECH": "💻", "UNI": "🎓", "DESIGN": "✏️", "ORGA": "📋",
}
SKILL_THRESHOLDS = [5, 10, 20, 35, 55, 80, 110, 145, 185, 230, 280, 335]

STAT_THRESHOLDS = {
    "hours":    [5, 10, 25, 50, 100, 250, 500, 750, 1000, 1300, 1600, 2000, 2500],
    "minutes":  [20, 60, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000],
    "sessions": [1, 3, 5, 10, 25, 50, 100, 250, 500, 2000, 5000, 10000],
    "over30":   [1, 3, 5, 10, 25, 50, 100, 250, 500, 2000, 5000, 10000],
    "over60":   [1, 3, 5, 10, 25, 50, 100, 250, 500, 2000, 5000, 10000],
}
