import sys
import time
import numpy as np

import config
from dsp import compute_power, remove_dc_spike, smooth_noise
from display_ui import DisplayUI
from led_control import LEDController
from buzzer import BuzzerController
import web_server
import database_manager

class GPSJammerHandheld:
    def __init__(self, preview=False):
        self.preview = preview
        self.running = False
        self.w = 480
        self.h = 320

        self.sample_count = 8192
        self._window = np.hanning(self.sample_count).astype(np.float32)
        self.center_freq_hz = 1575.42e6
        self.sample_rate_hz = config.SAMPLE_RATE
        self.gain_db = config.GAIN

        self.target_fps = 10

        self.alpha_idle = 0.97
        self.alpha_alert = 0.998

        self.floor_rise_threshold_db = config.FLOOR_RISE_THRESHOLD
        self.peak_threshold_db = config.PEAK_THRESHOLD

        self.warn_floor_rise_threshold_db = config.WARN_FLOOR
        self.warn_peak_threshold_db = config.WARN_PEAK

        self.hit_frames_required = getattr(config, 'HIT_FRAMES', 3)
        self.clear_frames_required = getattr(config, 'CLEAR_FRAMES', 6)

        self.frame_count = 0
        self.start_time = time.time()

        self.noise_floor = None
        self.jam_hits = 0
        self.clear_hits = 0
        self.jammer_active = False
        self.current_state = "SCANNING"
        self.request_calibration = False

        self.device = None
        self.sdr = None

        # Initialize UI first to show splash screens
        self.ui = DisplayUI(self, preview=self.preview)
        self.ui.draw_splash("SYSTEM BOOTING...")
        time.sleep(1.5) # Give user time to read
        
        if not self.preview:
            self.ui.draw_splash("INITIALIZING DB...")
            database_manager.init_db()
            time.sleep(0.5)
            
            self.ui.draw_splash("INIT SDR...")
            self._init_sdr()
            time.sleep(0.5)
            
            self.ui.draw_splash("CALIBRATING...")
            self._calibrate()
            
            self.ui.draw_splash("STARTING MODULES...")
            self.led = LEDController(enabled=True)
            self.buzzer = BuzzerController(enabled=True)
            time.sleep(1.0)
        else:
            self.noise_floor = -90.0
            self.led = LEDController(enabled=False)
            self.buzzer = BuzzerController(enabled=False)
            print("[INFO] Preview mode: synthetic spectrum is enabled.")

        # Start background web dashboard
        self.last_log_time = 0
        self.log_interval = 1.0 # Seconds between logs for the same persistent event
        
        web_server.start_server(port=8080)
        
        self.buzzer.play_startup()
        
    def _init_sdr(self):
        print("[SYSTEM] Initializing RTL-SDR...")
        try:
            from rtlsdr import RtlSdr
        except ImportError as exc:
            raise RuntimeError("RTL-SDR library is not installed. Install pyrtlsdr to run on hardware.") from exc

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
        
        # Log startup baseline to database
        database_manager.log_event("STARTUP", 0, self.noise_floor, 0.0, self.noise_floor, 0)

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

        # Update noise floor carefully based on state to prevent jammer from dragging the baseline
        if not getattr(config, 'STATIC_MODE', False):
            if state == "SCANNING":
                self.noise_floor = smooth_noise(self.noise_floor, current_floor, self.alpha_idle)
            elif state == "WATCH":
                self.noise_floor = smooth_noise(self.noise_floor, current_floor, self.alpha_alert)
            # In JAMMING state, we do not update noise_floor at all to preserve the baseline
        
        self.current_state = state
        self.led.set_state(state)
        self.buzzer.set_state(state)
        # Calculate score based on normalized distance from thresholds
        # A score of 50 roughly indicates reaching the jamming threshold
        score_f = (floor_rise / self.floor_rise_threshold_db) * 50.0
        score_p = (peak_diff / self.peak_threshold_db) * 50.0
        score = int(np.clip(max(score_f, score_p), 0, 99))

        if self.jammer_active:
            threshold = self.noise_floor + self.peak_threshold_db
        else:
            threshold = self.noise_floor + self.warn_peak_threshold_db
        margin = peak_p - threshold

        return {
            "avg_p": avg_p,
            "peak_p": peak_p,
            "baseline_p": baseline_p,
            "floor_rise": floor_rise,
            "peak_diff": peak_diff,
            "state": state,
            "jammer": self.jammer_active,
            "score": score,
            "noise_floor": self.noise_floor,
            "threshold": threshold,
            "margin": margin
        }
    
    def run(self):
        print("[ACTIVE] Monitoring GPS L1...")
        self.running = True
        frame_period = 1.0 / self.target_fps

        while self.running:
            frame_start = time.time()
            try:
                if self.preview:
                    samples = self._generate_preview_samples()
                else:
                    samples = self.sdr.read_samples(self.sample_count)

                power = compute_power(samples, self._window)
                power = remove_dc_spike(power)

                metrics = self._detect_jamming(power)
                if not self.preview:
                    try:
                        import sys
                        if sys.platform == "win32":
                            import msvcrt
                            if msvcrt.kbhit():
                                try:
                                    line = sys.stdin.readline().strip().lower()
                                    if line == 'v':
                                        self.ui.toggle_view_mode()
                                    elif line == 'm':
                                        self.toggle_mute()
                                    elif line == 'c':
                                        self.recalibrate()
                                    elif line == 's':
                                        self.manual_capture()
                                    elif line == 'g':
                                        self.adjust_gain(2.0)
                                    elif line == 'h':
                                        self.adjust_gain(-2.0)
                                    else:
                                        angle = int(line)
                                        self.ui.record_bearing(angle, metrics["peak_p"])
                                except Exception:
                                    pass
                        else:
                            import select
                            if select.select([sys.stdin], [], [], 0)[0]:
                                try:
                                    line = input().strip().lower()
                                    if line == 'v':
                                        self.ui.toggle_view_mode()
                                    elif line == 'm':
                                        self.toggle_mute()
                                    elif line == 'c':
                                        self.recalibrate()
                                    elif line == 's':
                                        self.manual_capture()
                                    elif line == 'g':
                                        self.adjust_gain(2.0)
                                    elif line == 'h':
                                        self.adjust_gain(-2.0)
                                    else:
                                        angle = int(line)
                                        self.ui.record_bearing(angle, metrics["peak_p"])
                                except Exception:
                                    pass
                    except Exception:
                        pass
                if getattr(self, 'request_calibration', False):
                    # Force a draw first so the "CALIBRATING..." toast is visible
                    self.ui.draw_ui(metrics, power)
                    self._calibrate()
                    self.request_calibration = False
                    self.ui.show_toast("CALIBRATION DONE!", 1.5)

                if self.frame_count % 10 == 0:
                    self._debug_print(power)
                self.ui.draw_ui(metrics, power)
                self.frame_count += 1

                # Update web server state
                uptime = int(time.time() - self.start_time)
                web_server.update_state(metrics, power, uptime)

                # Log to database every second for a live web feed
                current_time = time.time()
                if current_time - self.last_log_time > 1.0:
                    database_manager.log_event(
                        metrics["state"],
                        metrics["score"],
                        metrics["peak_p"],
                        metrics["floor_rise"],
                        metrics["noise_floor"],
                        uptime
                    )
                    self.last_log_time = current_time

                elapsed = time.time() - frame_start
                if elapsed < frame_period:
                    time.sleep(frame_period - elapsed)
            except KeyboardInterrupt:
                self.running = False
            except Exception as exc:
                import traceback
                print(f"[ERROR] Runtime loop: {exc}")
                traceback.print_exc()
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
    
    def toggle_mute(self):
        """Toggle buzzer mute state."""
        return self.buzzer.toggle_mute()

    def recalibrate(self):
        """Manually trigger noise floor recalibration."""
        print("[UI] Recalibrating Noise Floor...")
        self._calibrate()

    def adjust_gain(self, delta):
        """Adjust SDR gain by delta dB."""
        self.gain_db = float(np.clip(self.gain_db + delta, 0, 50))
        if self.sdr:
            try:
                self.sdr.gain = self.gain_db
                print(f"[UI] Gain adjusted to: {self.sdr.gain:.1f} dB")
            except Exception as e:
                print(f"[ERROR] Failed to set gain: {e}")

    def manual_capture(self):
        """Log a manual snapshot event to database."""
        print("[UI] Manual Snapshot Captured!")
        uptime = int(time.time() - self.start_time)
        database_manager.log_event(
            "MANUAL_SNAP",
            99, # High priority indicator
            -50.0, # Dummy peak or use real metrics
            0.0,
            self.noise_floor,
            uptime
        )
        # We could also trigger a screen save here if implemented
        
    def safe_power_off(self):
        """Safely shut down the Raspberry Pi."""
        print("[SYSTEM] Initiating safe shutdown...")
        self.ui.draw_splash("SHUTTING DOWN...")
        time.sleep(2)  # Let user see the message
        self.shutdown() # Cleanup hardware
        import os
        if sys.platform != "win32" and not self.preview:
            os.system("sudo poweroff")
            # Block forever — prevent process from exiting so systemd
            # won't restart us. OS shutdown will kill us naturally.
            while True:
                time.sleep(1)
        else:
            print("[INFO] Shutdown command skipped in preview/Windows mode.")
            self.running = False
    
    def shutdown(self):
        print("\n[SYSTEM] Stopping...")
        uptime = max(0.001, time.time() - self.start_time)
        print(f"[STATS] Uptime: {uptime:.1f}s  Frames: {self.frame_count}  Rate: {self.frame_count / uptime:.1f} FPS")

        if self.led is not None:
            self.led.cleanup()

        if getattr(self, 'buzzer', None) is not None:
            self.buzzer.cleanup()

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



# อันนี้เพิ่มมาไว้ทดสอบโหมดพรีวิวโดยไม่ต้องใช้ฮาร์ดแวร์จริง
    def _generate_preview_samples(self):
        noise = np.random.normal(loc=0.0, scale=0.25, size=self.sample_count).astype(np.complex64)
        phase = 2.0 * np.pi * 10.0 * np.arange(self.sample_count) / self.sample_count
        tone = np.exp(1j * phase).astype(np.complex64)
        if np.random.rand() > 0.7:
            return 0.2 * tone + noise
        return noise