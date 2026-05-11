import spidev
import time
import RPi.GPIO as GPIO

# ตั้งค่าพิน CS เอง (Pin 26 = GPIO 7)
CS_PIN = 7
GPIO.setmode(GPIO.BCM)
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.output(CS_PIN, GPIO.HIGH) # เริ่มต้นด้วย High (ยังไม่เลือก chip)

spi = spidev.SpiDev()
spi.open(0, 1)
spi.max_speed_hz = 100000
spi.mode = 0

print("--- Manual CS Control Test ---")
print("Manually toggling GPIO 7 (Pin 26)...")

try:
    while True:
        # สั่งเลือก chip ด้วยมือ (Pull LOW)
        GPIO.output(CS_PIN, GPIO.LOW)
        
        # ส่งคำสั่งอ่าน X
        resp = spi.xfer2([0x90, 0, 0])
        x_val = ((resp[1] << 8) | resp[2]) >> 3
        
        # ส่งคำสั่งอ่าน Y
        resp = spi.xfer2([0xD0, 0, 0])
        y_val = ((resp[1] << 8) | resp[2]) >> 3
        
        # ปล่อย chip (Pull HIGH)
        GPIO.output(CS_PIN, GPIO.HIGH)
        
        if x_val > 0 or y_val > 0:
            print(f"FOUND DATA! -> X: {x_val}, Y: {y_val}")
        else:
            print("Still zero...", end='\r')
            
        time.sleep(0.1)
        
except KeyboardInterrupt:
    GPIO.cleanup()
    spi.close()
    print("\nStopped.")
