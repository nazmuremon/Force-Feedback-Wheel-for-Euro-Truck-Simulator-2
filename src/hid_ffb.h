#pragma once

#include <Arduino.h>

namespace hid_ffb {

struct DeviceState {
  bool actuators_enabled;
  bool device_paused;
  uint8_t global_gain;
  uint32_t rx_reports;
  uint8_t last_report_id;
  uint8_t last_allocated_effect;
  uint8_t last_load_status;
  int16_t last_constant_magnitude;
  bool any_effect_running;
  bool first_slot_configured;
  uint8_t first_slot_type;
  uint8_t first_slot_gain;
  float debug_constant_torque;
};

void init();
size_t expectedReportLength(uint8_t report_id);
bool handleReport(uint8_t report_id, const uint8_t* data, size_t length);
uint8_t* getFeatureReport(uint8_t report_id, uint8_t report_type, uint16_t* report_length);
size_t buildPidStateReport(uint8_t* report, size_t capacity);
void update();
DeviceState getState();

}  // namespace hid_ffb
