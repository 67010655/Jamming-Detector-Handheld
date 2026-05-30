import time
import sys
import config

# Dynamically import correct IMU model based on configuration
IMU_MODEL = getattr(config, 'IMU_MODEL', 'MPU6050').upper()
if IMU_MODEL == 'MPU9250':
    from hardware.mpu9250 import MPU9250 as IMU_CLASS
else:
    from hardware.mpu6050 import MPU6050 as IMU_CLASS

def main():
    try:
        # Initialize sensors
        imu = IMU_CLASS(address=getattr(config, 'IMU_ADDRESS', 0x69))
        # RTC is handled by Kernel now, so we use system time
        
        print("--- Sensor Test Utility ---")
        print(f"System Time (Synced with RTC): {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Calibrate IMU
        print("\nStarting IMU Calibration. PLEASE KEEP THE DEVICE STILL...")
        imu.calibrate(samples=50)
        
        print("\nStarting live view (Press Ctrl+C to stop)...")
        print("Time | Bearing (Degrees)")
        print("-" * 30)
        
        while True:
            bearing = imu.update_bearing()
            timestamp = time.strftime('%H:%M:%S')
            
            # Print with carriage return to update the same line
            sys.stdout.write(f"\r{timestamp} | Bearing: {bearing:6.2f} deg")
            sys.stdout.flush()
            
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()
