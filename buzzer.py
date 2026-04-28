"""
Buzzer control module for Raspberry Pi.

This module provides a simple buzzer interface for startup and state
notifications. The buzzer uses PWM on a GPIO pin and can be disabled for
preview mode or on systems without GPIO access.
"""

import time

import config


class BuzzerController:
    def __init__(self, buzzer_pin=None, enabled=True):
        self.buzzer_pin = buzzer_pin or config.BUZZER_PIN
        self.enabled = enabled
        self.gpio = None
        self.pwm = None
        self.current_state = None

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

    def _buzz(self, duration_s, frequency_hz=1200, duty_cycle=50):
        if not self.enabled or self.gpio is None:
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

    def _tone(self, pulses=2, pulse_duration=0.08, gap_duration=0.08, frequency_hz=1200):
        for index in range(pulses):
            self._buzz(pulse_duration, frequency_hz)
            if index < pulses - 1:
                time.sleep(gap_duration)

    def play_startup(self):
        """Play a short startup chime when the device starts."""
        print("[BUZZER] Playing startup sound")
        self._tone(pulses=3, pulse_duration=0.08, gap_duration=0.08, frequency_hz=1000)

    def set_state(self, state):
        """Play a notification sound for each detector state change."""
        if state == self.current_state:
            return

        self.current_state = state
        if state == "SCANNING":
            print("[BUZZER] SCANNING notification")
            self._tone(pulses=2, pulse_duration=0.08, gap_duration=0.10, frequency_hz=900)
            time.sleep(2.0)
        elif state == "WATCH":
            print("[BUZZER] WATCH notification")
            self._tone(pulses=2, pulse_duration=0.08, gap_duration=0.08, frequency_hz=1200)
            time.sleep(1.0)
        elif state == "JAMMING":
            print("[BUZZER] JAMMING notification")
            self._tone(pulses=2, pulse_duration=0.08, gap_duration=0.05, frequency_hz=1500)
            time.sleep(0.5)

    def cleanup(self):
        """Clean up GPIO resources used by the buzzer."""
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
        self._tone(pulses=3, pulse_duration=0.06, gap_duration=0.06, frequency_hz=1200)
