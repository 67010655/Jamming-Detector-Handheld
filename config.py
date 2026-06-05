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

DEFAULT_NOISE_FLOOR_DB = -89.9  # Chamber baseline / fallback when no calibration data
HIT_FRAMES = 3
CLEAR_FRAMES = 10

# ── Baseline Guard Thresholds ──────────────────────────────────────────
GUARD_HIGH_THRESHOLD = 8.0     # dB above calibrated_base_nf → lock baseline
GUARD_RELEASE_THRESHOLD = 5.0  # dB above calibrated_base_nf → release lock

# ── Hardware Comms ─────────────────────────────────────────────────────
SPI_CLOCK_HZ = 24_000_000      # ILI9488 SPI bus speed (24 MHz)

# ── IMU Orientation Setup ──────────────────────────────────
IMU_MODEL = 'GY-9250'   # Permanent IMU model for this build
IMU_ADDRESS = 0x69      # Keep IMU at 0x69 so it does not collide with DS3231 RTC at 0x68
IMU_GYRO_AXIS = 'X'     # Axis to measure horizontal rotation: 'X', 'Y', or 'Z'
                        # - Use 'Z' if IMU is mounted flat (horizontal)
                        # - Use 'X' or 'Y' if mounted vertically on a wall
IMU_INVERT_GYRO = True  # Invert gyro sign so radar ring matches physical turn (left ↔ left)

# ── Sensor Fusion & Compass Setup ──────────────────────────
IMU_FUSION_MODE = 'COMPLEMENTARY'  # Mode: 'COMPLEMENTARY' (Fused 9-axis), 'GYRO_ONLY' (like MPU6050), 'MAG_ONLY' (True Compass only)
IMU_FUSION_ALPHA = 0.95          # Gyro weight in complementary filter (0.90 to 0.99). Higher = smoother radar, Lower = reacts faster to compass
IMU_MAG_SMOOTH_ALPHA = 0.3       # EMA smoothing on raw mag readings (0.05=very smooth/laggy, 0.3=responsive/noisy)
# Device is mounted VERTICALLY: chip Y axis is vertical (discarded). Heading is
# computed from the two HORIZONTAL axes X and Z. Offsets below from diagnose_magnetometer.py.
IMU_MAG_OFFSET_X = -171.0        # Hard-iron offset for horizontal X axis (circle center)
IMU_MAG_OFFSET_Z = 393.0         # Hard-iron offset for horizontal Z axis (circle center)
IMU_MAG_INVERT = True            # Compass rotated wrong way before invert (verified via live_compass.py)
IMU_DECLINATION_DEG = -0.5       # Local magnetic declination (e.g. -0.5 deg in Bangkok) to align with True North
IMU_COMPASS_OFFSET_DEG = -179.5  # Rotate heading so North reads 0 (calibrated from N/E live readings)

LED_RED_PIN = 17        # GPIO17 (Physical Pin 11) for RED LED (JAMMING state)
LED_YELLOW_PIN = 27     # GPIO27 (Physical Pin 13) for YELLOW LED (WATCH state)
LED_GREEN_PIN = 26      # GPIO26 (Physical Pin 37) for GREEN LED (SCANNING state)
BUZZER_PIN = 18         # GPIO18 (Physical Pin 12) for piezo buzzer
