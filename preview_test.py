from detector import GPSJammerHandheld
from dsp import compute_power, remove_dc_spike

app = GPSJammerHandheld(preview=True)
samples = app._generate_preview_samples()
power = compute_power(samples, app._window)
power = remove_dc_spike(power)
metrics = app._detect_jamming(power)
app.ui.draw_ui(metrics, power)
print('preview done')