"""
Magnetometer diagnostic tool.

Purpose
-------
Stop guessing the compass math. This captures raw 3-axis magnetometer data
while you rotate the device, then tells you mechanically:

  1. Which axis is VERTICAL (stays ~constant during a flat 360° turn) — discard it.
  2. Which two axes are HORIZONTAL (trace a sine wave) — use these for heading.
  3. The real hard-iron offset (circle center) on the horizontal axes.
  4. Whether the data is a clean circle (good) or a squashed ellipse (soft-iron).

It also runs an interference test: hold one heading still while the SDR is
idle, then while it is active. If the numbers jump, the GunJam case has a
time-varying magnetic field and NO static calibration will ever hold.

Usage
-----
  python3 diagnose_magnetometer.py

Hold the device in its NORMAL operating orientation (as you carry it) the
whole time. Follow the on-screen prompts.
"""
import time
import sys
import json
import math
from hardware.imu import create_imu, normalize_imu_model


def _open_imu():
    model = normalize_imu_model()
    try:
        imu = create_imu(model=model)
    except Exception as e:
        print(f"[FAIL] Could not initialize IMU: {e}")
        sys.exit(1)
    if not getattr(imu, "_mag_enabled", False):
        print("[FAIL] Magnetometer (AK8963) not enabled. Check I2C wiring.")
        sys.exit(1)
    return imu


def capture_rotation(imu, duration=20.0):
    """Capture hx, hy, hz while the user rotates the device 360 degrees."""
    print("\n=== STEP 1: ROTATION CAPTURE ===")
    print(f"Slowly rotate the device a FULL 360 degrees over the next {int(duration)}s,")
    print("keeping it in the SAME orientation you hold it during normal use.")
    print("Starting in 3 seconds...")
    time.sleep(3.0)
    print("--- GO: rotate slowly and smoothly ---")

    samples = []
    start = time.time()
    last_print = 0.0
    while time.time() - start < duration:
        raw = imu.read_mag_raw()
        if raw is not None and len(raw) == 3:
            hx, hy, hz = raw
            samples.append((hx, hy, hz))
        elapsed = time.time() - start
        if elapsed - last_print >= 0.5:
            pct = int(elapsed / duration * 100)
            bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
            sys.stdout.write(f"\r[{bar}] {pct}% | {len(samples)} samples")
            sys.stdout.flush()
            last_print = elapsed
        time.sleep(0.02)
    sys.stdout.write(f"\r[####################] 100% | {len(samples)} samples\n")
    return samples


def analyze(samples):
    if len(samples) < 50:
        print("\n[FAIL] Too few samples. Re-run and rotate more slowly.")
        return None

    xs = [s[0] for s in samples]
    ys = [s[1] for s in samples]
    zs = [s[2] for s in samples]

    stats = {}
    for name, vals in (("X", xs), ("Y", ys), ("Z", zs)):
        lo, hi = min(vals), max(vals)
        center = (lo + hi) / 2.0
        rng = hi - lo
        stats[name] = {"min": lo, "max": hi, "center": center, "range": rng}

    print("\n=== ANALYSIS ===")
    print(f"{'Axis':<5}{'min':>10}{'max':>10}{'center':>10}{'range':>10}")
    for name in ("X", "Y", "Z"):
        s = stats[name]
        print(f"{name:<5}{s['min']:>10.0f}{s['max']:>10.0f}{s['center']:>10.1f}{s['range']:>10.0f}")

    # Vertical axis = smallest swing during a horizontal turn.
    ranges = {n: stats[n]["range"] for n in ("X", "Y", "Z")}
    vertical = min(ranges, key=ranges.get)
    horizontal = [n for n in ("X", "Y", "Z") if n != vertical]

    print(f"\n--> VERTICAL axis (constant, discard): {vertical}")
    print(f"--> HORIZONTAL axes (use for heading):  {horizontal[0]} and {horizontal[1]}")

    # Hard-iron offsets on the two horizontal axes.
    h1, h2 = horizontal
    print(f"\nHard-iron offsets (circle center) for horizontal axes:")
    print(f"    {h1} offset = {stats[h1]['center']:.1f}")
    print(f"    {h2} offset = {stats[h2]['center']:.1f}")

    # Roundness check: ratio of the two horizontal ranges. 1.0 = perfect circle.
    r1, r2 = stats[h1]["range"], stats[h2]["range"]
    if min(r1, r2) > 0:
        ratio = max(r1, r2) / min(r1, r2)
        print(f"\nCircle roundness ratio: {ratio:.2f}  (1.0=perfect circle)")
        if ratio > 1.4:
            print("    [WARN] Strong soft-iron distortion (ellipse). A single")
            print("           offset will NOT fully fix heading. Soft-iron scaling needed.")
        else:
            print("    [OK] Reasonably circular — hard-iron offset should work.")

    return {"stats": stats, "vertical": vertical, "horizontal": horizontal}


def interference_test(imu, seconds=6.0):
    """Hold still; measure mag noise. Run once SDR-idle, once SDR-active."""
    print(f"\nHold the device PERFECTLY STILL for {int(seconds)}s...")
    time.sleep(1.0)
    xs, ys, zs = [], [], []
    start = time.time()
    while time.time() - start < seconds:
        raw = imu.read_mag_raw()
        if raw is not None and len(raw) == 3:
            xs.append(raw[0]); ys.append(raw[1]); zs.append(raw[2])
        time.sleep(0.02)
    if not xs:
        print("    [FAIL] no samples")
        return None
    avg = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
    spread = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    print(f"    avg   X={avg[0]:.0f}  Y={avg[1]:.0f}  Z={avg[2]:.0f}")
    print(f"    noise X={spread[0]:.0f}  Y={spread[1]:.0f}  Z={spread[2]:.0f}")
    return {"avg": avg, "noise": spread}


def main():
    print("=" * 60)
    print(" GY-9250 MAGNETOMETER DIAGNOSTIC")
    print("=" * 60)
    imu = _open_imu()

    samples = capture_rotation(imu)
    result = analyze(samples)

    print("\n=== STEP 2: SDR INTERFERENCE TEST ===")
    print("First, make sure the SDR / detector app is NOT running.")
    input("Press ENTER when SDR is IDLE...")
    idle = interference_test(imu)

    print("\nNow START the SDR (run the detector, or trigger scanning).")
    input("Press ENTER when SDR is ACTIVE...")
    active = interference_test(imu)

    if idle and active:
        shift = math.sqrt(
            (idle["avg"][0] - active["avg"][0]) ** 2 +
            (idle["avg"][1] - active["avg"][1]) ** 2 +
            (idle["avg"][2] - active["avg"][2]) ** 2
        )
        print(f"\n--> Field shift when SDR turns on: {shift:.0f} units")
        if shift > 30:
            print("    [CRITICAL] The SDR moves the magnetic field. No static")
            print("    calibration will hold. Recommend gyro-relative heading")
            print("    with a manual 'set North', OR move the AK8963 away from SDR.")
        else:
            print("    [OK] SDR interference is small. Calibration can work.")

    # Save everything for sharing/analysis.
    out = {
        "rotation_samples": samples,
        "analysis": result,
        "sdr_idle": idle,
        "sdr_active": active,
    }
    with open("mag_diagnostic.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("\n[SAVED] Full data written to mag_diagnostic.json")
    print("Send that file back so the exact heading formula can be set.")


if __name__ == "__main__":
    main()
