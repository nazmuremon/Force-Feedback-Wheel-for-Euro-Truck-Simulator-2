#pragma once

#include <Arduino.h>

struct PedalChannelStatus {
  uint16_t raw;
  float filtered;
  float normalized;
  uint16_t min_raw;
  uint16_t max_raw;
  bool inverted;
};

struct PedalsSnapshot {
  PedalChannelStatus brake;
  PedalChannelStatus accel;
};

namespace pedals {

void init();
void update();
PedalsSnapshot getSnapshot();
void setCalibration(uint8_t channel, uint16_t min_raw, uint16_t max_raw, bool inverted);
void captureMinimums();
void captureMaximums();

}  // namespace pedals
