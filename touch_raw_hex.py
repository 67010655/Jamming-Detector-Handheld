import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 1)
spi.max_speed_hz = 50000
spi.mode = 0

print("--- XPT2046 Raw Hex Diagnostic ---")
print("Press and move your finger on the screen...")

try:
    while True:
        # อ่าน X
        rx = spi.xfer2([0x90, 0, 0])
        # อ่าน Y
        ry = spi.xfer2([0xD0, 0, 0])
        
        # พิมพ์ค่าดิบเป็น HEX
        print(f"RAW X: [{hex(rx[0])}, {hex(rx[1])}, {hex(rx[2])}] | RAW Y: [{hex(ry[0])}, {hex(ry[1])}, {hex(ry[2])}]", end='\r')
        
        time.sleep(0.1)
except KeyboardInterrupt:
    spi.close()
