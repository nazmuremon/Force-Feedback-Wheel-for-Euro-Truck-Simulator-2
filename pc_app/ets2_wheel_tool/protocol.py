from __future__ import annotations

from dataclasses import dataclass
import struct


SYNC = b"\xA5\x5A"
HID_REPORT_SIZE = 64
HID_REPORT_ID_COMMAND = 0x02
HID_REPORT_ID_STATUS = 0x03
HID_REPORT_ID_COMMAND_FEATURE = 0x04
HID_REPORT_ID_STATUS_FEATURE = 0x05
HID_VENDOR_USAGE_PAGE = 0xFF00
HID_VENDOR_USAGE = 0x01
CMD_PING = 0x01
CMD_SET_ENABLE = 0x02
CMD_SET_CONSTANT = 0x03
CMD_SET_SPRING = 0x04
CMD_SET_DAMPER = 0x05
CMD_SET_FRICTION = 0x06
CMD_SET_VIBRATION = 0x07
CMD_TRIGGER_IMPULSE = 0x08
CMD_SET_PWM_RAW = 0x09
CMD_ZERO_ENCODER = 0x0A
CMD_SET_PEDAL_CAL = 0x0B
CMD_CAPTURE_PEDAL_MIN = 0x0C
CMD_CAPTURE_PEDAL_MAX = 0x0D
CMD_SET_ESTOP = 0x0E
CMD_REQUEST_STATUS = 0x0F
CMD_CLEAR_FAULTS = 0x10
RSP_ACK = 0x80
RSP_STATUS = 0x81


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def pack_packet(command: int, sequence: int, payload: bytes = b"") -> bytes:
    header = struct.pack("<2sBBB", SYNC, len(payload), command, sequence)
    crc = crc16_ccitt(header + payload)
    return header + payload + struct.pack("<H", crc)


@dataclass
class StatusPacket:
    encoder_count: int
    wheel_angle_deg: float
    wheel_speed_deg_s: float
    brake_raw: int
    accel_raw: int
    brake_norm: float
    accel_norm: float
    motor_torque: float
    motor_pwm: int
    fault_flags: int
    command_age_ms: int
    rx_packets: int
    tx_packets: int
    version: str

    @classmethod
    def from_payload(cls, payload: bytes) -> "StatusPacket":
        if len(payload) == struct.calcsize("<iffHHfffhIIII8s"):
            values = struct.unpack("<iffHHfffhIIII8s", payload)
        else:
            values = struct.unpack("<iffHHfffhIIII12s", payload)
        return cls(
            encoder_count=values[0],
            wheel_angle_deg=values[1],
            wheel_speed_deg_s=values[2],
            brake_raw=values[3],
            accel_raw=values[4],
            brake_norm=values[5],
            accel_norm=values[6],
            motor_torque=values[7],
            motor_pwm=values[8],
            fault_flags=values[9],
            command_age_ms=values[10],
            rx_packets=values[11],
            tx_packets=values[12],
            version=values[13].split(b"\x00", 1)[0].decode("ascii", errors="ignore"),
        )


class PacketParser:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, int, bytes]]:
        self._buffer.extend(data)
        packets: list[tuple[int, int, bytes]] = []
        while len(self._buffer) >= 7:
            if self._buffer[0:2] != SYNC:
                del self._buffer[0]
                continue
            payload_len = self._buffer[2]
            frame_len = 5 + payload_len + 2
            if len(self._buffer) < frame_len:
                break
            frame = bytes(self._buffer[:frame_len])
            del self._buffer[:frame_len]
            if crc16_ccitt(frame[:-2]) != struct.unpack("<H", frame[-2:])[0]:
                continue
            packets.append((frame[3], frame[4], frame[5:-2]))
        return packets


def pack_float(value: float) -> bytes:
    return struct.pack("<f", value)


def pack_spring(gain: float, center_deg: float) -> bytes:
    return struct.pack("<ff", gain, center_deg)


def pack_vibration(gain: float, freq_hz: float) -> bytes:
    return struct.pack("<ff", gain, freq_hz)


def pack_impulse(torque: float, duration_ms: int) -> bytes:
    return struct.pack("<fH", torque, duration_ms)


def pack_pwm(value: int) -> bytes:
    return struct.pack("<h", value)


def pack_pedal_cal(channel: int, min_raw: int, max_raw: int, invert: bool) -> bytes:
    return struct.pack("<BHHB", channel, min_raw, max_raw, int(invert))


def pack_hid_command_report(command: int, sequence: int, payload: bytes = b"") -> bytes:
    packet = pack_packet(command, sequence, payload)
    if len(packet) > HID_REPORT_SIZE - 2:
        raise ValueError("packet is too large for a HID report")
    report = bytearray(HID_REPORT_SIZE)
    report[0] = HID_REPORT_ID_COMMAND
    report[1] = len(packet)
    report[2 : 2 + len(packet)] = packet
    return bytes(report)


def pack_hid_feature_command_report(command: int, sequence: int, payload: bytes = b"") -> bytes:
    packet = pack_packet(command, sequence, payload)
    if len(packet) > HID_REPORT_SIZE - 2:
        raise ValueError("packet is too large for a HID feature report")
    report = bytearray(HID_REPORT_SIZE)
    report[0] = HID_REPORT_ID_COMMAND_FEATURE
    report[1] = len(packet)
    report[2 : 2 + len(packet)] = packet
    return bytes(report)


def unpack_hid_transport_frame(report: bytes) -> bytes | None:
    if len(report) >= 2 and report[0] in (HID_REPORT_ID_STATUS, HID_REPORT_ID_STATUS_FEATURE):
        frame_len = min(report[1], len(report) - 2)
        if frame_len <= 0:
            return None
        return bytes(report[2 : 2 + frame_len])

    if len(report) >= 3 and report[1:3] == SYNC:
        frame_len = min(report[0], len(report) - 1)
        if frame_len <= 0:
            return None
        return bytes(report[1 : 1 + frame_len])

    return None
