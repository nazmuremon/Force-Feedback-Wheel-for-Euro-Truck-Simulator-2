#include "motor.h"

#include "app_config.h"

namespace {

bool g_enabled = false;
bool g_estop = false;
int g_target_pwm = 0;
int g_applied_pwm = 0;
float g_applied_torque = 0.0f;

void setEnablePins(bool active) {
  if (!app::kUseMotorEnablePins) {
    return;
  }

  digitalWrite(app::kMotorEnableRPin, active ? HIGH : LOW);
  digitalWrite(app::kMotorEnableLPin, active ? HIGH : LOW);
}

void writeOutputs(int pwm) {
  pwm = constrain(pwm, -app::kPwmClamp, app::kPwmClamp);

  if (!g_enabled || g_estop || pwm == 0) {
    setEnablePins(false);
    analogWrite(app::kMotorRpwmPin, 0);
    analogWrite(app::kMotorLpwmPin, 0);
    g_applied_pwm = 0;
    g_applied_torque = 0.0f;
    return;
  }

  setEnablePins(true);
  const int magnitude = constrain(abs(pwm), 0, app::kPwmClamp);
  if (pwm > 0) {
    analogWrite(app::kMotorRpwmPin, magnitude);
    analogWrite(app::kMotorLpwmPin, 0);
  } else {
    analogWrite(app::kMotorRpwmPin, 0);
    analogWrite(app::kMotorLpwmPin, magnitude);
  }

  g_applied_pwm = pwm;
  g_applied_torque = static_cast<float>(pwm) / static_cast<float>(app::kPwmClamp);
}

}  // namespace

namespace motor {

void init() {
  pinMode(app::kMotorRpwmPin, OUTPUT);
  pinMode(app::kMotorLpwmPin, OUTPUT);
  analogWriteFrequency(app::kPwmFrequencyHz);
  analogWriteResolution(app::kPwmResolutionBits);

  if (app::kUseMotorEnablePins) {
    pinMode(app::kMotorEnableRPin, OUTPUT);
    pinMode(app::kMotorEnableLPin, OUTPUT);
    setEnablePins(false);
  }

  stop();
}

void update() {
  if (!g_enabled || g_estop) {
    g_target_pwm = 0;
  }

  if (g_applied_pwm < g_target_pwm) {
    g_applied_pwm = min(g_applied_pwm + app::kPwmRampPerControlTick, g_target_pwm);
  } else if (g_applied_pwm > g_target_pwm) {
    g_applied_pwm = max(g_applied_pwm - app::kPwmRampPerControlTick, g_target_pwm);
  }

  if (abs(g_target_pwm) < app::kPwmDeadband && abs(g_applied_pwm) < app::kPwmDeadband) {
    g_applied_pwm = 0;
  }

  writeOutputs(g_applied_pwm);
}

void setEnabled(bool enabled) {
  g_enabled = enabled && !g_estop;
  if (!g_enabled) {
    g_target_pwm = 0;
  }
}

void setEmergencyStop(bool enabled) {
  g_estop = enabled;
  if (enabled) {
    g_enabled = false;
    g_target_pwm = 0;
    writeOutputs(0);
  }
}

void setTorque(float torque) {
  torque = constrain(torque, -app::kTorqueCommandLimit, app::kTorqueCommandLimit);
  setPwmRaw(static_cast<int>(torque * static_cast<float>(app::kPwmClamp)));
}

void stop() {
  g_target_pwm = 0;
  g_applied_pwm = 0;
  writeOutputs(0);
}

void setPwmRaw(int pwm) {
  g_target_pwm = constrain(pwm, -app::kPwmClamp, app::kPwmClamp);
}

MotorSnapshot getSnapshot() {
  MotorSnapshot snapshot{};
  snapshot.applied_pwm = g_applied_pwm;
  snapshot.applied_torque = g_applied_torque;
  snapshot.enabled = g_enabled;
  snapshot.estop = g_estop;
  return snapshot;
}

}  // namespace motor
