#include "usb_protocol.h"

#include "app_config.h"
#include "control.h"
#include "pedals.h"

namespace {

Stream* g_serial = nullptr;
usb_protocol::SendCallback g_send_callback = nullptr;
uint8_t g_buffer[96];
size_t g_index = 0;
uint32_t g_rx_packets = 0;
uint32_t g_tx_packets = 0;

enum PacketCommand : uint8_t {
  CMD_PING = 0x01,
  CMD_SET_ENABLE = 0x02,
  CMD_SET_CONSTANT = 0x03,
  CMD_SET_SPRING = 0x04,
  CMD_SET_DAMPER = 0x05,
  CMD_SET_FRICTION = 0x06,
  CMD_SET_VIBRATION = 0x07,
  CMD_TRIGGER_IMPULSE = 0x08,
  CMD_SET_PWM_RAW = 0x09,
  CMD_ZERO_ENCODER = 0x0A,
  CMD_SET_PEDAL_CAL = 0x0B,
  CMD_CAPTURE_PEDAL_MIN = 0x0C,
  CMD_CAPTURE_PEDAL_MAX = 0x0D,
  CMD_SET_ESTOP = 0x0E,
  CMD_REQUEST_STATUS = 0x0F,
  CMD_CLEAR_FAULTS = 0x10,
  RSP_ACK = 0x80,
  RSP_STATUS = 0x81,
};

struct __attribute__((packed)) PacketHeader {
  uint8_t sync1;
  uint8_t sync2;
  uint8_t length;
  uint8_t command;
  uint8_t sequence;
};

struct __attribute__((packed)) StatusPayload {
  int32_t encoder_count;
  float wheel_angle_deg;
  float wheel_speed_deg_s;
  uint16_t brake_raw;
  uint16_t accel_raw;
  float brake_norm;
  float accel_norm;
  float motor_torque;
  int16_t motor_pwm;
  uint32_t fault_flags;
  uint32_t command_age_ms;
  uint32_t rx_packets;
  uint32_t tx_packets;
  char version[8];
};

uint16_t crc16_ccitt(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      if ((crc & 0x8000U) != 0U) {
        crc = static_cast<uint16_t>((crc << 1U) ^ 0x1021U);
      } else {
        crc <<= 1U;
      }
    }
  }
  return crc;
}

void sendPacket(uint8_t command, uint8_t sequence, const uint8_t* payload, uint8_t length) {
  if (g_serial == nullptr && g_send_callback == nullptr) {
    return;
  }

  PacketHeader header{0xA5, 0x5A, length, command, sequence};
  uint8_t frame[128];
  memcpy(frame, &header, sizeof(header));
  if (length > 0U) {
    memcpy(frame + sizeof(header), payload, length);
  }
  const size_t crc_offset = sizeof(header) + length;
  const uint16_t crc = crc16_ccitt(frame, crc_offset);
  frame[crc_offset] = static_cast<uint8_t>(crc & 0xFFU);
  frame[crc_offset + 1U] = static_cast<uint8_t>((crc >> 8U) & 0xFFU);
  const size_t frame_length = crc_offset + 2U;
  bool sent = false;
  if (g_send_callback != nullptr) {
    sent = g_send_callback(frame, frame_length);
  } else if (g_serial != nullptr) {
    sent = g_serial->write(frame, frame_length) == frame_length;
  }
  if (sent) {
    ++g_tx_packets;
  }
}

void sendAck(uint8_t sequence, uint8_t command) { sendPacket(RSP_ACK, sequence, &command, 1); }

template <typename T>
bool readPayload(const uint8_t* payload, uint8_t length, T& out) {
  if (length != sizeof(T)) {
    return false;
  }
  memcpy(&out, payload, sizeof(T));
  return true;
}

