# LED Control Setup Guide

This guide explains how to connect and configure the 3 status LEDs to indicate jamming detection state.

## LED States

- **RED LED** (GPIO 17): Lights up when **JAMMING** is detected
- **YELLOW LED** (GPIO 27): Lights up during **WATCH** state (warning)
- **GREEN LED** (GPIO 22): Lights up during **SCANNING** state (normal operation)

## Hardware Requirements

- 3x LEDs (Red, Yellow, Green)
- 3x 330Ω resistors
- 3x GPIO pins on Raspberry Pi Zero 2W
- Jumper wires
- Breadboard (optional)

## Wiring Diagram

### Raspberry Pi Zero 2W GPIO Pinout (Physical Pin Numbers)

```
        [USB]
  1 3v3  [XX]  2 5v
  3 GPIO2[XX]  4 5v
  5 GPIO3[XX]  6 GND
  7 GPIO4[XX]  8 GPIO14
  9 GND [XX] 10 GPIO15
 11 GPIO17   12 GPIO18
 13 GPIO27   14 GND
 15 GPIO22   16 GPIO23
 17 3v3  [XX] 18 GPIO24
 19 GPIO10[XX] 20 GND
 21 GPIO9 [XX] 22 GPIO25
 23 GPIO11[XX] 24 GPIO8
 25 GND  [XX] 26 GPIO7
        [Pi Logo]
```

### LED Connections

**Red LED (JAMMING)**
- GPIO 17 (Pin 11) → 330Ω Resistor → Red LED Anode
- Red LED Cathode → GND (Pin 9, 14, 20, or 25)

**Yellow LED (WATCH)**
- GPIO 27 (Pin 13) → 330Ω Resistor → Yellow LED Anode
- Yellow LED Cathode → GND

**Green LED (SCANNING)**
- GPIO 22 (Pin 15) → 330Ω Resistor → Green LED Anode
- Green LED Cathode → GND

## Configuration

Edit `config.py` to adjust GPIO pins if needed:

```python
# LED GPIO Configuration
LED_RED_PIN = 17        # GPIO17 for RED LED (JAMMING state)
LED_YELLOW_PIN = 27     # GPIO27 for YELLOW LED (WATCH state)
LED_GREEN_PIN = 22      # GPIO22 for GREEN LED (SCANNING state)
```
## Testing

On Raspberry Pi, you can test LED control from Python:

```python
from led_control import LEDController

led = LEDController(enabled=True)
led.test_sequence()  # Tests all LEDs in sequence
led.cleanup()
```

## Troubleshooting

### LEDs not lighting up
- Check GPIO connections
- Verify resistor values (330Ω recommended)
- Ensure LEDs are oriented correctly (long leg to GPIO)
- Check if Python GPIO library is installed: `pip install RPi.GPIO`

### Only on real Pi hardware
- LED control requires `RPi.GPIO` which only works on Raspberry Pi
- Preview mode (`--preview`) disables LED control automatically
- On non-Pi systems, LED initialization is skipped safely

## Safe Shutdown

The LED controller automatically cleans up GPIO on shutdown:

```python
app.shutdown()  # Turns off all LEDs and cleanups GPIO
```

## Notes

- Each LED uses ~20mA with 330Ω resistor and 3.3V GPIO
- 3x LEDs = ~60mA total (safe for Pi GPIO)
- If using longer wires, consider lower resistor values (220Ω) for better brightness
- Always use resistors to protect GPIO pins and LEDs
