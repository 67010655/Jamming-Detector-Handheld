import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from detector import GPSJammerHandheld

class MockLED:
    def set_state(self, s): pass

class MockBuzzer:
    def set_state(self, s): pass

class HelperMockDetector(GPSJammerHandheld):
    def __init__(self):
        self.preview = True
        self.fixed_nf = False
        self.calibrated_base_nf = config.DEFAULT_NOISE_FLOOR_DB
        self.noise_floor = config.DEFAULT_NOISE_FLOOR_DB
        self.baseline_guard_active = False
        
        self.alpha_idle = config.ALPHA_IDLE
        self.alpha_alert = config.ALPHA_ALERT
        self.floor_rise_threshold_db = config.FLOOR_RISE_THRESHOLD
        self.peak_threshold_db = config.PEAK_THRESHOLD
        self.warn_floor_rise_threshold_db = config.WARN_FLOOR
        self.warn_peak_threshold_db = config.WARN_PEAK
        
        self.hit_frames_required = getattr(config, 'HIT_FRAMES', 3)
        self.clear_frames_required = getattr(config, 'CLEAR_FRAMES', 10)
        self.jam_hits = 0
        self.clear_hits = 0
        self.jammer_active = False
        self.current_state = "SCANNING"
        
        self.led = MockLED()
        self.buzzer = MockBuzzer()

def test_scanning_state_at_baseline():
    det = HelperMockDetector()
    # Floor rise = 0, peak diff = 0
    power = np.full(100, det.noise_floor)
    metrics = det._detect_jamming(power)
    assert metrics["state"] == "SCANNING"
    assert det.baseline_guard_active is False

def test_watch_state_moderate_floor_rise():
    det = HelperMockDetector()
    # Floor rise = 9 dB (above WARN_FLOOR=8.0, below FLOOR_RISE_THRESHOLD=15.0)
    power = np.full(100, det.noise_floor + 9.0)
    metrics = det._detect_jamming(power)
    
    # State should be WATCH, and baseline guard should be active to lock baseline
    assert metrics["state"] == "WATCH"
    assert det.baseline_guard_active is True

def test_jamming_state_high_floor_rise_immediate():
    det = HelperMockDetector()
    # Floor rise = 16 dB (above FLOOR_RISE_THRESHOLD=15.0)
    power = np.full(100, det.noise_floor + 16.0)
    metrics = det._detect_jamming(power)
    
    # State should be JAMMING immediately because baseline guard is active and rise > threshold
    assert metrics["state"] == "JAMMING"
    assert det.baseline_guard_active is True
    assert det.jammer_active is True

def test_peak_debounce_transitions():
    det = HelperMockDetector()
    # Peak diff = 30 dB (above PEAK_THRESHOLD=28.0), but floor rise = 0
    # No floor rise means baseline guard will NOT trigger (since floor_rise=0 < 8.0)
    # Therefore, state transition should be debounced via jam_hits count.
    
    power = np.full(100, det.noise_floor)
    power[0] = det.noise_floor + 30.0 # Peak spike
    
    # Frame 1: jam_hits = 1, state = WATCH (since jammer_active is False, but warn_now is True)
    metrics = det._detect_jamming(power)
    assert metrics["state"] == "WATCH"
    assert det.jam_hits == 1
    assert det.jammer_active is False
    
    # Frame 2: jam_hits = 2, state = WATCH
    metrics = det._detect_jamming(power)
    assert metrics["state"] == "WATCH"
    assert det.jam_hits == 2
    assert det.jammer_active is False
    
    # Frame 3: jam_hits = 3, state = JAMMING (jammer_active becomes True)
    metrics = det._detect_jamming(power)
    assert metrics["state"] == "JAMMING"
    assert det.jam_hits == 3
    assert det.jammer_active is True
