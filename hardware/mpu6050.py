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
            time.sleep(0.1)
            return True
        except Exception as e:
            print(f"[IMU] Initialization failed: {e}")
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
            print(f"[IMU] I2C Read Error at 0x{addr:02x}: {e}")
            # Try to recover the bus if it fails
            self._init_sensor()
            return self.last_raw_z # Return last known to avoid sudden jumps

    def calibrate(self, samples=100):
        print(f"Calibrating MPU6050 at 0x{self.address:02x}... Keep it still.")
        sum_z = 0
        valid_samples = 0
        for _ in range(samples):
            val = self.read_raw_data(0x47)
            if val is not None:
                sum_z += val
                valid_samples += 1
            time.sleep(0.01)
        
        if valid_samples > 0:
            self.gyro_z_offset = sum_z / valid_samples
            print(f"Calibration done. Offset: {self.gyro_z_offset:.2f}")
        else:
            print("[IMU] Calibration FAILED. No valid data.")

    def update_bearing(self):
        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time
        
        raw_z = self.read_raw_data(0x47)
        
        # Check for frozen sensor (same value many times in a row)
        if raw_z == self.last_raw_z and raw_z != 0:
            self.frozen_count += 1
            if self.frozen_count > 50: # If frozen for ~50 reads
                print("[IMU] Sensor seems frozen, restarting...")
                self._init_sensor()
                self.frozen_count = 0
        else:
            self.frozen_count = 0
            
        self.last_raw_z = raw_z
        
        # Sensitivity for FS_SEL=0 (default) is 131 LSB/degree/s
        gyro_z_rate = (raw_z - self.gyro_z_offset) / 131.0
        
        if abs(gyro_z_rate) < 0.2:
            gyro_z_rate = 0
            
        self.bearing += gyro_z_rate * dt
        self.bearing %= 360
        
        return self.bearing

    def reset_bearing(self):
        self.bearing = 0.0
