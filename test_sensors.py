import time
import sys
import config
from hardware.imu import create_imu, normalize_imu_model

def main():
    try:
        # Initialize sensors
        imu_model = normalize_imu_model()
        imu = create_imu(model=imu_model)
        # RTC is handled by Kernel now, so we use system time
        
        print("--- Sensor Test Utility ---")
        print(f"IMU Model: {imu_model} at 0x{imu.address:02x}")
        print(f"System Time (Synced with RTC): {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Calibrate IMU
        print("\nStarting IMU Calibration. PLEASE KEEP THE DEVICE STILL...")
        imu.calibrate(samples=50)
        
        print("\nStarting live view (Press Ctrl+C to stop)...")
        has_mag = hasattr(imu, "get_heading_mag")
        print("Time | Bearing (Degrees)" + (" | Mag Heading" if has_mag else ""))
        print("-" * 30)
        
        while True:
            bearing = imu.update_bearing()
            timestamp = time.strftime('%H:%M:%S')
            mag_heading = imu.get_heading_mag() if has_mag else None
            
            # Print with carriage return to update the same line
            line = f"\r{timestamp} | Bearing: {bearing:6.2f} deg"
            if has_mag:
                mag_text = "--" if mag_heading is None else f"{mag_heading:6.2f} deg"
                line += f" | Mag: {mag_text}"
            sys.stdout.write(line)
            sys.stdout.flush()
            
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()
