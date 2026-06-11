# GUNJAM Field Readiness Checklist

Use this checklist before a controlled demo, handoff, or field run. It separates software evidence from RF, power, and safety checks so the project does not rely on broad "approved" claims without current verification.

## Software Evidence

- [ ] `python -m pytest -q` passes with no failures.
- [ ] `python generate_previews.py` regenerates LCD preview images successfully.
- [ ] `config.py` values match the physical build:
  - `CENTER_FREQ = 1575.42e6`
  - `GAIN = 7.7` or a documented field-tuned value
  - `IMU_MODEL = 'GY-9250'`
  - `IMU_ADDRESS = 0x69`
  - `IMU_FUSION_MODE = 'COMPLEMENTARY'`
  - `IMU_FUSION_ALPHA`, `IMU_FUSION_STILL_ALPHA`, and `IMU_STILL_GYRO_DPS` are tuned for the current mount.
- [ ] `live_compass.py` or `test_sensors.py` confirms heading behavior after slow turns and fast turns.
- [ ] The latest `CODE_REVIEW.md` is used instead of older external "approved" summaries.

## RF Front End

- [ ] GPS L1 antenna and RTL-SDR are mechanically secure.
- [ ] GPS L1 bandpass or SAW filter is installed when operating near high-power RF sources.
- [ ] RTL-SDR gain is checked for saturation in quiet and strong-signal scenarios.
- [ ] Coax, USB, and power cable routing is inspected to reduce coupling into the receiver.
- [ ] Ferrite cores are fitted to USB or power leads when field noise is visible.

## Shielding And Layout

- [ ] Raspberry Pi and display cabling are separated from the antenna feed.
- [ ] Copper foil or conductive shielding is installed where enclosure testing shows self-noise.
- [ ] Shielding does not short GPIO, USB, display, IMU, RTC, or power contacts.
- [ ] Self-noise is checked with the antenna connected, disconnected, and moved away from the enclosure.

## Sensor And Direction Checks

- [ ] GY-9250 is wired to 3.3 V and uses address `0x69`; DS3231 remains at `0x68`.
- [ ] Magnetometer offsets are collected away from vehicle hard-iron sources.
- [ ] Fast-rotation heading error is checked against a reference compass after adaptive fusion.
- [ ] Vehicle-mounted operation is treated separately from handheld operation because chassis steel can distort heading.
- [ ] Gyro-only or relative-bearing operation is documented if absolute magnetic heading is not trusted.

## Power And Runtime

- [ ] Battery pack is fully charged and tested under display, SDR, Wi-Fi, LED, and buzzer load.
- [ ] Thermal behavior is checked with the enclosure closed.
- [ ] Safe shutdown and in-place restart paths are verified.
- [ ] System time is correct through DS3231 or a documented manual sync step.
- [ ] SQLite event logging and CSV export are tested after at least one sample run.

## Safety And Handoff

- [ ] The device is used only as a passive receiver unless a separate authorized test plan says otherwise.
- [ ] Field operators know that this project detects GNSS L1 interference; it does not certify aviation equipment.
- [ ] Any AEROTHAI, RTCA DO-160, or DO-178 language is treated as a future certification path, not a current approval.
- [ ] The handoff package includes `README.md`, `HARDWARE_WIRING.md`, `CODE_REVIEW.md`, and this checklist.
