# Code Review — GUNJAM Handheld GNSS Jamming Detector

**Reviewer:** Antigravity (AI Senior Engineer — outsider full-codebase audit)
**Date:** 30 May 2026
**Status:** **APPROVED WITH NOTES** — production-ready for field deployment; two concrete bugs should be fixed before next release
**Scope:** Full source review of `main` branch — every `.py`, `.js`, `.html`, `.css` file in the repo (18 source files, ~4,281 LOC total)

**Files reviewed:**

| File | Lines | Role |
|------|------:|------|
| `main.py` | 16 | CLI entry point |
| `detector.py` | 564 | Core orchestrator + state machine |
| `config.py` | 45 | Centralised constants |
| `dsp.py` | 85 | Pure DSP functions |
| `database_manager.py` | 148 | SQLite persistence layer |
| `display_ui.py` | 970 | ILI9488 LCD + XPT2046 touch driver |
| `web_server.py` | 207 | Flask/Waitress web dashboard API |
| `buzzer.py` | 130 | PWM buzzer controller |
| `led_control.py` | 99 | GPIO LED state indicator |
| `calibrate_touch.py` | 271 | 4-point touchscreen calibrator |
| `test_sensors.py` | 40 | IMU live-view diagnostic |
| `generate_previews.py` | 128 | Offline screenshot generator |
| `hardware/mpu6050.py` | 150 | 6-DoF IMU gyro driver |
| `hardware/mpu9250.py` | 215 | 9-DoF IMU + AK8963 magnetometer |
| `hardware/rtc_ds3231.py` | 78 | RTC I2C driver |
| `web/index.html` | 235 | Dashboard HTML |
| `web/script.js` | 778 | Dashboard client-side logic |
| `tests/test_dsp.py` | 122 | DSP unit tests (pytest) |

**Post-review fix status (30 May 2026):** The two concrete bugs called out in this report have been addressed after this audit. SQLite connections in `database_manager.py` now close through `finally` blocks, including the startup migration path, and the dashboard particle loop now cancels/resumes via `visibilitychange` instead of continuing RAF callbacks while hidden. Verification passed with Python compile, `node --check`, targeted close-on-exception checks, and `18 passed` in pytest.

---

## 1. Executive Summary

GUNJAM is a handheld GNSS jamming detector running on Raspberry Pi Zero 2W. The system reads RF samples from an RTL-SDR dongle, runs real-time FFT-based power analysis, classifies signal state via a multi-stage state machine (`SCANNING → WATCH → JAMMING`), renders results on a 480×320 ILI9488 LCD with touch control, and exposes a web dashboard on port 8080.

**Overall Assessment:** The codebase is well-structured for an embedded RF project. The DSP domain logic is correct and well-tuned. Thread synchronisation is handled carefully. The web dashboard delivers smooth real-time visualisation. Two concrete bugs were found: SQLite connection leaks on error paths, and the particle animation wasting CPU on hidden tabs. The structural concern of a growing orchestrator class is noted but is not blocking.

