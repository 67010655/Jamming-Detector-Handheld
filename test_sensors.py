from hardware.mpu6050 import MPU6050
from hardware.rtc_ds3231 import DS3231
import time
import sys

def main():
    try:
        # Initialize sensors
        imu = MPU6050(address=0x69)
        rtc = DS3231(address=0x68)
        
        print("--- Sensor Test Utility ---")
        print(f"Current RTC Time: {rtc.get_timestamp_str()}")
        
        # Calibrate IMU
        print("\nStarting IMU Calibration. PLEASE KEEP THE DEVICE STILL...")
        imu.calibrate(samples=50)
        
        print("\nStarting live view (Press Ctrl+C to stop)...")
        print("Time | Bearing (Degrees)")
        print("-" * 30)
        
        while True:
            bearing = imu.update_bearing()
            timestamp = rtc.get_timestamp_str()
            
            # Print with carriage return to update the same line
            sys.stdout.write(f"\r{timestamp} | Bearing: {bearing:6.2f}°")
            sys.stdout.flush()
            
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()
