import smbus2
import time
import math

class MPU6050:
    def __init__(self, address=0x69, bus=1):
        self.address = address
        self.bus_num = bus
        self.bus = None
        self.last_time = time.time()
        self.bearing = 0.0 # Relative bearing in degrees
        self.gyro_z_offset = 0
        self.last_raw_z = 0
        self.frozen_count = 0
        self._init_success = False
        
        self._init_sensor()

    def _init_sensor(self):
        """Initialize or Re-initialize the sensor."""
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
            print(f"[IMU] Initialization failed: {e}")
            self._init_success = False
            return False

    def read_raw_data(self, addr):
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
        print(f"Calibrating MPU6050 at 0x{self.address:02x}... PLEASE KEEP STILL.")
        sum_z = 0
        valid_count = 0
        
        # Warm up
        for _ in range(20):
            self.read_raw_data(0x47)
            time.sleep(0.01)

        for _ in range(samples):
            val = self.read_raw_data(0x47)
            if val is not None:
                sum_z += val
                valid_count += 1
            time.sleep(0.01)
        
        if valid_count > 10:
            self.gyro_z_offset = sum_z / valid_count
            print(f"Calibration done. Offset: {self.gyro_z_offset:.2f} (from {valid_count} samples)")
        else:
            print("[IMU] Calibration FAILED. Check wiring.")

    def update_bearing(self):
        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time
        
        raw_z = self.read_raw_data(0x47)
        
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
        gyro_z_rate = (raw_z - self.gyro_z_offset) / 131.0
        
        # Dynamic Calibration & Deadzone
        # If the movement is very small, assume the device is still.
        # This will filter out noise AND automatically correct long-term drift.
        if abs(gyro_z_rate) < 2.0:
            # Slowly adjust the offset to compensate for temperature/bias drift
            self.gyro_z_offset = (self.gyro_z_offset * 0.99) + (raw_z * 0.01)
            gyro_z_rate = 0
            
        self.bearing += gyro_z_rate * dt
        self.bearing %= 360
        
        return self.bearing

    def reset_bearing(self):
        self.bearing = 0.0
