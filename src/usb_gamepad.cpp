#include "usb_gamepad.h"

#ifdef DIY_WHEEL_NATIVE_GAMEPAD

#include <cstring>

#include "app_config.h"
#include "usb_protocol.h"
#include "usbd_customhid.h"
#include "usbd_desc.h"
#include "usbd_if.h"

namespace {

constexpr uint8_t kReportIdGamepad = 0x01;
constexpr uint8_t kReportIdCommandOut = 0x02;
constexpr uint8_t kReportIdStatusIn = 0x03;
constexpr uint8_t kReportIdCommandFeature = 0x04;
constexpr uint8_t kReportIdStatusFeature = 0x05;
constexpr size_t kHidReportSize = 64;
constexpr size_t kHidPayloadSize = kHidReportSize - 1U;

struct __attribute__((packed)) GamepadReport {
  uint8_t report_id;
  uint16_t buttons;
  int16_t steer;
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
GamepadReport g_last_report{kReportIdGamepad, 0, 0, 0, 0};
TransportReport g_pending_transport_report{};
bool g_transport_pending = false;
uint8_t g_feature_status_report[kHidReportSize]{};

constexpr uint8_t kGamepadReportDescriptor[] = {
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x05,        // Usage (Game Pad)
    0xA1, 0x01,        // Collection (Application)
    0x85, kReportIdGamepad,  //   Report ID
    0x05, 0x09,        //   Usage Page (Button)
    0x19, 0x01,        //   Usage Minimum (Button 1)
    0x29, 0x10,        //   Usage Maximum (Button 16)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x01,        //   Logical Maximum (1)
    0x75, 0x01,        //   Report Size (1)
    0x95, 0x10,        //   Report Count (16)
    0x81, 0x02,        //   Input (Data,Var,Abs)
    0x05, 0x01,        //   Usage Page (Generic Desktop)
    0x16, 0x01, 0x80,  //   Logical Minimum (-32767)
    0x26, 0xFF, 0x7F,  //   Logical Maximum (32767)
    0x75, 0x10,        //   Report Size (16)
    0x95, 0x01,        //   Report Count (1)
    0x09, 0x30,        //   Usage (X)
    0x81, 0x02,        //   Input (Data,Var,Abs)
    0x15, 0x00,        //   Logical Minimum (0)
    0x26, 0xFF, 0x7F,  //   Logical Maximum (32767)
    0x95, 0x02,        //   Report Count (2)
    0x09, 0x32,        //   Usage (Z)
    0x09, 0x35,        //   Usage (Rz)
    0x81, 0x02,        //   Input (Data,Var,Abs)
    0xC0,              // End Collection
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

  if (first == kReportIdCommandOut || first == kReportIdCommandFeature) {
    const size_t max_payload = kHidPayloadSize - 1U;
    const size_t bounded_length = (static_cast<size_t>(second) < max_payload) ? static_cast<size_t>(second)
                                                                               : max_payload;
    tryHandleCommandFrame(hid->Report_buf + 2, bounded_length);
  } else if (second == 0xA5U && hid->Report_buf[2] == 0x5AU) {
    // Some host stacks strip the report ID before handing us the output report.
    tryHandleCommandFrame(hid->Report_buf + 1, first);
  }
  USBD_CUSTOM_HID_ReceivePacket(&g_usb_device);
  return 0;
}

uint8_t* customHidGetReport(uint16_t* report_length) {
  if (report_length == nullptr) {
    return nullptr;
  }

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

void sendReport(const GamepadReport& report) {
  if (!g_initialized) {
    return;
  }
  if (USBD_CUSTOM_HID_SendReport(&g_usb_device, reinterpret_cast<uint8_t*>(const_cast<GamepadReport*>(&report)),
                                 sizeof(report)) == USBD_OK) {
    g_last_report = report;
  }
}

bool trySendTransportReport(const TransportReport& report) {
  return USBD_CUSTOM_HID_SendReport(&g_usb_device, reinterpret_cast<uint8_t*>(const_cast<TransportReport*>(&report)),
                                    sizeof(report)) == USBD_OK;
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
  if (!g_transport_pending) {
    return;
  }
  if (trySendTransportReport(g_pending_transport_report)) {
    g_transport_pending = false;
  }
}

void update(float wheel_angle_deg, float brake_norm, float accel_norm) {
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

  GamepadReport report{};
  report.report_id = kReportIdGamepad;
  report.buttons = 0;
  report.steer = normalizedSignedAxis(wheel_angle_deg / (app::kWheelRangeDeg * 0.5f));
  report.accel = normalizedUnsignedAxis(accel_norm);
  report.brake = normalizedUnsignedAxis(brake_norm);

  if (memcmp(&report, &g_last_report, sizeof(report)) != 0) {
    sendReport(report);
  }
}

bool sendTransportPacket(const uint8_t* data, size_t length) { return sendTransportReport(data, length); }

}  // namespace usb_gamepad

#endif  // DIY_WHEEL_NATIVE_GAMEPAD
