# 📡 GNSS Jamming Detector — Handheld

[![Status](https://img.shields.io/badge/status-development-orange.svg)](README.md)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%20Zero%202W-red.svg)](README.md)
[![Language](https://img.shields.io/badge/language-Python%203-brightgreen.svg)](README.md)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE)
[![Type](https://img.shields.io/badge/type-Educational%20Prototype-blueviolet.svg)](README.md)

A portable, low-cost handheld device for detecting and monitoring GNSS (GPS/GLONASS/Galileo) jamming signals in real time. Built on a Raspberry Pi Zero 2 W with an RTL-SDR USB dongle and a directional LPDA antenna, this project samples RF energy, computes a power spectrum, tracks a dynamic noise floor, and raises a jamming/watch alert on an ILI9488 SPI TFT display.

> ⚠️ **Educational Prototype** — This is a student-built passive receiver. It does not transmit any signals and must not be used for operational, safety-critical, or legal jamming-mitigation decisions.

---

## 📸 Screenshots / Demo

> 📷 Screenshots and demo GIFs will be added after hardware assembly is complete.
>
> Planned additions:
> - `docs/screenshot_lcd_ui.jpg` — LCD dashboard in the field
> - `docs/demo_detection.gif` — Live spectrum scanning demo
> - `docs/architecture.png` — System block diagram

---

## 🔍 Overview

GNSS signals (e.g., GPS L1 at 1575.42 MHz) are extremely weak by the time they reach Earth's surface, making them highly susceptible to intentional interference known as **jamming** — where a nearby emitter raises the noise floor or masks satellite signals, causing receivers to lose lock or produce incorrect positioning.

This handheld detector uses a **Software Defined Radio (RTL-SDR)** to passively monitor the GNSS frequency band. It performs real-time **FFT-based spectral analysis**, estimates a dynamic noise floor using exponential moving average smoothing, and scores the signal environment using multiple metrics (noise floor rise, peak differential). When thresholds are exceeded, an alert is raised on the LCD display.

A directional **LPDA antenna** allows the user to perform a manual **bearing sweep** — rotating the antenna and logging signal strength at each orientation — to estimate the approximate direction of the jamming source.

---

## ✨ Features

| Feature | Status | Implementation |
|---|---|---|
| Real-time FFT spectrum display | ✅ Implemented | `display_ui.py` → ILI9488 display |
| Noise floor baseline & smoothing | ✅ Implemented | Exponential moving average (`dsp.py`, `detector.py`) |
| Jamming detection scoring & thresholds | ✅ Implemented | Multi-metric scoring: floor rise + peak differential |
| Auto-calibration routine | ✅ Implemented | Short warm-up sampling to establish baseline NF |
| Directional bearing logging (manual) | ✅ Implemented | Accepts bearing via stdin; polar plot visualization |
| Data logging to CSV / SD card | 🔜 Planned | For post-mission analysis |
| Network alerts / remote monitoring | 🔜 Planned | MQTT / HTTP webhook |
| Improved UI and touch controls | 🔧 In Progress | UI enhancements and interaction |

---

## 🔧 Hardware Requirements

| Component | Notes |
|---|---|
| **Raspberry Pi Zero 2 W** | Main compute unit — tested platform |
| **RTL-SDR USB Dongle** | Any RTL2832-based device with `librtlsdr` support |
| **LPDA Directional Antenna** | 800 MHz–2700 MHz, 8–9 dBi gain for directionality |
| **3.5" TFT SPI Display (ILI9488)** | Driver: `luma.lcd.device.ili9488` |
| **USB OTG Adapter** | For connecting RTL-SDR to Pi Zero's micro-USB port |
| **Power Bank** | Portable power supply _(model TBC)_ |
| **microSD Card** | Standard Pi OS installation |

> 💡 The LPDA antenna covers all primary GNSS frequency bands:
> - **GPS L1:** 1575.42 MHz
> - **GLONASS L1:** ~1602 MHz
> - **Galileo E1:** 1575.42 MHz

---

## 💻 Software Requirements

**Operating System:** Raspberry Pi OS (Bullseye / Bookworm), 32-bit recommended for Pi Zero 2 W

**Python Version:** Python 3.7+ (3.9+ recommended)

**Python Dependencies** (see `requirements.txt`):

```
numpy
Pillow
pyrtlsdr
luma.core
luma.lcd
```

**System Dependencies:**

```
librtlsdr-dev
rtl-sdr
```

**SPI must be enabled** in `raspi-config` for the ILI9488 display to function.

**Development Tools:**
- Visual Studio Code (remote SSH or local)
- Thonny IDE (for on-device development)

---

## 🚀 Installation

The steps below outline a minimal setup on Raspberry Pi OS (Bullseye/Bookworm). Adapt package manager commands if you use a different distribution.

### 1. Update system and install native dependencies

```bash
sudo apt update
sudo apt install -y build-essential git python3 python3-pip python3-venv \
    librtlsdr-dev rtl-sdr
```

### 2. Disable the default DVB-T kernel driver

The default kernel driver conflicts with `librtlsdr`. Create a blacklist file:

```bash
sudo nano /etc/modprobe.d/rtl-sdr-blacklist.conf
```

Add this line:

```text
blacklist dvb_usb_rtl28xxu
```

Then reboot:

```bash
sudo reboot
```

### 3. Enable SPI interface

```bash
sudo raspi-config nonint do_spi 0
```

### 4. Clone the repository

```bash
git clone https://github.com/67010655/gnss-jamming-detector-handheld.git
cd gnss-jamming-detector-handheld
```

### 5. Create a virtual environment and install Python packages

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 6. Verify RTL-SDR is recognized

```bash
rtl_test -t
```

A successful output confirms the dongle is accessible. If not, double-check the blacklist and reboot.

---

## ▶️ Usage

### 1. Configure parameters

Edit `config.py` before running. Key parameters:

```python
WIDTH, HEIGHT       # Display resolution
SAMPLE_COUNT        # FFT sample size
CENTER_FREQ         # Target frequency in Hz (default: 1575.42e6 = GPS L1)
SAMPLE_RATE         # SDR sample rate
GAIN                # SDR gain (tune for your RF environment)
# Thresholds and smoothing alphas for detection behaviour
```

> 💡 Adjust detection thresholds based on your local RF environment. Higher thresholds reduce false positives in noisy areas.

### 2. Run the application

```bash
source venv/bin/activate
python3 main.py
```

### 3. Supply bearing input (optional)

While the program is running, type an integer bearing value (0–359°) and press **Enter** to log a directional sample. The polar plot on the display will update accordingly.

```bash
# Example: type 90 and press Enter to log East direction
90
```

---

## 📁 Project Structure

```
gnss-jamming-detector-handheld/
│
├── main.py             # Entry point — instantiates and runs the app
├── config.py           # Central configuration and tuning parameters
├── detector.py         # Main app class GPSJammerHandheld: SDR init,
│                       # main loop, detection logic and state machine
├── dsp.py              # DSP helpers: windowing, FFT, power calculation,
│                       # DC spike removal, noise floor smoothing
├── display_ui.py       # UI rendering for ILI9488 display via luma.lcd
│
├── requirements.txt    # Python dependencies (pip install -r requirements.txt)
├── LICENSE             # MIT License
├── .gitignore          # Git ignore rules (.venv, __pycache__, etc.)
└── README.md           # Project documentation
```

---

## ⚙️ How It Works

```
+------------------+     +-------------------+     +--------------------+
| RTL-SDR Input    | --> | Windowing &       | --> | FFT → Power (dB)   |
| IQ samples       |     | DC Spike Removal  |     | Spectrum           |
| detector.py      |     | dsp.py            |     | dsp.py             |
+------------------+     +-------------------+     +--------------------+
                                                            |
                                                            v
                                                  +---------------------+
                                                  | Noise Floor         |
                                                  | Estimation &        |
                                                  | Smoothing (EMA)     |
                                                  | dsp.py              |
                                                  +---------------------+
                                                            |
                                                            v
                                                  +---------------------+
                                                  | Detection & Scoring |
                                                  | floor rise +        |
                                                  | peak differential   |
                                                  | detector.py         |
                                                  +---------------------+
                                                            |
                                          +-----------------+-----------------+
                                          |                                   |
                                          v                                   v
                                  +--------------+                   +----------------+
                                  | No Jamming   |                   | ALERT / WATCH  |
                                  | Normal UI    |                   | Log Bearing    |
                                  +--------------+                   +----------------+
                                          |                                   |
                                          +------------------+----------------+
                                                             |
                                                             v
                                                  +---------------------+
                                                  | LCD Dashboard       |
                                                  | Spectrum + Score +  |
                                                  | Polar Bearing Plot  |
                                                  | display_ui.py       |
                                                  +---------------------+
```

**Step-by-step explanation:**

1. **IQ Sampling** — `detector._init_sdr()` and `detector.run()` tune the RTL-SDR to `CENTER_FREQ` (GPS L1: 1575.42 MHz) and read blocks of raw IQ samples continuously.

2. **Windowing & DC Spike Removal** — `dsp.compute_power()` applies a window function before FFT to reduce spectral leakage. `dsp.remove_dc_spike()` suppresses the center DC artifact common to direct-conversion RTL-SDR devices.

3. **FFT → Power Spectrum** — The windowed IQ samples are transformed via Fast Fourier Transform and converted to a dB-scale power spectrum for analysis.

4. **Noise Floor Estimation & Smoothing** — A dynamic noise floor baseline is maintained using an **Exponential Moving Average (EMA)** via `dsp.smooth_noise`. This adapts to the local RF environment over time.

5. **Detection & Scoring** — `detector._detect_jamming()` applies a **multi-metric scoring system**: comparing percentile power levels and spectral peaks against the baseline. A hit/clear counter latches the alarm state to prevent flickering.

6. **Bearing Estimation** — The user manually rotates the directional LPDA antenna and inputs bearing values (0–359°) via stdin. Signal strength at each bearing is logged and visualized as a polar plot, indicating the likely direction of the jamming source.

7. **LCD Display** — `display_ui.draw_ui()` renders the full dashboard on the ILI9488 display: live spectrum, noise floor overlay, detection score, alert status, and the polar bearing plot.

---

## 🔮 Future Improvements

- [ ] Add persistent CSV / SD card logging of raw metrics and detection events
- [ ] Add automated antenna sweeping with servo control for auto-triangulation of bearings
- [ ] Add optional network reporting (MQTT / HTTP webhook) for remote alerts
- [ ] Improve noise floor calibration: drift compensation and environmental profiles
- [ ] Add unit tests for DSP routines (`dsp.py`)
- [ ] Add multi-band scanning (GPS L2, L5, GLONASS, BeiDou, Galileo E5)
- [ ] Serve a local Wi-Fi web dashboard via Pi's built-in wireless for remote monitoring
- [ ] Integrate GPS module to timestamp and geolocate detection events

---

## ⚠️ Disclaimer

This project is developed **solely for educational and research purposes** as part of an academic program in Space and Geospatial Engineering at KMITL.

- This device is a **passive receiver only** — it does **not** transmit any signals.
- Detection accuracy of this prototype is **not guaranteed** and has not been independently verified.
- This project is **not certified** and must not be used for safety-critical, operational, or legal jamming-mitigation applications.
- Laws regarding RF monitoring vary by country — **ensure you comply with local regulations** before deploying this device.
- This project is not affiliated with any government agency or commercial organization.

---

## 📄 License

This project is released under the **MIT License** — see [LICENSE](LICENSE) for the full text.

---

## 👤 Author

67010655 — Space and Geospatial Engineering Student
King Mongkut's Institute of Technology Ladkrabang (KMITL), Thailand

> Built as an academic project exploring RF signal processing, Software Defined Radio, and portable embedded systems.

---

## 🙏 Acknowledgements

Built with Python, NumPy, and the RTL-SDR open-source community tools.
Inspiration and components drawn from open GNSS research and hobbyist SDR communities.

---

_If you find this project useful or interesting, feel free to ⭐ star the repository!_