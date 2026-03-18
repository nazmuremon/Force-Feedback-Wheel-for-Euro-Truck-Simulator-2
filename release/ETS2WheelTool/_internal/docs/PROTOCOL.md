# STM32 Controller Protocol

The controller packet format is shared by both supported transports in this repo:

- native USB HID transport in the standard `nucleo_g431kb_usb_gamepad` build
- USB CDC serial transport in the legacy `nucleo_g431kb` build

In both cases the PC computes effects, and the STM32 acts as the motor-and-sensor controller.

## Frame format

Each packet uses little-endian encoding.

```text
+--------+--------+--------+---------+----------+-----------+-----------+
| 0xA5   | 0x5A   | LEN    | CMD     | SEQ      | PAYLOAD   | CRC16     |
+--------+--------+--------+---------+----------+-----------+-----------+
| 1 byte | 1 byte | 1 byte | 1 byte  | 1 byte   | LEN bytes | 2 bytes   |
```

## Commands

| Code | Name | Payload |
|---|---|---|
| `0x01` | `CMD_PING` | none |
| `0x02` | `CMD_SET_ENABLE` | `uint8 enabled` |
| `0x03` | `CMD_SET_CONSTANT` | `float torque` |
| `0x04` | `CMD_SET_SPRING` | `float gain, float center_deg` |
| `0x05` | `CMD_SET_DAMPER` | `float gain` |
| `0x06` | `CMD_SET_FRICTION` | `float gain` |
| `0x07` | `CMD_SET_VIBRATION` | `float gain, float freq_hz` |
| `0x08` | `CMD_TRIGGER_IMPULSE` | `float torque, uint16 duration_ms` |
| `0x09` | `CMD_SET_PWM_RAW` | `int16 pwm` |
| `0x0A` | `CMD_ZERO_ENCODER` | none |
| `0x0B` | `CMD_SET_PEDAL_CAL` | `uint8 channel, uint16 min, uint16 max, uint8 invert` |
| `0x0C` | `CMD_CAPTURE_PEDAL_MIN` | none |
| `0x0D` | `CMD_CAPTURE_PEDAL_MAX` | none |
| `0x0E` | `CMD_SET_ESTOP` | `uint8 enabled` |
| `0x0F` | `CMD_REQUEST_STATUS` | none |
| `0x10` | `CMD_CLEAR_FAULTS` | none |

## Responses

| Code | Name | Payload |
|---|---|---|
| `0x80` | `RSP_ACK` | `uint8 command` |
| `0x81` | `RSP_STATUS` | packed status structure |

`RSP_STATUS` payload:

```c
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
```

## Fault flags

| Bit | Meaning |
|---|---|
| `0` | PC communication timeout |
| `1` | Encoder fault |
| `2` | Emergency stop active |
| `3` | Motor disabled |
| `4` | Software end-stop active |
