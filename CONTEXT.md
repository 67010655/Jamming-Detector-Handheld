# Project Context: GNSS L1 Jamming Detector Handheld

## Overview
A handheld system designed to detect and log GNSS (GPS L1) jamming signals in the field using a Software-Defined Radio (SDR). It features an integrated hardware display for real-time monitoring and a web dashboard for historical data analysis and remote access.

## Hardware System
- **Core Processing:** Raspberry Pi Zero 2W
- **SDR Receiver:** RTL-SDR v3 (USB interface)
- **Display:** 3.5" ILI9488 TFT LCD with Touch (SPI interface)
- **Sensors:** MPU6050 (IMU) for directional mapping and compass functionality
- **Antenna:** Directional Antenna (tuned for 1575.42 MHz)
- **Peripherals:** Status RGB LEDs, Active Buzzer (GPIO)

## Power Architecture
- **Battery:** 2x 18650 Lithium-ion batteries
- **Power Management:** LX-28UPS module (Provides safe charging circuitry and 5V boost conversion)

## Software Stack & File Structure
- `main.py`: The application entry point that initializes all modules.
- `detector.py`: Core signal processing, Power Spectral Density (PSD) calculation, and jamming state logic evaluation.
- `display_ui.py`: Manages the LCD interface rendering (e.g., Normal, Search, Analytics modes) and touch interactions.
- `web_server.py` / `web/`: Flask API and frontend dashboard (Glassmorphism UI) for remote monitoring.
- `database_manager.py`: Handles SQLite database logging with adaptive heartbeat intervals to optimize I/O.
- `dsp.py`: Contains DSP utilities for FFT operations and power metric calculations.
- `buzzer.py` / `led_control.py`: Controls hardware feedback modules via GPIO.

## Known Issues & Development Focus
- UI responsiveness on the ILI9488 touch screen needs continuous optimization to prevent blocking the DSP thread.
- Integration of the MPU6050 IMU to enable accurate "Search Mode" (Polar Radar) is an ongoing focus.
- CPU/Thermal limitations of the Pi Zero 2W when running SDR sampling, DSP calculations, database I/O, and UI rendering concurrently.
