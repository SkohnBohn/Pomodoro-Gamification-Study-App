import os

BASE_DIR    = os.path.expanduser("~/Desktop/Pomodoro/NEWUI")
DB_FILE     = os.path.join(BASE_DIR, "DB", "pomodoro_sessions.db")
BADGE_DIR   = os.path.expanduser("~/Desktop/Pomodoro/badges")
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
