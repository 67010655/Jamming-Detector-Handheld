import smbus2
import time
import math

class MPU6050:
    def __init__(self, address=0x69, bus=1):
        self.address = address
        self.bus = smbus2.SMBus(bus)
        # Wake up the MPU6050 as it starts in sleep mode
        self.bus.write_byte_data(self.address, 0x6B, 0)
        
        self.last_time = time.time()
        self.bearing = 0.0 # Relative bearing in degrees
        
        # Calibration offsets (will be calculated on start)
        self.gyro_z_offset = 0

    def read_raw_data(self, addr):
        # Accel and Gyro data are 16-bit
        high = self.bus.read_byte_data(self.address, addr)
        low = self.bus.read_byte_data(self.address, addr + 1)
        
        # Combine high and low bytes
        value = ((high << 8) | low)
        
        # Get signed value
        if value > 32768:
            value = value - 65536
        return value

    def calibrate(self, samples=100):
        print(f"Calibrating MPU6050 at 0x{self.address:02x}... Keep it still.")
        sum_z = 0
        for _ in range(samples):
            sum_z += self.read_raw_data(0x47) # Gyro Z register
            time.sleep(0.01)
        self.gyro_z_offset = sum_z / samples
        print(f"Calibration done. Offset: {self.gyro_z_offset:.2f}")

    def update_bearing(self):
        """
        Call this frequently to integrate gyro data into a bearing angle.
        """
        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time
        
        # Read raw Gyro Z and remove offset
        # Sensitivity for FS_SEL=0 (default) is 131 LSB/degree/s
        raw_z = self.read_raw_data(0x47)
        gyro_z_rate = (raw_z - self.gyro_z_offset) / 131.0
        
        # Integrate to get angle (Bearing)
        self.bearing += gyro_z_rate * dt
        
        # Keep bearing within 0-360 degrees
        self.bearing %= 360
        
        return self.bearing

    def reset_bearing(self):
        self.bearing = 0.0