| Category | Score | Evidence |
|----------|-------|----------|
| Domain Logic / DSP | **10 / 10** | Adaptive NF via EMA (`dsp.py:3–5`), baseline guard lock/release (`detector.py:190–203`), hit/clear debounce (`detector.py:169–179`) — all correct and well-tuned. |
| Architecture | **8 / 10** | `DisplayUI` decoupling complete (`display_ui.py:74–75`); `GPSJammerHandheld` at 564 lines is a god class mixing SDR, state machine, UI, DB, GPS, IMU, web, and shutdown. |
| Thread Safety | **9 / 10** | `threading.Event` for control signals (`detector.py:60–62`); `RLock` atomic zone swap (`display_ui.py:628–629`); `_clear_lock` race fix (`web_server.py:162–175`). |
| Reliability | **8 / 10** | SQLite WAL (`database_manager.py:11–12`); RTC bus guard (`rtc_ds3231.py:26, 65`); frozen sensor recovery (`mpu6050.py:115–121`). **Deducted 1 point:** connection leak on exception in all `database_manager.py` functions — see §4.5. |
| Performance | **9 / 10** | AABB + squared-distance particle filter (`script.js:757–763`); event-driven canvas redraws (`script.js:528`). **Deducted 1 point:** `Math.sqrt` still called inside the hot loop for connected pairs (`script.js:764`), and `animateParticles` runs `requestAnimationFrame` on hidden tabs (`script.js:714–716`). |
| Security | **8.5 / 10** | Waitress WSGI (`web_server.py:7, 188`); trusted-LAN model with comment explaining token auth omission (`web_server.py:24–25`); rate-limited `POST /api/clear` with atomic lock (`web_server.py:162–175`). |
| Code Quality | **8.5 / 10** | Constants centralised in `config.py`; 18 DSP unit tests; HTML uses `escHtml()` for log rendering (`script.js:549–551`). God class remains as deferred tech debt. |
| Web Dashboard UI/UX | **9.5 / 10** | Responsive dark/light theme; smooth spectrum morphing (`script.js:253–301`); waterfall spectrogram; session statistics. DOM write throttling via `setDomText()` (`script.js:45–51`). **Deducted 0.5:** particle animation fires RAF on hidden tabs, wasting battery on mobile. |

---

## 2. Architecture

### 2.1 `DisplayUI ↔ GPSJammerHandheld` Decoupling — RESOLVED

Drawing context (`_img`, `_draw`, image buffer) are fully encapsulated within `DisplayUI` (`display_ui.py:74–75`). The orchestrator passes `metrics` and `power` arrays to `draw_ui()` (`detector.py:343`), never touching the drawing surface directly. The only place the orchestrator accesses `_draw` is during shutdown screen-clear (`detector.py:537`), which is an acceptable edge case.

### 2.2 God Class: `GPSJammerHandheld` — OPEN

`detector.py` (564 lines) orchestrates SDR sampling, FFT, state machine, UI updates, database writes, IMU reads, keyboard input, web state pushes, and shutdown/reboot handling in a single class. At this size it is manageable today, but any significant new feature (GPS parsing, magnetometer heading, data logging modes) risks entangling concerns.

**Suggested future split:**
- `SignalProcessor` — SDR read, FFT, `_detect_jamming()` state machine
- `DataLogger` — database writes, logging intervals, export
- `InputHandler` — keyboard dispatch, touch events

**Status:** Deferred to post-v1 roadmap.

### 2.3 Display and Hardware Constants Centralised — RESOLVED

All magic numbers are in `config.py` (45 lines):
- Screen: `WIDTH=480`, `HEIGHT=320` (line 1–2)
- SDR: `SAMPLE_COUNT=8192`, `CENTER_FREQ=1575.42e6`, `SAMPLE_RATE=1.024e6`, `GAIN=7.7` (lines 4–7)
- SPI: `SPI_CLOCK_HZ=24_000_000` (line 33)
- IMU: `IMU_ADDRESS`, `IMU_GYRO_AXIS`, `IMU_INVERT_GYRO` (lines 36–40)
- GPIO: `LED_RED_PIN=17`, `LED_YELLOW_PIN=27`, `LED_GREEN_PIN=26`, `BUZZER_PIN=18` (lines 42–45)

Hardware porting is localised to this single file.

---

## 3. Thread Safety

### 3.1 Control Signals via `threading.Event` — RESOLVED

Three cross-thread control signals at `detector.py:60–62`:
```python
self.request_calibration = threading.Event()
self.shutdown_requested = threading.Event()
self.reboot_requested = threading.Event()
```
Main loop checks with `.is_set()` (`detector.py:311, 318, 322`); touch thread sets them (`display_ui.py:921, 923, 945`). `threading.Event` guarantees cross-thread visibility without raw boolean races.

### 3.2 Atomic Touch Zone Updates — RESOLVED

