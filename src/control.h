#pragma once

#include <Arduino.h>

#include "encoder.h"
#include "motor.h"
#include "pedals.h"

enum FaultFlags : uint32_t {
  FAULT_NONE = 0,
  FAULT_COMM_TIMEOUT = 1u << 0,
  FAULT_ENCODER = 1u << 1,
  FAULT_ESTOP = 1u << 2,
  FAULT_MOTOR_DISABLED = 1u << 3,
  FAULT_SOFT_ENDSTOP = 1u << 4,
};

struct ControlEffects {
  bool motor_enabled;
  bool estop;
  bool raw_pwm_override;
  float constant_torque;
  float spring_gain;
  float spring_center_deg;
  float damper_gain;
  float friction_gain;
  float vibration_gain;
  float vibration_freq_hz;
  float impulse_torque;
  uint32_t impulse_expire_ms;
  float max_torque_limit;
  int16_t raw_pwm;
};

struct ControlSnapshot {
  EncoderSnapshot encoder;
  PedalsSnapshot pedals;
  MotorSnapshot motor;
  float output_torque;
  uint32_t fault_flags;
  uint32_t last_command_age_ms;
};

namespace control {

void init();
void markCommandReceived();
void updateFast();
void updateControl();
ControlSnapshot getSnapshot();
ControlEffects& effects();
void clearFaults();
void zeroEncoder();
void triggerImpulse(float torque, uint32_t duration_ms);
void notifyMotorTestCommand();
bool isMotorTestActive();

}  // namespace control
