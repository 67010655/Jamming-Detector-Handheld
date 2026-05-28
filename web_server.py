import os
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

API_TOKEN = os.environ.get('GUNJAM_API_TOKEN', '')

class ServerState:
    def __init__(self):
        self._lock = threading.Lock()
        self.metrics = {}
        self.power_spectrum = []
        self.uptime = 0
        self.bearing = 0
        self.gain = config.GAIN
        self.current_time = '00:00:00'

    def update(self, metrics, power, uptime, bearing=0, gain=7.7):
        if len(power) > 0:
            display_pts = min(240, len(power))
            step = max(1, len(power) // display_pts)
            usable = (len(power) // step) * step
            if usable > 0:
                power_resampled = power[:usable].reshape(-1, step).max(axis=1) if step > 1 else power[:usable]
                spectrum = [float(x) for x in power_resampled]
            else:
                spectrum = []
        else:
            spectrum = []
        with self._lock:
            self.metrics = metrics
            self.uptime = uptime
            self.bearing = bearing
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
                'gain': self.gain,
                'current_time': self.current_time,
            }

state = ServerState()


@app.before_request
def check_auth():
    if not API_TOKEN:
        return
    if not request.path.startswith('/api/'):
        return
    token = request.headers.get('X-API-Token', '')
    if token != API_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

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
        "gain": snap['gain'],
        "real_time": snap['current_time'],
        "real_date": time.strftime('%d %b %Y')
    })

@app.route('/api/history')
def history():
    limit = 50
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
            
        # Write CSV header
        yield "ID,Date,Time,Uptime,State,Score,Peak_Power,Floor_Rise,Noise_Floor,Bearing\n"
        
        for row in data:
            # Split timestamp into Date and Time for Excel friendliness
            parts = row['timestamp'].split(' ')
            date_str = parts[0]
            time_str = parts[1]
            uptime_str = format_uptime(row['uptime_sec'])
            
            yield f"{row['id']},{date_str},{time_str},{uptime_str},{row['state']},{row['score']},{row['peak_p']:.2f},{row['floor_rise']:.2f},{row['noise_floor']:.2f},{row.get('bearing_deg', 0)}\n"

    return Response(generate(), mimetype='text/csv', headers={"Content-disposition": "attachment; filename=jamming_history.csv"})

_last_clear_time = 0
_CLEAR_RATE_LIMIT_S = 60  # Minimum seconds between database clears

@app.route('/api/clear', methods=['POST'])
def clear_history():
    global _last_clear_time
    now = time.time()
    if now - _last_clear_time < _CLEAR_RATE_LIMIT_S:
        remaining = int(_CLEAR_RATE_LIMIT_S - (now - _last_clear_time))
        return jsonify({"success": False, "error": f"Rate limited. Try again in {remaining}s."}), 429
    success = database_manager.clear_db()
    if success:
        _last_clear_time = now
        print(f"[WEB] Database cleared by {request.remote_addr} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return jsonify({"success": success})

def start_server(port=8080):
    os.makedirs(web_dir, exist_ok=True)
    thread = threading.Thread(
        target=waitress_serve,
        args=(app,),
        kwargs={"host": "0.0.0.0", "port": port, "threads": 2, "_quiet": True},
        daemon=True
    )
    thread.start()
    print(f"[WEB] Dashboard Server running at http://0.0.0.0:{port}")

def update_state(metrics, power, uptime, bearing=0, gain=7.7):
    state.update(metrics, power, uptime, bearing=bearing, gain=gain)
