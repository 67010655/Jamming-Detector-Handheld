try:
    import smbus2
except ImportError:
    smbus2 = None
import time
import math
import config

class MPU6050:
    def __init__(self, address=None, bus=1):
        self.address = address if address is not None else getattr(config, 'IMU_ADDRESS', 0x69)
        self.bus_num = bus
        self.bus = None
        self.last_time = time.time()
        self.bearing = 0.0 # Relative bearing in degrees
        self.gyro_z_offset = 0
        self.last_raw_z = 0
        self.frozen_count = 0
        self._init_success = False
        
        self._init_sensor()

    def _get_gyro_register(self):
        axis = getattr(config, 'IMU_GYRO_AXIS', 'Z').upper()
        if axis == 'X':
            return 0x43
        elif axis == 'Y':
            return 0x45
        else:
            return 0x47 # Default Z

    def _init_sensor(self):
        """Initialize or Re-initialize the sensor."""
        if smbus2 is None:
            print("[IMU] smbus2 module is not available (expected on Windows). Simulated IMU enabled.")
            self._init_success = False
            return False
        try:
            if self.bus:
                try:
                    self.bus.close()
                except:
                    pass
            self.bus = smbus2.SMBus(self.bus_num)
            # Wake up the MPU6050
            self.bus.write_byte_data(self.address, 0x6B, 0)
            # Set Gyro Full Scale Range to 250deg/s (most sensitive)
            self.bus.write_byte_data(self.address, 0x1B, 0x00)
            time.sleep(0.1)
            self._init_success = True
            return True
        except Exception as e:
            print(f"[IMU] Initialization failed at 0x{self.address:02x}: {e}")
            self._init_success = False
            return False

    def read_raw_data(self, addr):
        if self.bus is None:
            return None
        try:
            high = self.bus.read_byte_data(self.address, addr)
            low = self.bus.read_byte_data(self.address, addr + 1)
            value = ((high << 8) | low)
            if value > 32768:
                value = value - 65536
            return value
        except Exception as e:
            # On I2C error, return None to indicate failure
            # Don't try to re-init here to avoid blocking the main loop
            return None

    def calibrate(self, samples=200):
        addr = self._get_gyro_register()
        axis_name = getattr(config, 'IMU_GYRO_AXIS', 'Z').upper()
        print(f"Calibrating MPU6050 ({axis_name}-Axis) at 0x{self.address:02x}... PLEASE KEEP STILL.")
        sum_z = 0
        valid_count = 0
        
        # Warm up
        for _ in range(20):
            self.read_raw_data(addr)
            time.sleep(0.01)

        for _ in range(samples):
            val = self.read_raw_data(addr)
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
            print("[IMU] Calibration FAILED — too few valid I2C reads. Check wiring. Bearing integration disabled.")

    def update_bearing(self):
        if not self._init_success:
            return self.bearing  # Calibration failed — skip integration to avoid drift

        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time
        
        addr = self._get_gyro_register()
        raw_z = self.read_raw_data(addr)
        
        # If I2C failed, don't integrate anything
        if raw_z is None:
            return self.bearing

        # Check for frozen sensor (stuck at exact same non-zero value)
        if raw_z == self.last_raw_z and raw_z != 0:
            self.frozen_count += 1
            if self.frozen_count > 40:
                print("[IMU] Sensor stuck, attempting recovery...")
                self._init_sensor()
                self.frozen_count = 0
                return self.bearing
        else:
            self.frozen_count = 0
            
        self.last_raw_z = raw_z
        
        # Sensitivity for FS_SEL=0 is 131.0 LSB/deg/s
        # Calculate rate and remove offset
        gyro_rate = (raw_z - self.gyro_z_offset) / 131.0
        
        # Dynamic Calibration & Deadzone
        # If the movement is very small, assume the device is still.
        # This will filter out noise AND automatically correct long-term drift.
        if abs(gyro_rate) < 2.0:
            # Slowly adjust the offset to compensate for temperature/bias drift
            self.gyro_z_offset = (self.gyro_z_offset * 0.99) + (raw_z * 0.01)
            gyro_rate = 0
            
        # Apply inversion if configured
        invert = getattr(config, 'IMU_INVERT_GYRO', False)
        direction = -1.0 if invert else 1.0
        
        self.bearing += gyro_rate * dt * direction
        self.bearing %= 360
        
        return self.bearing

    def reset_bearing(self):
        self.bearing = 0.0
