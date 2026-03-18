from __future__ import annotations

import ctypes
import json
import mmap
from urllib.error import URLError
from urllib.request import urlopen

from ..ffb import TelemetrySample
from .base import TelemetryProvider


class _TelemetryStruct(ctypes.Structure):
    _fields_ = [
        ("time", ctypes.c_uint32),
        ("paused", ctypes.c_uint32),
        ("ets2_telemetry_plugin_revision", ctypes.c_uint32),
        ("ets2_version_major", ctypes.c_uint32),
        ("ets2_version_minor", ctypes.c_uint32),
        ("padding1", ctypes.c_uint8),
        ("trailer_attached", ctypes.c_uint8),
        ("padding2", ctypes.c_uint8),
        ("padding3", ctypes.c_uint8),
        ("speed", ctypes.c_float),
        ("accelerationX", ctypes.c_float),
        ("accelerationY", ctypes.c_float),
        ("accelerationZ", ctypes.c_float),
        ("coordinateX", ctypes.c_float),
        ("coordinateY", ctypes.c_float),
        ("coordinateZ", ctypes.c_float),
        ("rotationX", ctypes.c_float),
        ("rotationY", ctypes.c_float),
        ("rotationZ", ctypes.c_float),
        ("gear", ctypes.c_int32),
        ("gearsForward", ctypes.c_int32),
        ("gearRanges", ctypes.c_int32),
        ("gearRangeActive", ctypes.c_int32),
        ("engineRpm", ctypes.c_float),
        ("engineRpmMax", ctypes.c_float),
        ("fuel", ctypes.c_float),
        ("fuelCapacity", ctypes.c_float),
        ("fuelRate", ctypes.c_float),
        ("fuelAvgConsumption", ctypes.c_float),
        ("userSteer", ctypes.c_float),
        ("userThrottle", ctypes.c_float),
        ("userBrake", ctypes.c_float),
        ("userClutch", ctypes.c_float),
        ("gameSteer", ctypes.c_float),
        ("gameThrottle", ctypes.c_float),
        ("gameBrake", ctypes.c_float),
        ("gameClutch", ctypes.c_float),
        ("truckWeight", ctypes.c_float),
        ("trailerWeight", ctypes.c_float),
        ("modelOffset", ctypes.c_int32),
        ("modelLength", ctypes.c_int32),
        ("trailerOffset", ctypes.c_int32),
        ("trailerLength", ctypes.c_int32),
        ("timeAbsolute", ctypes.c_int32),
        ("gearsReverse", ctypes.c_int32),
        ("trailerMass", ctypes.c_float),
        ("trailerId", ctypes.c_uint8 * 64),
        ("trailerName", ctypes.c_uint8 * 64),
        ("jobIncome", ctypes.c_int32),
        ("jobDeadline", ctypes.c_int32),
        ("jobCitySource", ctypes.c_uint8 * 64),
        ("jobCityDestination", ctypes.c_uint8 * 64),
        ("jobCompanySource", ctypes.c_uint8 * 64),
        ("jobCompanyDestination", ctypes.c_uint8 * 64),
        ("retarderBrake", ctypes.c_int32),
        ("shifterSlot", ctypes.c_int32),
        ("shifterToggle", ctypes.c_int32),
        ("padding4", ctypes.c_int32),
        ("cruiseControl", ctypes.c_uint8),
        ("wipers", ctypes.c_uint8),
        ("parkBrake", ctypes.c_uint8),
        ("motorBrake", ctypes.c_uint8),
        ("electricEnabled", ctypes.c_uint8),
        ("engineEnabled", ctypes.c_uint8),
        ("blinkerLeftActive", ctypes.c_uint8),
        ("blinkerRightActive", ctypes.c_uint8),
        ("blinkerLeftOn", ctypes.c_uint8),
        ("blinkerRightOn", ctypes.c_uint8),
        ("lightsParking", ctypes.c_uint8),
        ("lightsBeamLow", ctypes.c_uint8),
        ("lightsBeamHigh", ctypes.c_uint8),
        ("lightsAuxFront", ctypes.c_uint32),
        ("lightsAuxRoof", ctypes.c_uint32),
        ("lightsBeacon", ctypes.c_uint8),
        ("lightsBrake", ctypes.c_uint8),
        ("lightsReverse", ctypes.c_uint8),
        ("batteryVoltageWarning", ctypes.c_uint8),
        ("airPressureWarning", ctypes.c_uint8),
        ("airPressureEmergency", ctypes.c_uint8),
        ("adblueWarning", ctypes.c_uint8),
        ("oilPressureWarning", ctypes.c_uint8),
        ("waterTemperatureWarning", ctypes.c_uint8),
        ("airPressure", ctypes.c_float),
        ("brakeTemperature", ctypes.c_float),
        ("fuelWarning", ctypes.c_int32),
        ("adblue", ctypes.c_float),
        ("adblueConsumption", ctypes.c_float),
        ("oilPressure", ctypes.c_float),
        ("oilTemperature", ctypes.c_float),
        ("waterTemperature", ctypes.c_float),
        ("batteryVoltage", ctypes.c_float),
        ("lightsDashboard", ctypes.c_float),
        ("wearEngine", ctypes.c_float),
        ("wearTransmission", ctypes.c_float),
        ("wearCabin", ctypes.c_float),
        ("wearChassis", ctypes.c_float),
        ("wearWheels", ctypes.c_float),
        ("wearTrailer", ctypes.c_float),
        ("truckOdometer", ctypes.c_float),
        ("cruiseControlSpeed", ctypes.c_float),
        ("truckMake", ctypes.c_uint8 * 64),
        ("truckMakeId", ctypes.c_uint8 * 64),
        ("truckModel", ctypes.c_uint8 * 64),
        ("fuelWarningFactor", ctypes.c_float),
        ("adblueCapacity", ctypes.c_float),
        ("airPressureWarningValue", ctypes.c_float),
        ("airPressureEmergencyValue", ctypes.c_float),
        ("oilPressureWarningValue", ctypes.c_float),
        ("waterTemperatureWarningValue", ctypes.c_float),
        ("batteryVoltageWarningValue", ctypes.c_float),
        ("retarderStepCount", ctypes.c_uint32),
        ("cabinPositionX", ctypes.c_float),
        ("cabinPositionY", ctypes.c_float),
        ("cabinPositionZ", ctypes.c_float),
        ("headPositionX", ctypes.c_float),
        ("headPositionY", ctypes.c_float),
        ("headPositionZ", ctypes.c_float),
        ("hookPositionX", ctypes.c_float),
        ("hookPositionY", ctypes.c_float),
        ("hookPositionZ", ctypes.c_float),
        ("shifterType", ctypes.c_uint8 * 16),
        ("localScale", ctypes.c_float),
        ("nextRestStop", ctypes.c_int32),
        ("trailerCoordinateX", ctypes.c_float),
        ("trailerCoordinateY", ctypes.c_float),
        ("trailerCoordinateZ", ctypes.c_float),
        ("trailerRotationX", ctypes.c_float),
        ("trailerRotationY", ctypes.c_float),
        ("trailerRotationZ", ctypes.c_float),
        ("displayedGear", ctypes.c_int32),
        ("navigationDistance", ctypes.c_float),
        ("navigationTime", ctypes.c_float),
        ("navigationSpeedLimit", ctypes.c_float),
    ]


