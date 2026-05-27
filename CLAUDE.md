# CLAUDE.md — Jamming Detector Handheld

AI agent and developer reference for the **GNSS L1 Jamming Detector Handheld** project.  
Target hardware: **Raspberry Pi Zero 2W** with RTL-SDR, ILI9488 TFT LCD, MPU6050 IMU, DS3231 RTC, LEDs, and active buzzer.

---

## Project Overview

A portable field device that detects GNSS (GPS L1, 1575.42 MHz) jamming signals via a Software-Defined Radio (SDR). The system renders a real-time spectrum display on a 3.5" SPI LCD, logs detection events to SQLite, exposes a web dashboard over Wi-Fi/hotspot, and provides audio/visual alerts through LEDs and a buzzer.

This is a **resource-constrained embedded Python application** running on a single-core Raspberry Pi Zero 2W that simultaneously runs DSP, a GUI renderer, and a Flask web server. Every change must keep CPU and I/O usage minimal.

---

## File Structure

```
main.py              — Entry point; parses --preview flag, launches GPSJammerHandheld
detector.py          — Core class: SDR init, DSP loop, jamming state machine, shutdown
config.py            — All hardware constants and tunable thresholds (single source of truth)
dsp.py               — DSP utilities: FFT power, DC spike removal, spectrum downsampling
display_ui.py        — PIL-based LCD renderer; touch input; three view modes
web_server.py        — Flask API + Waitress WSGI; thread-safe state; serves web/
database_manager.py  — SQLite event logging with adaptive write intervals and auto-pruning
led_control.py       — GPIO LED controller (RED/YELLOW/GREEN)
buzzer.py            — PWM buzzer controller with background queue thread
calibrate_touch.py   — Standalone touchscreen calibration utility
test_sensors.py      — Standalone IMU live-view utility
generate_previews.py — Renders preview PNG images without hardware

hardware/
  mpu6050.py         — MPU6050 I2C gyroscope driver (bearing integration, self-calibration)
  rtc_ds3231.py      — DS3231 RTC driver (BCD read/write; falls back to system time)

web/
  index.html         — Dashboard SPA (Thai/English, dark/light theme toggle)
  style.css          — CSS variables for theme, glassmorphism, state colors
  script.js          — Canvas-based spectrum, waterfall, margin trend; poll at 500ms

requirements.txt     — Python dependencies
```

---

## Key Architecture Points

### Main Loop (`detector.py:GPSJammerHandheld.run`)
The single main thread runs at `config.FPS` (10 Hz) and performs in order:
1. Read IMU bearing (or simulate in preview mode)
2. Capture SDR samples (`sdr.read_samples(8192)`)
3. `dsp.compute_power` → FFT → dB
4. `dsp.remove_dc_spike` → eliminate center LO artifact
5. `_detect_jamming` → threshold logic → update `current_state`
6. `led.set_state` / `buzzer.set_state` → hardware feedback
7. `ui.draw_ui` → render LCD frame
8. `web_server.update_state` → push to in-memory state for web API
9. Adaptive SQLite write (see Database Rules below)

### Detection States
| State | Trigger | LED | Buzzer |
|---|---|---|---|
| `SCANNING` | Floor rise < 8 dB AND peak diff < 24 dB | GREEN | 2 × 900 Hz tone |
| `WATCH` | Floor rise > 8 dB OR peak diff > 24 dB | YELLOW | 2 × 1200 Hz tone |
| `JAMMING` | Floor rise > 15 dB OR peak diff > 28 dB (held for 3 frames) | RED | 2 × 1500 Hz tone |

State requires `HIT_FRAMES=3` consecutive detections to activate and `CLEAR_FRAMES=10` to clear.  
The **Smart Baseline Guard** (`baseline_guard_active`) freezes noise-floor adaptation when the floor rises >8 dB above calibrated baseline to prevent a jammer from masking itself by dragging the baseline up.

### Threading Model
- **Main thread**: DSP loop + LCD rendering
- **Buzzer thread** (`buzzer.py:_worker`): daemon thread consuming a queue; clears stale tones on state change
- **Touch thread** (`display_ui.py`): daemon thread polling XPT2046 SPI touchscreen
- **Web server thread**: Waitress WSGI, 2 worker threads, daemon=True
- All inter-thread state in `web_server.ServerState` is protected by `threading.Lock`.
- `display_ui.DisplayUI._touch_zones` is protected by `threading.RLock`.

### Preview Mode
Run `python main.py --preview` on any machine without hardware to see a rendered `preview.png`.
- Skips SDR init, GPIO, DB init
- Generates synthetic IQ noise + tone samples
- Simulates slow compass rotation
- Disables LED and buzzer hardware
- All other code paths (detection, UI rendering) run identically

