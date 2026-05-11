#!/usr/bin/env python3
"""
Touch Diagnostic Tool for XPT2046
Run this script on the Pi to see what the touch controller is sending.
Usage: python3 touch_test.py
Press Ctrl+C to stop.
"""
import spidev
import time

print("=" * 50)
print("  XPT2046 Touch Diagnostic Tool")
print("=" * 50)
print()

# Open SPI
spi = spidev.SpiDev()
try:
    spi.open(0, 1)  # Bus 0, Device 1 (CS1 = GPIO 7)
    spi.max_speed_hz = 500000
    spi.mode = 0
    print("[OK] SPI0.1 opened successfully")
except Exception as e:
    print(f"[FAIL] Cannot open SPI0.1: {e}")
    exit(1)

print()
print("Touch the screen now! Raw values will appear below.")
print("If values stay at 0 when you touch, wiring may be wrong.")
print("Press Ctrl+C to stop.")
print()
print(f"{'X_RAW':>8}  {'Y_RAW':>8}  {'Status'}")
print("-" * 40)

try:
    count = 0
    while True:
        # Read X channel (command 0x90 = X position, 12-bit, DFR mode)
        resp_x = spi.xfer2([0x90, 0x00, 0x00])
        x_raw = ((resp_x[1] << 8) | resp_x[2]) >> 3

        # Read Y channel (command 0xD0 = Y position, 12-bit, DFR mode)
        resp_y = spi.xfer2([0xD0, 0x00, 0x00])
        y_raw = ((resp_y[1] << 8) | resp_y[2]) >> 3

        # Print every reading so we can see what's happening
        if x_raw > 50 or y_raw > 50:
            print(f"{x_raw:>8}  {y_raw:>8}  << TOUCHED!")
        else:
            count += 1
            if count % 20 == 0:  # Print idle status every ~1 second
                print(f"{x_raw:>8}  {y_raw:>8}     (idle - no touch)")

        time.sleep(0.05)

except KeyboardInterrupt:
    print()
    print("Stopped.")
finally:
    spi.close()
