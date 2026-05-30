# Code Review — GUNJAM Handheld GNSS Jamming Detector

**Reviewer:** Senior Software Engineer
**Date:** 28 May 2026
**Status:** **APPROVED** — production-ready for field deployment
**Scope:** Full source review of `main` branch — `main.py`, `detector.py`, `config.py`, `dsp.py`, `database_manager.py`, `display_ui.py`, `web_server.py`, `buzzer.py`, `led_control.py`, `calibrate_touch.py`, `test_sensors.py`, `generate_previews.py`, `hardware/mpu6050.py`, `hardware/mpu9250.py`, `hardware/rtc_ds3231.py`, `web/index.html`, `web/script.js`, `web/style.css`

---

## 1. Executive Summary

GUNJAM is a handheld GNSS jamming detector running on Raspberry Pi Zero 2W. The system reads RF samples from an RTL-SDR dongle, runs real-time FFT-based power analysis, classifies signal state via a multi-stage state machine (`SCANNING → WATCH → JAMMING`), renders results on a 480×320 ILI9488 LCD with touch control, and exposes a web dashboard on port 8080.

**Overall Assessment:** The codebase is in strong shape. Architecture decoupling, thread synchronization, and database concurrency are all handled correctly. The DSP domain logic is excellent. Key remaining gaps are the absence of an automated regression test suite (now partially addressed with `tests/test_dsp.py`) and a god-class orchestrator that will become a maintenance burden if the feature set grows.

| Category            | Score      | Notes                                                                                  |
| ------------------- | ---------- | -------------------------------------------------------------------------------------- |
| Domain Logic / DSP  | **10/10**  | Adaptive NF, baseline guard, hit/clear debounce — correct and well-tuned.              |
| Architecture        | **8/10**   | `DisplayUI` decoupling complete; `GPSJammerHandheld` is still a god class.             |
| Thread Safety       | **9/10**   | `threading.Event` + `RLock` zones done well; `_last_clear_time` race fixed this cycle. |
| Reliability         | **9/10**   | SQLite WAL, RTC bus safety, frozen sensor recovery all solid.                          |
| Performance         | **10/10**  | AABB + squared-distance particles; event-driven canvas redraws; mobile throttling.     |
| Security            | **8.5/10** | Waitress WSGI; trusted-LAN model (token auth omitted by design); `/api/clear` rate-limit race fixed this cycle. |
| Code Quality        | **8.5/10** | Constants centralized; 18 DSP unit tests added this cycle; god class remains.         |
| Web Dashboard UI/UX | **10/10**  | Responsive dark/light dashboard; high-performance event-driven rendering.              |

---

## 2. Architecture

### 2.1 `DisplayUI ↔ GPSJammerHandheld` Decoupling — RESOLVED
Drawing context (`_img`, `_draw`, image buffer) previously lived in the orchestrator and was reached back into by the UI layer. These are now fully encapsulated within `DisplayUI`. Separation of concerns is clean; modules can be tested in isolation.

### 2.2 God Class: `GPSJammerHandheld` — OPEN
`detector.py` orchestrates SDR sampling, FFT, state machine, UI updates, database writes, GPS parsing, IMU reads, web state pushes, and shutdown handling in a single class. At ~500 lines it is manageable today, but any significant new feature risks entangling concerns. Suggested future split: `SignalProcessor`, `DataLogger`, `InputHandler`. Deferred to post-v1 roadmap.

### 2.3 Display and SPI Constants Centralized — RESOLVED
All magic numbers (`480`, `320`, `24000000`) have been moved to `config.py`. Hardware porting is now localized to a single file.

---

## 3. Thread Safety

### 3.1 Control Signals via `threading.Event` — RESOLVED
`request_calibration`, `shutdown_requested`, and `reboot_requested` are `threading.Event` objects. Cross-thread visibility is guaranteed; no raw boolean races.

### 3.2 Atomic Touch Zone Updates — RESOLVED
Touch button zones are rebuilt into a new `_new_zones` dict, then swapped atomically inside `threading.RLock` (`display_ui.py:618`). The touch handler thread never sees a partially-updated zone map.

### 3.3 `_last_clear_time` Race on `/api/clear` — FIXED THIS CYCLE
Two concurrent `POST /api/clear` requests could both pass the rate-limit check before either updated `_last_clear_time`, allowing a double-clear. Fixed by adding `_clear_lock = threading.Lock()` and checking+reserving the timestamp atomically inside the lock before the database call (`web_server.py:162–176`).

---

## 4. Reliability

