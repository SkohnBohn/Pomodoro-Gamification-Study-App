import pygame
from config import ALARM_SOUND

def play_sound():
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(ALARM_SOUND)
        pygame.mixer.music.play()
    except Exception as e:
        print("Fehler beim Abspielen des Sounds:", e)
