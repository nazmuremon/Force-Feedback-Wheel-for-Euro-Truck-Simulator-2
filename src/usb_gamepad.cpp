#include "usb_gamepad.h"

#ifdef DIY_WHEEL_NATIVE_GAMEPAD

#include <cstring>

#include "app_config.h"
#include "control.h"
#include "hid_ffb.h"
#include "usb_protocol.h"
#include "usbd_customhid.h"
#include "usbd_desc.h"
#include "usbd_if.h"

namespace {

constexpr uint8_t kReportIdWheelInput = 0x01;
constexpr uint8_t kReportIdCommandOut = 0x02;
constexpr uint8_t kReportIdStatusIn = 0x03;
constexpr uint8_t kReportIdCommandFeature = 0x04;
constexpr uint8_t kReportIdStatusFeature = 0x05;
constexpr uint8_t kReportIdPidState = 0x10;
constexpr uint8_t kReportIdSetEffect = 0x11;
constexpr uint8_t kReportIdSetConstantForce = 0x12;
constexpr uint8_t kReportIdSetCondition = 0x13;
constexpr uint8_t kReportIdEffectOperation = 0x14;
constexpr uint8_t kReportIdDeviceControl = 0x15;
constexpr uint8_t kReportIdDeviceGain = 0x16;
constexpr uint8_t kReportIdCreateNewEffect = 0x17;
constexpr uint8_t kReportIdBlockLoad = 0x18;
constexpr uint8_t kReportIdPool = 0x19;
constexpr uint8_t kReportIdBlockFree = 0x1A;
constexpr size_t kHidReportSize = 64;
constexpr size_t kHidPayloadSize = kHidReportSize - 1U;

struct __attribute__((packed)) WheelInputReport {
  uint8_t report_id;
  uint16_t buttons;
  int16_t steering;
  uint16_t accel;
  uint16_t brake;
};

struct __attribute__((packed)) TransportReport {
  uint8_t report_id;
  uint8_t length;
  uint8_t payload[kHidPayloadSize - 1U];
};

USBD_HandleTypeDef g_usb_device;
bool g_initialized = false;
uint32_t g_last_report_us = 0;
uint32_t g_last_pid_state_report_ms = 0;
WheelInputReport g_last_report{kReportIdWheelInput, 0, 0, 0, 0};
TransportReport g_pending_transport_report{};
bool g_transport_pending = false;
uint8_t g_feature_status_report[kHidReportSize]{};
uint8_t g_last_pid_state_report[kHidReportSize]{};
size_t g_last_pid_state_length = 0U;

constexpr uint8_t kGamepadReportDescriptor[] = {
    // Wheel input plus native Physical Interface Device force-feedback reports.
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x04,        // Usage (Joystick)
    0xA1, 0x01,        // Collection (Application)
    0x85, kReportIdWheelInput,  //   Report ID
    0x05, 0x09,        //   Usage Page (Button)
    0x19, 0x01,        //   Usage Minimum (Button 1)
    0x29, 0x10,        //   Usage Maximum (Button 16)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x01,        //   Logical Maximum (1)
    0x75, 0x01,        //   Report Size (1)
    0x95, 0x10,        //   Report Count (16)
    0x81, 0x02,        //   Input (Data,Var,Abs)
    0x05, 0x01,        //   Usage Page (Generic Desktop)
    0x09, 0x30,        //   Usage (X)
    0x16, 0x01, 0x80,  //   Logical Minimum (-32767)
    0x26, 0xFF, 0x7F,  //   Logical Maximum (32767)
    0x75, 0x10,        //   Report Size (16)
    0x95, 0x01,        //   Report Count (1)
    0x81, 0x02,        //   Input (Data,Var,Abs)
    0x15, 0x00,        //   Logical Minimum (0)
    0x26, 0xFF, 0x7F,  //   Logical Maximum (32767)
    0x09, 0x31,        //   Usage (Y)
    0x09, 0x32,        //   Usage (Z)
    0x95, 0x02,        //   Report Count (2)
    0x81, 0x02,        //   Input (Data,Var,Abs)
    0x05, 0x0F,        //   Usage Page (Physical Interface)
    0x09, 0x92,        //   Usage (PID State Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdPidState,  //     Report ID
    0x09, 0x22,        //     Usage (Effect Parameter Block Index)
    0x15, 0x00,        //     Logical Minimum (0)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0x81, 0x02,        //     Input (Data,Var,Abs)
    0x09, 0x94,        //     Usage (Effect Playing)
    0x09, 0x9F,        //     Usage (Device Paused)
    0x09, 0xA0,        //     Usage (Actuators Enabled)
    0x09, 0xA4,        //     Usage (Safety Switch)
    0x09, 0xA5,        //     Usage (Actuator Override Switch)
    0x09, 0xA6,        //     Usage (Actuator Power)
    0x15, 0x00,        //     Logical Minimum (0)
    0x25, 0x01,        //     Logical Maximum (1)
    0x75, 0x01,        //     Report Size (1)
    0x95, 0x06,        //     Report Count (6)
    0x81, 0x02,        //     Input (Data,Var,Abs)
    0x75, 0x02,        //     Report Size (2)
    0x95, 0x01,        //     Report Count (1)
    0x81, 0x03,        //     Input (Const,Var,Abs)
    0xC0,              //   End Collection
    0x09, 0x21,        //   Usage (Set Effect Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdSetEffect,  //     Report ID
    0x09, 0x22,        //     Usage (Effect Parameter Block Index)
    0x15, 0x01,        //     Logical Minimum (1)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x09, 0x25,        //     Usage (Effect Type)
    0xA1, 0x02,        //     Collection (Logical)
    0x09, 0x26,        //       Usage (ET Constant Force)
    0x09, 0x27,        //       Usage (ET Ramp)
    0x09, 0x30,        //       Usage (ET Square)
    0x09, 0x31,        //       Usage (ET Sine)
    0x09, 0x32,        //       Usage (ET Triangle)
    0x09, 0x33,        //       Usage (ET Sawtooth Up)
    0x09, 0x34,        //       Usage (ET Sawtooth Down)
    0x09, 0x40,        //       Usage (ET Spring)
    0x09, 0x41,        //       Usage (ET Damper)
    0x09, 0x42,        //       Usage (ET Inertia)
    0x09, 0x43,        //       Usage (ET Friction)
    0x15, 0x01,        //       Logical Minimum (1)
    0x25, 0x0B,        //       Logical Maximum (11)
    0x75, 0x08,        //       Report Size (8)
    0x95, 0x01,        //       Report Count (1)
    0xB1, 0x00,        //       Feature (Data,Arr,Abs)
    0xC0,              //     End Collection
    0x09, 0x50,        //     Usage (Duration)
    0x09, 0x54,        //     Usage (Trigger Repeat Interval)
    0x09, 0x51,        //     Usage (Sample Period)
    0x26, 0x10, 0x27,  //     Logical Maximum (10000)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x03,        //     Report Count (3)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x09, 0x52,        //     Usage (Gain)
    0x09, 0x53,        //     Usage (Trigger Button)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x02,        //     Report Count (2)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x09, 0x55,        //     Usage (Axes Enable)
    0xA1, 0x02,        //     Collection (Logical)
    0x05, 0x01,        //       Usage Page (Generic Desktop)
    0x09, 0x30,        //       Usage (X)
    0x15, 0x00,        //       Logical Minimum (0)
    0x25, 0x01,        //       Logical Maximum (1)
    0x75, 0x01,        //       Report Size (1)
    0x95, 0x01,        //       Report Count (1)
    0xB1, 0x02,        //       Feature (Data,Var,Abs)
    0x75, 0x07,        //       Report Size (7)
    0x95, 0x01,        //       Report Count (1)
    0xB1, 0x03,        //       Feature (Const,Var,Abs)
    0xC0,              //     End Collection
    0x05, 0x0F,        //     Usage Page (Physical Interface)
    0x09, 0x57,        //     Usage (Direction)
    0xA1, 0x02,        //     Collection (Logical)
    0x05, 0x01,        //       Usage Page (Generic Desktop)
    0x09, 0x30,        //       Usage (X)
    0x09, 0x31,        //       Usage (Y)
    0x15, 0x00,        //       Logical Minimum (0)
    0x26, 0xFF, 0x00,  //       Logical Maximum (255)
    0x75, 0x08,        //       Report Size (8)
    0x95, 0x02,        //       Report Count (2)
    0xB1, 0x02,        //       Feature (Data,Var,Abs)
    0xC0,              //     End Collection
    0xC0,              //   End Collection
    0x09, 0x5F,        //   Usage (Set Condition Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdSetCondition,  //     Report ID
    0x09, 0x22,        //     Usage (Effect Parameter Block Index)
    0x09, 0x23,        //     Usage (Parameter Block Offset)
    0x15, 0x00,        //     Logical Minimum (0)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x02,        //     Report Count (2)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x16, 0x01, 0x80,  //     Logical Minimum (-32767)
    0x26, 0xFF, 0x7F,  //     Logical Maximum (32767)
    0x09, 0x60,        //     Usage (CP Offset)
    0x09, 0x61,        //     Usage (Positive Coefficient)
    0x09, 0x62,        //     Usage (Negative Coefficient)
    0x09, 0x63,        //     Usage (Positive Saturation)
    0x09, 0x64,        //     Usage (Negative Saturation)
    0x09, 0x65,        //     Usage (Dead Band)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x06,        //     Report Count (6)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0xC0,              //   End Collection
    0x09, 0x73,        //   Usage (Set Constant Force Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdSetConstantForce,  //     Report ID
    0x09, 0x22,        //     Usage (Effect Parameter Block Index)
    0x15, 0x01,        //     Logical Minimum (1)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x09, 0x70,        //     Usage (Magnitude)
    0x16, 0x01, 0x80,  //     Logical Minimum (-32767)
    0x26, 0xFF, 0x7F,  //     Logical Maximum (32767)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0xC0,              //   End Collection
    0x09, 0x77,        //   Usage (Effect Operation Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdEffectOperation,  //     Report ID
    0x09, 0x22,        //     Usage (Effect Parameter Block Index)
    0x15, 0x01,        //     Logical Minimum (1)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0x91, 0x02,        //     Output (Data,Var,Abs)
    0x09, 0x78,        //     Usage (Effect Operation)
    0xA1, 0x02,        //     Collection (Logical)
    0x09, 0x79,        //       Usage (Op Effect Start)
    0x09, 0x7A,        //       Usage (Op Effect Start Solo)
    0x09, 0x7B,        //       Usage (Op Effect Stop)
    0x15, 0x01,        //       Logical Minimum (1)
    0x25, 0x03,        //       Logical Maximum (3)
    0x75, 0x08,        //       Report Size (8)
    0x95, 0x01,        //       Report Count (1)
    0xB1, 0x00,        //       Feature (Data,Arr,Abs)
    0xC0,              //     End Collection
    0x09, 0x7C,        //     Usage (Loop Count)
    0x15, 0x00,        //     Logical Minimum (0)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0xC0,              //   End Collection
    0x09, 0x95,        //   Usage (PID Device Control Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdDeviceControl,  //     Report ID
    0x09, 0x96,        //     Usage (PID Device Control)
    0xA1, 0x02,        //     Collection (Logical)
    0x09, 0x97,        //       Usage (DC Enable Actuators)
    0x09, 0x98,        //       Usage (DC Disable Actuators)
    0x09, 0x99,        //       Usage (DC Stop All Effects)
    0x09, 0x9A,        //       Usage (DC Device Reset)
    0x09, 0x9B,        //       Usage (DC Device Pause)
    0x09, 0x9C,        //       Usage (DC Device Continue)
    0x15, 0x01,        //       Logical Minimum (1)
    0x25, 0x06,        //       Logical Maximum (6)
    0x75, 0x08,        //       Report Size (8)
    0x95, 0x01,        //       Report Count (1)
    0xB1, 0x00,        //       Feature (Data,Arr,Abs)
    0xC0,              //     End Collection
    0xC0,              //   End Collection
    0x09, 0x7D,        //   Usage (Device Gain Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdDeviceGain,  //     Report ID
    0x09, 0x7E,        //     Usage (Device Gain)
    0x15, 0x00,        //     Logical Minimum (0)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0xC0,              //   End Collection
    0x09, 0xAB,        //   Usage (Create New Effect Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdCreateNewEffect,  //     Report ID
    0x09, 0x25,        //     Usage (Effect Type)
    0xA1, 0x02,        //     Collection (Logical)
    0x09, 0x26,        //       Usage (ET Constant Force)
    0x09, 0x27,        //       Usage (ET Ramp)
    0x09, 0x30,        //       Usage (ET Square)
    0x09, 0x31,        //       Usage (ET Sine)
    0x09, 0x32,        //       Usage (ET Triangle)
    0x09, 0x33,        //       Usage (ET Sawtooth Up)
    0x09, 0x34,        //       Usage (ET Sawtooth Down)
    0x09, 0x40,        //       Usage (ET Spring)
    0x09, 0x41,        //       Usage (ET Damper)
    0x09, 0x42,        //       Usage (ET Inertia)
    0x09, 0x43,        //       Usage (ET Friction)
    0x15, 0x01,        //       Logical Minimum (1)
    0x25, 0x0B,        //       Logical Maximum (11)
    0x75, 0x08,        //       Report Size (8)
    0x95, 0x01,        //       Report Count (1)
    0xB1, 0x00,        //       Feature (Data,Arr,Abs)
    0xC0,              //     End Collection
    0x09, 0x58,        //     Usage (Type Specific Block Offset)
    0x26, 0xFF, 0x7F,  //     Logical Maximum (32767)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0xC0,              //   End Collection
    0x09, 0x89,        //   Usage (PID Block Load Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdBlockLoad,  //     Report ID
    0x09, 0x22,        //     Usage (Effect Parameter Block Index)
    0x15, 0x00,        //     Logical Minimum (0)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x09, 0x8B,        //     Usage (Effect Parameter Block Load Status)
    0xA1, 0x02,        //     Collection (Logical)
    0x09, 0x8C,        //       Usage (Block Load Success)
    0x09, 0x8D,        //       Usage (Block Load Full)
    0x09, 0x8E,        //       Usage (Block Load Error)
    0x15, 0x01,        //       Logical Minimum (1)
    0x25, 0x03,        //       Logical Maximum (3)
    0x75, 0x08,        //       Report Size (8)
    0x95, 0x01,        //       Report Count (1)
    0xB1, 0x00,        //       Feature (Data,Arr,Abs)
    0xC0,              //     End Collection
    0x09, 0xAC,        //     Usage (RAM Pool Available)
    0x26, 0xFF, 0x0F,  //     Logical Maximum (4095)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0xC0,              //   End Collection
    0x09, 0x7F,        //   Usage (Parameter Block Pools Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdPool,  //     Report ID
    0x09, 0x80,        //     Usage (RAM Pool Size)
    0x09, 0x81,        //     Usage (ROM Pool Size)
    0x26, 0xFF, 0x0F,  //     Logical Maximum (4095)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x02,        //     Report Count (2)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x09, 0x83,        //     Usage (Simultaneous Effects Max)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x09, 0xA9,        //     Usage (Device Managed Pool)
    0x09, 0xAA,        //     Usage (Shared Parameter Blocks)
    0x15, 0x00,        //     Logical Minimum (0)
    0x25, 0x01,        //     Logical Maximum (1)
    0x75, 0x01,        //     Report Size (1)
    0x95, 0x02,        //     Report Count (2)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0x75, 0x06,        //     Report Size (6)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x03,        //     Feature (Const,Var,Abs)
    0xC0,              //   End Collection
    0x09, 0x90,        //   Usage (PID Block Free Report)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, kReportIdBlockFree,  //     Report ID
    0x09, 0x22,        //     Usage (Effect Parameter Block Index)
    0x15, 0x01,        //     Logical Minimum (1)
    0x26, 0xFF, 0x00,  //     Logical Maximum (255)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0xB1, 0x02,        //     Feature (Data,Var,Abs)
    0xC0,              //   End Collection
    0xC0,              // End wheel/FFB collection
    0x06, 0x00, 0xFF,  // Usage Page (Vendor Defined 0xFF00)
    0x09, 0x01,        // Usage (0x01)
    0xA1, 0x01,        // Collection (Application)
    0x85, kReportIdCommandOut,  //   Report ID
    0x09, 0x02,        //   Usage (0x02)
    0x15, 0x00,        //   Logical Minimum (0)
    0x26, 0xFF, 0x00,  //   Logical Maximum (255)
    0x75, 0x08,        //   Report Size (8)
    0x95, 0x3F,        //   Report Count (63)
    0x91, 0x02,        //   Output (Data,Var,Abs)
    0x85, kReportIdStatusIn,  //   Report ID
    0x09, 0x03,        //   Usage (0x03)
    0x95, 0x3F,        //   Report Count (63)
    0x81, 0x02,        //   Input (Data,Var,Abs)
    0x85, kReportIdCommandFeature,  //   Report ID
    0x09, 0x04,        //   Usage (0x04)
    0x95, 0x3F,        //   Report Count (63)
    0xB1, 0x02,        //   Feature (Data,Var,Abs)
    0x85, kReportIdStatusFeature,  //   Report ID
    0x09, 0x05,        //   Usage (0x05)
    0x95, 0x3F,        //   Report Count (63)
    0xB1, 0x02,        //   Feature (Data,Var,Abs)
    0xC0,              // End Collection
};

static_assert(sizeof(kGamepadReportDescriptor) == USBD_CUSTOM_HID_REPORT_DESC_SIZE,
              "HID report descriptor size macro is out of sync with the descriptor bytes");

int8_t customHidInit() { return 0; }

int8_t customHidDeInit() { return 0; }

bool tryHandleCommandFrame(const uint8_t* data, size_t length) {
  if (length == 0U || data == nullptr) {
    return false;
  }
  const size_t bounded_length = (length < kHidPayloadSize) ? length : kHidPayloadSize;
  usb_protocol::processBytes(data, bounded_length);
  return true;
}

int8_t customHidOutEvent(uint8_t event_idx, uint8_t state) {
  UNUSED(event_idx);
  UNUSED(state);

  auto* hid =
      reinterpret_cast<USBD_CUSTOM_HID_HandleTypeDef*>(g_usb_device.pClassDataCmsit[g_usb_device.classId]);
  if (hid == nullptr) {
    return 0;
  }

  const uint8_t first = hid->Report_buf[0];
  const uint8_t second = hid->Report_buf[1];
  const size_t pid_length = hid_ffb::expectedReportLength(first);

  if (first == kReportIdCommandOut || first == kReportIdCommandFeature) {
    const size_t max_payload = kHidPayloadSize - 1U;
    const size_t bounded_length = (static_cast<size_t>(second) < max_payload) ? static_cast<size_t>(second)
                                                                               : max_payload;
    tryHandleCommandFrame(hid->Report_buf + 2, bounded_length);
  } else if (pid_length > 0U) {
    bool handled = hid_ffb::handleReport(first, hid->Report_buf + 1, pid_length);
    if (!handled && (pid_length + 2U) <= sizeof(hid->Report_buf)) {
      hid_ffb::handleReport(first, hid->Report_buf + 2, pid_length);
    }
  } else if (second == 0xA5U && hid->Report_buf[2] == 0x5AU) {
    // Some host stacks strip the report ID before handing us the output report.
    tryHandleCommandFrame(hid->Report_buf + 1, first);
  }
  USBD_CUSTOM_HID_ReceivePacket(&g_usb_device);
  return 0;
}

uint8_t* customHidGetReport(uint8_t report_id, uint8_t report_type, uint16_t* report_length) {
  if (report_length == nullptr) {
    return nullptr;
  }

  if (report_id == kReportIdStatusFeature) {
    const size_t frame_length =
        usb_protocol::buildStatusFrame(0, g_feature_status_report + 2, sizeof(g_feature_status_report) - 2U);
    if (frame_length == 0U) {
      *report_length = 0U;
      return nullptr;
    }

    g_feature_status_report[0] = kReportIdStatusFeature;
    g_feature_status_report[1] = static_cast<uint8_t>(frame_length);
    *report_length = static_cast<uint16_t>(frame_length + 2U);
    return g_feature_status_report;
  }

  return hid_ffb::getFeatureReport(report_id, report_type, report_length);
}

USBD_CUSTOM_HID_ItfTypeDef g_custom_hid_interface = {
    const_cast<uint8_t*>(kGamepadReportDescriptor),
    customHidInit,
    customHidDeInit,
    customHidOutEvent,
#ifdef USBD_CUSTOMHID_CTRL_REQ_GET_REPORT_ENABLED
    customHidGetReport,
#endif
};

int16_t normalizedSignedAxis(float value) {
  value = constrain(value, -1.0f, 1.0f);
  return static_cast<int16_t>(value * 32767.0f);
}

uint16_t normalizedUnsignedAxis(float value) {
  value = constrain(value, 0.0f, 1.0f);
  return static_cast<uint16_t>(value * 32767.0f);
}

void sendReport(const WheelInputReport& report) {
  if (!g_initialized) {
    return;
  }
  if (USBD_CUSTOM_HID_SendReport(&g_usb_device, reinterpret_cast<uint8_t*>(const_cast<WheelInputReport*>(&report)),
                                 sizeof(report)) == USBD_OK) {
    g_last_report = report;
  }
}

bool trySendTransportReport(const TransportReport& report) {
  return USBD_CUSTOM_HID_SendReport(&g_usb_device, reinterpret_cast<uint8_t*>(const_cast<TransportReport*>(&report)),
                                    sizeof(report)) == USBD_OK;
}

bool trySendPidStateReport(const uint8_t* report, size_t length) {
  if (report == nullptr || length == 0U) {
    return false;
  }
  return USBD_CUSTOM_HID_SendReport(&g_usb_device, const_cast<uint8_t*>(report), length) == USBD_OK;
}

bool sendTransportReport(const uint8_t* data, size_t length) {
  if (!g_initialized || length > (kHidPayloadSize - 1U)) {
    return false;
  }

  TransportReport report{};
  report.report_id = kReportIdStatusIn;
  report.length = static_cast<uint8_t>(length);
  memcpy(report.payload, data, length);
  if (trySendTransportReport(report)) {
    g_transport_pending = false;
    return true;
  }

  g_pending_transport_report = report;
  g_transport_pending = true;
  return true;
}

}  // namespace