Touch button zones are rebuilt into a local `_new_zones` dict during each `draw_ui()` frame, then swapped atomically at `display_ui.py:628–629`:
```python
with self._zones_lock:
    self._touch_zones = _new_zones
```
The touch handler thread copies the zone dict under the same `RLock` at `display_ui.py:909–910`:
```python
with self._zones_lock:
    zones = dict(self._touch_zones)
```
The touch thread never sees a partially-updated zone map.

### 3.3 `_last_clear_time` Race on `/api/clear` — FIXED

Two concurrent `POST /api/clear` requests could previously both pass the rate-limit check before either updated `_last_clear_time`. Fixed by adding `_clear_lock = threading.Lock()` at `web_server.py:162` and performing the check-and-reserve atomically inside the lock before the database call (`web_server.py:168–175`):
```python
with _clear_lock:
    if now - _last_clear_time < _CLEAR_RATE_LIMIT_S:
        ...return 429...
    success = database_manager.clear_db()
    if success:
        _last_clear_time = now
```

### 3.4 SPI Bus Sharing Between LCD and Touch — RESOLVED

The ILI9488 display and XPT2046 touch controller share SPI0 with separate CS pins (LCD: GPIO 8, Touch: GPIO 22). `display_ui.py` guards all SPI access with `self._spi_lock = threading.Lock()` (line 40):
- Touch reads: `_read_xpt2046()` acquires `_spi_lock` (line 833)
- Display writes: `draw_ui()` and `draw_splash()` acquire `_spi_lock` (lines 318, 635)

No SPI bus contention between the touch worker thread and the main rendering loop.

---

## 4. Reliability

### 4.1 SQLite WAL Mode — IMPLEMENTED

`database_manager.py:8–13` — `_get_connection()` opens every connection with:
```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```
The web server thread reads event history concurrently with the main loop writing jamming events without lock contention or UI pauses.

### 4.2 Database Pruning — IMPLEMENTED

`database_manager.py:59–65` — After every `INSERT`, a cleanup query retains only the latest 1,000 non-STARTUP records. STARTUP records are preserved permanently to maintain session baselines across restarts. This prevents SD card fill on long field deployments.

### 4.3 Preview State Snapshot — IMPLEMENTED

`generate_previews.py:26–28` saves and restores `(noise_floor, jammer_active, current_state, jam_hits, clear_hits)` before and after injecting synthetic signals via `_detect_jamming()`. Preview generation cannot corrupt live detector state.

### 4.4 Hardware Bus Safety

**RTC (DS3231):** `hardware/rtc_ds3231.py` guards every I2C method with `if self.bus is None: return` (lines 26, 65). Windows debugging and offline CI runs gracefully fall back to system time.

**IMU (MPU6050):** `hardware/mpu6050.py:58` — `read_raw_data()` returns `None` if `self.bus is None`. Frozen sensor recovery triggers re-initialisation after 40 identical non-zero readings (lines 115–121).

**IMU (MPU9250):** `hardware/mpu9250.py` — Same pattern: bus-None guards (lines 100, 142, 188), frozen sensor recovery (lines 156–162), and AK8963 magnetometer access via I2C bypass mode (lines 73–81). This driver enables future compass-heading functionality without affecting the existing MPU6050 pipeline.

### 4.5 ⚠️ SQLite Connection Leak on Exception — BUG (NEW FINDING)

**All four public functions** in `database_manager.py` (`log_event`, `get_history`, `get_filtered_history`, `clear_db`) open a connection with `_get_connection()` inside a `try` block but only call `conn.close()` in the **success path**. If any `execute()` or `commit()` raises, the connection leaks.

**Affected locations:**
- `log_event()` — `conn.close()` at line 68, inside `try` after `conn.commit()` at line 67
- `get_history()` — `conn.close()` at line 85, inside `try` after `cursor.fetchall()` at line 79
- `get_filtered_history()` — `conn.close()` at line 100, inside `try` after `cursor.fetchall()` at line 99
- `clear_db()` — `conn.close()` at line 136, inside `try` after `conn.commit()` at line 135

**Impact:** Under sustained failure scenarios (full SD card, corrupted DB file), leaked connections accumulate. SQLite's WAL mode limits concurrent readers to one writer, so leaked writer connections can block subsequent writes.

