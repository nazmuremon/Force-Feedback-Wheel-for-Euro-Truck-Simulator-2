#include "control.h"

#include "app_config.h"

namespace {

ControlEffects g_effects{};
HostFfbOverlay g_host_ffb{};
uint32_t g_last_command_ms = 0;
uint32_t g_last_motor_test_ms = 0;
uint32_t g_fault_flags = FAULT_MOTOR_DISABLED;
float g_output_torque = 0.0f;
float g_filtered_torque = 0.0f;
uint32_t g_start_ms = 0;

float clampSigned(float value, float limit) {
  return constrain(value, -limit, limit);
}

}  // namespace

namespace control {

void init() {
  g_effects.motor_enabled = false;
  g_effects.estop = false;
  g_effects.raw_pwm_override = false;
  g_effects.max_torque_limit = app::kTorqueCommandLimit;
  g_effects.raw_pwm = 0;
  g_last_command_ms = millis();
  g_last_motor_test_ms = 0;
  g_start_ms = millis();
  g_host_ffb = HostFfbOverlay{};
}

void markCommandReceived() { g_last_command_ms = millis(); }

void updateFast() { encoder::update(); }

void updateControl() {
  const EncoderSnapshot enc = encoder::getSnapshot();
  const uint32_t now = millis();

  g_fault_flags = FAULT_NONE;
  if (enc.fault) {
    g_fault_flags |= FAULT_ENCODER;
  }
  if (g_effects.estop) {
    g_fault_flags |= FAULT_ESTOP;
  }
  if (!g_effects.motor_enabled) {
    g_fault_flags |= FAULT_MOTOR_DISABLED;
  }
  if ((now - g_last_command_ms) > app::kCommTimeoutMs) {
    g_fault_flags |= FAULT_COMM_TIMEOUT;
  }

  float torque = 0.0f;
  torque += g_effects.constant_torque;

  if (g_host_ffb.active) {
    torque += g_host_ffb.constant_torque;
  }

  const float spring_center_deg = g_host_ffb.active ? g_host_ffb.spring_center_deg : g_effects.spring_center_deg;
  const float spring_gain =
      max(constrain(g_effects.spring_gain, 0.0f, app::kSpringMax),
          g_host_ffb.active ? constrain(g_host_ffb.spring_gain, 0.0f, app::kSpringMax) : 0.0f);
  const float spring_error_deg = spring_center_deg - enc.angle_deg;
  torque += spring_gain * (spring_error_deg / (app::kWheelRangeDeg * 0.5f));

  const float damper_gain =
      max(constrain(g_effects.damper_gain, 0.0f, app::kDamperMax),
          g_host_ffb.active ? constrain(g_host_ffb.damper_gain, 0.0f, app::kDamperMax) : 0.0f);
  torque += damper_gain * (-enc.speed_deg_s / 720.0f);

  if (fabsf(enc.speed_deg_s) > 1.5f) {
    const float friction_gain =
        max(constrain(g_effects.friction_gain, 0.0f, app::kFrictionMax),
            g_host_ffb.active ? constrain(g_host_ffb.friction_gain, 0.0f, app::kFrictionMax) : 0.0f);
    torque += friction_gain * ((enc.speed_deg_s > 0.0f) ? -0.10f : 0.10f);
  }

  if (g_effects.vibration_gain > 0.0f && g_effects.vibration_freq_hz > 0.0f) {
    const float phase =
        (2.0f * PI * g_effects.vibration_freq_hz * static_cast<float>(now)) / 1000.0f;
    torque += constrain(g_effects.vibration_gain, 0.0f, app::kVibrationMax) *
              0.14f * sinf(phase);
  }

  if (g_effects.impulse_expire_ms > now) {
    torque += g_effects.impulse_torque;
  }

  const float half_range = app::kWheelRangeDeg * 0.5f;
  if (fabsf(enc.angle_deg) > (half_range - app::kWheelSoftEndstopMarginDeg)) {
    const float overflow = fabsf(enc.angle_deg) - (half_range - app::kWheelSoftEndstopMarginDeg);
    torque += ((enc.angle_deg > 0.0f) ? -1.0f : 1.0f) *
              overflow * app::kSoftwareEndstopGain / app::kWheelSoftEndstopMarginDeg;
    g_fault_flags |= FAULT_SOFT_ENDSTOP;
  }

  torque = clampSigned(torque, min(g_effects.max_torque_limit, app::kTorqueCommandLimit));

  if ((now - g_start_ms) < app::kStartupQuietTimeMs) {
    torque = 0.0f;
  }

  const bool output_blocked = (g_fault_flags & (FAULT_COMM_TIMEOUT | FAULT_ENCODER | FAULT_ESTOP)) != 0U;
  if (output_blocked) {
    torque = 0.0f;
    motor::setEnabled(false);
  } else {
    motor::setEnabled(g_effects.motor_enabled);
  }

  if (!g_effects.motor_enabled || (g_fault_flags & (FAULT_COMM_TIMEOUT | FAULT_ESTOP)) != 0U) {
    motor::stop();
    g_filtered_torque = 0.0f;
    g_output_torque = 0.0f;
  } else if (g_effects.raw_pwm_override) {
    motor::setPwmRaw(g_effects.raw_pwm);
    g_filtered_torque = static_cast<float>(g_effects.raw_pwm) / static_cast<float>(app::kPwmClamp);
    g_output_torque = g_filtered_torque;
  } else {
    g_filtered_torque += (torque - g_filtered_torque) * app::kTorqueFilterAlpha;
    g_output_torque = g_filtered_torque;
    motor::setTorque(g_output_torque);
  }

  motor::setEmergencyStop(g_effects.estop);
  motor::update();
}

ControlSnapshot getSnapshot() {
  ControlSnapshot snapshot{};
  snapshot.encoder = encoder::getSnapshot();
  snapshot.pedals = pedals::getSnapshot();
  snapshot.motor = motor::getSnapshot();
  snapshot.output_torque = g_output_torque;
  snapshot.fault_flags = g_fault_flags;
  snapshot.last_command_age_ms = millis() - g_last_command_ms;
  return snapshot;
}

ControlEffects& effects() { return g_effects; }

void setHostFfbOverlay(const HostFfbOverlay& overlay) { g_host_ffb = overlay; }

void clearHostFfbOverlay() { g_host_ffb = HostFfbOverlay{}; }

void clearFaults() {
  g_fault_flags = FAULT_NONE;
  g_effects.estop = false;
  encoder::clearFault();
}

void zeroEncoder() { encoder::zeroAtCurrentPosition(); }

void triggerImpulse(float torque, uint32_t duration_ms) {
  g_effects.impulse_torque = clampSigned(torque, app::kTorqueCommandLimit);
  g_effects.impulse_expire_ms = millis() + min(duration_ms, app::kImpulseTimeoutMs);
}

void notifyMotorTestCommand() { g_last_motor_test_ms = millis(); }

bool isMotorTestActive() { return (millis() - g_last_motor_test_ms) <= app::kMotorTestLedHoldMs; }

}  // namespace control