class FunbitTelemetryProvider(TelemetryProvider):
    def __init__(self) -> None:
        self._map_name = "Local\\Ets2TelemetryServer"
        self._urls = (
            "http://127.0.0.1:25555/api/ets2/telemetry",
            "http://127.0.0.1:25555/api/telemetry",
        )
        self.endpoint_label = "127.0.0.1:25555"

    def read(self) -> TelemetrySample:
        shared_sample = self._read_shared_memory()
        if shared_sample is not None:
            return shared_sample

        payload: dict | None = None
        for url in self._urls:
            try:
                with urlopen(url, timeout=0.15) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
            except (URLError, TimeoutError, ValueError):
                continue

        if not payload:
            return TelemetrySample(
                connected=False,
                source=f"ets2-plugin offline / ets2-http offline ({self.endpoint_label})",
            )

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

    def _read_shared_memory(self) -> TelemetrySample | None:
        mapping = ctypes.windll.kernel32.OpenFileMappingW(0x0004, False, self._map_name)
        if not mapping:
            return None
        ctypes.windll.kernel32.CloseHandle(mapping)

        try:
            with mmap.mmap(-1, ctypes.sizeof(_TelemetryStruct), tagname=self._map_name, access=mmap.ACCESS_READ) as shared:
                data = _TelemetryStruct.from_buffer_copy(shared.read(ctypes.sizeof(_TelemetryStruct)))
        except (FileNotFoundError, OSError, ValueError):
            return None

        connected = bool(data.time or data.engineRpm or data.speed or data.userThrottle or data.userBrake)
        return TelemetrySample(
            connected=connected,
            source="ets2-plugin shared-memory",
            speed_mps=float(data.speed),
            engine_rpm=float(data.engineRpm),
            throttle=float(data.userThrottle if data.userThrottle else data.gameThrottle),
            brake=float(data.userBrake if data.userBrake else data.gameBrake),
            steer_input=float(data.gameSteer),
            accel_x=float(data.accelerationX),
            accel_y=float(data.accelerationY),
            accel_z=float(data.accelerationZ),
            suspension_bump=abs(float(data.navigationSpeedLimit)) * 0.0,
            collision=float(data.wearEngine) * 0.0,
        )