void handlePacket(uint8_t command, uint8_t sequence, const uint8_t* payload, uint8_t length) {
  auto& effects = control::effects();
  control::markCommandReceived();
  ++g_rx_packets;

  switch (command) {
    case CMD_PING:
      sendAck(sequence, command);
      return;
    case CMD_SET_ENABLE:
      if (length == 1U) {
        effects.motor_enabled = payload[0] != 0U;
        sendAck(sequence, command);
      }
      return;
    case CMD_SET_CONSTANT: {
      float value = 0.0f;
      if (readPayload(payload, length, value)) {
        effects.raw_pwm_override = false;
        effects.constant_torque = value;
        control::notifyMotorTestCommand();
        sendAck(sequence, command);
      }
      return;
    }
    case CMD_SET_SPRING: {
      struct __attribute__((packed)) SpringPayload {
        float gain;
        float center_deg;
      } spring{};
      if (readPayload(payload, length, spring)) {
        effects.raw_pwm_override = false;
        effects.spring_gain = spring.gain;
        effects.spring_center_deg = spring.center_deg;
        control::notifyMotorTestCommand();
        sendAck(sequence, command);
      }
      return;
    }
    case CMD_SET_DAMPER: {
      float value = 0.0f;
      if (readPayload(payload, length, value)) {
        effects.raw_pwm_override = false;
        effects.damper_gain = value;
        control::notifyMotorTestCommand();
        sendAck(sequence, command);
      }
      return;
    }
    case CMD_SET_FRICTION: {
      float value = 0.0f;
      if (readPayload(payload, length, value)) {
        effects.raw_pwm_override = false;
        effects.friction_gain = value;
        control::notifyMotorTestCommand();
        sendAck(sequence, command);
      }
      return;
    }
    case CMD_SET_VIBRATION: {
      struct __attribute__((packed)) VibrationPayload {
        float gain;
        float frequency_hz;
      } vibration{};
      if (readPayload(payload, length, vibration)) {
        effects.raw_pwm_override = false;
        effects.vibration_gain = vibration.gain;
        effects.vibration_freq_hz = vibration.frequency_hz;
        control::notifyMotorTestCommand();
        sendAck(sequence, command);
      }
      return;
    }
    case CMD_TRIGGER_IMPULSE: {
      struct __attribute__((packed)) ImpulsePayload {
        float torque;
        uint16_t duration_ms;
      } impulse{};
      if (readPayload(payload, length, impulse)) {
        effects.raw_pwm_override = false;
        control::triggerImpulse(impulse.torque, impulse.duration_ms);
        control::notifyMotorTestCommand();
        sendAck(sequence, command);
      }
      return;
    }
    case CMD_SET_PWM_RAW: {
      int16_t pwm = 0;
      if (readPayload(payload, length, pwm)) {
        effects.raw_pwm_override = true;
        effects.raw_pwm = pwm;
        control::notifyMotorTestCommand();
        sendAck(sequence, command);
      }
      return;
    }
    case CMD_ZERO_ENCODER:
      control::zeroEncoder();
      sendAck(sequence, command);
      return;
    case CMD_SET_PEDAL_CAL: {
      struct __attribute__((packed)) PedalCalPayload {
        uint8_t channel;
        uint16_t min_raw;
        uint16_t max_raw;
        uint8_t invert;
      } pedal{};
      if (readPayload(payload, length, pedal)) {
        pedals::setCalibration(pedal.channel, pedal.min_raw, pedal.max_raw, pedal.invert != 0U);
        sendAck(sequence, command);
      }
      return;
    }
    case CMD_CAPTURE_PEDAL_MIN:
      pedals::captureMinimums();
      sendAck(sequence, command);
      return;
    case CMD_CAPTURE_PEDAL_MAX:
      pedals::captureMaximums();
      sendAck(sequence, command);
      return;
    case CMD_SET_ESTOP:
      if (length == 1U) {
        effects.estop = payload[0] != 0U;
        sendAck(sequence, command);
      }
      return;
    case CMD_REQUEST_STATUS:
      usb_protocol::sendStatus(sequence);
      return;
    case CMD_CLEAR_FAULTS:
      control::clearFaults();
      sendAck(sequence, command);
      return;
    default:
      return;
  }
}

}  // namespace

