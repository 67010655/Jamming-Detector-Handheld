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
    spi.open(0, 1)
    spi.max_speed_hz = 50000  # ต่ำสุดๆ เพื่อลดสัญญาณรบกวน
    spi.mode = 0
    print("[OK] SPI0.1 opened")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

print("Testing all SPI Modes (0, 1, 2, 3)...")

try:
    while True:
        for mode in [0, 1, 2, 3]:
            spi.mode = mode
            # อ่าน X
            rx = spi.xfer2([0x90, 0, 0])
            x = ((rx[1] << 8) | rx[2]) >> 3
            # อ่าน Y
            ry = spi.xfer2([0xD0, 0, 0])
            y = ((ry[1] << 8) | ry[2]) >> 3
            
            if x > 10 or y > 10:
                print(f"MODE {mode} -> X: {x}, Y: {y}  << SUCCESS!")
                time.sleep(0.2)
        
        time.sleep(0.1)
except KeyboardInterrupt:
    spi.close()