**Suggested fix:** Use `try/finally` in every function:
```python
def log_event(...):
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(...)
        cursor.execute(...)   # prune
        conn.commit()
    except Exception as e:
        print(f"[DATABASE] Error logging event: {e}")
    finally:
        conn.close()
```

**Priority:** P1 — simple fix, high reliability impact.

### 4.6 Schema Migration — IMPLEMENTED

`database_manager.py:33–41` — `init_db()` checks for the `bearing_deg` column using `PRAGMA table_info(events)` and applies `ALTER TABLE` if missing. This supports upgrading from older database files without data loss.

---

## 5. Performance

### 5.1 Particle Connection Optimisation — IMPLEMENTED

Particle-to-particle connection checks in `web/script.js:754–772` use:
1. **AABB early-out** — `if (Math.abs(dx) >= CONNECTION_DIST) continue` (line 757) before the more expensive distance check.
2. **Squared-distance filter** — `dx*dx + dy*dy < CONNECTION_DIST_SQ` (line 763) eliminates most candidates without `Math.sqrt`.
3. **Tiered particle count** — `LOW_POWER_VISUALS ? 0 : (isMobile ? 12 : 32)` (line 679) — zero particles on low-power hardware (≤4 cores), 12 on mobile touch devices, 32 on desktop.
4. **`prefers-reduced-motion` respect** — particles disabled entirely when the OS accessibility setting is active (line 703).

**Note:** `Math.sqrt(distSq)` is still called at line 764 for every pair that passes the squared-distance filter, to compute the distance-based line alpha gradient. This is the correct tradeoff — the AABB and squared-distance filters eliminate the vast majority of pairs, so the remaining `sqrt` calls are few.

### 5.2 Event-Driven Canvas Redraws — IMPLEMENTED

`requestAnimationFrame` is triggered only when a new metrics/spectrum payload arrives via `fetchStatus()` (line 528), polling at `POLL_MS = 500ms` intervals (line 6). Canvas redraws happen at most 2 Hz, not on a fixed 60 Hz timer. Battery drain on connected mobile clients is minimal.

Spectrum morphing between data frames uses `easeOutCubic` interpolation at a throttled render FPS (`SPECTRUM_RENDER_FPS`: 8 on low-power, 14 on desktop — line 11), giving smooth visual transitions without wasting CPU on intermediate frames.

### 5.3 DOM Write Throttling — IMPLEMENTED

`setDomText()` (line 45–51) caches the last written value per element ID and skips the DOM write if the value hasn't changed. This avoids forced layout/reflows on every 500ms poll cycle when metrics are stable. Same pattern applied to CSS variable updates in `applyStateTheme()` (line 133).

### 5.4 ⚠️ Particle Animation on Hidden Tabs — MINOR ISSUE

`animateParticles()` at `script.js:713–716` schedules `requestAnimationFrame` even when `document.hidden` is true — it just returns early without drawing. While modern browsers throttle RAF to ~1 Hz on hidden tabs, this still wastes a callback and wakeup per second.

**Suggested fix:**
```js
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && particles.length > 0) requestAnimationFrame(animateParticles);
});
// In animateParticles: if (document.hidden) return;  // don't schedule next
```

**Priority:** P3 — minor battery optimisation.

---

## 6. Security

### 6.1 Waitress WSGI — IMPLEMENTED

Flask's single-threaded development server is replaced with Waitress (`web_server.py:7` import, line 188 call) running on a daemon thread with 2 worker threads. Concurrent API requests are handled correctly. `_quiet=True` suppresses Waitress access logs to avoid cluttering the console.

### 6.2 Network-Level Access Control — BY DESIGN

API token auth is intentionally omitted (`web_server.py:24–25`): the unit serves its dashboard only on a trusted, operator-controlled Wi‑Fi hotspot/LAN, so access is enforced at the network layer (isolated AP + WPA2) rather than per-request.

