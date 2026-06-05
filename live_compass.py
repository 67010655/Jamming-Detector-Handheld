"""
Live magnetometer readout — pure mag, no gyro fusion.

This reads the AK8963 directly and prints the computed magnetic heading in
real time. It does NOT use the complementary filter, so what you see is 100%
magnetometer (unlike the main app, which is mostly gyro).

How to use
----------
1. Run it:  python3 live_compass.py
2. CHECK the offsets line says X=-171.0  Z=393.0
   If it shows different numbers, the Pi is running OLD code (git pull failed).
3. Hold the device in your NORMAL operating position (the SAME way you held it
   during the 360 rotation capture). Keep that hold for every reading.
4. Using your iPhone compass, point the device at NORTH. Read the HEADING value.
5. Then point it at EAST. Read the HEADING value.
6. Send both numbers back. The exact sign + offset will be set from them.

Press Ctrl+C to stop.
"""
import time
import sys
import config
from hardware.imu import create_imu, normalize_imu_model


def main():
    print("=" * 56)
    print(" LIVE MAG COMPASS (pure magnetometer, no gyro)")
    print("=" * 56)

    ox = getattr(config, "IMU_MAG_OFFSET_X", None)
    oz = getattr(config, "IMU_MAG_OFFSET_Z", None)
    inv = getattr(config, "IMU_MAG_INVERT", None)
    coff = getattr(config, "IMU_COMPASS_OFFSET_DEG", None)
    print(f"Loaded offsets:  X={ox}   Z={oz}")
    print(f"Invert={inv}   CompassOffset={coff}")
    if ox != -171.0 or oz != 393.0:
        print(">>> WARNING: offsets are not X=-171 Z=393.")
        print(">>> The Pi may be running OLD code. Re-run: git stash && git pull")
    print()

    imu = create_imu(model=normalize_imu_model())
    if not getattr(imu, "_mag_enabled", False):
        print("[FAIL] Magnetometer not enabled. Check I2C wiring.")
        return

    print("Hold the device in NORMAL position (same as the 360 capture).")
    print("Point at a known direction (iPhone) and read HEADING.\n")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            heading = imu.get_heading_mag()
            sx = getattr(imu, "_mag_smooth_x", None)
            sz = getattr(imu, "_mag_smooth_z", None)
            if heading is not None and sx is not None:
                sys.stdout.write(
                    f"\r X={sx:8.0f}  Z={sz:8.0f}  |  HEADING = {heading:6.1f} deg     "
                )
                sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
