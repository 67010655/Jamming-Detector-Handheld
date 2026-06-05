"""
GY-9250 / MPU9250 IMU driver for the permanent 9-axis hardware build.

Address scheme
--------------
  0x68  MPU9250 main registers (gyro / accel / config).  AD0 pin = LOW (default).
  0x0C  AK8963 magnetometer.  Reached via I2C bypass mode: the MPU9250 I2C-master
        lines are bridged to the host I2C bus by setting BYPASS_EN in INT_PIN_CFG
        (register 0x37), so the host processor can address the AK8963 directly.
"""
try:
    import smbus2
except ImportError:
    smbus2 = None

import time
import math
import config


class MPU9250:
    # ── AK8963 magnetometer registers ──────────────────────────────────
    _AK8963_ADDR  = 0x0C
    _AK8963_WIA   = 0x00   # Who-am-I (expected 0x48)
    _AK8963_ST1   = 0x02   # Status 1: bit 0 = DRDY
    _AK8963_HXL   = 0x03   # Mag data first byte (HXL … HZH, then ST2)
    _AK8963_ST2   = 0x09   # Status 2: bit 3 = HOFL (overflow); must read to release latch
    _AK8963_CNTL1 = 0x0A   # Control 1: measurement mode
    _AK8963_CONT2 = 0x16   # Continuous measurement mode 2 (100 Hz, 16-bit output)

    # ── MPU9250 registers (subset) ──────────────────────────────────────
    _PWR_MGMT_1  = 0x6B
    _GYRO_CONFIG = 0x1B
    _INT_PIN_CFG = 0x37    # bit 1 = I2C_BYPASS_EN
    _USER_CTRL   = 0x6A    # bit 5 = I2C_MST_EN (disable to allow bypass)

    def __init__(self, address=None, bus=1):
        configured_address = getattr(config, 'IMU_ADDRESS', None)
        self.address = address if address is not None else (configured_address if configured_address is not None else 0x69)
        self.bus_num = bus
        self.bus = None
        self.last_time = time.time()
        self.bearing = 0.0
        self.gyro_z_offset = 0
        self.last_raw_z = 0
        self.frozen_count = 0
        self._init_success = False
        self._mag_enabled = False

        # Load sensor fusion and magnetometer settings from config
        self.fusion_mode = getattr(config, 'IMU_FUSION_MODE', 'COMPLEMENTARY')
        self.fusion_alpha = getattr(config, 'IMU_FUSION_ALPHA', 0.96)
        self.mag_offset_x = getattr(config, 'IMU_MAG_OFFSET_X', 0.0)
        self.mag_offset_y = getattr(config, 'IMU_MAG_OFFSET_Y', 0.0)
        self.declination_deg = getattr(config, 'IMU_DECLINATION_DEG', 0.0)
        self.mag_smooth_alpha = getattr(config, 'IMU_MAG_SMOOTH_ALPHA', 0.1)
        self._mag_smooth_x = None
        self._mag_smooth_y = None
        self.bearing_initialized = False

        self._init_sensor()

    # ── sensor init ─────────────────────────────────────────────────────
    def _init_sensor(self):
        """Initialize or re-initialize MPU9250 and AK8963."""
        if smbus2 is None:
            print("[IMU9] smbus2 not available (expected on Windows). Simulated IMU enabled.")
            self._init_success = False
            return False
        try:
            if self.bus:
                try:
                    self.bus.close()
                except Exception:
                    pass
            self.bus = smbus2.SMBus(self.bus_num)
            # Reset MPU9250 to ensure clean boot
            self.bus.write_byte_data(self.address, self._PWR_MGMT_1, 0x80)
            time.sleep(0.1)
            # Wake MPU9250 and set clock source to Gyro Z for stability
            self.bus.write_byte_data(self.address, self._PWR_MGMT_1, 0x01)
            time.sleep(0.1)
            # Gyro full-scale ±250 °/s (131 LSB/°/s, most sensitive)
            self.bus.write_byte_data(self.address, self._GYRO_CONFIG, 0x00)
            # Enable I2C bypass so host can reach AK8963 directly
            self.bus.write_byte_data(self.address, self._USER_CTRL, 0x00)    # disable I2C master
            self.bus.write_byte_data(self.address, self._INT_PIN_CFG, 0x02)  # set BYPASS_EN
            time.sleep(0.1)
            self._mag_enabled = self._init_magnetometer()
            self._init_success = True
            return True
        except Exception as e:
            print(f"[IMU9] Initialization failed at 0x{self.address:02x}: {e}")
            self._init_success = False
            return False

    def _init_magnetometer(self):
        try:
            self.bus.write_byte_data(self._AK8963_ADDR, self._AK8963_CNTL1, 0x00)
            time.sleep(0.01)
            self.bus.write_byte_data(self._AK8963_ADDR, self._AK8963_CNTL1, self._AK8963_CONT2)
            time.sleep(0.01)
            return True
        except Exception as e:
            print(f"[IMU9] Magnetometer unavailable at 0x{self._AK8963_ADDR:02x}: {e}")
            return False

    # ── gyro helpers ────────────────────────────────────────────────────
    def _get_gyro_register(self):
        axis = getattr(config, 'IMU_GYRO_AXIS', 'Z').upper()
        if axis == 'X':
            return 0x43
        elif axis == 'Y':
            return 0x45
        else:
            return 0x47  # Z (default)

    def _read_gyro_raw(self):
        if self.bus is None:
            return None
        try:
            addr = self._get_gyro_register()
            high = self.bus.read_byte_data(self.address, addr)
            low  = self.bus.read_byte_data(self.address, addr + 1)
            value = (high << 8) | low
            if value > 32768:
                value -= 65536
            return value
        except Exception:
            return None

    # ── public interface ─────────────────────────────────────────────────
    def calibrate(self, samples=150):
        """Read gyro at rest to compute zero-offset."""
        axis_name = getattr(config, 'IMU_GYRO_AXIS', 'Z').upper()
        print(f"Calibrating MPU9250 ({axis_name}-Axis) at 0x{self.address:02x}... PLEASE KEEP STILL.")
        sum_z = 0
        valid_count = 0

        for _ in range(20):  # warm-up
            self._read_gyro_raw()
            time.sleep(0.01)

        for _ in range(samples):
            val = self._read_gyro_raw()
            if val is not None:
                sum_z += val
                valid_count += 1
            time.sleep(0.01)

        if valid_count > 10:
            self.gyro_z_offset = sum_z / valid_count
            self._init_success = True
            print(f"Calibration done. Offset: {self.gyro_z_offset:.2f} (from {valid_count} samples)")
        else:
            self._init_success = False
            print("[IMU9] Calibration FAILED — too few valid I2C reads. Check wiring.")

    def update_bearing(self):
        """Get absolute heading (via complementary fusion, raw mag, or gyro fallback)."""
        if self.bus is None:
            return 0.0
        if not self._init_success:
            return self.bearing

        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time

        raw_z = self._read_gyro_raw()
        if raw_z is None:
            return self.bearing

        # Frozen sensor recovery: detect stuck readings after 40 identical frames
        if raw_z == self.last_raw_z and raw_z != 0:
            self.frozen_count += 1
            if self.frozen_count > 40:
                print("[IMU9] Sensor stuck, attempting recovery...")
                self._init_sensor()
                self.frozen_count = 0
                return self.bearing
        else:
            self.frozen_count = 0
        self.last_raw_z = raw_z

        # 131 LSB/(°/s) at FS_SEL=0
        gyro_rate = (raw_z - self.gyro_z_offset) / 131.0

        # Deadzone + dynamic drift correction
        if abs(gyro_rate) < 2.0:
            self.gyro_z_offset = self.gyro_z_offset * 0.99 + raw_z * 0.01
            gyro_rate = 0

        invert = getattr(config, 'IMU_INVERT_GYRO', False)
        direction = -1.0 if invert else 1.0
        gyro_delta = gyro_rate * dt * direction

        # Fetch absolute magnetometer heading
        mag_heading = self.get_heading_mag()

        if self.fusion_mode == 'MAG_ONLY' and mag_heading is not None:
            self.bearing = mag_heading
            self.bearing_initialized = True
        elif self.fusion_mode == 'COMPLEMENTARY' and mag_heading is not None:
            # Gyro prediction
            gyro_predicted = (self.bearing + gyro_delta) % 360
            if not self.bearing_initialized:
                # Seed with magnetic heading initially to avoid slow convergence
                self.bearing = mag_heading
                self.bearing_initialized = True
            else:
                # Shortest angular distance to prevent wrapping spin at 0/360 boundary
                diff = mag_heading - gyro_predicted
                diff = (diff + 180) % 360 - 180
                # Complementary filter fusion
                self.bearing = (gyro_predicted + (1.0 - self.fusion_alpha) * diff) % 360
        else:
            # Fallback to pure gyro integration
            self.bearing = (self.bearing + gyro_delta) % 360

        return self.bearing

    def read_mag_raw(self):
        """Read raw X and Y from the AK8963 magnetometer. Returns (hx, hy) or None."""
        if self.bus is None or not self._mag_enabled:
            return None
        try:
            st1 = self.bus.read_byte_data(self._AK8963_ADDR, self._AK8963_ST1)
            if not (st1 & 0x01):
                return None  # data not ready

            # Read HXL…HZH + ST2 (7 bytes); ST2 must be read to release the latch
            data = self.bus.read_i2c_block_data(self._AK8963_ADDR, self._AK8963_HXL, 7)
            if data[6] & 0x08:
                return None  # magnetic sensor overflow

            hx = (data[1] << 8) | data[0]
            hy = (data[3] << 8) | data[2]
            if hx > 32767:
                hx -= 65536
            if hy > 32767:
                hy -= 65536
            return hx, hy
        except Exception:
            return None

    def get_heading_mag(self):
        """
        Read AK8963 and return magnetic heading in degrees (0–360) aligned with True North.
        Returns None if bus unavailable, data not ready, or sensor overflow.
        """
        raw = self.read_mag_raw()
        if raw is None:
            return None
        hx, hy = raw
        mx = float(hx) - self.mag_offset_x
        my = float(hy) - self.mag_offset_y

        # EMA low-pass filter to reduce magnetometer noise
        if self._mag_smooth_x is None:
            self._mag_smooth_x = mx
            self._mag_smooth_y = my
        else:
            a = self.mag_smooth_alpha
            self._mag_smooth_x = a * mx + (1.0 - a) * self._mag_smooth_x
            self._mag_smooth_y = a * my + (1.0 - a) * self._mag_smooth_y

        heading = math.degrees(math.atan2(-self._mag_smooth_y, -self._mag_smooth_x)) + self.declination_deg
        return heading % 360

    def reset_bearing(self):
        self.bearing = 0.0
        self.bearing_initialized = False

