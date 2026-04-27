import numpy as np

def smooth_noise(prev_nf, avg_p, alpha):
    """Exponential moving average for the noise floor."""
    return (alpha * prev_nf) + ((1.0 - alpha) * avg_p)

def scale_points(power, nf, width, graph_top, graph_bottom):
    """
    Downsample spectrum to screen width and convert to drawable points.
    """
    if len(power) == 0:
        return []

    display_pts = min(width, len(power))
    step = max(1, len(power) // display_pts)
    usable = (len(power) // step) * step

    if usable == 0:
        return []

    power_resampled = power[:usable].reshape(-1, step).mean(axis=1)

    if len(power_resampled) > display_pts:
        power_resampled = power_resampled[:display_pts]

    y_vals = graph_bottom - (power_resampled - (nf - 25.0)) * 4.5
    y_vals = np.clip(
        y_vals,
        graph_top + 2,
        graph_bottom - 2
    ).astype(np.int32)

    if len(power_resampled) == 1:
        return [(0, int(y_vals[0]))]

    x_vals = np.linspace(
        0,
        width - 1,
        num=len(power_resampled),
        dtype=np.int32
    )

    return [(int(x), int(y)) for x, y in zip(x_vals, y_vals)]


def compute_power(samples, window):
    """
    Apply window + FFT + convert to dB power.
    """
    windowed = samples * window
    window_sum = np.sum(window)
    fft_raw = np.fft.fftshift(np.fft.fft(windowed))

    fft_norm = fft_raw / window_sum 
    return 20.0 * np.log10(np.abs(fft_norm) + 1e-12)


def remove_dc_spike(power, dc_bins=10):
    """
    Remove center DC spike from RTL-SDR spectrum.
    """
    cleaned = power.copy()

    mid = len(cleaned) // 2
    left = max(0, mid - dc_bins)
    right = min(len(cleaned), mid + dc_bins)

    neighbor_left = cleaned[max(0, left - 50):left]
    neighbor_right = cleaned[right:min(len(cleaned), right + 50)]

    neighbors = np.concatenate((neighbor_left, neighbor_right))

    if len(neighbors):
        replacement = float(np.mean(neighbors))
    else:
        replacement = float(np.mean(cleaned))

    cleaned[left:right] = replacement

    return cleaned