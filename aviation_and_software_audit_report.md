# GUNJAM Technical And Operational Audit Report

**Project:** GUNJAM Handheld GNSS Jamming Detector, GPS L1 1575.42 MHz  
**Audit date:** 11 June 2026  
**Repository:** `D:\Documents\GitHub\Jamming-Detector-Handheld`  
**Status:** Software verified for controlled field validation. This document is not a formal aviation approval.

## Executive Summary

The earlier pasted audit report is now superseded by this repo-local version. Current repository evidence shows:

- `python -m pytest -q` passes: **36 passed**
- `python generate_previews.py` passes
- current Python source count: **24 `.py` files**, about **3,730 lines**
- current IMU operating mode: `COMPLEMENTARY`
- current IMU tuning includes adaptive still-state recentering after fast rotations

The software design is suitable for controlled field validation of passive GNSS L1 interference detection. It should not be described as formally approved or aviation-certified unless a separate real-world approval process has actually occurred.

## Software Audit

### Concurrency And Safety

The system runs the main SDR/IMU loop, Waitress/Flask dashboard, and touch input concurrently. Current code protects the main shared resources:

- SPI display/touch access uses `self._spi_lock`
- touch zones are swapped under `_zones_lock`
- `/api/clear` uses `_clear_lock` and rate limiting
- cross-thread control uses `threading.Event`

### Reliability

- SQLite uses `journal_mode=WAL`
- database operations close connections in `finally`
- the database prunes old non-STARTUP rows beyond the 1,000-row retention window
- GY-9250 initialization keeps gyro operation available even if the AK8963 magnetometer is unavailable
- soft restart uses in-process `os.execv`, but actual restart timing must be measured on the target Raspberry Pi

### DSP And Detection

The DSP path uses Hanning-windowed FFT, normalized power, DC spike removal, adaptive baseline smoothing, guard lock/release, and hit/clear debounce. Detector tests now cover the key state transitions.

### IMU Heading

The current GY-9250 path uses vertical-mount X/Z magnetometer axes, hard-iron offsets, compass inversion, and a calibrated compass offset. Complementary fusion is adaptive:

- active rotation uses `IMU_FUSION_ALPHA = 0.95`
- still or slow movement uses `IMU_FUSION_STILL_ALPHA = 0.75`
- still detection uses `IMU_STILL_GYRO_DPS = 8.0`

This is intended to reduce the observed 10-20 degree post-fast-turn drift by letting the compass recenter faster once the unit slows down.

## Aviation And RF Notes

GNSS L1 interference can affect aviation systems that depend on GNSS-derived position, but this repository does not prove aviation certification. Treat the following as field-readiness recommendations:

- use a GPS L1 SAW or bandpass filter near high-power RF environments
- check RTL-SDR saturation at the selected gain
- check enclosure self-noise and shielding
- add ferrites if USB or power leads couple noise into the receiver
- validate heading behavior away from steel chassis and hard-iron sources

Formal deployment near aviation operations needs separate RF/EMC testing, operational approval, and documented field procedures.

## Current Verification Plan

Run before handoff:

```powershell
python -m pytest -q
python generate_previews.py
python live_compass.py
```

For hardware validation, record:

- iPhone/reference compass heading
- GUNJAM magnetic heading
- fused bearing
- error after fast clockwise and counter-clockwise rotations
- time to settle within the acceptable error band

## Sign-Off Language

Use this wording:

> Software verified for controlled field validation on 11 June 2026. Field RF, shielding, power, thermal, and heading accuracy checks remain required before operational handoff.

Do not use approval or certification wording unless a separate authority actually grants it.
