from __future__ import annotations

from dataclasses import dataclass
import math
import time

from .config import WheelProfile


@dataclass
class TelemetrySample:
    connected: bool = False
    source: str = "test"
    speed_mps: float = 0.0
    engine_rpm: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    steer_input: float = 0.0
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0
    suspension_bump: float = 0.0
    collision: float = 0.0


@dataclass
class ForceCommand:
    constant: float
    spring_gain: float
    spring_center_deg: float
    damper_gain: float
    friction_gain: float
    vibration_gain: float
    vibration_freq_hz: float
    impulse_torque: float
    impulse_duration_ms: int
    debug_total: float


class ForceFeedbackModel:
    def __init__(self) -> None:
        self._last_time = time.perf_counter()
        self._phase = 0.0

    def compute(
        self,
        telemetry: TelemetrySample,
        wheel_angle_deg: float,
        wheel_speed_deg_s: float,
        profile: WheelProfile,
        test_mode: bool = False,
    ) -> ForceCommand:
        now = time.perf_counter()
        dt = max(1e-3, now - self._last_time)
        self._last_time = now

        telemetry_live = test_mode or telemetry.connected

        if telemetry_live:
            road_speed_factor = min(1.0, telemetry.speed_mps / 35.0)
            speed_gain = 0.3 + 0.7 * profile.speed_sensitivity * road_speed_factor
            spring_gain = profile.spring_gain * speed_gain
            damper_gain = profile.damper_gain * (0.4 + road_speed_factor)
            friction_gain = profile.friction_gain * (0.2 + 0.8 * road_speed_factor)
        else:
            # Keep passive wheel feel alive even before ETS2 telemetry comes up.
            road_speed_factor = 0.0
            spring_gain = profile.spring_gain
            damper_gain = profile.damper_gain * 0.55
            friction_gain = profile.friction_gain * 0.35

        engine_factor = min(1.0, telemetry.engine_rpm / 2500.0)
        self._phase += dt * (profile.vibration_freq_hz + engine_factor * 16.0)

        bump_signal = abs(telemetry.accel_y) + telemetry.suspension_bump
        impulse = min(profile.bump_gain * bump_signal, 0.3)
        duration = 55
        if telemetry.collision > 0.05:
            impulse = max(impulse, min(profile.collision_gain * telemetry.collision, 0.4))
            duration = 90

        # Keep continuous vibration tied to actual road speed and bumps instead of
        # throttle position. This avoids one-sided crawling on undervolted H-bridges.
        vibration_gain = 0.0
        if telemetry_live and telemetry.speed_mps > 0.8:
            bump_factor = min(1.0, bump_signal * 2.5)
            vibration_gain = profile.vibration_gain * road_speed_factor * (0.18 + bump_factor * 0.55)

        test_constant = 0.0
        if test_mode:
            test_constant = 0.08 * math.sin(self._phase * 1.1)
            vibration_gain = max(vibration_gain, 0.12)
        elif not telemetry.connected:
            vibration_gain = 0.0

        if telemetry_live:
            damper_gain *= 1.0 + min(1.0, telemetry.brake) * 0.65

        friction_term = 0.0
        if abs(wheel_speed_deg_s) > 1.0:
            friction_term = math.copysign(friction_gain * 0.12, -wheel_speed_deg_s)

        total = (
            test_constant
            + (-wheel_angle_deg / 450.0) * spring_gain
            + (-wheel_speed_deg_s / 720.0) * damper_gain
            + friction_term
        )
        total = max(-profile.torque_limit, min(profile.torque_limit, total * profile.master_gain))

        return ForceCommand(
            constant=total,
            spring_gain=spring_gain * profile.master_gain,
            spring_center_deg=profile.wheel_center_deg,
            damper_gain=damper_gain * profile.master_gain,
            friction_gain=friction_gain * profile.master_gain,
            vibration_gain=vibration_gain * profile.master_gain,
            vibration_freq_hz=profile.vibration_freq_hz,
            impulse_torque=impulse * profile.master_gain,
            impulse_duration_ms=duration,
            debug_total=total,
        )
