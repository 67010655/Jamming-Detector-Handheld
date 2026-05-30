try:
    import smbus2
except ImportError:
    smbus2 = None
import time

class DS3231:
    def __init__(self, address=0x68, bus=1):
        self.address = address
        if smbus2 is not None:
            self.bus = smbus2.SMBus(bus)
        else:
            self.bus = None
            print("[RTC] smbus2 module is not available (expected on Windows). Simulated RTC enabled.")

    def bcd_to_int(self, bcd):
        return (bcd & 0x0F) + ((bcd >> 4) * 10)

    def int_to_bcd(self, val):
        return ((val // 10) << 4) | (val % 10)

    def get_datetime(self):
        """
        Returns a dictionary with current time from RTC
        """
        if self.bus is None:
            # Fallback to system time on Windows
            t = time.localtime()
            return {
                "year": t.tm_year,
                "month": t.tm_mon,
                "day": t.tm_mday,
                "hour": t.tm_hour,
                "minute": t.tm_min,
                "second": t.tm_sec
            }
        
        data = self.bus.read_i2c_block_data(self.address, 0, 7)
        
        seconds = self.bcd_to_int(data[0] & 0x7F)
        minutes = self.bcd_to_int(data[1])
        hours = self.bcd_to_int(data[2] & 0x3F) # 24h mode
        day = self.bcd_to_int(data[3])
        date = self.bcd_to_int(data[4])
        month = self.bcd_to_int(data[5] & 0x1F)
        year = self.bcd_to_int(data[6]) + 2000
        
        return {
            "year": year,
            "month": month,
            "day": date,
            "hour": hours,
            "minute": minutes,
            "second": seconds
        }

    def get_timestamp_str(self):
        dt = self.get_datetime()
        return f"{dt['year']}-{dt['month']:02d}-{dt['day']:02d} {dt['hour']:02d}:{dt['minute']:02d}:{dt['second']:02d}"

    def set_datetime(self, year, month, date, hour, minute, second):
        """
        Sets the RTC time. Year should be last 2 digits (e.g. 24 for 2024)
        """
        if self.bus is None:
            print("[RTC] set_datetime() skipped — no I2C bus available")
            return
        data = [
            self.int_to_bcd(second),
            self.int_to_bcd(minute),
            self.int_to_bcd(hour),
            self.int_to_bcd(1), # Day of week (unused)
            self.int_to_bcd(date),
            self.int_to_bcd(month),
            self.int_to_bcd(year % 100)
        ]
        self.bus.write_i2c_block_data(self.address, 0, data)
