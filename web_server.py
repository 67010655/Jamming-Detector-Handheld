import os
import threading
import logging
import numpy as np
from flask import Flask, jsonify, send_from_directory, Response
import database_manager
import io
import csv

# Disable Flask default logging to avoid cluttering the terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Get absolute path for static folder to ensure it works regardless of cwd
current_dir = os.path.dirname(os.path.abspath(__file__))
web_dir = os.path.join(current_dir, 'web')

app = Flask(__name__, static_folder=web_dir)

class ServerState:
    metrics = {}
    power_spectrum = []
    uptime = 0

state = ServerState()

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/status')
def status():
    return jsonify({
        "metrics": state.metrics,
        "spectrum": state.power_spectrum,
        "uptime": state.uptime
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
        yield "ID,Date,Time,Uptime,State,Score,Peak_Power,Floor_Rise,Noise_Floor\n"
        
        for row in data:
            # Split timestamp into Date and Time for Excel friendliness
            parts = row['timestamp'].split(' ')
            date_str = parts[0]
            time_str = parts[1]
            uptime_str = format_uptime(row['uptime_sec'])
            
            yield f"{row['id']},{date_str},{time_str},{uptime_str},{row['state']},{row['score']},{row['peak_p']:.2f},{row['floor_rise']:.2f},{row['noise_floor']:.2f}\n"

    return Response(generate(), mimetype='text/csv', headers={"Content-disposition": "attachment; filename=jamming_history.csv"})

@app.route('/api/clear', methods=['POST'])
def clear_history():
    success = database_manager.clear_db()
    return jsonify({"success": success})

def start_server(port=8080):
    os.makedirs(web_dir, exist_ok=True)
    thread = threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": port, "debug": False, "use_reloader": False}, daemon=True)
    thread.start()
    print(f"[WEB] Dashboard Server running at http://0.0.0.0:{port}")

def update_state(metrics, power, uptime):
    state.metrics = metrics
    state.uptime = uptime
    
    # Downsample the spectrum slightly to ensure the JSON payload remains small and fast.
    # 240 points is plenty for a smooth, responsive web graph.
    if len(power) > 0:
        display_pts = min(240, len(power))
        step = max(1, len(power) // display_pts)
        usable = (len(power) // step) * step
        if usable > 0:
            if step > 1:
                power_resampled = power[:usable].reshape(-1, step).max(axis=1)
            else:
                power_resampled = power[:usable]
            
            # Convert float32 numpy array to standard python floats for JSON
            state.power_spectrum = [float(x) for x in power_resampled]
