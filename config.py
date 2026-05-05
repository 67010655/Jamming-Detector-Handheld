WIDTH = 480
HEIGHT = 320

SAMPLE_COUNT = 8192
CENTER_FREQ = 1575.42e6
SAMPLE_RATE = 1.0e6
GAIN = 7.7

FPS = 10

ALPHA_IDLE = 0.97
ALPHA_ALERT = 0.998
STATIC_MODE = True  # Set to True for Chamber/Lab experiments (Fixed Baseline)
                    # Set to False for Field use (Adaptive Baseline)

FLOOR_RISE_THRESHOLD = 20.0
PEAK_THRESHOLD = 40.0

WARN_FLOOR = 15.0
WARN_PEAK = 36.0

DC_BINS = 10
HIT_FRAMES = 2
CLEAR_FRAMES = 2

LED_RED_PIN = 17        # GPIO17 (Physical Pin 11) for RED LED (JAMMING state)
LED_YELLOW_PIN = 27     # GPIO27 (Physical Pin 13) for YELLOW LED (WATCH state)
LED_GREEN_PIN = 26      # GPIO26 (Physical Pin 37) for GREEN LED (SCANNING state)
BUZZER_PIN = 18         # GPIO18 (Physical Pin 12) for piezo buzzer