from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable

try:
    import hid  # type: ignore[import-not-found]
    _HID_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on local hidapi runtime
    hid = None  # type: ignore[assignment]
    _HID_IMPORT_ERROR = exc

from . import protocol


def _load_hid_fallback() -> Any | None:
    search_roots = [Path(__file__).resolve().parents[2]]
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        search_roots.insert(0, bundle_root)
        search_roots.insert(0, Path(sys.executable).resolve().parent)

    candidate_names = (
        "hid.cp311-win_amd64.pyd",
        "hid.pyd",
    )
    for root in search_roots:
        for name in candidate_names:
            candidate = root / name
            if not candidate.exists():
                continue
            spec = importlib.util.spec_from_file_location("hid", candidate)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return None


if hid is None:
    fallback_module = _load_hid_fallback()
    if fallback_module is not None:
        hid = fallback_module  # type: ignore[assignment]
        _HID_IMPORT_ERROR = None


@dataclass
class HidDeviceInfo:
    path: str
    raw_path: bytes | None
    vendor_id: int
    product_id: int
    product_string: str
    manufacturer_string: str
    serial_number: str
    usage_page: int = 0
    usage: int = 0
    interface_number: int = -1

    @property
    def label(self) -> str:
        product = self.product_string or "USB HID Device"
        role = "Transport" if self.is_transport else "Other HID"
        serial = f" [{self.serial_number}]" if self.serial_number else ""
        return f"{product} - {role}{serial}"

    @property
    def is_transport(self) -> bool:
        return self.usage_page == protocol.HID_VENDOR_USAGE_PAGE and self.usage == protocol.HID_VENDOR_USAGE


class HidTransport:
    VENDOR_ID = 0x0483
    PRODUCT_ID = 0x57FF
    USE_FEATURE_TRANSPORT = True

    def __init__(self) -> None:
        self._device: Any | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._parser = protocol.PacketParser()
        self._callbacks: list[Callable[[int, int, bytes], None]] = []
        self._tx_sequence = 1
        self._latencies_ms: deque[float] = deque(maxlen=50)
        self._pending: dict[int, float] = {}
        self.log_callback: Callable[[str], None] | None = None

    @staticmethod
    def list_devices() -> list[HidDeviceInfo]:
        if hid is None:
            return []
        devices: list[HidDeviceInfo] = []
        for entry in hid.enumerate():
            vendor_id = int(entry.get("vendor_id") or 0)
            product_id = int(entry.get("product_id") or 0)
            if vendor_id != HidTransport.VENDOR_ID or product_id != HidTransport.PRODUCT_ID:
                continue
            product_string = entry.get("product_string") or ""
            raw_path = entry.get("path")
            if isinstance(raw_path, bytes):
                path = raw_path.decode("utf-8", errors="ignore")
                raw_path_bytes = raw_path
            else:
                path = str(raw_path)
                raw_path_bytes = None
            devices.append(
                HidDeviceInfo(
                    path=path,
                    raw_path=raw_path_bytes,
                    vendor_id=vendor_id,
                    product_id=product_id,
                    product_string=product_string,
                    manufacturer_string=entry.get("manufacturer_string") or "",
                    serial_number=entry.get("serial_number") or "",
                    usage_page=int(entry.get("usage_page") or 0),
                    usage=int(entry.get("usage") or 0),
                    interface_number=int(entry.get("interface_number") or -1),
                )
            )
        transport_devices = [device for device in devices if device.is_transport]
        return transport_devices or devices

    @property
    def connected(self) -> bool:
        return self._device is not None

    @property
    def latency_ms(self) -> float:
        return sum(self._latencies_ms) / len(self._latencies_ms) if self._latencies_ms else 0.0

    def add_callback(self, callback: Callable[[int, int, bytes], None]) -> None:
        self._callbacks.append(callback)

    def connect(self, path: str) -> None:
        self.disconnect()
        if hid is None:
            message = "HID support is unavailable"
            if _HID_IMPORT_ERROR is not None:
                message = f"{message}: {_HID_IMPORT_ERROR}"
            raise RuntimeError(message)
        device = hid.device()
        open_path: bytes = path.encode("utf-8")
        for entry in self.list_devices():
            if entry.path == path and entry.raw_path is not None:
                open_path = entry.raw_path
                break
        device.open_path(open_path)
        device.set_nonblocking(True)
        self._device = device
        if not self.USE_FEATURE_TRANSPORT:
            self._running = True
            self._thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._thread.start()
        self._log(f"Connected to HID device {path}")

    def disconnect(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        if self._device:
            try:
                self._device.close()
            finally:
                self._device = None
        self._pending.clear()

    def send(self, command: int, payload: bytes = b"") -> int:
        if not self.connected or self._device is None:
            raise RuntimeError("HID device not connected")
        sequence = self._tx_sequence & 0xFF
        self._tx_sequence = (self._tx_sequence + 1) & 0xFF
        if self.USE_FEATURE_TRANSPORT:
            if command == protocol.CMD_REQUEST_STATUS:
                self._poll_feature_status(sequence)
                return sequence
            report = protocol.pack_hid_feature_command_report(command, sequence, payload)
            written = self._device.send_feature_report(report)
        else:
            report = protocol.pack_hid_command_report(command, sequence, payload)
            written = self._device.write(report)
        if written <= 0:
            raise RuntimeError("failed to write HID report")
        self._pending[sequence] = time.perf_counter()
        return sequence

    def _poll_feature_status(self, sequence: int) -> None:
        if self._device is None:
            return
        report = bytes(self._device.get_feature_report(protocol.HID_REPORT_ID_STATUS_FEATURE, protocol.HID_REPORT_SIZE))
        frame = protocol.unpack_hid_transport_frame(report)
        if frame is None:
            return
        for command, response_sequence, payload in self._parser.feed(frame):
            measured_sequence = response_sequence or sequence
            if measured_sequence in self._pending:
                self._latencies_ms.append((time.perf_counter() - self._pending.pop(measured_sequence)) * 1000.0)
            for callback in self._callbacks:
                callback(command, measured_sequence, payload)

    def _reader_loop(self) -> None:
        assert self._device is not None
        while self._running and self._device is not None:
            try:
                data = self._device.read(protocol.HID_REPORT_SIZE, timeout_ms=20)
            except OSError as exc:
                self._log(f"HID error: {exc}")
                self._running = False
                break
            if not data:
                continue
            report = bytes(data)
            frame = protocol.unpack_hid_transport_frame(report)
            if frame is None:
                continue
            for command, sequence, payload in self._parser.feed(frame):
                if sequence in self._pending:
                    self._latencies_ms.append((time.perf_counter() - self._pending.pop(sequence)) * 1000.0)
                for callback in self._callbacks:
                    callback(command, sequence, payload)

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)