namespace usb_protocol {

void init(Stream& serial_port) {
  g_serial = &serial_port;
  g_send_callback = nullptr;
}

void init(SendCallback send_callback) {
  g_serial = nullptr;
  g_send_callback = send_callback;
}

void process() {
  if (g_serial == nullptr) {
    return;
  }

  while (g_serial->available() > 0) {
    const uint8_t byte = static_cast<uint8_t>(g_serial->read());
    processBytes(&byte, 1);
  }
}

void processBytes(const uint8_t* data, size_t length) {
  for (size_t offset = 0; offset < length; ++offset) {
    const uint8_t byte = data[offset];

    if (g_index == 0U && byte != 0xA5U) {
      continue;
    }
    if (g_index == 1U && byte != 0x5AU) {
      g_index = 0U;
      continue;
    }

    g_buffer[g_index++] = byte;

    if (g_index >= sizeof(PacketHeader)) {
      const auto* header = reinterpret_cast<const PacketHeader*>(g_buffer);
      const size_t full_length = sizeof(PacketHeader) + header->length + 2U;
      if (g_index == full_length) {
        const uint16_t received_crc = static_cast<uint16_t>(g_buffer[full_length - 2U]) |
                                      (static_cast<uint16_t>(g_buffer[full_length - 1U]) << 8U);
        const uint16_t computed_crc = crc16_ccitt(g_buffer, full_length - 2U);
        if (computed_crc == received_crc) {
          handlePacket(header->command, header->sequence, g_buffer + sizeof(PacketHeader),
                       header->length);
        }
        g_index = 0U;
      } else if (full_length > sizeof(g_buffer)) {
        g_index = 0U;
      }
    }
  }
}

size_t buildStatusFrame(uint8_t sequence, uint8_t* out_buffer, size_t capacity) {
  if (out_buffer == nullptr) {
    return 0U;
  }

  const ControlSnapshot snapshot = control::getSnapshot();
  StatusPayload payload{};
  payload.encoder_count = snapshot.encoder.count;
  payload.wheel_angle_deg = snapshot.encoder.angle_deg;
  payload.wheel_speed_deg_s = snapshot.encoder.speed_deg_s;
  payload.brake_raw = snapshot.pedals.brake.raw;
  payload.accel_raw = snapshot.pedals.accel.raw;
  payload.brake_norm = snapshot.pedals.brake.normalized;
  payload.accel_norm = snapshot.pedals.accel.normalized;
  payload.motor_torque = snapshot.output_torque;
  payload.motor_pwm = static_cast<int16_t>(snapshot.motor.applied_pwm);
  payload.fault_flags = snapshot.fault_flags;
  payload.command_age_ms = snapshot.last_command_age_ms;
  payload.rx_packets = g_rx_packets;
  payload.tx_packets = g_tx_packets;
  memset(payload.version, 0, sizeof(payload.version));
  strncpy(payload.version, app::kFirmwareVersion, sizeof(payload.version) - 1U);

  const size_t payload_length = sizeof(payload);
  const size_t frame_length = sizeof(PacketHeader) + payload_length + 2U;
  if (capacity < frame_length) {
    return 0U;
  }

  PacketHeader header{0xA5, 0x5A, static_cast<uint8_t>(payload_length), RSP_STATUS, sequence};
  memcpy(out_buffer, &header, sizeof(header));
  memcpy(out_buffer + sizeof(header), &payload, payload_length);
  const uint16_t crc = crc16_ccitt(out_buffer, sizeof(header) + payload_length);
  out_buffer[sizeof(header) + payload_length] = static_cast<uint8_t>(crc & 0xFFU);
  out_buffer[sizeof(header) + payload_length + 1U] = static_cast<uint8_t>((crc >> 8U) & 0xFFU);
  return frame_length;
}

void sendStatus(uint8_t sequence) {
  uint8_t frame[128];
  const size_t frame_length = buildStatusFrame(sequence, frame, sizeof(frame));
  if (frame_length == 0U) {
    return;
  }
  sendPacket(RSP_STATUS, sequence, frame + sizeof(PacketHeader), static_cast<uint8_t>(frame_length - sizeof(PacketHeader) - 2U));
}

}  // namespace usb_protocol