namespace usb_gamepad {

void init() {
  USBD_reenumerate();
  if (USBD_Init(&g_usb_device, &USBD_Desc, 0) != USBD_OK) {
    return;
  }
  if (USBD_RegisterClass(&g_usb_device, USBD_CUSTOM_HID_CLASS) != USBD_OK) {
    return;
  }
  if (USBD_CUSTOM_HID_RegisterInterface(&g_usb_device, &g_custom_hid_interface) != USBD_OK) {
    return;
  }
  if (USBD_Start(&g_usb_device) != USBD_OK) {
    return;
  }
  g_initialized = true;
  USBD_CUSTOM_HID_ReceivePacket(&g_usb_device);
  delay(50);
}

void task() {
  if (g_transport_pending) {
    if (trySendTransportReport(g_pending_transport_report)) {
      g_transport_pending = false;
    }
    return;
  }

  const uint32_t now_ms = millis();
  if ((now_ms - g_last_pid_state_report_ms) < 50U) {
    return;
  }
  uint8_t report[kHidReportSize]{};
  const size_t length = hid_ffb::buildPidStateReport(report, sizeof(report));
  if (length == 0U) {
    return;
  }
  if (length != g_last_pid_state_length || memcmp(report, g_last_pid_state_report, length) != 0) {
    if (trySendPidStateReport(report, length)) {
      memcpy(g_last_pid_state_report, report, length);
      g_last_pid_state_length = length;
      g_last_pid_state_report_ms = now_ms;
    }
  }
}

void update(const ControlSnapshot& snapshot) {
  task();
  if (g_transport_pending) {
    return;
  }
  const uint32_t report_period_us = 1000000UL / app::kUsbReportRateHz;
  const uint32_t now_us = micros();
  if ((now_us - g_last_report_us) < report_period_us) {
    return;
  }
  g_last_report_us = now_us;

  WheelInputReport report{};
  report.report_id = kReportIdWheelInput;
  uint16_t buttons = 0;
  if (snapshot.motor.enabled) {
    buttons |= 0x0001U;
  }
  if (snapshot.motor.applied_pwm != 0) {
    buttons |= 0x0002U;
  }
  if (snapshot.fault_flags == FAULT_NONE) {
    buttons |= 0x0004U;
  }
  if ((snapshot.fault_flags & FAULT_MOTOR_DISABLED) != 0U) {
    buttons |= 0x0008U;
  }
  if (hid_ffb::getState().last_constant_magnitude != 0) {
    buttons |= 0x0010U;
  }
  if (hid_ffb::getState().last_report_id == 0x12U) {
    buttons |= 0x0020U;
  }
  report.buttons = buttons;
  report.steering = normalizedSignedAxis(snapshot.encoder.angle_deg / (app::kWheelRangeDeg * 0.5f));
  report.accel = normalizedUnsignedAxis(snapshot.pedals.accel.normalized);
  report.brake = normalizedUnsignedAxis(snapshot.pedals.brake.normalized);

  sendReport(report);
}

bool sendTransportPacket(const uint8_t* data, size_t length) { return sendTransportReport(data, length); }

}  // namespace usb_gamepad

#endif  // DIY_WHEEL_NATIVE_GAMEPAD
