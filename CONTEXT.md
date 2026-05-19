# Project Context: GNSS L1 Jamming Detector Handheld

## Overview
A handheld system designed to detect and log GNSS (GPS L1) jamming signals in the field using a Software-Defined Radio (SDR). It features an integrated hardware display for real-time monitoring and a web dashboard for historical data analysis and remote access.

## Hardware System
- **Core Processing:** Raspberry Pi Zero 2W
- **SDR Receiver:** RTL-SDR v3 (USB interface)
- **Display:** 3.5" ILI9488 TFT LCD with Touch (SPI interface)
- **Sensors:** 
  - **MPU6050 (IMU):** Directional mapping and compass heading calculations (Fully Integrated, I2C `0x69`)
  - **DS3231 (RTC):** Precise Real-Time Clock for offline system time sync in field operations (I2C `0x68`)
- **Antenna:** Directional Antenna (tuned for 1575.42 MHz)
- **Peripherals:** Status RGB LEDs, Active Buzzer (GPIO 18), and Physical Mute Switch (GPIO 23 / Configurable)

## Power Architecture
- **Battery:** 2x 18650 Lithium-ion batteries
- **Power Management:** LX-28UPS module (Provides safe charging circuitry and 5V boost conversion)
- **Soft Power Actions:** 3-button Confirm Dialogue on LCD (SHUTDOWN / RESTART / CANCEL).
  - **SHUTDOWN:** Safe OS halt sequence to prevent MicroSD corruption.
  - **RESTART:** Fast 2-second in-process Python reload (`os.execv`) to reset system & MPU6050 I2C states instantly without a full OS reboot.

## Software Stack & File Structure
- `main.py`: The application entry point that initializes all modules.
- `detector.py`: Core signal processing, Power Spectral Density (PSD) calculation, and jamming state logic evaluation. Supports soft reboot signals.
- `display_ui.py`: Manages the LCD interface rendering (e.g., Normal, Search, Analytics modes) and touch interactions. Features a clean header with MUTE state visual feedback.
- `web_server.py` / `web/`: Flask API and frontend dashboard. Includes minimalist **Day/Night Theme Toggle** ☀️🌙.
- `database_manager.py`: Handles SQLite database logging with adaptive heartbeat intervals to optimize I/O.
- `dsp.py`: Contains DSP utilities for FFT operations and power metric calculations.
- `buzzer.py` / `led_control.py`: Controls hardware feedback modules via GPIO.

## Known Issues & Development Focus
- **Solved:** UI lag on both Pi Zero and client browsers completely resolved via Event-Driven Canvas rendering (Spectrum & Margin Trend at 4Hz, Waterfall Spectrogram at 2Hz) and DOM Value Differencing (bypassing DOM writes for unchanged values).
- **Solved:** MPU6050 connection drops due to loose wiring handled smoothly with the instant LCD RESTART button.
- **Ongoing:** Maximizing RF shielding in the handheld enclosure to isolate internal Pi Zero clock noise from the RTL-SDR front-end.
