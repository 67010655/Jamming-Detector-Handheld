# GNSS Jamming Detector — Handheld

[![Status](https://img.shields.io/badge/status-development-orange.svg)](README.md)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-blue.svg)](README.md)
[![Language](https://img.shields.io/badge/language-Python%203-brightgreen.svg)](README.md)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE)
[![Type](https://img.shields.io/badge/type-prototype-blueviolet.svg)](README.md)

Short description
-----------------

GNSS Jamming Detector — Handheld is an educational prototype for detecting interference against GNSS L1 (1575.42 MHz) using a Raspberry Pi Zero 2 W, an RTL‑SDR USB dongle and a directional LPDA antenna. The project samples RF, computes a spectrum, tracks a noise floor, and raises a jamming/watch indication on a small ILI9488 SPI TFT display.

Screenshots / Demo
------------------

Placeholder images and demo GIFs should be added here when available. You can drop screenshots into the repository and reference them below.

Overview
--------

GNSS jamming is when an emitter transmits signals that raise the noise floor or mask legitimate GNSS satellite signals, causing receivers to lose lock or produce incorrect positioning. This project demonstrates a passive, low-cost detector that monitors spectrum energy around GPS L1 and alerts when the spectral noise floor and peak patterns indicate possible jamming.

This repository is a student-built educational prototype — it is not certified, should not be used for operational safety decisions, and does not transmit any signals.

Features
--------

| Feature | Status | Notes |
|---|---:|---|
| Real-time FFT spectrum display | Implemented | Spectrum rendering to ILI9488 display (`display_ui.py`) |
| Noise-floor baseline and smoothing | Implemented | Exponential moving average with alert modes (`dsp.py`, `detector.py`) |
| Jamming detection scoring & thresholds | Implemented | Multi‑metric scoring (floor rise, peak diff) |
| Directional bearing logging (manual input) | Implemented | Accepts bearing via stdin; simple logging & visualization |
| Auto-calibration routine | Implemented | Short warm-up sampling to establish baseline NF |
| Data logging to SD / CSV | Planned | Useful for post-analysis |
| Network alerts / remote monitoring | Planned | MQTT / HTTP webhook ideas |
| Improved UI and touch controls | In Progress | UI enhancements and interaction

Hardware Requirements
---------------------

| Component | Notes |
|---|---|
| Raspberry Pi Zero 2 W | Tested platform |
| RTL‑SDR USB dongle | Any RTL2832-based device with `librtlsdr` support |
| LPDA directional antenna (800–2700 MHz) | 8–9 dBi recommended for directionality |
| 3.5" TFT SPI display (ILI9488) | Driver: `luma.lcd.device.ili9488` |
| USB power, microSD card | Standard Pi setup |

Software Requirements
---------------------

- Python 3.7+ (3.9+ recommended on Pi OS)
- NumPy
- Pillow
- pyrtlsdr (Python wrapper around librtlsdr)
- luma.core and luma.lcd (display drivers)
- System: `librtlsdr` (native RTL-SDR library), SPI enabled in Raspberry Pi config

Installation
------------

The steps below outline a minimal setup on Raspberry Pi OS (Bullseye/Bookworm). Adapt package manager commands if you use a different distribution.

1. Update system and install native deps

```bash
sudo apt update
sudo apt install -y build-essential git python3 python3-pip python3-venv \
	librtlsdr-dev rtl-sdr
```

2. Disable the kernel driver for RTL-SDR devices (so librtl can access the dongle). Add the following to `/etc/modprobe.d/rtl-sdr-blacklist.conf`:

```text
blacklist dvb_usb_rtl28xxu
```

Then reboot.

3. Enable SPI

```bash
sudo raspi-config nonint do_spi 0
```

4. Create a Python virtual environment and install Python packages

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install numpy pillow pyrtlsdr luma.core luma.lcd
```

5. (Optional) If you plan to run headless at boot, set up a systemd service or a supervised launcher.

Usage
-----

1. Edit runtime parameters in [config.py](config.py). Key parameters:

- `WIDTH`, `HEIGHT` — display resolution
- `SAMPLE_COUNT` — FFT sample size
- `CENTER_FREQ`, `SAMPLE_RATE`, `GAIN` — SDR tuning and gain
- Thresholds and smoothing alphas for detection behavior

2. Run the application (from repository root):

```bash
source venv/bin/activate
python3 main.py
```

3. Optional: supply direction (bearing) samples to the program via stdin (used to visualize bearing on the polar plot). Example:

```bash
# type an integer (0-359) and press Enter while the program runs
```

Project Structure
-----------------

- [main.py](main.py) — Entry point that instantiates and runs the app.
- [config.py](config.py) — Central configuration and tuning parameters.
- [detector.py](detector.py) — Main application class `GPSJammerHandheld`: SDR initialization, main loop, detection logic and state machine.
- [dsp.py](dsp.py) — Signal processing helpers: windowing, FFT, power calculation and DC spike removal.
- [display_ui.py](display_ui.py) — UI rendering code for the ILI9488 display using `luma.lcd`.

How It Works
------------

ASCII flow diagram:

```
+----------------+     +-------------+     +-----------------+     +--------------+
| RTL-SDR input  | --> | Windowing & | --> | FFT -> Power    | --> | Detection &  |
| (samples)      |     | DC removal  |     | (dB spectrum)   |     | Scoring      |
+----------------+     +-------------+     +-----------------+     +--------------+
																  |
																  v
														 +--------------------+
														 | Display & Bearing  |
														 | visualization      |
														 +--------------------+
```

Explanation of steps and files:

- Sampling (RTl‑SDR): `detector._init_sdr()` and `detector.run()` read blocks of IQ samples from the RTL‑SDR.
- Windowing & DC spike removal: `dsp.compute_power()` applies a window, computes an FFT and converts magnitude to dB. `dsp.remove_dc_spike()` removes center DC artifacts common to RTL devices.
- Detection & scoring: `detector._detect_jamming()` compares percentiles and peaks against baseline noise floor, applies smoothing (`dsp.smooth_noise`) and maintains a simple hit/clear counter to latch alarm state.
- UI: `display_ui.draw_ui()` renders the spectrum, noise floor, score and a polar bearing plot on the ILI9488 display.

Future Improvements (Checklist)
-----------------------------

- [ ] Add persistent CSV/SD logging of raw metrics and spectra
- [ ] Add automated antenna sweeping + servo control to auto‑triangulate bearings
- [ ] Add optional network reporting (MQTT/HTTP) for remote alerts
- [ ] Improve calibration (noise floor drift compensation, environmental profiles)
- [ ] Add unit tests for DSP routines
- [ ] Create an installable `requirements.txt` and packaging script

Disclaimer
----------

This project is a passive receiver prototype for educational and research purposes only. It does not transmit. It is not certified and should not be used for legal, safety-critical, or operational jamming mitigation. Laws regarding RF monitoring vary by country — ensure you follow local regulations.

License
-------

This project is released under the MIT License. See [LICENSE](LICENSE) for the full text.

Author
------

Student project — Space and Geospatial Engineering, King Mongkut's Institute of Technology Ladkrabang (KMITL).

Acknowledgements
----------------

Built with Python, NumPy and the RTL‑SDR community tools. Inspiration and components from open GNSS research and hobbyist SDR communities.