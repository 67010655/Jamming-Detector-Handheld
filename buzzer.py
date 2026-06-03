import time
import threading
import queue
import config


class BuzzerController:
    def __init__(self, buzzer_pin=None, enabled=True):
        self.buzzer_pin = buzzer_pin or config.BUZZER_PIN
        self.enabled = enabled
        self.muted = False  # Added for UI control
        self.gpio = None
        self.pwm = None
        self.current_state = None

        self._queue = queue.Queue()
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)

        if self.enabled:
            try:
                import RPi.GPIO as GPIO
                self.gpio = GPIO
                self.gpio.setmode(GPIO.BCM)
                self.gpio.setwarnings(False)
                self.gpio.setup(self.buzzer_pin, GPIO.OUT)
                self.gpio.output(self.buzzer_pin, GPIO.LOW)
                self.pwm = self.gpio.PWM(self.buzzer_pin, 1200)
                self.pwm.start(0)
                print(f"[BUZZER] GPIO initialized on pin {self.buzzer_pin}")
            except Exception as exc:
                print(f"[BUZZER] Warning: GPIO unavailable: {exc}")
                self.enabled = False

        self._thread.start()

    def _worker(self):
        while self._running:
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task is None:
                break
                
            if isinstance(task, list):
                for note in task:
                    if not self._running:
                        break
                    freq = note[0]
                    dur = note[1]
                    gap = note[2] if len(note) > 2 else 0.0
                    self._buzz(dur, freq)
                    if gap > 0:
                        time.sleep(gap)
            else:
                pulses, pulse_duration, gap_duration, frequency_hz = task
                for index in range(pulses):
                    if not self._running:
                        break
                    self._buzz(pulse_duration, frequency_hz)
                    if index < pulses - 1 and gap_duration > 0:
                        time.sleep(gap_duration)
                    
            self._queue.task_done()

    def _buzz(self, duration_s, frequency_hz=1200, duty_cycle=50):
        if not self.enabled or self.gpio is None or self.muted:
            time.sleep(duration_s)
            return

        try:
            self.pwm.ChangeFrequency(frequency_hz)
            self.pwm.ChangeDutyCycle(duty_cycle)
            time.sleep(duration_s)
        except Exception as exc:
            print(f"[BUZZER] Error during buzz: {exc}")
        finally:
            try:
                self.pwm.ChangeDutyCycle(0)
            except Exception:
                pass

    def _tone(self, pulses=2, pulse_duration=0.08, gap_duration=0.08, frequency_hz=1200, sequence=None):
        # Clear any pending tones so the new state overrides immediately
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
                
        if sequence is not None:
            self._queue.put(sequence)
        else:
            self._queue.put((pulses, pulse_duration, gap_duration, frequency_hz))

    def play_startup(self):
        """Play a short startup chime when the device starts."""
        print("[BUZZER] Playing startup sound")
        # Ascending major triad arpeggio (C6 -> E6 -> G6)
        startup_seq = [(1047, 0.05, 0.02), (1319, 0.05, 0.02), (1568, 0.08, 0.0)]
        self._tone(sequence=startup_seq)

    def set_state(self, state):
        """Play a notification sound for each detector state change."""
        if state == self.current_state:
            return

        self.current_state = state
        if state == "SCANNING":
            # Pleasant descending chime (E6 -> A5)
            scan_seq = [(1319, 0.06, 0.02), (880, 0.10, 0.0)]
            self._tone(sequence=scan_seq)
        elif state == "WATCH":
            # Soft caution warning double-pulse
            watch_seq = [(1100, 0.06, 0.05), (1100, 0.06, 0.0)]
            self._tone(sequence=watch_seq)
        elif state == "JAMMING":
            # Rapid high-tech alarm chirp sequence
            jam_seq = [(1800, 0.04, 0.02), (1500, 0.04, 0.02), (1800, 0.04, 0.02), (1500, 0.06, 0.0)]
            self._tone(sequence=jam_seq)

    def play_click(self):
        """Play a short 'click' sound for UI interaction."""
        # Short haptic click (1800Hz for 0.015 seconds)
        click_seq = [(1800, 0.015, 0.0)]
        self._tone(sequence=click_seq)

    def cleanup(self):
        """Clean up GPIO resources used by the buzzer."""
        self._running = False
        self._queue.put(None)  # Wake up thread to exit

        if self.enabled and self.gpio is not None:
            try:
                if self.pwm is not None:
                    self.pwm.stop()
                self.gpio.output(self.buzzer_pin, self.gpio.LOW)
                self.gpio.cleanup()
                print("[BUZZER] GPIO cleanup complete")
            except Exception as exc:
                print(f"[BUZZER] Cleanup warning: {exc}")

    def test_sequence(self):
        """Play a test sound sequence for debugging."""
        print("[BUZZER] Running test sequence")
        self._tone(pulses=3, pulse_duration=0.06, gap_duration=0.06, frequency_hz=1200)

    def toggle_mute(self):
        """Toggle the mute state of the buzzer."""
        self.muted = not self.muted
        print(f"[BUZZER] {'MUTED' if self.muted else 'UNMUTED'}")
        return self.muted
