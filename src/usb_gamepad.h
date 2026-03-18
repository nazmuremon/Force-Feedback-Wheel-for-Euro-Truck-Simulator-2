#pragma once

#include <Arduino.h>

namespace usb_gamepad {

void init();
void task();
void update(float wheel_angle_deg, float brake_norm, float accel_norm);
bool sendTransportPacket(const uint8_t* data, size_t length);

}  // namespace usb_gamepad
