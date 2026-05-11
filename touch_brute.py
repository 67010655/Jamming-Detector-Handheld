import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 1)
spi.max_speed_hz = 100000 # ลองความเร็วต่ำๆ เพื่อความชัวร์

print("--- XPT2046 Brute Force Test ---")
print("Trying to read with different commands...")

try:
    while True:
        # ลองอ่านทั้ง X (0x90) และ Y (0xD0) 
        # และลองโหมด 8-bit (0x98, 0xD8) เผื่อบางรุ่นรับค่าต่างกัน
        cmds = [0x90, 0xD0, 0x98, 0xD8]
        results = []
        
        for cmd in cmds:
            resp = spi.xfer2([cmd, 0, 0])
            val = ((resp[1] << 8) | resp[2]) >> 3
            results.append(val)
        
        print(f"X: {results[0]:>4} | Y: {results[1]:>4} | X8: {results[2]:>4} | Y8: {results[3]:>4}", end='\r')
        
        time.sleep(0.1)
except KeyboardInterrupt:
    spi.close()
    print("\nStopped.")