### 4.1 SQLite WAL Mode — IMPLEMENTED
`database_manager.py` opens every connection with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`. The web server thread reads event history concurrently with the main loop writing jamming events without lock contention or UI pauses.

### 4.2 Preview State Snapshot — IMPLEMENTED
`generate_previews.py` saves and restores `(noise_floor, jammer_active, current_state, jam_hits, clear_hits)` before and after injecting synthetic signals. Preview generation cannot corrupt live detector state.

### 4.3 RTC I2C Bus Safety — IMPLEMENTED
`hardware/rtc_ds3231.py` guards every I2C call with `if self.bus is None: return`. Windows debugging and offline CI runs do not raise `AttributeError`.

### 4.4 MPU9250 9-DoF Driver — NEW FEATURE
A complete `MPU9250` driver (`hardware/mpu9250.py`) with AK8963 magnetometer access via I2C bypass mode has been added. This is a **feature addition** enabling future compass-heading functionality — it does not affect reliability of the existing IMU pipeline.

---

## 5. Performance

### 5.1 Particle Connection Optimization — IMPLEMENTED
Particle-to-particle connection checks in `web/script.js` use:
1. **AABB early-out** — `if (Math.abs(dx) >= CONNECTION_DIST) continue` before the more expensive distance check.
2. **Squared-distance comparison** — `dx*dx + dy*dy < CONNECTION_DIST_SQ` eliminates `Math.sqrt` entirely.
3. **Mobile particle throttle** — 25 particles on touch devices vs. 65 on desktop.

This reduces per-frame work from O(n²·√) to O(n²) with a fast early-exit for the common case, giving smooth rendering on low-end tablets.

### 5.2 Event-Driven Canvas Redraws — IMPLEMENTED
`requestAnimationFrame` is triggered only when a new metrics/spectrum payload arrives (max 4 Hz), not on a fixed 60 Hz timer. Battery drain on connected mobile clients is negligible.

---

## 6. Security

### 6.1 Waitress WSGI — IMPLEMENTED
Flask's single-threaded development server replaced with Waitress (`web_server.py:7`, `187`) running on a daemon thread with 2 worker threads. Concurrent API requests are handled correctly.

### 6.2 Network-Level Access Control — BY DESIGN
API token auth is intentionally omitted (`web_server.py:24-25`): the unit serves its dashboard only on a trusted, operator-controlled Wi‑Fi hotspot/LAN, so access is enforced at the network layer (isolated AP + WPA2) rather than per-request. If the dashboard is ever exposed beyond that trusted LAN, add an `X-API-Token` check (e.g. against a `GUNJAM_API_TOKEN` env var) returning 401 on mismatch as a follow-up.

### 6.3 Rate-Limited `POST /api/clear` — IMPLEMENTED + RACE FIXED
A 60-second cooldown prevents database abuse. The check-and-reserve is now atomic under `_clear_lock` (see §3.3). Remote IP is logged on every successful clear for audit trail.

---

## 7. Code Quality

### 7.1 DSP Unit Tests — ADDED THIS CYCLE
`tests/test_dsp.py` provides 18 pytest tests covering all four pure functions in `dsp.py`:

| Function          | Tests | What is verified                                               |
| ----------------- | ----- | -------------------------------------------------------------- |
| `smooth_noise`    | 4     | Alpha boundary values (0, 0.5, 1), EMA formula correctness.   |
| `compute_power`   | 4     | Output shape, DC peak at bin n//2, zero-input floor value.     |
| `remove_dc_spike` | 4     | Spike replaced, outer region preserved, input not mutated.     |
| `scale_points`    | 6     | Empty input, screen bounds, width cap, high/low power Y, type. |

Run with: `.venv\Scripts\python.exe -m pytest`

### 7.2 Duplicate Keyboard Handling — RESOLVED
Previously duplicated key-handling branches have been consolidated.

---

## 8. Remaining Recommendations (Priority Order)

| Priority | Item                                 | Effort | Impact                                                     |
| -------- | ------------------------------------ | ------ | ---------------------------------------------------------- |
| P1       | Expand test suite to `detector.py` state machine | Medium | Catches logic regressions in SCANNING→WATCH→JAMMING transitions |
| P2       | Magnetometer calibration wizard      | Medium | Makes MPU9250 compass heading field-accurate               |
| P3       | Split `GPSJammerHandheld` god class  | Large  | Long-term maintainability if feature scope grows           |

---

## 9. Conclusion

GUNJAM is a well-built embedded RF detection system. The DSP logic is sound, concurrency is handled correctly, and the web dashboard performs well on mobile. Two concrete issues were resolved in this cycle: the `_last_clear_time` race condition and missing DSP regression tests. The one structural concern (god class) is noted but is not blocking for the current feature scope.
