import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dsp import smooth_noise, compute_power, remove_dc_spike, scale_points


class TestSmoothNoise:
    def test_alpha_one_retains_old(self):
        assert smooth_noise(50.0, 30.0, 1.0) == pytest.approx(50.0)

    def test_alpha_zero_adopts_new(self):
        assert smooth_noise(50.0, 30.0, 0.0) == pytest.approx(30.0)

    def test_midpoint(self):
        assert smooth_noise(10.0, 20.0, 0.5) == pytest.approx(15.0)

    def test_typical_ema(self):
        prev, avg, alpha = 100.0, 80.0, 0.95
        assert smooth_noise(prev, avg, alpha) == pytest.approx(alpha * prev + (1 - alpha) * avg)


class TestComputePower:
    def _rect(self, n):
        return np.ones(n, dtype=np.float64)

    def test_output_length_matches_input(self):
        n = 256
        samples = np.ones(n, dtype=np.complex64)
        result = compute_power(samples, self._rect(n))
        assert len(result) == n

    def test_returns_numpy_array(self):
        result = compute_power(np.ones(64, dtype=np.complex64), self._rect(64))
        assert isinstance(result, np.ndarray)

    def test_dc_signal_peak_at_center(self):
        n = 256
        samples = np.ones(n, dtype=np.complex64)
        result = compute_power(samples, self._rect(n))
        # DC component lands at bin n//2 after fftshift
        assert result[n // 2] == pytest.approx(0.0, abs=1e-4)
        assert result[0] < -200

    def test_zero_input_all_at_floor(self):
        n = 256
        result = compute_power(np.zeros(n, dtype=np.complex64), self._rect(n))
        expected = 20.0 * np.log10(1e-12)
        assert np.all(result == pytest.approx(expected, abs=1e-4))


class TestRemoveDcSpike:
    def test_center_spike_is_replaced(self):
        n = 200
        power = np.full(n, -75.0)
        mid = n // 2
        power[mid - 5: mid + 5] = 0.0
        result = remove_dc_spike(power, dc_bins=10)
        # Replaced values should be close to neighbor mean (-75), not the spike (0)
        assert np.all(result[mid - 10: mid + 10] < -50)

    def test_outer_region_unchanged(self):
        n = 200
        power = np.full(n, -75.0)
        power[n // 2] = 0.0
        result = remove_dc_spike(power, dc_bins=1)
        np.testing.assert_array_equal(result[: n // 2 - 1], power[: n // 2 - 1])
        np.testing.assert_array_equal(result[n // 2 + 2 :], power[n // 2 + 2 :])

    def test_does_not_modify_input(self):
        power = np.full(200, -75.0)
        power[100] = 999.0
        original = power.copy()
        remove_dc_spike(power)
        np.testing.assert_array_equal(power, original)

    def test_flat_signal_unchanged_values(self):
        # If signal is already flat, replacement = neighbor mean = same value
        power = np.full(200, -80.0)
        result = remove_dc_spike(power, dc_bins=10)
        mid = 100
        assert np.all(result[mid - 10: mid + 10] == pytest.approx(-80.0, abs=1e-6))


class TestScalePoints:
    def test_empty_input(self):
        assert scale_points(np.array([]), 0.0, 480, 0, 320) == []

    def test_all_points_within_screen_bounds(self):
        power = np.random.uniform(-80, -40, 512)
        result = scale_points(power, -70.0, 480, 10, 300)
        for _, y in result:
            assert 10 + 2 <= y <= 300 - 2

    def test_max_points_bounded_by_width(self):
        power = np.random.uniform(-80, -50, 1024)
        result = scale_points(power, -70.0, 480, 0, 320)
        assert len(result) <= 480

    def test_high_power_near_top(self):
        # power 60 dB above display floor → normalized clips to span → y near graph_top
        # display_floor = nf - 10 = -90; power = -30 → normalized = clip(60, 0, 50) = 50
        # y = 300 - (50/50)*(300-10-4) = 300 - 286 = 14
        power = np.full(256, -30.0)
        result = scale_points(power, -80.0, 480, 10, 300)
        assert all(y <= 20 for _, y in result)

    def test_floor_power_near_bottom(self):
        # power at display_floor_db (= nf - 10) → normalized = 0 → y = graph_bottom → clipped to graph_bottom - 2
        power = np.full(256, -90.0)  # nf=-80, display_floor = -90
        result = scale_points(power, -80.0, 480, 10, 300)
        assert all(y >= 295 for _, y in result)

    def test_single_bin_returns_one_point(self):
        result = scale_points(np.array([-70.0]), -70.0, 480, 0, 320)
        assert len(result) == 1
        x, y = result[0]
        assert isinstance(x, int)
        assert isinstance(y, int)
