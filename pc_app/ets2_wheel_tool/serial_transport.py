from __future__ import annotations

from collections import deque
import threading
import time
from typing import Callable

import serial
import serial.tools.list_ports

from . import protocol


class SerialTransport:
    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._parser = protocol.PacketParser()
        self._callbacks: list[Callable[[int, int, bytes], None]] = []
        self._tx_sequence = 1
        self._latencies_ms: deque[float] = deque(maxlen=50)
        self._pending: dict[int, float] = {}
        self.log_callback: Callable[[str], None] | None = None

    @staticmethod
    def list_ports() -> list[str]:
        return [port.device for port in serial.tools.list_ports.comports()]

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def latency_ms(self) -> float:
        return sum(self._latencies_ms) / len(self._latencies_ms) if self._latencies_ms else 0.0

    def add_callback(self, callback: Callable[[int, int, bytes], None]) -> None:
        self._callbacks.append(callback)

    def connect(self, port: str, baudrate: int = 115200) -> None:
        self.disconnect()
        self._serial = serial.Serial(port, baudrate=baudrate, timeout=0.02)
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()
        self._log(f"Connected to {port} at {baudrate} baud")

    def disconnect(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        if self._serial:
            try:
                self._serial.close()
            finally:
                self._serial = None
        self._pending.clear()

    def send(self, command: int, payload: bytes = b"") -> int:
        if not self.connected or self._serial is None:
            raise RuntimeError("Serial port not connected")
        sequence = self._tx_sequence & 0xFF
        self._tx_sequence = (self._tx_sequence + 1) & 0xFF
        self._serial.write(protocol.pack_packet(command, sequence, payload))
        self._pending[sequence] = time.perf_counter()
        return sequence

    def _reader_loop(self) -> None:
        assert self._serial is not None
        while self._running and self._serial is not None:
            try:
                data = self._serial.read(256)
            except serial.SerialException as exc:
                self._log(f"Serial error: {exc}")
                self._running = False
                break
            if not data:
                continue
            for command, sequence, payload in self._parser.feed(data):
                if sequence in self._pending:
                    self._latencies_ms.append((time.perf_counter() - self._pending.pop(sequence)) * 1000.0)
                for callback in self._callbacks:
                    callback(command, sequence, payload)

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)
