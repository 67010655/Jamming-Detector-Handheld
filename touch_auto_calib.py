import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 1)
spi.max_speed_hz = 100000
spi.mode = 0

x_min, x_max = 4095, 0
y_min, y_max = 4095, 0

print("=" * 50)
print("   Touch Auto-Calibration Tool")
print("=" * 50)
print("Instructions:")
print("1. Drag your finger to all 4 corners and along the edges.")
print("2. The script will track the MIN and MAX values seen.")
print("3. Press Ctrl+C when you are done.")
print("-" * 50)

try:
    while True:
        # Read X and Y
        rx = spi.xfer2([0x94, 0, 0])
        x = ((rx[1] << 8) | rx[2]) >> 3
        
        ry = spi.xfer2([0xD4, 0, 0])
        y = ((ry[1] << 8) | ry[2]) >> 3
        
        # Only track if actually touching (not 0 or 4095 noise)
        if 50 < x < 4000 and 50 < y < 4000:
            if x < x_min: x_min = x
            if x > x_max: x_max = x
            if y < y_min: y_min = y
            if y > y_max: y_max = y
            
            print(f"Current: ({x:>4}, {y:>4}) | X: [{x_min} - {x_max}] | Y: [{y_min} - {y_max}]    ", end='\r')
            
        time.sleep(0.02)
except KeyboardInterrupt:
    print("\n" + "=" * 50)
    print("FINAL CALIBRATION VALUES:")
    print(f"X_MIN = {x_min}")
    print(f"X_MAX = {x_max}")
    print(f"Y_MIN = {y_min}")
    print(f"Y_MAX = {y_max}")
    print("=" * 50)
    spi.close()