**If the dashboard is ever exposed beyond that trusted LAN**, add an `X-API-Token` header check (e.g. against a `GUNJAM_API_TOKEN` environment variable) returning 401 on mismatch.

### 6.3 Rate-Limited `POST /api/clear` — IMPLEMENTED + RACE FIXED

A 60-second cooldown (`_CLEAR_RATE_LIMIT_S = 60` at line 161) prevents database abuse. The check-and-reserve is atomic under `_clear_lock` (see §3.3). Remote IP is logged on every successful clear for audit trail (`web_server.py:175`).

### 6.4 Server Startup Port Probe — IMPLEMENTED

`start_server()` at `web_server.py:178–203` probes the port before binding, raises `RuntimeError` with a clear message if the port is occupied, and polls with a 3-second deadline to confirm the server is ready. The main loop catches this and calls `shutdown()` (`detector.py:107–109`), preventing the device from running headless without a dashboard.

### 6.5 HTML Escaping in Log Rendering — IMPLEMENTED

`escHtml()` at `script.js:549–551` escapes `&`, `<`, `>`, `"` in all user-facing log data before insertion via `innerHTML`. While the data originates from the device's own database (not user input), this is a good defence-in-depth practice.

---

## 7. DSP Correctness (Deep Trace)

### 7.1 `compute_power()` — CORRECT

`dsp.py:51–60`:
1. Applies Hanning window to reduce spectral leakage: `windowed = samples * window`
2. Normalises by window sum (not length) for correct amplitude: `fft_norm = fft_raw / window_sum`
3. Uses `fftshift` for centre-frequency-at-centre display convention
4. Adds `1e-12` epsilon to prevent `log10(0)` — returns floor of ~-240 dB for zero input

### 7.2 `remove_dc_spike()` — CORRECT

`dsp.py:63–85`:
1. Operates on a `.copy()` — input array is never mutated (verified by test `test_does_not_modify_input`)
2. Replaces `dc_bins=10` centre bins with the mean of 50-sample neighbour regions on each side
3. Gracefully handles edge cases: if neighbours are empty, falls back to global mean

### 7.3 `smooth_noise()` — CORRECT

`dsp.py:3–5`: Standard EMA formula `α × prev + (1-α) × new`. With `ALPHA_IDLE=0.97` (slow tracking during SCANNING) and `ALPHA_ALERT=0.998` (near-frozen during WATCH), the noise floor adapts to ambient conditions while resisting jammer-induced drift.

### 7.4 Baseline Guard Logic — CORRECT

`detector.py:190–214` implements a two-threshold hysteresis guard:
- **Lock:** current floor > calibrated base + `GUARD_HIGH_THRESHOLD` (8 dB) → freeze NF, force `JAMMING` state
- **Release:** current floor < calibrated base + `GUARD_RELEASE_THRESHOLD` (5 dB) → resume dynamic NF tracking
- **During guard:** noise floor update is completely suppressed (line 206: `if not self.baseline_guard_active`), preventing a powerful jammer from dragging the baseline up and blinding the detector

### 7.5 State Machine Debounce — CORRECT

`detector.py:169–186`:
- `jam_now` requires `hit_frames_required` (3) consecutive positive frames to transition to `JAMMING`
- Clearing requires `clear_frames_required` (10) consecutive clean frames
- Any single `jam_now` frame resets `clear_hits` to 0, preventing premature exit from alert state
- `WATCH` state is independent of debounce — it triggers on instantaneous `warn_now` without requiring hit accumulation, giving immediate visual feedback

---

## 8. Code Quality

### 8.1 DSP Unit Tests — 18 TESTS

`tests/test_dsp.py` provides 18 pytest tests covering all four pure functions in `dsp.py`:

| Function | Tests | What is verified |
|----------|------:|------------------|
| `smooth_noise` | 4 | Alpha boundary values (0, 0.5, 1), EMA formula correctness |
| `compute_power` | 4 | Output shape, DC peak at bin n//2, zero-input floor value |
| `remove_dc_spike` | 4 | Spike replaced, outer region preserved, input not mutated |
| `scale_points` | 6 | Empty input, screen bounds, width cap, high/low power Y, single-bin type |

