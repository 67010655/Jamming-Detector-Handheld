import time
import sys
import re
import math
from hardware.imu import create_imu, normalize_imu_model

def update_config_file(x_offset, y_offset):
    config_path = "config.py"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Update X offset using regex
        content = re.sub(
            r"IMU_MAG_OFFSET_X\s*=\s*[-+]?\d*\.\d+|\bIMU_MAG_OFFSET_X\s*=\s*[-+]?\d+",
            f"IMU_MAG_OFFSET_X = {x_offset:.1f}",
            content
        )
        # Update Y offset using regex
        content = re.sub(
            r"IMU_MAG_OFFSET_Y\s*=\s*[-+]?\d*\.\d+|\bIMU_MAG_OFFSET_Y\s*=\s*[-+]?\d+",
            f"IMU_MAG_OFFSET_Y = {y_offset:.1f}",
            content
        )

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("\n[SUCCESS] config.py updated successfully!")
        print(f"  IMU_MAG_OFFSET_X = {x_offset:.1f}")
        print(f"  IMU_MAG_OFFSET_Y = {y_offset:.1f}")
    except Exception as e:
        print(f"\n[ERROR] Failed to write to config.py: {e}")

def main():
    print("=== GY-9250 Magnetometer Calibration Utility ===")
    print("This script will calculate hard-iron magnetic offsets for your handheld device.")
    print("---------------------------------------------------------------------")
    
    # Initialize sensor
    imu_model = normalize_imu_model()
    try:
        imu = create_imu(model=imu_model)
    except Exception as e:
        print(f"[FAIL] Could not initialize IMU: {e}")
        return

    # Check if magnetometer is supported and enabled
    if not getattr(imu, "_mag_enabled", False):
        print("[FAIL] Magnetometer (AK8963) is not enabled or not found on I2C bus.")
        print("Please check your I2C connections and ensure AD0 is connected to 3.3V.")
        return

    print("\n[INSTRUCTION] Please prepare to rotate the device in all directions.")
    print("You should rotate it 360 degrees horizontally and tip it up/down (figure-8 pattern).")
    print("Calibration will start in 3 seconds...")
    time.sleep(3.0)

    print("\n--- CALIBRATING NOW: ROTATE THE SENSOR SLOWLY ---")
    
    x_min, x_max = 99999.0, -99999.0
    y_min, y_max = 99999.0, -99999.0
    
    duration = 15.0  # seconds
    start_time = time.time()
    last_print = 0
    samples_collected = 0

    while time.time() - start_time < duration:
        raw = imu.read_mag_raw()
        if raw is not None:
            hx, hy, _hz = raw
            x_min = min(x_min, hx)
            x_max = max(x_max, hx)
            y_min = min(y_min, hy)
            y_max = max(y_max, hy)
            samples_collected += 1
            
        elapsed = time.time() - start_time
        if elapsed - last_print >= 0.5:
            # Print a progress bar
            pct = int((elapsed / duration) * 100)
            bar = "#" * (pct // 5) + "-" * (20 - (pct // 5))
            sys.stdout.write(f"\r[{bar}] {pct}% | Collected: {samples_collected} samples")
            sys.stdout.flush()
            last_print = elapsed
            
        time.sleep(0.02)  # ~50Hz sample rate

    sys.stdout.write(f"\r[####################] 100% | Collected: {samples_collected} samples\n")
    sys.stdout.flush()

    if samples_collected < 50:
        print("\n[FAIL] Too few valid magnetometer samples collected. Check wiring.")
        return

    print("\n--- Calibration Results ---")
    print(f"X Range: [{x_min}, {x_max}]")
    print(f"Y Range: [{y_min}, {y_max}]")

    # Hard-iron offset calculation
    x_offset = (x_max + x_min) / 2.0
    y_offset = (y_max + y_min) / 2.0

    print(f"\nCalculated Hard-Iron Offsets:")
    print(f"  Offset X: {x_offset:.1f}")
    print(f"  Offset Y: {y_offset:.1f}")

    update_config_file(x_offset, y_offset)

if __name__ == "__main__":
    main()
