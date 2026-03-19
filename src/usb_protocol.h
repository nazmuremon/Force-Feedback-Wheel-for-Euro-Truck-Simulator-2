#pragma once

#include <Arduino.h>

namespace usb_protocol {

using SendCallback = bool (*)(const uint8_t* data, size_t length);

void init(Stream& serial_port);
void init(SendCallback send_callback);
void attachSerial(Stream& serial_port);
void attachSendCallback(SendCallback send_callback);
void process();
void processBytes(const uint8_t* data, size_t length);
size_t buildStatusFrame(uint8_t sequence, uint8_t* out_buffer, size_t capacity);
void sendStatus(uint8_t sequence = 0);

}  // namespace usb_protocol