---

## Configuration Reference (`config.py`)

| Constant | Default | Purpose |
|---|---|---|
| `WIDTH` / `HEIGHT` | 480 / 320 | LCD resolution |
| `SAMPLE_COUNT` | 8192 | FFT size |
| `CENTER_FREQ` | 1575.42e6 | GPS L1 center frequency (Hz) |
| `SAMPLE_RATE` | 1.024e6 | RTL-SDR sample rate |
| `GAIN` | 7.7 | SDR gain (dB) |
| `FPS` | 10 | Target frame rate |
| `ALPHA_IDLE` | 0.97 | EMA alpha for noise floor in SCANNING |
| `ALPHA_ALERT` | 0.998 | EMA alpha during WATCH (slower adaptation) |
| `STATIC_MODE` | False | True = chamber/fixed baseline; False = adaptive field mode |
| `FLOOR_RISE_THRESHOLD` | 15.0 | dB floor rise → JAMMING |
| `PEAK_THRESHOLD` | 28.0 | dB peak above baseline → JAMMING |
| `WARN_FLOOR` | 8.0 | dB floor rise → WATCH |
| `WARN_PEAK` | 24.0 | dB peak above baseline → WATCH |
| `DC_BINS` | 10 | Bins masked around DC spike |
| `DEFAULT_NOISE_FLOOR_DB` | -89.9 | Fallback baseline / chamber reference |
| `HIT_FRAMES` | 3 | Consecutive frames to enter JAMMING |
| `CLEAR_FRAMES` | 10 | Consecutive frames to exit JAMMING |
| `IMU_ADDRESS` | 0x69 | MPU6050 I2C address |
| `IMU_GYRO_AXIS` | 'X' | Gyro axis used for bearing integration |
| `IMU_INVERT_GYRO` | True | Flip rotation sign |
| `LED_RED_PIN` | 17 | GPIO (BCM) for JAMMING LED |
| `LED_YELLOW_PIN` | 27 | GPIO (BCM) for WATCH LED |
| `LED_GREEN_PIN` | 26 | GPIO (BCM) for SCANNING LED |
| `BUZZER_PIN` | 18 | GPIO (BCM) for buzzer PWM |

**Do not hard-code any of these values in other modules.** Always import from `config`.

---

## Hardware & Safety Rules

### CRITICAL — I2C Voltage
- **Never apply 5V to the MPU6050 AD0 pin.** The chip is not 5V tolerant. Doing so causes latch-up, overheats the chip, and can crash the Wi-Fi hotspot by dragging down the power rail.
- MPU6050 is at **I2C address 0x69** (AD0 tied to 3.3V). DS3231 RTC is at **0x68**.
- Both share **I2C1** (SDA: Pin 3, SCL: Pin 5). This is intentional; no conflicts as addresses differ.

### SPI Bus (Display + Touch)
- ILI9488 LCD and XPT2046 touchscreen share **SPI0** with separate CS lines:
  - `LCD_CS` → GPIO 8 (Pin 24)
  - `T_CS` → GPIO 22 (Pin 15)
- Do **not** change SPI pins or the ILI9488 initialization parameters. Wrong values cause a white screen or continuous touch phantom events.
- Never connect/disconnect SPI jumpers while the Pi is powered on — the LCD is fragile.

### Power Budget
- RTL-SDR draws 300–500 mA. Combined with LCD and Wi-Fi, sustained 100% CPU load causes under-voltage, which drops the Wi-Fi hotspot.
- Do not write CPU-spin loops or increase SQLite write frequency without necessity.

### GPIO Pin Summary
| Signal | GPIO (BCM) | Physical Pin |
|---|---|---|
| SPI MOSI | 10 | 19 |
| SPI MISO | 9 | 21 |
| SPI SCLK | 11 | 23 |
| LCD CS | 8 | 24 |
| LCD DC | 24 | 18 |
| LCD RST | 25 | 22 |
| Touch CS | 22 | 15 |
| I2C SDA | 2 | 3 |
| I2C SCL | 3 | 5 |
| RED LED | 17 | 11 |
| YELLOW LED | 27 | 13 |
| GREEN LED | 26 | 37 |
| Buzzer | 18 | 12 |
| Mute Switch | 23 | 16 |
| Wi-Fi Toggle | 16 | 36 |

---

## Database Rules (SD Card Protection)

SQLite DB path: `jamming_events.db` (same directory as `main.py`)

**Adaptive write intervals — do not change:**
- State unchanged + `SCANNING`: write every **30 seconds**
- State unchanged + `WATCH` or `JAMMING`: write every **3 seconds**
- State transition (any → any): write **immediately**

