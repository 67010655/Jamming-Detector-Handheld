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
                # Advanced note sequence: each note is (frequency_hz, duration_s, gap_duration_s)
                for item in task:
                    if len(item) == 3:
                        frequency_hz, duration_s, gap_duration_s = item
                    else:
                        frequency_hz, duration_s = item
                        gap_duration_s = 0.0
                        
                    if frequency_hz > 0:
                        self._buzz(duration_s, frequency_hz)
                    else:
                        time.sleep(duration_s) # Rest/silence note
                        
                    if gap_duration_s > 0:
                        time.sleep(gap_duration_s)
            else:
                # Backward compatibility for traditional flat pulse train
                pulses, pulse_duration, gap_duration, frequency_hz = task
                for index in range(pulses):
                    self._buzz(pulse_duration, frequency_hz)
                    if index < pulses - 1:
                        time.sleep(gap_duration)
                    
            self._queue.task_done()

    def _buzz(self, duration_s, frequency_hz=1200, duty_cycle=50):
        if not self.enabled or self.gpio is None or self.muted:
            time.sleep(duration_s)
            return

        try:
            self.pwm = self.gpio.PWM(self.buzzer_pin, frequency_hz)
            self.pwm.start(duty_cycle)
            time.sleep(duration_s)
        except Exception as exc:
            print(f"[BUZZER] Error during buzz: {exc}")
        finally:
            if self.pwm is not None:
                try:
                    self.pwm.stop()
                except Exception:
                    pass
                self.pwm = None
            try:
                self.gpio.output(self.buzzer_pin, self.gpio.LOW)
            except Exception:
                pass

    def _get_melody_for_event(self, event):
        profile = getattr(config, 'BUZZER_PROFILE', 'STANDARD').upper()
        
        if profile == "CUSTOM":
            custom_tones = getattr(config, 'CUSTOM_BUZZER_TONES', {})
            if event in custom_tones:
                return custom_tones[event]
            profile = "STANDARD"

        if profile == "PREMIUM_CHIME":
            if event == "STARTUP":
                return [
                    (523, 0.08, 0.02),
                    (659, 0.08, 0.02),
                    (784, 0.08, 0.02),
                    (1047, 0.15, 0.0)
                ]
            elif event == "SCANNING":
                return [
                    (988, 0.04, 0.06),
                    (988, 0.04, 0.0)
                ]
            elif event == "WATCH":
                return [
                    (880, 0.06, 0.04),
                    (1175, 0.08, 0.0)
                ]
            elif event == "JAMMING":
                return [
                    (1318, 0.06, 0.03),
                    (1318, 0.06, 0.03),
                    (1568, 0.12, 0.0)
                ]
            elif event == "TEST":
                return [
                    (523, 0.05, 0.05),
                    (587, 0.05, 0.05),
                    (659, 0.05, 0.05),
                    (698, 0.05, 0.05),
                    (784, 0.10, 0.0)
                ]

        elif profile == "SIREN_WARP":
            if event == "STARTUP":
                return [(f, 0.005, 0.001) for f in range(800, 1600, 40)]
            elif event == "SCANNING":
                return [(900, 0.05, 0.0)]
            elif event == "WATCH":
                return ([(f, 0.008, 0.001) for f in range(1000, 1500, 50)] + 
                        [(f, 0.008, 0.001) for f in range(1500, 1000, -50)])
            elif event == "JAMMING":
                sweep = ([(f, 0.004, 0.001) for f in range(1200, 2200, 50)] + 
                         [(f, 0.004, 0.001) for f in range(2200, 1200, -50)])
                return sweep * 2
            elif event == "TEST":
                return [(f, 0.005, 0.001) for f in range(600, 1800, 30)]

        # Default STANDARD profiles (original beeps)
        if event == "STARTUP":
            return [(1000, 0.08, 0.08)] * 3
        elif event == "SCANNING":
            return [(900, 0.08, 0.10)] * 2
        elif event == "WATCH":
            return [(1200, 0.08, 0.08)] * 2
        elif event == "JAMMING":
            return [(1500, 0.08, 0.05)] * 2
        elif event == "TEST":
            return [(1200, 0.06, 0.06)] * 3

    def _play_event(self, event):
        melody = self._get_melody_for_event(event)
        # Clear any pending tones so the new state overrides immediately
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
                
        self._queue.put(melody)

    def _tone(self, pulses=2, pulse_duration=0.08, gap_duration=0.08, frequency_hz=1200):
        # Kept for direct manual calls
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
                
        self._queue.put((pulses, pulse_duration, gap_duration, frequency_hz))

    def play_startup(self):
        """Play a short startup chime when the device starts."""
        print("[BUZZER] Playing startup sound")
        self._play_event("STARTUP")

    def set_state(self, state):
        """Play a notification sound for each detector state change."""
        if state == self.current_state:
            return

        self.current_state = state
        self._play_event(state)

    def play_click(self):
        """Play a short 'click' sound for UI interaction."""
        self._tone(pulses=1, pulse_duration=0.03, gap_duration=0, frequency_hz=1500)

    def cleanup(self):
        """Clean up GPIO resources used by the buzzer."""
        self._running = False
        self._queue.put(None)  # Wake up thread to exit
        
        if self.enabled and self.gpio is not None:
            try:
                self.gpio.output(self.buzzer_pin, self.gpio.LOW)
                self.gpio.cleanup()
                print("[BUZZER] GPIO cleanup complete")
            except Exception as exc:
                print(f"[BUZZER] Cleanup warning: {exc}")

    def test_sequence(self):
        """Play a test sound sequence for debugging."""
        print("[BUZZER] Running test sequence")
        self._play_event("TEST")

    def toggle_mute(self):
        """Toggle the mute state of the buzzer."""
        self.muted = not self.muted
        print(f"[BUZZER] {'MUTED' if self.muted else 'UNMUTED'}")
        return self.muted
