#pragma once

#include <Arduino.h>

namespace app {

using PinId = uint32_t;

constexpr char kFirmwareVersion[] = "0.1.0";
constexpr PinId kEncoderPinA = D3;
constexpr PinId kEncoderPinB = D4;
constexpr PinId kBrakeAdcPin = A0;
constexpr PinId kAccelAdcPin = A1;
constexpr PinId kMotorRpwmPin = D9;
constexpr PinId kMotorLpwmPin = D11;
constexpr PinId kMotorEnableRPin = D6;
constexpr PinId kMotorEnableLPin = D5;
constexpr PinId kStatusLedPin = LED_BUILTIN;

constexpr bool kUseMotorEnablePins = true;
constexpr bool kBrakeInvertDefault = false;
constexpr bool kAccelInvertDefault = false;
#ifdef DIY_WHEEL_SIMULATE_PEDALS
constexpr bool kSimulatePedals = true;
#else
constexpr bool kSimulatePedals = false;
#endif
constexpr float kSimulatedBrakeNormalized = 0.0f;
constexpr float kSimulatedAccelNormalized = 0.10f;

constexpr uint32_t kUsbBaudRate = 115200;
constexpr uint32_t kFastLoopHz = 1000;
constexpr uint32_t kControlLoopHz = 1000;
constexpr uint32_t kStatusLoopHz = 50;

constexpr float kWheelRangeDeg = 900.0f;
constexpr int32_t kEncoderCountsPerRevolution = 8000;
constexpr float kWheelSoftEndstopMarginDeg = 10.0f;
constexpr float kWheelMaxSpeedDegPerSec = 3200.0f;

constexpr int kPwmFrequencyHz = 20000;
constexpr int kPwmResolutionBits = 8;
constexpr int kPwmClamp = 255;
constexpr int kPwmDeadband = 4;
constexpr int kPwmMinDrive = 32;
constexpr int kPwmRampPerControlTick = 28;

constexpr uint32_t kCommTimeoutMs = 250;
constexpr uint32_t kStartupQuietTimeMs = 1500;
constexpr uint32_t kImpulseTimeoutMs = 120;
constexpr uint32_t kMotorTestLedHoldMs = 400;

constexpr float kTorqueCommandLimit = 1.0f;
constexpr float kTorqueFilterAlpha = 0.82f;
constexpr float kDamperMax = 1.50f;
constexpr float kSpringMax = 1.50f;
constexpr float kFrictionMax = 1.00f;
constexpr float kVibrationMax = 1.00f;
constexpr float kSoftwareEndstopGain = 0.35f;

#ifdef DIY_WHEEL_NATIVE_GAMEPAD
constexpr bool kNativeUsbGamepadMode = true;
constexpr uint32_t kUsbReportRateHz = 500;
#else
constexpr bool kNativeUsbGamepadMode = false;
#endif

}  // namespace app