**Auto-pruning:** `log_event` deletes rows beyond the 1,000 most recent non-STARTUP records after every insert. `STARTUP` rows are kept permanently for session baseline reference.

**Schema migration:** `init_db` checks for the `bearing_deg` column and adds it if missing, supporting older database files.

---

## Web Dashboard Rules

- **API poll interval**: 500 ms minimum (`POLL_MS = 500` in `script.js`). Do not reduce.
- **Spectrum downsampling**: Power array is always reduced to ≤240 points before sending over the API (`web_server.py:ServerState.update`). This must be preserved.
- **Rendering rates** (client-side): Spectrum + Margin Trend at 4 Hz; Waterfall Spectrogram at 2 Hz — achieved via event-driven canvas rendering, not polling.
- **Authentication**: Optional token via `GUNJAM_API_TOKEN` env var. When set, all `/api/*` routes require `X-API-Token` header or `?token=` query param.
- **Web server**: Runs in a daemon thread using Waitress (`threads=2`). Flask's dev server (`app.run`) must never be used.
- **Static assets**: Served from `web/` directory. Logos (`KMITL_Sublogo.svg.png`, `BTFP_Logo.webp`, NBTC seal) are Thai institutional branding — keep them.
- **Styling**: Dark/light theme via CSS `data-theme` attribute; theme toggled by a button in the header. State colors (green/yellow/red) are CSS variables tied to `data-state` attribute on the state badge. Maintain the dark glassmorphism aesthetic.

---

## Development Workflows

### Running in Preview Mode (No Hardware Required)
```bash
pip install -r requirements.txt
python main.py --preview
```
Renders one frame to `preview.png`. Use `generate_previews.py` to render all UI modes.

### Generating UI Previews
```bash
python generate_previews.py
```
Outputs PNG screenshots for all view modes to `preview_example/`.

### Testing Sensors on Hardware
```bash
# IMU live bearing readout
python test_sensors.py

# Touchscreen calibration
python calibrate_touch.py
```

### Running on Raspberry Pi
```bash
sudo python main.py
```
Requires `sudo` for GPIO access. The web dashboard is available at `http://<pi-ip>:8080`.

### Installing Dependencies
```bash
pip install -r requirements.txt
# On Raspberry Pi, RPi.GPIO and spidev come from system packages:
# sudo apt install python3-rpi.gpio python3-spidev
```

---

## Code Conventions

- **All hardware constants** live in `config.py`. Never duplicate them inline.
- **Preview/hardware branches**: Conditioned on `self.preview` in `GPSJammerHandheld`. Hardware-only code is always guarded with `if not self.preview:`.
- **Hardware imports** (`RPi.GPIO`, `spidev`, `smbus2`, `rtlsdr`) are wrapped in `try/except ImportError` at module level so the code loads on non-Pi machines for preview mode.
- **Logging prefix convention**: `[MODULE]` prefix in print statements (e.g. `[SDR]`, `[IMU]`, `[DATABASE]`, `[WEB]`, `[LED]`, `[BUZZER]`, `[SYSTEM]`, `[UI]`, `[ERROR]`).
- **No blocking I/O in the main loop**: Database writes, web updates, and buzzer tones are either non-blocking (Waitress thread, buzzer queue) or timed to be infrequent.
- **Minimal Invasive principle**: Only change code directly relevant to the task. Do not refactor, rename, or reformat surrounding code without explicit instruction.
- **No placeholders**: All code must be complete and functional. No `# TODO` stubs.

---

## Constraints for AI Agents

1. **Do not introduce CPU-bound loops** that run without sleeping. The Pi Zero 2W is already near capacity.
2. **Do not increase SQLite write frequency** beyond the adaptive intervals above.
3. **Do not modify SPI pin assignments** (`LCD_CS`, `T_CS`, `DC`, `RST`) or the ILI9488 `spi()` initialization.
4. **Do not change web polling** below 500ms.
5. **Do not use Flask's development server** (`app.run`). Always use Waitress.
6. **Do not add `time.sleep()` calls in the main detection loop** beyond the frame-rate throttle already in place.
7. **Preserve the spectrum downsampling** to ≤240 points in `web_server.py` and `dsp.py`.
8. **Keep `STARTUP` events** exempt from the 1,000-row pruning limit.
9. **IMU and RTC share I2C1** — never reconfigure I2C bus numbers or add separate `smbus2.SMBus` instances for each sensor unnecessarily.
10. **Never write 5V to MPU6050 AD0** — this is a hardware-irreversible error; any code generating GPIO output to I2C-adjacent pins must be reviewed carefully.
