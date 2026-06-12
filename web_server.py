import os
import socket
import threading
import logging
import numpy as np
from flask import Flask, jsonify, send_from_directory, Response, request
from waitress import serve as waitress_serve
import config
import database_manager
import io
import csv
import time

# Disable Flask default logging to avoid cluttering the terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Get absolute path for static folder to ensure it works regardless of cwd
current_dir = os.path.dirname(os.path.abspath(__file__))
web_dir = os.path.join(current_dir, 'web')

app = Flask(__name__, static_folder=web_dir)

# Field deployment runs on a trusted Pi hotspot/LAN. Access control is handled
# at the network/operator level, so API token auth is intentionally omitted.
class ServerState:
    def __init__(self):
        self._lock = threading.Lock()
        self.metrics = {}
        self.power_spectrum = []
        self.uptime = 0
        self.bearing = 0
        self.latitude = None
        self.longitude = None
        self.gain = config.GAIN
        self.current_time = '00:00:00'

    def update(self, metrics, power, uptime, bearing=0, gain=7.7, latitude=None, longitude=None):
        try:
            power_array = np.asarray(power, dtype=np.float64).ravel()
            power_array = power_array[np.isfinite(power_array)]
        except (TypeError, ValueError):
            power_array = np.array([], dtype=np.float64)

        if len(power_array) > 0:
            display_pts = min(240, len(power_array))
            step = max(1, len(power_array) // display_pts)
            usable = (len(power_array) // step) * step
            if usable > 0:
                power_resampled = power_array[:usable].reshape(-1, step).max(axis=1) if step > 1 else power_array[:usable]
                spectrum = [float(x) for x in power_resampled]
            else:
                spectrum = []
        else:
            spectrum = []
        with self._lock:
            self.metrics = metrics
            self.uptime = uptime
            self.bearing = bearing
            self.latitude = latitude
            self.longitude = longitude
            self.gain = gain
            self.current_time = time.strftime('%H:%M:%S')
            self.power_spectrum = spectrum

    def snapshot(self):
        with self._lock:
            return {
                'metrics': self.metrics,
                'spectrum': self.power_spectrum,
                'uptime': self.uptime,
                'bearing': self.bearing,
                'latitude': self.latitude,
                'longitude': self.longitude,
                'gain': self.gain,
                'current_time': self.current_time,
            }

state = ServerState()
app_instance = None


@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/status')
def status():
    snap = state.snapshot()
    return jsonify({
        "metrics": snap['metrics'],
        "spectrum": snap['spectrum'],
        "uptime": snap['uptime'],
        "bearing": snap['bearing'],
        "latitude": snap['latitude'],
        "longitude": snap['longitude'],
        "gain": snap['gain'],
        "real_time": snap['current_time'],
        "real_date": time.strftime('%d %b %Y')
    })

@app.route('/api/history')
def history():
    try:
        limit = int(request.args.get('limit', 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 500))
    data = database_manager.get_history(limit)
    return jsonify(data)

@app.route('/api/export')
def export_csv():
    data = database_manager.get_filtered_history(limit=5000) # Apply 1s/15s Heartbeat filter
    
    def format_uptime(seconds):
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def generate():
        if not data:
            yield "No data available"
            return

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["ID", "Date", "Time", "Uptime", "State", "Score", "Peak_Power", "Floor_Rise", "Noise_Floor", "Bearing", "Latitude", "Longitude"])
        yield buffer.getvalue()

        for row in data:
            buffer.seek(0)
            buffer.truncate(0)

            timestamp = str(row.get('timestamp', ''))
            if ' ' in timestamp:
                date_str, time_str = timestamp.split(' ', 1)
            elif 'T' in timestamp:
                date_str, time_str = timestamp.split('T', 1)
            else:
                date_str, time_str = timestamp, ''

            uptime_str = format_uptime(int(row.get('uptime_sec') or 0))
            peak_p = row.get('peak_p')
            floor_rise = row.get('floor_rise')
            noise_floor = row.get('noise_floor')
            lat = row.get('latitude')
            lon = row.get('longitude')

            writer.writerow([
                row.get('id', ''),
                date_str,
                time_str,
                uptime_str,
                row.get('state', ''),
                row.get('score', ''),
                f"{peak_p:.2f}" if isinstance(peak_p, (int, float)) else '',
                f"{floor_rise:.2f}" if isinstance(floor_rise, (int, float)) else '',
                f"{noise_floor:.2f}" if isinstance(noise_floor, (int, float)) else '',
                row.get('bearing_deg', 0),
                f"{lat:.6f}" if isinstance(lat, (int, float)) else '',
                f"{lon:.6f}" if isinstance(lon, (int, float)) else '',
            ])
            yield buffer.getvalue()

    return Response(generate(), mimetype='text/csv', headers={"Content-disposition": "attachment; filename=jamming_history.csv"})

_last_clear_time = 0
_CLEAR_RATE_LIMIT_S = 60  # Minimum seconds between database clears
_clear_lock = threading.Lock()

@app.route('/api/clear', methods=['POST'])
def clear_history():
    global _last_clear_time
    now = time.time()
    with _clear_lock:
        if now - _last_clear_time < _CLEAR_RATE_LIMIT_S:
            remaining = int(_CLEAR_RATE_LIMIT_S - (now - _last_clear_time))
            return jsonify({"success": False, "error": f"Rate limited. Try again in {remaining}s."}), 429
        success = database_manager.clear_db()
        if success:
            _last_clear_time = now
            print(f"[WEB] Database cleared by {request.remote_addr} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return jsonify({"success": success})

@app.route('/api/recalibrate', methods=['POST'])
def web_recalibrate():
    global app_instance
    if app_instance is not None:
        app_instance.calibration_source = "remote"
        app_instance.request_calibration.set()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "App instance not initialized"}), 500

