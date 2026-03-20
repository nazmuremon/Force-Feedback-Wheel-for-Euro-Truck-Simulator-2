#pragma once

#include <Arduino.h>

struct ControlSnapshot;

namespace usb_gamepad {

void init();
void task();
void update(const ControlSnapshot& snapshot);
bool sendTransportPacket(const uint8_t* data, size_t length);

}  // namespace usb_gamepad
