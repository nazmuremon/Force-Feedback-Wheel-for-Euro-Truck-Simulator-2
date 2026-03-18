#pragma once

#include <Arduino.h>

struct MotorSnapshot {
  int applied_pwm;
  float applied_torque;
  bool enabled;
  bool estop;
};

namespace motor {

void init();
void update();
void setEnabled(bool enabled);
void setEmergencyStop(bool enabled);
void setTorque(float torque);
void stop();
void setPwmRaw(int pwm);
MotorSnapshot getSnapshot();

}  // namespace motor
