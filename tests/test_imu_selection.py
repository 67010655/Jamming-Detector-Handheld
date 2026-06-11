import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.parametrize("model", ["MPU9250", "GY9250", "GY-9250", "gy_9250"])
def test_create_imu_accepts_gy9250_aliases(monkeypatch, model):
    import hardware.imu as imu

    created = {}

    class FakeMPU9250:
        def __init__(self, address=None, bus=1):
            created["address"] = address
            created["bus"] = bus

    monkeypatch.setattr(imu, "MPU9250", FakeMPU9250)

    sensor = imu.create_imu(model=model, address=0x69, bus=1)

    assert isinstance(sensor, FakeMPU9250)
    assert created == {"address": 0x69, "bus": 1}


def test_gy9250_default_address_avoids_ds3231_rtc_collision():
    import hardware.imu as imu

    assert imu.default_imu_address("GY-9250") == 0x69


def test_unknown_imu_model_is_rejected():
    import hardware.imu as imu

    with pytest.raises(ValueError, match="Unsupported IMU_MODEL"):
        imu.get_imu_class("BNO055")


def test_mpu9250_direct_default_address_avoids_rtc_collision(monkeypatch):
    import config
    from hardware.mpu9250 import MPU9250

    monkeypatch.setattr(config, "IMU_ADDRESS", None, raising=False)

    sensor = MPU9250()

    assert sensor.address == 0x69


def test_mpu9250_loads_adaptive_fusion_config():
    import config
    from hardware.mpu9250 import MPU9250

    sensor = MPU9250(address=0x69)

    assert sensor.fusion_alpha == config.IMU_FUSION_ALPHA
    assert sensor.fusion_still_alpha == config.IMU_FUSION_STILL_ALPHA
    assert sensor.still_gyro_dps == config.IMU_STILL_GYRO_DPS


def test_mag_only_mode_holds_last_heading_when_magnetometer_unavailable(monkeypatch):
    import hardware.mpu9250 as mpu9250

    sensor = mpu9250.MPU9250(address=0x69)
    sensor.bus = "mock_bus"
    sensor._init_success = True
    sensor.fusion_mode = "MAG_ONLY"
    sensor.bearing = 10.0

    monkeypatch.setattr(sensor, "get_heading_mag", lambda: None)
    monkeypatch.setattr(sensor, "_read_gyro_raw", lambda: 393)
    monkeypatch.setattr(mpu9250.time, "time", lambda: 101.0)

    sensor.last_time = 100.0

    assert sensor.update_bearing() == 10.0


def test_mpu9250_keeps_gyro_ready_when_magnetometer_init_fails(monkeypatch):
    import hardware.mpu9250 as mpu9250

    class FakeBus:
        def write_byte_data(self, address, _register, _value):
            if address == mpu9250.MPU9250._AK8963_ADDR:
                raise OSError("magnetometer unavailable")

        def close(self):
            pass

        def read_byte_data(self, _address, register):
            values = {0x43: 0x00, 0x44: 0x2A}
            return values.get(register, 0)

    class FakeSMBusModule:
        @staticmethod
        def SMBus(_bus):
            return FakeBus()

    monkeypatch.setattr(mpu9250, "smbus2", FakeSMBusModule)
    monkeypatch.setattr(mpu9250.time, "sleep", lambda _seconds: None)

    sensor = mpu9250.MPU9250(address=0x69)

    assert sensor._init_success is True
    assert sensor._mag_enabled is False
    assert sensor._read_gyro_raw() == 42


def test_get_heading_mag_applies_offset_and_declination(monkeypatch):
    import hardware.mpu9250 as mpu9250

    sensor = mpu9250.MPU9250(address=0x69)
    sensor._mag_enabled = True
    sensor.mag_offset_x = 100.0
    sensor.mag_offset_z = 50.0
    sensor.mag_scale_x = 1.0
    sensor.mag_scale_z = 1.0
    sensor.compass_offset_deg = 0.0
    sensor.mag_invert = False
    sensor.declination_deg = 5.0

    monkeypatch.setattr(sensor, "read_mag_raw", lambda: (200, 0, 150))

    assert abs(sensor.get_heading_mag() - 50.0) < 0.001


def test_get_heading_mag_applies_soft_iron_scale(monkeypatch):
    import hardware.mpu9250 as mpu9250

    sensor = mpu9250.MPU9250(address=0x69)
    sensor._mag_enabled = True
    sensor.mag_offset_x = 0.0
    sensor.mag_offset_z = 0.0
    sensor.mag_scale_x = 0.5
    sensor.mag_scale_z = 1.0
    sensor.compass_offset_deg = 0.0
    sensor.mag_invert = False
    sensor.declination_deg = 0.0

    monkeypatch.setattr(sensor, "read_mag_raw", lambda: (100, 0, 100))

    assert abs(sensor.get_heading_mag() - 63.43494882292201) < 0.001


def test_complementary_filter_bearing_wrapping_and_fusion(monkeypatch):
    import hardware.mpu9250 as mpu9250

    sensor = mpu9250.MPU9250(address=0x69)
    sensor.bus = "mock_bus"
    sensor._init_success = True
    sensor.fusion_mode = "COMPLEMENTARY"
    sensor.fusion_alpha = 0.90  # 90% gyro, 10% mag
    sensor.fusion_still_alpha = 0.90
    sensor.bearing = 359.0
    sensor.bearing_initialized = True

    monkeypatch.setattr(sensor, "get_heading_mag", lambda: 1.0)
    monkeypatch.setattr(sensor, "_read_gyro_raw", lambda: 0)  # no gyro drift
    monkeypatch.setattr(mpu9250.time, "time", lambda: 100.0)

    sensor.last_time = 99.0
    sensor.gyro_z_offset = 0

    bearing = sensor.update_bearing()
    # predicted bearing is 359.0
    # diff = 1.0 - 359.0 = -358.0 -> wrapping makes it +2.0
    # complementary output = 359.0 + 0.1 * 2.0 = 359.2
    assert abs(bearing - 359.2) < 0.001


def test_complementary_filter_recenters_faster_when_still(monkeypatch):
    import hardware.mpu9250 as mpu9250

    sensor = mpu9250.MPU9250(address=0x69)
    sensor.bus = "mock_bus"
    sensor._init_success = True
    sensor.fusion_mode = "COMPLEMENTARY"
    sensor.fusion_alpha = 0.95
    sensor.fusion_still_alpha = 0.75
    sensor.still_gyro_dps = 8.0
    sensor.bearing = 100.0
    sensor.bearing_initialized = True

    monkeypatch.setattr(sensor, "get_heading_mag", lambda: 120.0)
    monkeypatch.setattr(sensor, "_read_gyro_raw", lambda: 0)
    monkeypatch.setattr(mpu9250.time, "time", lambda: 101.0)

    sensor.last_time = 100.0
    sensor.gyro_z_offset = 0

    assert abs(sensor.update_bearing() - 105.0) < 0.001

