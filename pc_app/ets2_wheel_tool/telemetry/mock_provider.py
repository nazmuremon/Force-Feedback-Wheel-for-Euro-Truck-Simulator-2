from __future__ import annotations

import math
import time

from ..ffb import TelemetrySample
from .base import TelemetryProvider


class MockTelemetryProvider(TelemetryProvider):
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def read(self) -> TelemetrySample:
        t = time.perf_counter() - self._start
        cycle = t % 32.0

        if cycle < 6.0:
            speed_mps = 2.0 + 2.4 * cycle
            throttle = 0.42
            brake = 0.0
            accel_x = 0.0
        elif cycle < 14.0:
            phase = (cycle - 6.0) / 8.0
            speed_mps = 16.0 + 4.0 * math.sin(phase * math.pi)
            throttle = 0.28 + 0.06 * math.sin(phase * math.pi)
            brake = 0.0
            accel_x = 0.18 * math.sin(phase * math.pi)
        elif cycle < 21.0:
            phase = (cycle - 14.0) / 7.0
            speed_mps = 18.0 - 7.0 * phase
            throttle = 0.18
            brake = 0.12 + 0.14 * phase
            accel_x = -0.12 * math.sin(phase * math.pi)
        elif cycle < 27.0:
            phase = (cycle - 21.0) / 6.0
            speed_mps = 10.0 + 6.5 * phase
            throttle = 0.26 + 0.10 * phase
            brake = 0.0
            accel_x = -0.20 * math.sin(phase * math.pi)
        else:
            phase = (cycle - 27.0) / 5.0
            speed_mps = 16.5 - 11.0 * phase
            throttle = 0.12
            brake = 0.10 + 0.18 * phase
            accel_x = 0.10 * math.sin(phase * math.pi)

        engine_rpm = 850.0 + speed_mps * 55.0 + throttle * 420.0
        road_wave = math.sin(t * 2.1) * 0.5 + math.sin(t * 5.3) * 0.25
        suspension_bump = max(0.0, road_wave) * (0.20 + min(1.0, speed_mps / 22.0) * 0.55)
        accel_y = suspension_bump * 0.8
        accel_z = 0.04 * math.cos(t * 1.9) + suspension_bump * 0.12
        collision = 0.18 if 18.0 < cycle < 18.08 else 0.0

        return TelemetrySample(
            connected=True,
            source="virtual-test",
            speed_mps=speed_mps,
            engine_rpm=engine_rpm,
            throttle=throttle,
            brake=brake,
            steer_input=0.0,
            accel_x=accel_x,
            accel_y=accel_y,
            accel_z=accel_z,
            suspension_bump=suspension_bump,
            collision=collision,
        )
