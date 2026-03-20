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

        effective_master_gain = max(profile.master_gain, 0.38)
        effective_spring_gain = max(profile.spring_gain, 0.12)
        effective_damper_gain = max(profile.damper_gain, 0.08)
        effective_friction_gain = max(profile.friction_gain, 0.02)
        effective_speed_sensitivity = max(profile.speed_sensitivity, 0.50)
        effective_torque_limit = max(profile.torque_limit, 0.35)

        telemetry_live = test_mode or telemetry.connected

        def shaped_center_error(angle_deg: float) -> float:
            deadzone_deg = 0.8
            max_angle_deg = 450.0
            magnitude = abs(angle_deg)
            if magnitude <= deadzone_deg:
                return 0.0
            normalized = min(1.0, (magnitude - deadzone_deg) / max(1.0, max_angle_deg - deadzone_deg))
            # Real road-car steering should feel light around center, with a
            # progressively firmer return only as steering angle builds.
            shaped = 0.28 * math.sqrt(normalized) + 0.22 * normalized + 0.50 * (normalized * normalized)
            return math.copysign(shaped, angle_deg)

        if telemetry_live:
            road_speed_factor = min(1.0, telemetry.speed_mps / 30.0)
            # Make return-to-center mostly speed-based. At parking speeds it
            # should stay easy to move; at road speed it should self-center.
            spring_gain = (
                (0.00045 + 0.0180 * pow(road_speed_factor, 1.7))
                * (0.30 + 0.90 * effective_spring_gain)
                * (0.58 + 0.42 * effective_speed_sensitivity)
            )
            damper_gain = (
                (0.00010 + 0.00070 * road_speed_factor)
                * (0.18 + 0.45 * effective_damper_gain)
            )
            friction_gain = effective_friction_gain * (0.01 + 0.04 * road_speed_factor)
        else:
            road_speed_factor = 0.0
            spring_gain = 0.00065 * (0.28 + 0.60 * effective_spring_gain)
            damper_gain = 0.00008 * (0.20 + 0.35 * effective_damper_gain)
            friction_gain = effective_friction_gain * 0.01

        # Use the game's own steering telemetry as the primary target so the
        # desktop app acts more like a transport/adaptation layer than an
        # independent steering-behavior generator.
        target_angle_deg = 0.0
        if telemetry_live:
            target_angle_deg = telemetry.steer_input * (profile.virtual_steering_range_deg * 0.5)

        engine_factor = min(1.0, telemetry.engine_rpm / 2500.0)
        self._phase += dt * (profile.vibration_freq_hz + engine_factor * 16.0)

        bump_signal = abs(telemetry.accel_y) + telemetry.suspension_bump
        # Do not turn road acceleration magnitude into a one-sided impulse.
        # A unipolar kick biases the wheel left/right during normal driving.
        impulse = 0.0
        duration = 55
        if telemetry.collision > 0.05:
            impulse = min(profile.collision_gain * telemetry.collision, 0.4)
            duration = 90

        # Keep continuous vibration tied to actual road speed and bumps instead of
        # throttle position. This avoids one-sided crawling on undervolted H-bridges.
        vibration_gain = 0.0
        if telemetry_live and telemetry.speed_mps > 0.8:
            bump_factor = min(1.0, bump_signal * 2.5)
            road_surface_gain = road_speed_factor * (
                0.10
                + (0.30 * profile.bump_gain)
                + bump_factor * (0.35 + 0.35 * profile.bump_gain)
            )
            vibration_gain = profile.vibration_gain * road_surface_gain

            # Under uphill load the forum plugin adds wheel buzz; emulate that
            # behavior with a restrained extra shudder instead of a hard kick.
            engine_load = max(
                0.0,
                min(
                    1.0,
                    (telemetry.throttle - 0.32) * 1.45
                    + max(0.0, 0.58 - engine_factor) * 0.55,
                ),
            )
            vibration_gain += profile.vibration_gain * engine_load * (0.04 + 0.20 * (1.0 - road_speed_factor))
            vibration_gain = min(max(profile.vibration_gain, 0.20), vibration_gain)

        test_constant = 0.0
        if test_mode:
            test_constant = 0.08 * math.sin(self._phase * 1.1)
            vibration_gain = max(vibration_gain, 0.12)
        elif not telemetry.connected:
            vibration_gain = 0.0

        if telemetry_live:
            damper_gain *= 1.0 + min(1.0, telemetry.brake) * 0.18

        friction_term = 0.0
        if abs(wheel_speed_deg_s) > 8.0:
            low_speed_blend = max(0.0, 1.0 - min(1.0, abs(wheel_speed_deg_s) / 260.0))
            friction_term = math.copysign(friction_gain * (0.006 + 0.010 * low_speed_blend), -wheel_speed_deg_s)

        shifted_angle_deg = wheel_angle_deg - target_angle_deg
        center_window_deg = 14.0 + 26.0 * road_speed_factor
        near_center_factor = 1.0 - min(1.0, abs(shifted_angle_deg) / max(1.0, center_window_deg))
        wheel_speed_factor = min(1.0, abs(wheel_speed_deg_s) / (110.0 + 190.0 * road_speed_factor))
        driver_is_steering_away = (shifted_angle_deg * wheel_speed_deg_s) > 0.0
        driver_override = 0.0
        if driver_is_steering_away:
            driver_override = min(
                1.0,
                (abs(wheel_speed_deg_s) / (22.0 + 50.0 * road_speed_factor))
                * (0.45 + 0.75 * min(1.0, abs(shifted_angle_deg) / 70.0)),
            )
        center_smoothing = 1.0 - 0.35 * near_center_factor
        center_smoothing *= 1.0 - 0.10 * road_speed_factor * wheel_speed_factor
        center_smoothing *= 1.0 - 0.88 * driver_override
        center_smoothing = max(0.20, center_smoothing)
        shaped_angle_deg = shaped_center_error(shifted_angle_deg) * 450.0
        center_term = -shaped_angle_deg * spring_gain * center_smoothing
        damping_term = (-wheel_speed_deg_s) * damper_gain * (
            0.65 + 0.12 * near_center_factor * road_speed_factor
        )
        if driver_override > 0.0:
            damping_term *= 1.0 - 0.75 * driver_override

        total = (
            test_constant
            + center_term
            + damping_term
            + friction_term
        )
        total = max(-effective_torque_limit, min(effective_torque_limit, total * effective_master_gain))

        return ForceCommand(
            constant=total,
            spring_gain=spring_gain * effective_master_gain,
            spring_center_deg=target_angle_deg,
            damper_gain=damper_gain * effective_master_gain,
            friction_gain=friction_gain * effective_master_gain,
            vibration_gain=vibration_gain * effective_master_gain,
            vibration_freq_hz=profile.vibration_freq_hz,
            impulse_torque=impulse * effective_master_gain,
            impulse_duration_ms=duration,
            debug_total=total,
        )
