import os
import threading
import logging
import numpy as np
from flask import Flask, jsonify, send_from_directory

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
