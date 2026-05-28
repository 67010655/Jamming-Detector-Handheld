import os
import sys
import time
import numpy as np
from PIL import Image

# Ensure the workspace is in the python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from detector import GPSJammerHandheld
from dsp import compute_power, remove_dc_spike

def generate_screenshots():
    print("[PREVIEW] Initializing GPSJammerHandheld in preview mode...")
    app = GPSJammerHandheld(preview=True)
    
    # Generate some fake data samples
    print("[PREVIEW] Generating samples and metrics...")
    samples = app._generate_preview_samples()
    power = compute_power(samples, app._window)
    power = remove_dc_spike(power)
    
    # Force state to JAMMING for dramatic preview rendering
    metrics = app._detect_jamming(power)
    app.jammer_active = True
    app.current_state = "JAMMING"
    metrics["state"] = "JAMMING"
    metrics["score"] = 92
    metrics["peak_p"] = -35.2
    metrics["floor_rise"] = 28.5
    metrics["margin"] = 18.2
    
    # Reset baseline guard and clear warning popups for the clean UI renders
    app.baseline_guard_active = False
    app.ui._toast_msg = None
    app.ui._toast_until = 0
    
    # Add a mock bearing log to show lines of different colors/lengths
    # SCANNING (Green, 0.33 height), WATCH (Yellow, 0.66 height), JAMMING (Red, full height)
    app.ui._bearing_log = [
        (45, 0.3, "SCANNING"),
        (135, 0.6, "WATCH"),
        (225, 0.9, "JAMMING"),
        (315, 0.5, "SCANNING")
    ]
    
    # Pinned last jam bearing
    app.ui._persistent_jam = (225, 0.9, "JAMMING")
    
    # Ensure preview_example folder exists
    out_dir = os.path.join(current_dir, "preview_example")
    os.makedirs(out_dir, exist_ok=True)
    
    # ----------------------------------------------------
    # Render Mode 0: NORMAL MODE
    # ----------------------------------------------------
    print("[PREVIEW] Rendering Mode 0: NORMAL...")
    app.ui.view_mode = 0
    app.ui.draw_ui(metrics, power)
    # Save output to preview_example
    Image.open("preview.png").save(os.path.join(out_dir, "mode_normal_clean.png"))
    
    # ----------------------------------------------------
    # Render Mode 1: SEARCH MODE (Radar/Compass - Clean for Presentation)
    # ----------------------------------------------------
    print("[PREVIEW] Rendering Mode 1: SEARCH...")
    app.ui.view_mode = 1
    # Mock some heading rotation
    app.current_bearing = 24.0
    app.baseline_guard_active = False  # Clean compass without popups for presentation
    app.ui.draw_ui(metrics, power)
    Image.open("preview.png").save(os.path.join(out_dir, "mode_search_clean.png"))
    
    # ----------------------------------------------------
    # Render Mode 1: SEARCH MODE (With Active Baseline Guard Alert)
    # ----------------------------------------------------
    print("[PREVIEW] Rendering Mode 1: SEARCH (GUARD ACTIVE)...")
    app.ui.view_mode = 1
    app.current_bearing = 24.0
    app.baseline_guard_active = True  # Mock active baseline guard to showcase the warning popup
    app.ui.show_toast("GUARD ACTIVE: BASELINE LOCKED", 9999.0)  # Explicitly trigger the warning toast
    app.ui.draw_ui(metrics, power)
    Image.open("preview.png").save(os.path.join(out_dir, "mode_search_guard.png"))
    
    # ----------------------------------------------------
    # Render Mode 2: ANALYTICS MODE
    # ----------------------------------------------------
    print("[PREVIEW] Rendering Mode 2: ANALYTICS...")
    app.ui.view_mode = 2
    app.baseline_guard_active = False
    app.ui._toast_msg = None
    app.ui._toast_until = 0
    app.ui._history_log = [float(x) for x in np.sin(np.linspace(0, 3 * np.pi, 50)) * 15 + 10]
    app.ui.draw_ui(metrics, power)
    Image.open("preview.png").save(os.path.join(out_dir, "mode_analytics_clean.png"))
    
    # ----------------------------------------------------
    # Render Splash: BOOTING
    # ----------------------------------------------------
    print("[PREVIEW] Rendering Splash: BOOTING...")
    app.ui.draw_splash("SYSTEM BOOTING...", progress=60)
    Image.open("preview.png").save(os.path.join(out_dir, "splash_boot.png"))
    
    # ----------------------------------------------------
    # Render Splash: SHUTDOWN
    # ----------------------------------------------------
    print("[PREVIEW] Rendering Splash: SHUTDOWN...")
    app.ui.draw_splash("SHUTTING DOWN...", progress=100)
    Image.open("preview.png").save(os.path.join(out_dir, "splash_shutdown.png"))
    
    # ----------------------------------------------------
    # Render Splash: REBOOT
    # ----------------------------------------------------
    print("[PREVIEW] Rendering Splash: REBOOT...")
    app.ui.draw_splash("RESTARTING SYSTEM...", progress=100)
    Image.open("preview.png").save(os.path.join(out_dir, "splash_reboot.png"))
    
    print("[PREVIEW] All screenshots generated successfully inside preview_example/ folder!")

if __name__ == "__main__":
    generate_screenshots()
