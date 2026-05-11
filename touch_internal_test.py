import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 1)
spi.max_speed_hz = 100000

print("--- XPT2046 Internal Sensor Test ---")
print("We are trying to read internal Reference Voltage (0x84)...")

try:
    while True:
        for mode in [0, 1, 2, 3]:
            spi.mode = mode
            # 0x84 คือคำสั่งอ่าน Internal Reference Voltage / Battery
            resp = spi.xfer2([0x84, 0, 0])
            val = ((resp[1] << 8) | resp[2]) >> 3
            
            if val > 0 and val < 4095:
                print(f"MODE {mode} -> SUCCESS! Internal Val: {val}       ")
            else:
                print(f"MODE {mode} -> Raw: {hex(resp[1])}, {hex(resp[2])} (Val: {val})", end='\r')
        
        time.sleep(0.2)
        print(" " * 50, end='\r') # Clear line
except KeyboardInterrupt:
    spi.close()