Run with: `.venv\Scripts\python.exe -m pytest`

### 8.2 Keyboard Input Consolidated — RESOLVED

Keyboard handling uses a single `_dispatch_command()` method (`detector.py:245–266`) called from both the Windows (`msvcrt`) and Unix (`select`) input paths (`detector.py:293–310`). No duplicated branching.

### 8.3 Buzzer Worker Thread Pattern — CLEAN

`buzzer.py` uses a `queue.Queue` worker thread (lines 37–53) with a `None` sentinel for clean shutdown (line 108). New state changes clear pending tones before enqueuing (lines 73–81), ensuring the buzzer reflects the current state immediately rather than playing stale sounds.

### 8.4 Touch Calibration System — IMPLEMENTED

`calibrate_touch.py` (271 lines) provides a standalone 4-point touch calibration wizard that:
1. Renders crosshair targets on the LCD at the four corners
2. Collects median-filtered raw ADC readings (15 samples per point, line 91)
3. Auto-detects axis swap via horizontal variance comparison (line 184)
4. Extrapolates linear mapping to screen edges (lines 208–215)
5. Saves calibration JSON loaded by `display_ui.py:839–864` at touch thread startup

---

## 9. Web Dashboard (Deep Trace)

### 9.1 Architecture

Single-page dashboard (`index.html`, 235 lines) with semantic HTML5 structure. Three canvases: spectrum (FFT line chart), margin trend (last 50 samples), and waterfall spectrogram (scrolling time-frequency heatmap). State is fetched via polling `GET /api/status` every 500ms.

### 9.2 Spectrum Morphing

`script.js:253–301` — When new spectrum data arrives, it doesn't snap to the new values. Instead, it captures the current display as `spectrumFromData`, sets the target as `spectrumTargetData`, and interpolates with `easeOutCubic` over `SPECTRUM_MORPH_MS` (~420ms). Render FPS is throttled to 8–14 FPS depending on hardware. This gives a smooth, premium feel without wasting CPU.

### 9.3 Waterfall Spectrogram

`script.js:376–426` — New rows are added at the top (newest-first), scrolling existing content down via `ctx.drawImage` self-copy. Row height auto-scales to fill the canvas. Colour mapping uses a 5-segment linear interpolation from deep blue (quiet) through green, yellow, orange to white (strong signal).

### 9.4 Theme Toggle

Dark and light themes supported via `data-theme` attribute on `<body>` (line 13). Theme preference persists in `localStorage` (line 57). Canvas colours adapt per theme via `canvasColors()` (lines 161–172). Cached background canvases are invalidated on theme switch (line 60).

---

## 10. Remaining Recommendations (Priority Order)

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| **P1** | Fix `database_manager.py` connection leak (§4.5) | Small | Prevents connection exhaustion under error scenarios |
| P1 | Expand test suite to `detector.py` state machine | Medium | Catches logic regressions in SCANNING→WATCH→JAMMING transitions |
| P2 | Magnetometer calibration wizard for MPU9250 | Medium | Makes compass heading field-accurate |
| P3 | Fix particle RAF on hidden tabs (§5.4) | Tiny | Marginal battery savings on mobile |
| P3 | Split `GPSJammerHandheld` god class | Large | Long-term maintainability if feature scope grows |

---

## 11. Conclusion

GUNJAM is a well-built embedded RF detection system. The DSP logic is sound — adaptive noise floor tracking, baseline guard hysteresis, and debounced state transitions are all implemented correctly. Thread synchronisation is handled with appropriate primitives (`Event`, `RLock`, `Lock`). The web dashboard delivers smooth, event-driven visualisations with thoughtful mobile optimisation.

**One concrete bug** was found: SQLite connections leak on exception paths in `database_manager.py`. This is a simple `try/finally` fix that should be applied before the next deployment.

The structural concern (god class in `detector.py`) is noted but does not block the current feature scope. The codebase is in strong shape for field deployment.
