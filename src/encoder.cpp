#include "encoder.h"

#include "app_config.h"

namespace {

volatile int32_t g_count = 0;
volatile uint8_t g_last_state = 0;
volatile uint32_t g_last_edge_us = 0;
volatile uint32_t g_edge_interval_us = 0;
volatile bool g_fault = false;
volatile int8_t g_direction = 0;
int32_t g_zero_offset = 0;
float g_speed_deg_s = 0.0f;
uint32_t g_last_motion_ms = 0;

constexpr uint32_t kMovementLedHoldMs = 120;

constexpr int8_t kTransitionTable[16] = {
    0, -1, 1, 0,
    1, 0, 0, -1,
    -1, 0, 0, 1,
    0, 1, -1, 0,
};

void handleEncoderEdge() {
  const uint8_t state =
      (static_cast<uint8_t>(digitalRead(app::kEncoderPinA)) << 1) |
      static_cast<uint8_t>(digitalRead(app::kEncoderPinB));

  const uint8_t transition = static_cast<uint8_t>((g_last_state << 2) | state);
  const int8_t delta = kTransitionTable[transition];
  const uint32_t now = micros();

  if (delta == 0 && state != g_last_state) {
    g_fault = true;
  }

  if (delta != 0) {
    g_count += delta;
    g_direction = (delta > 0) ? 1 : -1;
    g_last_motion_ms = millis();
    if (g_last_edge_us != 0U) {
      g_edge_interval_us = now - g_last_edge_us;
    }
    g_last_edge_us = now;
  }

  g_last_state = state;
}

}  // namespace

namespace encoder {

void init() {
  pinMode(app::kEncoderPinA, INPUT_PULLUP);
  pinMode(app::kEncoderPinB, INPUT_PULLUP);
  g_last_state =
      (static_cast<uint8_t>(digitalRead(app::kEncoderPinA)) << 1) |
      static_cast<uint8_t>(digitalRead(app::kEncoderPinB));
  attachInterrupt(digitalPinToInterrupt(app::kEncoderPinA), handleEncoderEdge, CHANGE);
  attachInterrupt(digitalPinToInterrupt(app::kEncoderPinB), handleEncoderEdge, CHANGE);
}

void update() {
  noInterrupts();
  const uint32_t interval_us = g_edge_interval_us;
  const uint32_t last_edge_us = g_last_edge_us;
  const int8_t direction = g_direction;
  interrupts();

  if (interval_us > 0U && (micros() - last_edge_us) < 200000U) {
    const float counts_per_second = 1000000.0f / static_cast<float>(interval_us);
    g_speed_deg_s = direction * countsToDegrees(static_cast<int32_t>(counts_per_second));
  } else {
    g_speed_deg_s *= 0.8f;
    if (fabsf(g_speed_deg_s) < 0.2f) {
      g_speed_deg_s = 0.0f;
    }
  }

  if (fabsf(g_speed_deg_s) > app::kWheelMaxSpeedDegPerSec) {
    g_fault = true;
  }
}

EncoderSnapshot getSnapshot() {
  noInterrupts();
  const int32_t raw_count = g_count;
  const bool fault = g_fault;
  const int8_t direction = g_direction;
  interrupts();

  EncoderSnapshot snapshot{};
  snapshot.count = raw_count - g_zero_offset;
  snapshot.angle_deg = countsToDegrees(snapshot.count);
  snapshot.speed_deg_s = g_speed_deg_s;
  snapshot.direction = direction;
  snapshot.fault = fault;
  return snapshot;
}

void setZeroOffset(int32_t offset_counts) { g_zero_offset = offset_counts; }

void zeroAtCurrentPosition() {
  noInterrupts();
  g_zero_offset = g_count;
  g_fault = false;
  g_edge_interval_us = 0;
  g_last_edge_us = 0;
  g_direction = 0;
  interrupts();
  g_speed_deg_s = 0.0f;
}

void clearFault() {
  noInterrupts();
  g_fault = false;
  interrupts();
}

int32_t getRawCount() {
  noInterrupts();
  const int32_t value = g_count;
  interrupts();
  return value;
}

float countsToDegrees(int32_t counts) {
  return static_cast<float>(counts) * 360.0f /
         static_cast<float>(app::kEncoderCountsPerRevolution);
}

bool isMoving() { return (millis() - g_last_motion_ms) <= kMovementLedHoldMs; }

}  // namespace encoder
