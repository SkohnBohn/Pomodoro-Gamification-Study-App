import io
import math
import struct
import threading
import wave

import pygame
from config import ALARM_SOUND, SOUND_CLICK

# ── Sound enable flags (toggled from settings) ─────────────────────────────────
sound_click_enabled   = True
sound_levelup_enabled = True
sound_finish_enabled  = True

# ── Alarm ─────────────────────────────────────────────────────────────────────

def play_sound():
    if not sound_finish_enabled:
        return
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(ALARM_SOUND)
        pygame.mixer.music.play()
    except Exception as e:
        print("Fehler beim Abspielen des Sounds:", e)


def play_click():
    if not sound_click_enabled:
        return
    def _go():
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.Sound(SOUND_CLICK).play()
        except Exception as e:
            print("Click sound error:", e)
    threading.Thread(target=_go, daemon=True).start()


# ── Reward sound synthesis ─────────────────────────────────────────────────────

_SR = 44100  # sample rate


def _samples(freq: float, dur: float, amp: float = 0.5,
             attack: float = 0.008, release: float = 0.12) -> list:
    n = int(_SR * dur)
    atk = max(1, int(_SR * attack))
    rel = max(1, int(_SR * release))
    out = []
    for i in range(n):
        t = i / _SR
        env = (i / atk if i < atk
               else (n - i) / rel if i > n - rel
               else 1.0)
        # Fundamental + 2nd + 3rd harmonic for warmth
        v = (math.sin(2 * math.pi * freq * t) * 0.60
           + math.sin(2 * math.pi * freq * 2 * t) * 0.25
           + math.sin(2 * math.pi * freq * 3 * t) * 0.15)
        out.append(v * env * amp)
    return out


def _wav(note_seq) -> bytes:
    """Build a WAV from [(freq, duration, amplitude), ...]."""
    pcm = []
    for freq, dur, amp in note_seq:
        pcm.extend(_samples(freq, dur, amp))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(_SR)
        for s in pcm:
            v = int(max(-1.0, min(1.0, s)) * 32767)
            wf.writeframes(struct.pack("<hh", v, v))
    return buf.getvalue()


# Note frequencies
_C5  = 523.25
_E5  = 659.25
_G5  = 783.99
_B5  = 987.77
_C6  = 1046.50
_F5  = 698.46
_A5  = 880.00

# Lazy-build once
_WAV_MAIN  = None  # triumphant 5-note sweep
_WAV_SKILL = None  # bright 4-note arpeggio
_WAV_STAT  = None  # warm 4-note arpeggio


def _ensure():
    global _WAV_MAIN, _WAV_SKILL, _WAV_STAT
    if _WAV_MAIN is None:
        _WAV_MAIN = _wav([
            (_C5, 0.08, 0.38),
            (_E5, 0.08, 0.40),
            (_G5, 0.08, 0.42),
            (_B5, 0.08, 0.44),
            (_C6, 0.38, 0.55),
        ])
    if _WAV_SKILL is None:
        _WAV_SKILL = _wav([
            (_C5, 0.09, 0.42),
            (_E5, 0.09, 0.44),
            (_G5, 0.09, 0.44),
            (_C6, 0.26, 0.50),
        ])
    if _WAV_STAT is None:
        _WAV_STAT = _wav([
            (_C5, 0.09, 0.42),
            (_F5, 0.09, 0.44),
            (_A5, 0.09, 0.44),
            (_C6, 0.26, 0.50),
        ])


def _play(wav_bytes: bytes):
    def _go():
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=_SR, size=-16, channels=2)
            pygame.mixer.Sound(io.BytesIO(wav_bytes)).play()
        except Exception as e:
            print("Sound error:", e)
    threading.Thread(target=_go, daemon=True).start()


def play_main_levelup():
    if not sound_levelup_enabled:
        return
    _ensure()
    _play(_WAV_MAIN)


def play_skill_levelup():
    if not sound_levelup_enabled:
        return
    _ensure()
    _play(_WAV_SKILL)


def play_stat_levelup():
    if not sound_levelup_enabled:
        return
    _ensure()
    _play(_WAV_STAT)
