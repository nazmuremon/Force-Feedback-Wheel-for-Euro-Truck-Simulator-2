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
        return TelemetrySample(
            connected=True,
            source="virtual-test",
            speed_mps=12.0 + 8.0 * math.sin(t * 0.25),
            engine_rpm=950.0 + 400.0 * (1.0 + math.sin(t * 0.7)),
            throttle=0.4 + 0.3 * math.sin(t * 0.4),
            brake=max(0.0, 0.4 * math.sin(t * 0.17)),
            steer_input=0.3 * math.sin(t * 0.3),
            accel_x=0.2 * math.sin(t * 1.4),
            accel_y=0.55 * max(0.0, math.sin(t * 3.2)),
            accel_z=0.1 * math.cos(t * 1.7),
            suspension_bump=max(0.0, math.sin(t * 4.7)) * 0.8,
            collision=0.25 if int(t) % 23 == 0 and (t % 23.0) < 0.12 else 0.0,
        )
