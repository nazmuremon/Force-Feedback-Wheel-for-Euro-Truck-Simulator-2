#pragma once

#include <Arduino.h>

struct EncoderSnapshot {
  int32_t count;
  float angle_deg;
  float speed_deg_s;
  int8_t direction;
  bool fault;
};

namespace encoder {

void init();
void update();
EncoderSnapshot getSnapshot();
void setZeroOffset(int32_t offset_counts);
void zeroAtCurrentPosition();
void clearFault();
int32_t getRawCount();
float countsToDegrees(int32_t counts);
bool isMoving();

}  // namespace encoder
