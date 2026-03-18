from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import sys


APP_NAME = "ETS2DIYFFBWheel"


def app_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    base = Path.home() / "AppData" / "Local" / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class WheelProfile:
    master_gain: float = 0.35
    spring_gain: float = 0.28
    damper_gain: float = 0.15
    friction_gain: float = 0.08
    vibration_gain: float = 0.08
    vibration_freq_hz: float = 28.0
    bump_gain: float = 0.22
    collision_gain: float = 0.30
    speed_sensitivity: float = 0.65
    wheel_center_deg: float = 0.0
    torque_limit: float = 0.45
    last_port: str = ""
    start_with_windows: bool = False
    test_mode: bool = True
    runtime_enabled: bool = True
    virtual_controller_enabled: bool = True
    virtual_steering_range_deg: float = 360.0
    brake: "PedalCalibration" = field(default_factory=lambda: PedalCalibration())
    accel: "PedalCalibration" = field(default_factory=lambda: PedalCalibration())
    encoder: "EncoderCalibration" = field(default_factory=lambda: EncoderCalibration())
    motor: "MotorConfiguration" = field(default_factory=lambda: MotorConfiguration())

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "WheelProfile":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            master_gain=raw.get("master_gain", 0.35),
            spring_gain=raw.get("spring_gain", 0.28),
            damper_gain=raw.get("damper_gain", 0.15),
            friction_gain=raw.get("friction_gain", 0.08),
            vibration_gain=raw.get("vibration_gain", 0.08),
            vibration_freq_hz=raw.get("vibration_freq_hz", 28.0),
            bump_gain=raw.get("bump_gain", 0.22),
            collision_gain=raw.get("collision_gain", 0.30),
            speed_sensitivity=raw.get("speed_sensitivity", 0.65),
            wheel_center_deg=raw.get("wheel_center_deg", 0.0),
            torque_limit=raw.get("torque_limit", 0.45),
            last_port=raw.get("last_port", ""),
            start_with_windows=raw.get("start_with_windows", False),
            test_mode=raw.get("test_mode", True),
            runtime_enabled=raw.get("runtime_enabled", True),
            virtual_controller_enabled=raw.get("virtual_controller_enabled", True),
            virtual_steering_range_deg=raw.get("virtual_steering_range_deg", 360.0),
            brake=PedalCalibration(**raw.get("brake", {})),
            accel=PedalCalibration(**raw.get("accel", {})),
            encoder=EncoderCalibration(**raw.get("encoder", {})),
            motor=MotorConfiguration(**raw.get("motor", {})),
        )


@dataclass
class PedalCalibration:
    min_raw: int = 300
    max_raw: int = 3800
    invert: bool = False


@dataclass
class EncoderCalibration:
    counts_per_rev: int = 8000
    wheel_range_deg: float = 900.0
    invert_direction: bool = False
    center_offset_deg: float = 0.0


@dataclass
class MotorConfiguration:
    invert_direction: bool = False
    startup_enable: bool = False


@dataclass
class AppSettings:
    last_profile_path: str = ""
    last_tab_index: int = 0

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "AppSettings":
        raw = json.loads(path.read_text(encoding="utf-8"))
        settings = cls(
            last_profile_path=raw.get("last_profile_path", ""),
            last_tab_index=raw.get("last_tab_index", 0),
        )
        for key in ("last_port", "start_with_windows", "test_mode", "runtime_enabled", "brake", "accel", "encoder", "motor"):
            if key not in raw:
                continue
            value = raw[key]
            if key in ("brake", "accel"):
                value = PedalCalibration(**value)
            elif key == "encoder":
                value = EncoderCalibration(**value)
            elif key == "motor":
                value = MotorConfiguration(**value)
            setattr(settings, key, value)
        return settings

BUNDLED_PROFILE_PATH = app_root() / "profiles" / "default_ets2_profile.json"
DEFAULT_PROFILE_PATH = user_data_dir() / "default_ets2_profile.json"
APP_SETTINGS_PATH = user_data_dir() / "app_settings.json"
