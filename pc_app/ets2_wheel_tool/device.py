from __future__ import annotations

from dataclasses import dataclass
import math
import time

from PySide6.QtCore import QObject, Signal

from . import protocol
from .ffb import ForceCommand
from .hid_transport import HidDeviceInfo, HidTransport


@dataclass
class DeviceState:
    connected: bool = False
    path: str = ""
    version: str = ""
    encoder_count: int = 0
    wheel_angle_deg: float = 0.0
    wheel_speed_deg_s: float = 0.0
    brake_raw: int = 0
    accel_raw: int = 0
    brake_norm: float = 0.0
    accel_norm: float = 0.0
    motor_torque: float = 0.0
    motor_pwm: int = 0
    fault_flags: int = 0
    command_age_ms: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    latency_ms: float = 0.0


class DeviceManager(QObject):
    state_changed = Signal(object)
    log_message = Signal(str)

    _FORCE_INTERVAL_S = 1.0 / 50.0
    _STATUS_INTERVAL_S = 1.0 / 12.0
    _FLOAT_EPSILON = 0.01
    _CENTER_EPSILON_DEG = 0.5
    _VIBRATION_FREQ_EPSILON_HZ = 0.5

    def __init__(self) -> None:
        super().__init__()
        self.transport = HidTransport()
        self.transport.add_callback(self._handle_packet)
        self.transport.log_callback = lambda msg: self.log_message.emit(msg)
        self.state = DeviceState()
        self._last_status_request_at = 0.0
        self._last_force_send_at = 0.0
        self._last_force_command = ForceCommand(
            constant=0.0,
            spring_gain=0.0,
            spring_center_deg=0.0,
            damper_gain=0.0,
            friction_gain=0.0,
            vibration_gain=0.0,
            vibration_freq_hz=0.0,
            impulse_torque=0.0,
            impulse_duration_ms=0,
            debug_total=0.0,
        )

    def devices(self) -> list[HidDeviceInfo]:
        return self.transport.list_devices()

    def connect_path(self, path: str) -> None:
        self.transport.connect(path)
        self.state.connected = False
        self.state.path = path
        self.request_status()
        self.log_message.emit("Transport opened, waiting for controller status...")
        self.state_changed.emit(self.state)

    def disconnect(self) -> None:
        self.transport.disconnect()
        self.state = DeviceState()
        self._last_status_request_at = 0.0
        self._last_force_send_at = 0.0
        self._reset_force_cache()
        self.state_changed.emit(self.state)

    def request_status(self) -> None:
        if not self.transport.connected:
            return
        now = time.perf_counter()
        if (now - self._last_status_request_at) < self._STATUS_INTERVAL_S:
            return
        # HID feature-report status polling does not touch the firmware command timer,
        # so keep a lightweight ping flowing while the app is connected.
        self.transport.send(protocol.CMD_PING)
        self.transport.send(protocol.CMD_REQUEST_STATUS)
        self._last_status_request_at = now

    def set_motor_enabled(self, enabled: bool) -> None:
        self.transport.send(protocol.CMD_SET_ENABLE, bytes([1 if enabled else 0]))

    def set_estop(self, enabled: bool) -> None:
        self.transport.send(protocol.CMD_SET_ESTOP, bytes([1 if enabled else 0]))

    def clear_faults(self) -> None:
        self.transport.send(protocol.CMD_CLEAR_FAULTS)

    def zero_encoder(self) -> None:
        self.transport.send(protocol.CMD_ZERO_ENCODER)

    def set_constant_torque(self, torque: float) -> None:
        self.transport.send(protocol.CMD_SET_CONSTANT, protocol.pack_float(torque))

    def set_pwm_raw(self, pwm: int) -> None:
        self.transport.send(protocol.CMD_SET_PWM_RAW, protocol.pack_pwm(pwm))

    def set_spring(self, gain: float, center_deg: float) -> None:
        self.transport.send(protocol.CMD_SET_SPRING, protocol.pack_spring(gain, center_deg))

    def set_damper(self, gain: float) -> None:
        self.transport.send(protocol.CMD_SET_DAMPER, protocol.pack_float(gain))

    def set_friction(self, gain: float) -> None:
        self.transport.send(protocol.CMD_SET_FRICTION, protocol.pack_float(gain))

    def set_vibration(self, gain: float, freq_hz: float) -> None:
        self.transport.send(protocol.CMD_SET_VIBRATION, protocol.pack_vibration(gain, freq_hz))

    def trigger_impulse(self, torque: float, duration_ms: int) -> None:
        self.transport.send(protocol.CMD_TRIGGER_IMPULSE, protocol.pack_impulse(torque, duration_ms))

    def capture_pedal_min(self) -> None:
        self.transport.send(protocol.CMD_CAPTURE_PEDAL_MIN)

    def capture_pedal_max(self) -> None:
        self.transport.send(protocol.CMD_CAPTURE_PEDAL_MAX)

    def set_pedal_cal(self, channel: int, min_raw: int, max_raw: int, invert: bool) -> None:
        self.transport.send(protocol.CMD_SET_PEDAL_CAL, protocol.pack_pedal_cal(channel, min_raw, max_raw, invert))

    def apply_force_command(self, command: ForceCommand) -> None:
        if not self.transport.connected:
            return
        now = time.perf_counter()
        if (now - self._last_force_send_at) < self._FORCE_INTERVAL_S:
            return
        if self._float_changed(command.constant, self._last_force_command.constant):
            self.set_constant_torque(command.constant)
        if (
            self._float_changed(command.spring_gain, self._last_force_command.spring_gain)
            or self._float_changed(command.spring_center_deg, self._last_force_command.spring_center_deg, self._CENTER_EPSILON_DEG)
        ):
            self.set_spring(command.spring_gain, command.spring_center_deg)
        if self._float_changed(command.damper_gain, self._last_force_command.damper_gain):
            self.set_damper(command.damper_gain)
        if self._float_changed(command.friction_gain, self._last_force_command.friction_gain):
            self.set_friction(command.friction_gain)
        if (
            self._float_changed(command.vibration_gain, self._last_force_command.vibration_gain)
            or self._float_changed(
                command.vibration_freq_hz,
                self._last_force_command.vibration_freq_hz,
                self._VIBRATION_FREQ_EPSILON_HZ,
            )
        ):
            self.set_vibration(command.vibration_gain, command.vibration_freq_hz)
        if abs(command.impulse_torque) > self._FLOAT_EPSILON:
            self.trigger_impulse(command.impulse_torque, command.impulse_duration_ms)
        self._last_force_send_at = now
        self._last_force_command = ForceCommand(
            constant=command.constant,
            spring_gain=command.spring_gain,
            spring_center_deg=command.spring_center_deg,
            damper_gain=command.damper_gain,
            friction_gain=command.friction_gain,
            vibration_gain=command.vibration_gain,
            vibration_freq_hz=command.vibration_freq_hz,
            impulse_torque=0.0,
            impulse_duration_ms=0,
            debug_total=command.debug_total,
        )

    def _handle_packet(self, command: int, sequence: int, payload: bytes) -> None:
        if command == protocol.RSP_STATUS:
            status = protocol.StatusPacket.from_payload(payload)
            self.state.connected = True
            self.state.version = status.version
            self.state.encoder_count = status.encoder_count
            self.state.wheel_angle_deg = status.wheel_angle_deg
            self.state.wheel_speed_deg_s = status.wheel_speed_deg_s
            self.state.brake_raw = status.brake_raw
            self.state.accel_raw = status.accel_raw
            self.state.brake_norm = status.brake_norm
            self.state.accel_norm = status.accel_norm
            self.state.motor_torque = status.motor_torque
            self.state.motor_pwm = status.motor_pwm
            self.state.fault_flags = status.fault_flags
            self.state.command_age_ms = status.command_age_ms
            self.state.rx_packets = status.rx_packets
            self.state.tx_packets = status.tx_packets
            self.state.latency_ms = self.transport.latency_ms
            self.state_changed.emit(self.state)
        elif command == protocol.RSP_ACK:
            self.log_message.emit(f"ACK for command 0x{payload[0]:02X}")

    @classmethod
    def _float_changed(cls, current: float, previous: float, epsilon: float | None = None) -> bool:
        threshold = cls._FLOAT_EPSILON if epsilon is None else epsilon
        return math.fabs(current - previous) >= threshold

    def _reset_force_cache(self) -> None:
        self._last_force_command = ForceCommand(
            constant=0.0,
            spring_gain=0.0,
            spring_center_deg=0.0,
            damper_gain=0.0,
            friction_gain=0.0,
            vibration_gain=0.0,
            vibration_freq_hz=0.0,
            impulse_torque=0.0,
            impulse_duration_ms=0,
            debug_total=0.0,
        )