@app.route('/api/gain', methods=['POST'])
def web_adjust_gain():
    global app_instance
    if app_instance is not None:
        try:
            data = request.get_json() or {}
            delta = float(data.get('delta', 2.0))
            app_instance.adjust_gain(delta, source="remote")
            return jsonify({"success": True, "gain": app_instance.gain_db})
        except (TypeError, ValueError) as e:
            return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": False, "error": "App instance not initialized"}), 500

@app.route('/api/reboot', methods=['POST'])
def web_reboot():
    global app_instance
    if app_instance is not None:
        print(f"[WEB] Remote reboot requested from {request.remote_addr}")
        threading.Thread(target=app_instance.safe_reboot, daemon=True).start()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "App instance not initialized"}), 500

@app.route('/api/shutdown', methods=['POST'])
def web_shutdown():
    global app_instance
    if app_instance is not None:
        print(f"[WEB] Remote shutdown requested from {request.remote_addr}")
        app_instance.shutdown_requested.set()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "App instance not initialized"}), 500


def start_server(port=8080, detector_app=None):
    global app_instance
    app_instance = detector_app
    os.makedirs(web_dir, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError as exc:
            raise RuntimeError(f"Dashboard port {port} is not available: {exc}") from exc

    thread = threading.Thread(
        target=waitress_serve,
        args=(app,),
        kwargs={"host": "0.0.0.0", "port": port, "threads": 2, "_quiet": True},
        daemon=True
    )
    thread.start()
    deadline = time.time() + 3.0
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
            check.settimeout(0.2)
            if check.connect_ex(("127.0.0.1", port)) == 0:
                print(f"[WEB] Dashboard Server running at http://0.0.0.0:{port}")
                return
        time.sleep(0.05)

    raise RuntimeError(f"Dashboard server did not become ready on port {port}")

def update_state(metrics, power, uptime, bearing=0, gain=7.7, latitude=None, longitude=None):
    state.update(metrics, power, uptime, bearing=bearing, gain=gain, latitude=latitude, longitude=longitude)
