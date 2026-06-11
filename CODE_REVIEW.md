# Code Review - GUNJAM Handheld GNSS Jamming Detector

**Reviewer:** Codex, source-grounded re-review  
**Review date:** 11 June 2026  
**Repository reviewed:** `D:\Documents\GitHub\Jamming-Detector-Handheld`  
**Branch state:** `main...origin/main` with local working-tree changes in `config.py`, `hardware/mpu9250.py`, and `tests/test_imu_selection.py`  
**Status:** **READY FOR CONTROLLED FIELD VALIDATION** after current software verification. This is not an aviation certification or AEROTHAI sign-off.

## Current Verification Snapshot

| Check | Result |
|---|---|
| `python -m pytest -q` | **36 passed** |
| `python generate_previews.py` | **Passed**; regenerated LCD preview images including calibration and power dialogs |
| Python source count | **24 `.py` files**, about **3,730 lines** at review time |
| Current IMU mode | `IMU_FUSION_MODE = 'COMPLEMENTARY'` |
| Current IMU hardware | GY-9250 / MPU9250 at `0x69`; DS3231 RTC at `0x68` |

## What Changed Since The Older Review

The previous audit text used older file counts, older line counts, and an older test total. That snapshot is stale. The current project contains additional diagnostics, detector tests, live compass tooling, GY-9250 calibration support, and adaptive IMU fusion tuning.

The recent IMU update adds:
- `IMU_FUSION_STILL_ALPHA = 0.75`
- `IMU_STILL_GYRO_DPS = 8.0`
- Adaptive complementary fusion in `hardware/mpu9250.py`: fast turns keep the normal gyro-heavy alpha, while still or slow movement trusts the magnetometer more so the heading recenters faster.
- Regression tests in `tests/test_imu_selection.py` for adaptive config loading, MAG-only missing-sample behavior, wraparound fusion, and still-state recentering.

## Executive Summary

GUNJAM is a portable GNSS L1 jamming detector for 1575.42 MHz, running on Raspberry Pi Zero 2W with RTL-SDR, ILI9488 touch LCD, GY-9250 IMU, DS3231 RTC, SQLite WAL logging, and a Flask/Waitress web dashboard.

The current software state is strong for controlled field validation:
- DSP, baseline guard, debounce, database lifecycle, detector state transitions, and IMU selection/fusion paths are covered by automated tests.
- LCD preview generation passes.
- SQLite connection cleanup and dashboard hidden-tab particle pause are implemented.
- The GY-9250 heading path is now tuned for faster recentering after quick rotations.

Remaining caveat: RF/aviation readiness must still be validated on the physical unit. SAW filtering, shielding, ferrites, power/thermal behavior, and field heading accuracy are hardware/field checks, not things the Python test suite can certify.

## Software Findings

### DSP And Detection Logic - Verified

The DSP path uses:
- Hanning window and FFT normalization in `dsp.py`
- DC spike cleanup via `remove_dc_spike()`
- adaptive noise floor smoothing
- baseline guard lock/release against jammer-induced noise-floor drift
- `HIT_FRAMES = 3` and `CLEAR_FRAMES = 10` debounce thresholds

Current detector tests cover normal SCANNING behavior, WATCH transitions, immediate guard-driven JAMMING, and peak debounce transitions.

### Concurrency And Thread Safety - Verified

The report's concurrency claims remain valid:
- LCD and touch SPI sharing is protected by `self._spi_lock` in `display_ui.py`
- dynamic touch zones are swapped under `_zones_lock`
- `/api/clear` uses `_clear_lock` and rate limiting
- cross-thread UI requests use `threading.Event`

### Database Reliability - Verified

SQLite uses WAL mode and synchronous NORMAL. The persistence functions close connections through `finally`, and `_get_connection()` closes partially initialized connections if PRAGMA setup fails. Database pruning retains the latest 1,000 non-STARTUP records to limit SD-card growth.

### IMU And Heading - Updated

The current build uses vertical GY-9250 mounting:
- X/Z are treated as the horizontal magnetometer axes
- Y is discarded for heading
- hard-iron offsets are stored in `config.py`
- `IMU_MAG_INVERT` and `IMU_COMPASS_OFFSET_DEG` align the live compass with the physical enclosure
- adaptive complementary fusion now recenters faster when the device is nearly still

This addresses the observed behavior where quick rotations could leave heading 10-20 degrees off until the device sat still. It should still be validated on the physical unit against `live_compass.py` or `test_sensors.py`.

### Web Dashboard - Verified

The web dashboard still follows the intended low-overhead pattern:
- JSON polling around 500 ms
- event-driven canvas redraws
- spectrum interpolation rather than continuous heavy charting
- particle animation pauses on `visibilitychange`
- HTML escaping is used for log rendering

## RF And Aviation Notes

The older audit wording implied formal sign-off and external operational approval. That is not supported by repository evidence and should not be used as a certification claim.

Correct current wording:
- The software is ready for controlled field validation.
- The device remains a passive GNSS L1 monitoring tool.
- Aviation-grade deployment requires separate RF/EMC validation, operational approval, and field procedure sign-off.

Recommended physical checks are kept in `FIELD_READINESS_CHECKLIST.md`.

## Current Scores

| Area | Current score | Rationale |
|---|---:|---|
| DSP correctness | 9.5 / 10 | Core math and state logic are tested; live RF calibration remains field-dependent |
| Thread safety | 9 / 10 | SPI, touch zones, API clear, and control events are guarded |
| Database reliability | 9.5 / 10 | WAL, cleanup, pruning, and regression coverage are in place |
| IMU heading | 8 / 10 | Adaptive fusion is improved and tested; physical fast-rotation validation remains needed |
| Web dashboard performance | 9.5 / 10 | Event-driven canvas and hidden-tab pause are implemented |
| RF field readiness | 7 / 10 | Software is ready; filter/shielding/self-noise checks are hardware tasks |

## Remaining Recommendations

| Priority | Item | Status |
|---|---|---|
| P1 | Run fast-rotation heading validation on the physical GY-9250 after adaptive fusion | Open field check |
| P1 | Use GPS L1 SAW/bandpass filtering near high-power RF sites | Hardware check |
| P1 | Check enclosure self-noise, shielding, ferrites, power, and thermal behavior | Hardware check |
| P2 | Keep `GPSJammerHandheld` split into smaller modules on the roadmap | Deferred |
| P2 | Keep `live_compass.py` and `diagnose_magnetometer.py` outputs with field handoff notes | Recommended |

## Verdict

**Ship for controlled field validation, not formal aviation-certified deployment.** The current code passes automated tests and preview generation, but RF/EMC behavior and heading accuracy after fast rotations must be verified on the physical unit.
