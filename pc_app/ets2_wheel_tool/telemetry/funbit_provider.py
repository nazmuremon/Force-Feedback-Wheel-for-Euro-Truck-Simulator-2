from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import urlopen

from ..ffb import TelemetrySample
from .base import TelemetryProvider


class FunbitTelemetryProvider(TelemetryProvider):
    def __init__(self) -> None:
        self._urls = (
            "http://127.0.0.1:25555/api/ets2/telemetry",
            "http://127.0.0.1:25555/api/telemetry",
        )
        self.endpoint_label = "127.0.0.1:25555"

    def read(self) -> TelemetrySample:
        payload: dict | None = None
        for url in self._urls:
            try:
                with urlopen(url, timeout=0.15) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
            except (URLError, TimeoutError, ValueError):
                continue

        if not payload:
            return TelemetrySample(connected=False, source=f"ets2-http offline ({self.endpoint_label})")

        truck = payload.get("truck", {})
        game = payload.get("game", {})
        navigation = payload.get("navigation", {})
        acc = truck.get("acceleration", {})

        return TelemetrySample(
            connected=bool(game.get("connected", True)),
            source=f"ets2-http live ({self.endpoint_label})",
            speed_mps=float(truck.get("speed", 0.0)),
            engine_rpm=float(truck.get("engineRpm", truck.get("engineRPM", 0.0))),
            throttle=float(truck.get("userThrottle", truck.get("gameThrottle", 0.0))),
            brake=float(truck.get("userBrake", truck.get("gameBrake", 0.0))),
            steer_input=float(truck.get("gameSteer", 0.0)),
            accel_x=float(acc.get("x", 0.0)) if isinstance(acc, dict) else 0.0,
            accel_y=float(acc.get("y", 0.0)) if isinstance(acc, dict) else 0.0,
            accel_z=float(acc.get("z", 0.0)) if isinstance(acc, dict) else 0.0,
            suspension_bump=abs(float(navigation.get("speedLimit", 0.0))) * 0.0,
            collision=float(truck.get("wearEngine", 0.0)) * 0.0,
        )
