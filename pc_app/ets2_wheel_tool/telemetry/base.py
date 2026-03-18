from __future__ import annotations

from abc import ABC, abstractmethod

from ..ffb import TelemetrySample


class TelemetryProvider(ABC):
    @abstractmethod
    def read(self) -> TelemetrySample:
        raise NotImplementedError
