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
