import config
from hardware.mpu9250 import MPU9250


_MPU9250_ALIASES = {"MPU9250", "MPU-9250", "GY9250", "GY-9250", "GY_9250"}


def normalize_imu_model(model=None):
    raw_model = model if model is not None else getattr(config, "IMU_MODEL", "GY-9250")
    return str(raw_model).strip().upper().replace(" ", "")


def get_imu_class(model=None):
    normalized = normalize_imu_model(model)
    if normalized in _MPU9250_ALIASES:
        return MPU9250
    supported = ", ".join(sorted(_MPU9250_ALIASES))
    raise ValueError(f"Unsupported IMU_MODEL '{model}'. Supported values: {supported}")


def default_imu_address(model=None):
    normalized = normalize_imu_model(model)
    configured_address = getattr(config, "IMU_ADDRESS", None)
    if configured_address is not None:
        return configured_address
    if normalized in _MPU9250_ALIASES:
        return 0x69
    return 0x69


def create_imu(model=None, address=None, bus=1):
    imu_class = get_imu_class(model)
    imu_address = address if address is not None else default_imu_address(model)
    return imu_class(address=imu_address, bus=bus)
