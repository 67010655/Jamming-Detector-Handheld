import threading
import time
import random

def parse_nmea_lat_lon(line):
    """
    Parses latitude and longitude from NMEA sentence ($GPRMC or $GPGGA)
    Returns: (latitude, longitude) as float or None
    """
    parts = line.split(',')
    if not parts:
        return None
    
    header = parts[0]
    # $GPRMC format
    if header in ['$GPRMC', '$GNGRM', '$GNRMC'] and len(parts) >= 7:
        status = parts[2]
        if status != 'A':  # Active/Valid status
            return None
        raw_lat = parts[3]
        lat_dir = parts[4]
        raw_lon = parts[5]
        lon_dir = parts[6]
        return convert_to_decimal(raw_lat, lat_dir, raw_lon, lon_dir)
        
    # $GPGGA format
    elif header in ['$GPGGA', '$GNGGA'] and len(parts) >= 6:
        raw_lat = parts[2]
        lat_dir = parts[3]
        raw_lon = parts[4]
        lon_dir = parts[5]
        if not raw_lat or not raw_lon:
            return None
        return convert_to_decimal(raw_lat, lat_dir, raw_lon, lon_dir)
    return None

def convert_to_decimal(raw_lat, lat_dir, raw_lon, lon_dir):
    try:
        # DDMM.MMMMM
        lat_deg = float(raw_lat[:2])
        lat_min = float(raw_lat[2:])
        lat = lat_deg + (lat_min / 60.0)
        if lat_dir == 'S':
            lat = -lat
            
        # DDDMM.MMMMM
        lon_deg = float(raw_lon[:3])
        lon_min = float(raw_lon[3:])
        lon = lon_deg + (lon_min / 60.0)
        if lon_dir == 'W':
            lon = -lon
            
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None


class GPSReceiver:
    def __init__(self, port="/dev/ttyS0", baudrate=9600, preview=False):
        self.port = port
        self.baudrate = baudrate
        self.preview = preview
        self.running = False
        # Default coordinates pointing to Telecom KMITL
        self.latitude = 13.7299
        self.longitude = 100.7782
        self.gps_lock = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _worker(self):
        if self.preview:
            # Simulate a slow random walk for the preview mode GPS
            while self.running:
                self.latitude += random.uniform(-0.00005, 0.00005)
                self.longitude += random.uniform(-0.00005, 0.00005)
                self.gps_lock = True
                time.sleep(1.0)
            return

        try:
            import serial
        except ImportError:
            print("[GPS] pySerial is not installed. Falling back to Mock GPS.")
            self._run_mock_loop()
            return

        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"[GPS] Connected to serial {self.port} at {self.baudrate} baud.")
        except Exception as e:
            print(f"[GPS] Serial port connection failed: {e}. Falling back to Mock GPS.")
            self._run_mock_loop()
            return

        while self.running:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('ascii', errors='ignore').strip()
                    coords = parse_nmea_lat_lon(line)
                    if coords:
                        self.latitude, self.longitude = coords
                        self.gps_lock = True
            except Exception as e:
                print(f"[GPS] Error reading serial data: {e}")
                time.sleep(0.5)
        
        try:
            ser.close()
        except:
            pass

    def _run_mock_loop(self):
        while self.running:
            self.latitude += random.uniform(-0.00003, 0.00003)
            self.longitude += random.uniform(-0.00003, 0.00003)
            self.gps_lock = True
            time.sleep(1.0)
