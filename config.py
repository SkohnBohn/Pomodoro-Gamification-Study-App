import os

# SQL-Lite DB 
DB_FILE = os.path.expanduser("~/Desktop/Pomodoro/DB/pomodoro_sessions.db")
# nur DB heißt sessions, table heißt session 

# Level-Grenzen (in Stunden)
LEVEL_THRESHOLDS = [25, 30, 40, 55, 75, 100, 130, 165, 205, 250, 300, 355, 415, 480, 550, 630, 720, 820, 930, 1050] # 20 level

# Pfad zu Badge-Bildern
BADGE_DIR = os.path.expanduser("~/Desktop/Pomodoro/badges")

# Sound-Datei
ALARM_SOUND = "alarm.mp3"
