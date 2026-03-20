#include <Arduino.h>

#include "app_config.h"
#include "control.h"
#include "encoder.h"
#include "hid_ffb.h"
#include "motor.h"
#include "pedals.h"
#include "usb_gamepad.h"
#include "usb_protocol.h"

namespace {

uint32_t g_last_fast_us = 0;
uint32_t g_last_control_us = 0;
uint32_t g_last_status_ms = 0;
bool g_fault_led_state = false;

}  // namespace

void setup() {
  pinMode(app::kStatusLedPin, OUTPUT);
  digitalWrite(app::kStatusLedPin, LOW);

  if (!app::kNativeUsbGamepadMode) {
    Serial.begin(app::kUsbBaudRate);
    while (!Serial && millis() < 2000U) {
      delay(10);
    }
  }

  encoder::init();
  pedals::init();
  motor::init();
  control::init();
  hid_ffb::init();
  encoder::zeroAtCurrentPosition();

  if (app::kNativeUsbGamepadMode) {
    usb_gamepad::init();
    usb_protocol::init(usb_gamepad::sendTransportPacket);
  } else {
    usb_protocol::init(Serial);
  }
}

void loop() {
  pedals::update();

  const uint32_t now_us = micros();
  const uint32_t fast_period_us = 1000000UL / app::kFastLoopHz;
  const uint32_t control_period_us = 1000000UL / app::kControlLoopHz;

  if (!app::kNativeUsbGamepadMode) {
    usb_protocol::process();
  }

  if (now_us - g_last_fast_us >= fast_period_us) {
    g_last_fast_us = now_us;
    control::updateFast();
  }

  if (now_us - g_last_control_us >= control_period_us) {
    g_last_control_us = now_us;
    hid_ffb::update();
    control::updateControl();
    const ControlSnapshot snapshot = control::getSnapshot();
    if (control::isMotorTestActive()) {
      digitalWrite(app::kStatusLedPin, HIGH);
      g_fault_led_state = false;
    } else if (snapshot.fault_flags == FAULT_NONE) {
      digitalWrite(app::kStatusLedPin, encoder::isMoving() ? HIGH : LOW);
      g_fault_led_state = false;
    } else {
      g_fault_led_state = !g_fault_led_state;
      digitalWrite(app::kStatusLedPin, g_fault_led_state ? HIGH : LOW);
    }
  }

  if (app::kNativeUsbGamepadMode) {
    const ControlSnapshot snapshot = control::getSnapshot();
    usb_gamepad::update(snapshot);
  }

  const uint32_t now_ms = millis();
  if (!app::kNativeUsbGamepadMode && now_ms - g_last_status_ms >= (1000UL / app::kStatusLoopHz)) {
    g_last_status_ms = now_ms;
    usb_protocol::sendStatus();
  }
}
