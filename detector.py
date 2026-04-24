import time
import numpy as np
from rtlsdr import RtlSdr

from dsp import compute_power, remove_dc_spike, smooth_noise
from display_ui import DisplayUI

class GPSJammerHandheld:
    def __init__(self):
        self.running = False
        self.w = 480
        self.h = 320

        self.sample_count = 8192
        self._window = np.hanning(self.sample_count).astype(np.float32)
        self.center_freq_hz = 1575.42e6
        self.sample_rate_hz = 1.024e6
        self.gain_db = 0.0

        self.target_fps = 10

        self.alpha_idle = 0.97
        self.alpha_alert = 0.998

        self.floor_rise_threshold_db = 3.2
        self.peak_threshold_db = 24.0

        self.warn_floor_rise_threshold_db = 2.0
        self.warn_peak_threshold_db = 18.0

        self.hit_frames_required = 3
        self.clear_frames_required = 6

        self.frame_count = 0
        self.start_time = time.time()

        self.noise_floor = None
        self.jam_hits = 0
        self.clear_hits = 0
        self.jammer_active = False
        self.current_state = "SCANNING"

        self.device = None
        self.sdr = None

        self._init_sdr()
        self._calibrate()
        self.ui = DisplayUI(self)
        
    def _init_sdr(self):
        print("[SYSTEM] Initializing RTL-SDR...")
        try:
            self.sdr = RtlSdr()
            self.sdr.sample_rate = self.sample_rate_hz
            self.sdr.center_freq = self.center_freq_hz
            self.sdr.gain = self.gain_db
            print(f"[SDR] Gain requested: {self.gain_db} dB")
            print(f"[SDR] Gain actual:    {self.sdr.gain} dB")
        except Exception as exc:
            raise RuntimeError(f"SDR init failed: {exc}") from exc
        
    def _calibrate(self):
        print("[SYSTEM] Calibrating...")
        warmup = []

        for _ in range(30):
            samples = self.sdr.read_samples(self.sample_count)
            power = compute_power(samples, self._window)
            power = remove_dc_spike(power)
            warmup.append(float(np.percentile(power, 20)))

        self.noise_floor = float(np.median(warmup))
        nf_min = min(warmup)
        nf_max = max(warmup)
        print(f"[READY] Base NF: {self.noise_floor:.2f} dB")
        print(f"[INFO]  NF range: {nf_min:.2f} ~ {nf_max:.2f} dB")

        # Warn if range too wide - likely jammer was active during calibration
        if (nf_max - nf_min) > 5.0:
            print("[WARN]  Wide NF range detected - possible jammer during calibration")
            print("[WARN]  Recommend restarting without jammer nearby")

    def _detect_jamming(self, power):
        avg_p = float(np.mean(power))
        peak_p = float(np.max(power))
        baseline_p = float(np.percentile(power, 55))
        current_floor = float(np.percentile(power, 20))
        floor_rise = current_floor - self.noise_floor
        peak_diff = peak_p - baseline_p

        warn_now = (floor_rise > self.warn_floor_rise_threshold_db) or (peak_diff > self.warn_peak_threshold_db)
        jam_now = (floor_rise > self.floor_rise_threshold_db) or (peak_diff > self.peak_threshold_db)

        if jam_now:
            self.jam_hits += 1
            self.clear_hits = 0
        else:
            self.jam_hits = 0
            self.clear_hits += 1

        if self.jam_hits >= self.hit_frames_required:
            self.jammer_active = True
        elif self.clear_hits >= self.clear_frames_required:
            self.jammer_active = False

        if self.jammer_active:
            state = "JAMMING"
        elif warn_now:
            state = "WATCH"
        else:
            state = "SCANNING"

        alpha = self.alpha_alert if self.jammer_active else self.alpha_idle
        self.noise_floor = smooth_noise(self.noise_floor, current_floor, alpha)
        self.current_state = state
        score = int(np.clip(max(floor_rise * 12.0, peak_diff * 6.0), 0, 99))

        return {
            "avg_p": avg_p,
            "peak_p": peak_p,
            "baseline_p": baseline_p,
            "floor_rise": floor_rise,
            "peak_diff": peak_diff,
            "state": state,
            "jammer": self.jammer_active,
            "score": score,
        }
    
    def run(self):
        print("[ACTIVE] Monitoring GPS L1...")
        self.running = True
        frame_period = 1.0 / self.target_fps

        while self.running:
            frame_start = time.time()
            try:
                samples = self.sdr.read_samples(self.sample_count)
                power = compute_power(samples, self._window)
                power = remove_dc_spike(power)

                metrics = self._detect_jamming(power)
                import select, sys
                if select.select([sys.stdin], [], [], 0)[0]:
                    try:
                        angle = int(input())
                        self.ui.record_bearing(angle, metrics["peak_p"])
                    except Exception:
                        pass
                self._debug_print(power)
                self.ui.draw_ui(metrics, power)
                self.frame_count += 1

                elapsed = time.time() - frame_start
                if elapsed < frame_period:
                    time.sleep(frame_period - elapsed)
            except KeyboardInterrupt:
                self.running = False
            except Exception as exc:
                print(f"[ERROR] Runtime loop: {exc}")
                time.sleep(0.2)

    def _debug_print(self, current_power):
        peak = float(np.max(current_power))
        threshold = self._get_threshold()
        margin = peak - threshold
        print(
            f"NF: {self.noise_floor:6.2f} | "
            f"Peak: {peak:6.2f} | "
            f"Threshold: {threshold:6.2f} | "
            f"Margin: {margin:+5.2f} | "
            f"State: {self.current_state}"
        )

    def _get_threshold(self):
        if self.jammer_active:
            return self.noise_floor + self.peak_threshold_db
        else:
            return self.noise_floor + self.warn_peak_threshold_db
    
    def shutdown(self):
        print("\n[SYSTEM] Stopping...")
        uptime = max(0.001, time.time() - self.start_time)
        print(f"[STATS] Uptime: {uptime:.1f}s  Frames: {self.frame_count}  Rate: {self.frame_count / uptime:.1f} FPS")

        if self.device is not None:
            try:
                self._draw.rectangle((0, 0, self.w, self.h), fill=(0, 0, 0))
                self.device.display(self._img)
            except Exception:
                pass

        if self.sdr is not None:
            try:
                self.sdr.close()
            except Exception:
                pass

    def _update_noise_floor(self, current_power):
        current_floor = float(np.percentile(current_power, 20))
        if self.jammer_active:
            alpha = self.alpha_alert 
        else:
            alpha = self.alpha_idle
        self.noise_floor = alpha * self.noise_floor + (1 - alpha) * current_floor

    def _get_threshold(self):
        if self.jammer_active:
            return self.noise_floor + self.peak_threshold_db
        else:
            return self.noise_floor + self.warn_peak_threshold_db
        
    def _debug_print(self, current_power):    
        peak = float(np.max(current_power))
        threshold = self._get_threshold()
        margin = peak - threshold  
        print(
            f"NF: {self.noise_floor:6.2f} | "
            f"Peak: {peak:6.2f} | "
            f"Threshold: {threshold:6.2f} | "
            f"Margin: {margin:+5.2f} | "
            f"State: {self.current_state}"
        )