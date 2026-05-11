import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 1)
spi.max_speed_hz = 100000

print("--- Final Touch Calibration Test ---")
print("SPI is working! Now testing X and Y with optimized settings...")

try:
    while True:
        # ใช้ Mode 0 ตามที่เราเจอว่า Success
        spi.mode = 0
        
        # ลองอ่านแบบ Single-Ended (0x94 และ 0xD4) เผื่อแบบเดิมสัญญาณรบกวนเยอะ
        # 0x94 = X, 0xD4 = Y
        rx = spi.xfer2([0x94, 0, 0])
        x = ((rx[1] << 8) | rx[2]) >> 3
        
        ry = spi.xfer2([0xD4, 0, 0])
        y = ((ry[1] << 8) | ry[2]) >> 3
        
        if x > 20 or y > 20:
            print(f"TOUCH DETECTED! -> X: {x}, Y: {y}       ")
        else:
            print(f"Waiting for touch... (Raw X: {x}, Y: {y})", end='\r')
            
        time.sleep(0.1)
except KeyboardInterrupt:
    spi.close()
