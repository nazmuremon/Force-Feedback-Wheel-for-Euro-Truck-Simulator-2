#include "pedals.h"

#include "app_config.h"

namespace {

struct PedalRuntime {
  app::PinId pin;
  uint16_t raw;
  float filtered;
  float normalized;
  uint16_t min_raw;
  uint16_t max_raw;
  bool inverted;
};

PedalRuntime g_brake{app::kBrakeAdcPin, 0, 0.0f, 0.0f, 300, 3800, app::kBrakeInvertDefault};
PedalRuntime g_accel{app::kAccelAdcPin, 0, 0.0f, 0.0f, 300, 3800, app::kAccelInvertDefault};

constexpr float kAdcMax = 4095.0f;

float normalize(const PedalRuntime& pedal) {
  const float span = static_cast<float>(max<uint16_t>(1, pedal.max_raw - pedal.min_raw));
  float value = (pedal.filtered - static_cast<float>(pedal.min_raw)) / span;
  value = constrain(value, 0.0f, 1.0f);
  return pedal.inverted ? (1.0f - value) : value;
}

void updatePedal(PedalRuntime& pedal) {
  if (app::kSimulatePedals) {
  const float normalized = (&pedal == &g_brake) ? app::kSimulatedBrakeNormalized : app::kSimulatedAccelNormalized;
  const float clamped = constrain(normalized, 0.0f, 1.0f);
  pedal.normalized = clamped;
  pedal.filtered = clamped * kAdcMax;
  pedal.raw = static_cast<uint16_t>(pedal.filtered);
  } else {
  pedal.raw = analogRead(pedal.pin);
  pedal.filtered += (static_cast<float>(pedal.raw) - pedal.filtered) * 0.15f;
  pedal.normalized = normalize(pedal);
  }
}

PedalChannelStatus toStatus(const PedalRuntime& pedal) {
  PedalChannelStatus status{};
  status.raw = pedal.raw;
  status.filtered = pedal.filtered;
  status.normalized = pedal.normalized;
  status.min_raw = pedal.min_raw;
  status.max_raw = pedal.max_raw;
  status.inverted = pedal.inverted;
  return status;
}

PedalRuntime& getChannel(uint8_t channel) {
  return (channel == 0) ? g_brake : g_accel;
}

}  // namespace

namespace pedals {

void init() {
  analogReadResolution(12);
  pinMode(app::kBrakeAdcPin, INPUT_ANALOG);
  pinMode(app::kAccelAdcPin, INPUT_ANALOG);
}

void update() {
  updatePedal(g_brake);
  updatePedal(g_accel);
}

PedalsSnapshot getSnapshot() {
  PedalsSnapshot snapshot{};
  snapshot.brake = toStatus(g_brake);
  snapshot.accel = toStatus(g_accel);
  return snapshot;
}

void setCalibration(uint8_t channel, uint16_t min_raw, uint16_t max_raw, bool inverted) {
  PedalRuntime& pedal = getChannel(channel);
  pedal.min_raw = min(min_raw, max_raw);
  pedal.max_raw = max(min_raw, max_raw);
  pedal.inverted = inverted;
}

void captureMinimums() {
  g_brake.min_raw = g_brake.raw;
  g_accel.min_raw = g_accel.raw;
}

void captureMaximums() {
  g_brake.max_raw = g_brake.raw;
  g_accel.max_raw = g_accel.raw;
}

}  // namespace pedals
