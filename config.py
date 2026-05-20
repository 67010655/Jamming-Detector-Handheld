WIDTH = 480
HEIGHT = 320

SAMPLE_COUNT = 8192
CENTER_FREQ = 1575.42e6
SAMPLE_RATE = 1.024e6
GAIN = 7.7

FPS = 10

ALPHA_IDLE = 0.97
ALPHA_ALERT = 0.998 
STATIC_MODE = False  # Set to True for Chamber/Lab experiments (Fixed Baseline)
                    # Set to False for Field use (Adaptive Baseline)

FLOOR_RISE_THRESHOLD = 15.0
PEAK_THRESHOLD = 28.0

WARN_FLOOR = 8.0
WARN_PEAK = 24.0

DC_BINS = 10
HIT_FRAMES = 3
CLEAR_FRAMES = 20

LED_RED_PIN = 17        # GPIO17 (Physical Pin 11) for RED LED (JAMMING state)
LED_YELLOW_PIN = 27     # GPIO27 (Physical Pin 13) for YELLOW LED (WATCH state)
LED_GREEN_PIN = 26      # GPIO26 (Physical Pin 37) for GREEN LED (SCANNING state)
BUZZER_PIN = 18         # GPIO18 (Physical Pin 12) for piezo buzzer

# ── Buzzer Alert Setup ───────────────────────────────────────────────
# Available profiles: "STANDARD" (default beep), "PREMIUM_CHIME" (harmonic chimes),
#                     "SIREN_WARP" (siren frequency sweep), "CUSTOM" (user defined)
BUZZER_PROFILE = "SIREN_WARP"

# Custom tone configuration (Melodies / Multi-frequency note sequences)
# Each note is defined as: (frequency_hz, duration_s, gap_duration_s)
# 0 frequency is treated as a rest (silence).
CUSTOM_BUZZER_TONES = {
    "STARTUP": [
        (880, 0.08, 0.02),
        (1109, 0.08, 0.02),
        (1318, 0.15, 0.0)
    ],
    "SCANNING": [
        (1000, 0.05, 0.05),
        (1000, 0.05, 0.0)
    ],
    "WATCH": [
        (1200, 0.06, 0.04),
        (1500, 0.06, 0.0)
    ],
    "JAMMING": [
        (1800, 0.05, 0.02),
        (1800, 0.05, 0.02),
        (2200, 0.12, 0.0)
    ]
}