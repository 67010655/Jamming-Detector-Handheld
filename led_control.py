"""
LED Control Module for Raspberry Pi
Controls 3 LEDs on GPIO pins to indicate detector state:
- RED LED: JAMMING state
- YELLOW LED: WATCH state
- GREEN LED: SCANNING state
"""

import config

class LEDController:
    def __init__(self, red_pin=None, yellow_pin=None, green_pin=None, enabled=True):
        """
        Initialize LED controller.
        
        Args:
            red_pin: GPIO pin for RED LED (JAMMING) - uses config.LED_RED_PIN if None
            yellow_pin: GPIO pin for YELLOW LED (WATCH) - uses config.LED_YELLOW_PIN if None
            green_pin: GPIO pin for GREEN LED (SCANNING) - uses config.LED_GREEN_PIN if None
            enabled: Whether to enable LED control (False in preview mode)
        """
        self.red_pin = red_pin or config.LED_RED_PIN
        self.yellow_pin = yellow_pin or config.LED_YELLOW_PIN
        self.green_pin = green_pin or config.LED_GREEN_PIN
        self.enabled = enabled
        self.current_state = None
        self.gpio = None
        
        if self.enabled:
            try:
                import RPi.GPIO as GPIO
                self.gpio = GPIO
                self.gpio.setmode(GPIO.BCM)
                self.gpio.setwarnings(False)
                
                for pin in [self.red_pin, self.yellow_pin, self.green_pin]:
                    self.gpio.setup(pin, self.gpio.OUT)
                    self.gpio.output(pin, self.gpio.LOW)
                
                print(f"[LED] GPIO initialized: RED={self.red_pin}, YELLOW={self.yellow_pin}, GREEN={self.green_pin}")
            except Exception as e:
                print(f"[LED] Warning: Could not initialize GPIO: {e}")
                self.enabled = False
    
    def set_state(self, state):
        """
        Update LED state based on detector state.
        
        Args:
            state: One of "JAMMING", "WATCH", or "SCANNING"
        """
        if not self.enabled or self.gpio is None:
            return
        
        if self.current_state == state:
            return  # No change needed
        
        self.current_state = state
        
        try:
            # Turn off all LEDs first
            self.gpio.output(self.red_pin, self.gpio.LOW)
            self.gpio.output(self.yellow_pin, self.gpio.LOW)
            self.gpio.output(self.green_pin, self.gpio.LOW)
            
            # Turn on appropriate LED
            if state == "JAMMING":
                self.gpio.output(self.red_pin, self.gpio.HIGH)
                print("[LED] RED - JAMMING")
            elif state == "WATCH":
                self.gpio.output(self.yellow_pin, self.gpio.HIGH)
                print("[LED] YELLOW - WATCH")
            elif state == "SCANNING":
                self.gpio.output(self.green_pin, self.gpio.HIGH)
                print("[LED] GREEN - SCANNING")
        except Exception as e:
            print(f"[LED] Error setting state: {e}")
    
    def cleanup(self):
        """Clean up GPIO when shutting down."""
        if self.enabled and self.gpio is not None:
            try:
                self.gpio.output(self.red_pin, self.gpio.LOW)
                self.gpio.output(self.yellow_pin, self.gpio.LOW)
                self.gpio.output(self.green_pin, self.gpio.LOW)
                self.gpio.cleanup()
                print("[LED] GPIO cleanup complete")
            except Exception as e:
                print(f"[LED] Warning during cleanup: {e}")
    
    def test_sequence(self):
        """Test all LEDs in sequence."""
        if not self.enabled or self.gpio is None:
            print("[LED] GPIO not available for testing")
            return
        
        import time
        states = ["SCANNING", "WATCH", "JAMMING"]
        for state in states:
            self.set_state(state)
            time.sleep(0.5)
        self.set_state("SCANNING")
