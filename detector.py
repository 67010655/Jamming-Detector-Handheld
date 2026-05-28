import sys
import os
import subprocess
import time
import numpy as np

import config
from dsp import compute_power, remove_dc_spike, smooth_noise
from display_ui import DisplayUI
from led_control import LEDController
from buzzer import BuzzerController
import web_server
import database_manager
from hardware.mpu6050 import MPU6050

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
        self.fixed_nf = False  # If True, noise floor doesn't update dynamically
        self.calibrated_base_nf = config.DEFAULT_NOISE_FLOOR_DB  # Chamber baseline default
        self.baseline_guard_active = False  # Auto-locking baseline guard
        self.jam_hits = 0
        self.clear_hits = 0
        self.jammer_active = False
        self.current_state = "SCANNING"
        self.request_calibration = False
        self.shutdown_requested = False
        self.reboot_requested = False

        self.device = None
        self.sdr = None
        self.imu = None
        self.current_bearing = 0.0

        # Initialize UI first to show splash screens with dynamic progress
        self.ui = DisplayUI(self, preview=self.preview)
        self.ui.draw_splash("SYSTEM BOOTING...", progress=10)
        time.sleep(1.0) # Give user time to read
        
        if not self.preview:
            self.ui.draw_splash("INITIALIZING DATABASE...", progress=30)
            database_manager.init_db()
            time.sleep(0.3)
            
            self.ui.draw_splash("INITIALIZING SDR RECEIVER...", progress=50)
            self._init_sdr()
            time.sleep(0.3)
            
            self.ui.draw_splash("CALIBRATING RADIO BASICS...", progress=70)
            self._calibrate()
            
            self.ui.draw_splash("CALIBRATING IMU SENSORS...", progress=90)
            try:
                self.imu = MPU6050(address=getattr(config, 'IMU_ADDRESS', 0x69))
                self.imu.calibrate(samples=150)
            except Exception as e:
                print(f"[IMU] Failed to initialize MPU6050: {e}")
                self.imu = None

            self.ui.draw_splash("STARTING SYSTEM MODULES...", progress=100)
            self.led = LEDController(enabled=True)
            self.buzzer = BuzzerController(enabled=True)
            time.sleep(0.8)
        else:
            self.noise_floor = config.DEFAULT_NOISE_FLOOR_DB
            self.calibrated_base_nf = config.DEFAULT_NOISE_FLOOR_DB
            self.baseline_guard_active = False
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
        self.calibrated_base_nf = self.noise_floor
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
        if self.fixed_nf:
            self.noise_floor = config.DEFAULT_NOISE_FLOOR_DB
            
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

        # Smart self-learning guard: if the current floor is extremely high compared to the calibrated base,
        # we freeze dynamic update to prevent the jammer from dragging up the baseline and blinding us.
        if not self.fixed_nf:
            guard_threshold = self.calibrated_base_nf + 8.0
            if current_floor > guard_threshold:
                if not getattr(self, 'baseline_guard_active', False):
                    self.baseline_guard_active = True
            else:
                if getattr(self, 'baseline_guard_active', False) and current_floor < (self.calibrated_base_nf + 5.0):
                    self.baseline_guard_active = False

        # Apply state override when baseline guard is active to trigger alarms immediately
        if getattr(self, 'baseline_guard_active', False):
            self.jammer_active = True
            state = "JAMMING"

        # Update noise floor carefully based on state to prevent jammer from dragging the baseline
        if not self.fixed_nf:
            if not getattr(self, 'baseline_guard_active', False):
                if state == "SCANNING":
                    self.noise_floor = smooth_noise(self.noise_floor, current_floor, self.alpha_idle)
                elif state == "WATCH":
                    self.noise_floor = smooth_noise(self.noise_floor, current_floor, self.alpha_alert)
            # In JAMMING or locked guard state, we do not update noise_floor at all to preserve the baseline
        else:
            # Fixed mode: optimal chamber baseline forced
            self.noise_floor = config.DEFAULT_NOISE_FLOOR_DB
        
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
                if self.imu:
                    self.current_bearing = self.imu.update_bearing()
                elif self.preview:
                    # Simulate slow compass rotation for preview testing
                    self.current_bearing = (self.current_bearing + 0.5) % 360

                if self.preview:
                    samples = self._generate_preview_samples()
                else:
                    samples = self.sdr.read_samples(self.sample_count)

                power = compute_power(samples, self._window)
                power = remove_dc_spike(power)

                metrics = self._detect_jamming(power)
                if not self.preview:
                    try:
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
                                        self.ui.record_bearing(angle, metrics["peak_p"], self.current_state)
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
                                        self.ui.record_bearing(angle, metrics["peak_p"], self.current_state)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                if self.request_calibration:
                    # Force a draw first so the "CALIBRATING..." toast is visible
                    self.ui.draw_ui(metrics, power)
                    self._calibrate()
                    self.request_calibration = False
                    self.ui.show_toast("CALIBRATION DONE!", 1.5)

                if self.shutdown_requested:
                    self.safe_power_off()
                    break

                if self.reboot_requested:
                    self.safe_reboot()
                    break

                if self.frame_count % 10 == 0:
                    self._debug_print(power)
                
                prev_state = getattr(self, '_prev_run_state', 'SCANNING')
                run_state = metrics["state"]

                if run_state == "JAMMING" and prev_state != "JAMMING":
                    self.ui.clear_persistent_jam()

                # Continuously log bearing vs sig strength (all states; peak tracked in JAMMING)
                self.ui.record_bearing(self.current_bearing, metrics["peak_p"], run_state)

                if prev_state == "JAMMING" and run_state != "JAMMING":
                    self.ui.keep_strongest_jamming_bearing()

                self._prev_run_state = run_state

                self.ui.draw_ui(metrics, power)
                self.frame_count += 1

                # Update web server state
                uptime = int(time.time() - self.start_time)
                web_server.update_state(metrics, power, uptime, bearing=int(self.current_bearing), gain=self.gain_db)

                # Log to database intelligently to prevent SD card wear and reduce CPU/IO lag.
                # Writes immediately on state change, every 30s in SCANNING, and every 3s in active events.
                current_time = time.time()
                state_changed = (metrics["state"] != getattr(self, '_last_logged_state', ''))
                log_interval = 30.0 if metrics["state"] == "SCANNING" else 3.0
                
                if state_changed or (current_time - self.last_log_time > log_interval):
                    database_manager.log_event(
                        metrics["state"],
                        metrics["score"],
                        metrics["peak_p"],
                        metrics["floor_rise"],
                        metrics["noise_floor"],
                        uptime,
                        bearing_deg=int(self.current_bearing)
                    )
                    self.last_log_time = current_time
                    self._last_logged_state = metrics["state"]

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
            uptime,
            bearing_deg=int(self.current_bearing)
        )
        # We could also trigger a screen save here if implemented
        
    def safe_power_off(self):
        """Safely shut down the Raspberry Pi."""
        self.running = False  # STOP the main loop immediately to prevent UI flicker
        time.sleep(0.1)       # Small gap to let the last frame finish
        
        print("[SYSTEM] Initiating safe shutdown...")
        self.ui.draw_splash("SHUTTING DOWN...")
        
        # Keep the splash screen visible for 5 seconds as requested
        time.sleep(5)
        
        # Cleanup hardware and black screen
        self.shutdown()

        # Attempt to power off the system. Try multiple safe methods and
        # then force-exit the process if none succeed so we don't hang.
        if sys.platform != "win32" and not self.preview:
            tried = []
            try_cmds = [
                ["sudo", "poweroff"],
                ["sudo", "systemctl", "poweroff"],
                ["sudo", "shutdown", "-h", "now"],
                ["/sbin/poweroff"],
            ]
            log_path = "/tmp/jamming_shutdown.log"
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"\n--- shutdown attempt {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                    for cmd in try_cmds:
                        cmd_s = " ".join(cmd)
                        tried.append(cmd_s)
                        lf.write(f"Trying: {cmd_s}\n")
                        try:
                            # capture output for debugging (synchronous block)
                            res = subprocess.run(cmd, timeout=8, capture_output=True, text=True)
                            lf.write(f"Returncode: {res.returncode}\n")
                            if res.stdout:
                                lf.write(f"STDOUT:\n{res.stdout}\n")
                            if res.stderr:
                                lf.write(f"STDERR:\n{res.stderr}\n")
                            if res.returncode == 0:
                                break
                        except Exception as e:
                            lf.write(f"Exception: {e}\n")

                    lf.write(f"Tried: {tried}\n")
                    lf.write("Waiting briefly for system to handle poweroff...\n")
            except Exception:
                pass

            # Small pause to allow systemd to act; if it didn't, force exit
            time.sleep(3)
            try:
                os._exit(0)
            except Exception:
                pass
        else:
            print("[INFO] Shutdown command skipped in preview/Windows mode.")

    def safe_reboot(self):
        """Safely restarts the jammer application in-place by replacing the current process."""
        self.running = False
        time.sleep(0.5)
        
        print("[SYSTEM] Initiating in-place application reload...")
        self.ui.draw_splash("RESTARTING...")
        time.sleep(1.5)
        
        # Stop background threads and release SDR/LED/Buzzer hardware resources cleanly
        self.shutdown()

        if not self.preview:
            try:
                print("[SYSTEM] Replacing process image now...")
                # Re-execute the python interpreter with the same script and arguments
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                print(f"[RESTART] In-place execv failed: {e}")
                # Fallback to exit if reload fails
                os._exit(1)
        else:
            print("[INFO] In-place restart skipped in preview mode.")
            os._exit(0)
    
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
                # Use the DisplayUI's drawing surface to clear the screen
                if getattr(self, 'ui', None) is not None and hasattr(self.ui, '_draw'):
                    try:
                        self.ui._draw.rectangle((0, 0, self.w, self.h), fill=(0, 0, 0))
                        self.device.display(self.ui._img)
                    except Exception:
                        # Fallback: try to blank device directly
                        try:
                            self.device.display(self.ui._img)
                        except Exception:
                            pass
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