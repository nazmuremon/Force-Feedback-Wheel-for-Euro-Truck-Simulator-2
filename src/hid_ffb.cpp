#include "hid_ffb.h"

#include <cstring>

#include "app_config.h"
#include "control.h"

namespace {

constexpr uint8_t kReportTypeFeature = 0x03;

constexpr uint8_t kReportIdPidState = 0x02;
constexpr uint8_t kReportIdSetEffect = 0x01;
constexpr uint8_t kReportIdSetConstantForce = 0x05;
constexpr uint8_t kReportIdSetCondition = 0x03;
constexpr uint8_t kReportIdEffectOperation = 0x0A;
constexpr uint8_t kReportIdDeviceControl = 0x0C;
constexpr uint8_t kReportIdDeviceGain = 0x0D;
constexpr uint8_t kReportIdCreateNewEffect = 0x17;
constexpr uint8_t kReportIdBlockLoad = 0x18;
constexpr uint8_t kReportIdPool = 0x19;
constexpr uint8_t kReportIdBlockFree = 0x0B;

constexpr uint8_t kEffectTypeConstant = 1;
constexpr uint8_t kEffectTypeSpring = 8;
constexpr uint8_t kEffectTypeDamper = 9;
constexpr uint8_t kEffectTypeFriction = 11;

constexpr uint8_t kEffectOpStart = 1;
constexpr uint8_t kEffectOpStartSolo = 2;
constexpr uint8_t kEffectOpStop = 3;

constexpr uint8_t kDeviceControlEnableActuators = 1;
constexpr uint8_t kDeviceControlDisableActuators = 2;
constexpr uint8_t kDeviceControlStopAllEffects = 3;
constexpr uint8_t kDeviceControlReset = 4;
constexpr uint8_t kDeviceControlPause = 5;
constexpr uint8_t kDeviceControlContinue = 6;

constexpr uint8_t kBlockLoadSuccess = 1;
constexpr uint8_t kBlockLoadFull = 2;
constexpr uint8_t kBlockLoadError = 3;

constexpr uint16_t kRamPoolSize = 4096;

struct __attribute__((packed)) SetEffectReport {
  uint8_t effect_block_index;
  uint8_t effect_type;
  uint16_t duration_ms;
  uint16_t trigger_repeat_ms;
  uint16_t sample_period_ms;
  uint8_t gain;
  uint8_t trigger_button;
  uint8_t enable_axis;
  uint8_t direction_x;
  uint8_t direction_y;
};

struct __attribute__((packed)) SetConstantForceReport {
  uint8_t effect_block_index;
  int16_t magnitude;
};

struct __attribute__((packed)) SetConditionReport {
  uint8_t effect_block_index;
  uint8_t parameter_block_offset;
  int16_t cp_offset;
  int16_t positive_coefficient;
  int16_t negative_coefficient;
  uint16_t positive_saturation;
  uint16_t negative_saturation;
  uint16_t deadband;
};

struct __attribute__((packed)) EffectOperationReport {
  uint8_t effect_block_index;
  uint8_t operation;
  uint8_t loop_count;
};

struct __attribute__((packed)) DeviceControlReport {
  uint8_t control;
};

struct __attribute__((packed)) DeviceGainReport {
  uint8_t gain;
};

struct __attribute__((packed)) CreateNewEffectReport {
  uint8_t effect_type;
  uint16_t byte_count;
};

struct __attribute__((packed)) BlockFreeReport {
  uint8_t effect_block_index;
};

struct __attribute__((packed)) BlockLoadFeatureReport {
  uint8_t report_id;
  uint8_t effect_block_index;
  uint8_t load_status;
  uint16_t ram_pool_available;
};

struct __attribute__((packed)) PoolFeatureReport {
  uint8_t report_id;
  uint16_t ram_pool_size;
  uint8_t max_simultaneous_effects;
  uint8_t flags;
};

struct EffectSlot {
  bool allocated;
  bool configured;
  bool running;
  uint8_t type;
  uint8_t gain;
  int16_t magnitude;
  int16_t condition_cp_offset;
  int16_t condition_positive;
  int16_t condition_negative;
};

hid_ffb::DeviceState g_state{};
EffectSlot g_slots[4]{};
BlockLoadFeatureReport g_block_load_report{};
PoolFeatureReport g_pool_report{};

float normalizedGain(uint8_t gain) { return static_cast<float>(gain) / 255.0f; }

float signedTorque(int16_t magnitude, uint8_t gain) {
  const float normalized =
      static_cast<float>(magnitude) / 32767.0f * normalizedGain(gain) * app::kTorqueCommandLimit;
  return constrain(normalized, -app::kTorqueCommandLimit, app::kTorqueCommandLimit);
}

float conditionGain(int16_t coefficient, uint8_t gain, float limit) {
  const float normalized = fabsf(static_cast<float>(coefficient) / 32767.0f) * normalizedGain(gain);
  return constrain(normalized, 0.0f, limit);
}

bool isSupportedEffectType(uint8_t type) {
  switch (type) {
    case kEffectTypeConstant:
    case kEffectTypeSpring:
    case kEffectTypeDamper:
    case kEffectTypeFriction:
      return true;
    default:
      return false;
  }
}

EffectSlot* slotForIndex(uint8_t effect_block_index) {
  if (effect_block_index == 0U || effect_block_index > 4U) {
    return nullptr;
  }
  return &g_slots[effect_block_index - 1U];
}

uint16_t ramPoolAvailable() {
  uint16_t used = 0U;
  for (const auto& slot : g_slots) {
    if (slot.allocated) {
      used = static_cast<uint16_t>(used + 1U);
    }
  }
  return static_cast<uint16_t>(kRamPoolSize - min<uint16_t>(kRamPoolSize, used * 128U));
}

void refreshFeatureReports() {
  g_block_load_report.report_id = kReportIdBlockLoad;
  g_block_load_report.ram_pool_available = ramPoolAvailable();

  g_pool_report.report_id = kReportIdPool;
  g_pool_report.ram_pool_size = kRamPoolSize;
  g_pool_report.max_simultaneous_effects = static_cast<uint8_t>(sizeof(g_slots) / sizeof(g_slots[0]));
  g_pool_report.flags = 0x01U;  // Device managed pool.
}

void stopAllEffects() {
  for (auto& slot : g_slots) {
    slot.running = false;
  }
}

void freeSlot(EffectSlot& slot) { slot = EffectSlot{}; }

void allocateEffect(uint8_t effect_type) {
  g_block_load_report.effect_block_index = 0U;
  g_block_load_report.load_status = kBlockLoadError;
  g_state.last_allocated_effect = 0U;
  g_state.last_load_status = kBlockLoadError;

  if (!isSupportedEffectType(effect_type)) {
    refreshFeatureReports();
    return;
  }

  for (uint8_t index = 0; index < 4U; ++index) {
    auto& slot = g_slots[index];
    if (slot.allocated) {
      continue;
    }
    slot = EffectSlot{};
    slot.allocated = true;
    slot.configured = true;
    slot.type = effect_type;
    slot.gain = 255;
    const uint8_t effect_block_index = static_cast<uint8_t>(index + 1U);
    g_block_load_report.effect_block_index = effect_block_index;
    g_block_load_report.load_status = kBlockLoadSuccess;
    g_state.last_allocated_effect = effect_block_index;
    g_state.last_load_status = kBlockLoadSuccess;
    refreshFeatureReports();
    return;
  }

  g_block_load_report.load_status = kBlockLoadFull;
  g_state.last_load_status = kBlockLoadFull;
  refreshFeatureReports();
}

}  // namespace

namespace hid_ffb {

void init() {
  g_state = DeviceState{};
  g_state.global_gain = 255;
  for (auto& slot : g_slots) {
    slot = EffectSlot{};
  }
  g_block_load_report = BlockLoadFeatureReport{};
  g_pool_report = PoolFeatureReport{};
  refreshFeatureReports();
}

size_t expectedReportLength(uint8_t report_id) {
  switch (report_id) {
    case kReportIdSetEffect:
      return sizeof(SetEffectReport);
    case kReportIdSetConstantForce:
      return sizeof(SetConstantForceReport);
    case kReportIdSetCondition:
      return sizeof(SetConditionReport);
    case kReportIdEffectOperation:
      return sizeof(EffectOperationReport);
    case kReportIdDeviceControl:
      return sizeof(DeviceControlReport);
    case kReportIdDeviceGain:
      return sizeof(DeviceGainReport);
    case kReportIdCreateNewEffect:
      return sizeof(CreateNewEffectReport);
    case kReportIdBlockFree:
      return sizeof(BlockFreeReport);
    default:
      return 0U;
  }
}

bool handleReport(uint8_t report_id, const uint8_t* data, size_t length) {
  if (data == nullptr || length == 0U) {
    return false;
  }

  g_state.last_report_id = report_id;
  ++g_state.rx_reports;

  switch (report_id) {
    case kReportIdSetEffect: {
      if (length != sizeof(SetEffectReport)) {
        return false;
      }
      const auto& report = *reinterpret_cast<const SetEffectReport*>(data);
      auto* slot = slotForIndex(report.effect_block_index);
      if (slot == nullptr || !slot->allocated || !isSupportedEffectType(report.effect_type)) {
        return false;
      }
      slot->configured = true;
      slot->type = report.effect_type;
      slot->gain = report.gain;
      return true;
    }
    case kReportIdSetConstantForce: {
      if (length != sizeof(SetConstantForceReport)) {
        return false;
      }
      const auto& report = *reinterpret_cast<const SetConstantForceReport*>(data);
      auto* slot = slotForIndex(report.effect_block_index);
      if (slot == nullptr || !slot->allocated) {
        return false;
      }
      slot->configured = true;
      slot->type = kEffectTypeConstant;
      slot->magnitude = report.magnitude;
      return true;
    }
    case kReportIdSetCondition: {
      if (length != sizeof(SetConditionReport)) {
        return false;
      }
      const auto& report = *reinterpret_cast<const SetConditionReport*>(data);
      auto* slot = slotForIndex(report.effect_block_index);
      if (slot == nullptr || !slot->allocated) {
        return false;
      }
      if (report.parameter_block_offset != 0U) {
        // This wheel exposes a single steering axis, so only axis index 0 is valid.
        return false;
      }
      slot->configured = true;
      slot->condition_cp_offset = report.cp_offset;
      slot->condition_positive = report.positive_coefficient;
      slot->condition_negative = report.negative_coefficient;
      return true;
    }
    case kReportIdEffectOperation: {
      if (length != sizeof(EffectOperationReport)) {
        return false;
      }
      const auto& report = *reinterpret_cast<const EffectOperationReport*>(data);
      auto* slot = slotForIndex(report.effect_block_index);
      if (slot == nullptr || !slot->allocated) {
        return false;
      }
      if (report.operation == kEffectOpStop) {
        slot->running = false;
      } else if (report.operation == kEffectOpStart || report.operation == kEffectOpStartSolo) {
        if (report.operation == kEffectOpStartSolo) {
          stopAllEffects();
        }
        slot->running = slot->configured;
      }
      return true;
    }
    case kReportIdDeviceControl: {
      if (length != sizeof(DeviceControlReport)) {
        return false;
      }
      const auto& report = *reinterpret_cast<const DeviceControlReport*>(data);
      switch (report.control) {
        case kDeviceControlEnableActuators:
          g_state.actuators_enabled = true;
          g_state.device_paused = false;
          return true;
        case kDeviceControlDisableActuators:
          g_state.actuators_enabled = false;
          stopAllEffects();
          return true;
        case kDeviceControlStopAllEffects:
          stopAllEffects();
          return true;
        case kDeviceControlReset:
          init();
          return true;
        case kDeviceControlPause:
          g_state.device_paused = true;
          return true;
        case kDeviceControlContinue:
          g_state.device_paused = false;
          return true;
        default:
          return false;
      }
    }
    case kReportIdDeviceGain: {
      if (length != sizeof(DeviceGainReport)) {
        return false;
      }
      const auto& report = *reinterpret_cast<const DeviceGainReport*>(data);
      g_state.global_gain = report.gain;
      return true;
    }
    case kReportIdCreateNewEffect: {
      if (length != sizeof(CreateNewEffectReport)) {
        return false;
      }
      const auto& report = *reinterpret_cast<const CreateNewEffectReport*>(data);
      UNUSED(report.byte_count);
      allocateEffect(report.effect_type);
      return true;
    }
    case kReportIdBlockFree: {
      if (length != sizeof(BlockFreeReport)) {
        return false;
      }
      const auto& report = *reinterpret_cast<const BlockFreeReport*>(data);
      auto* slot = slotForIndex(report.effect_block_index);
      if (slot == nullptr || !slot->allocated) {
        return false;
      }
      freeSlot(*slot);
      refreshFeatureReports();
      return true;
    }
    default:
      return false;
  }
}

uint8_t* getFeatureReport(uint8_t report_id, uint8_t report_type, uint16_t* report_length) {
  if (report_length == nullptr || report_type != kReportTypeFeature) {
    return nullptr;
  }

  switch (report_id) {
    case kReportIdBlockLoad:
      refreshFeatureReports();
      *report_length = sizeof(g_block_load_report);
      return reinterpret_cast<uint8_t*>(&g_block_load_report);
    case kReportIdPool:
      refreshFeatureReports();
      *report_length = sizeof(g_pool_report);
      return reinterpret_cast<uint8_t*>(&g_pool_report);
    default:
      return nullptr;
  }
}

void update() {
  HostFfbOverlay overlay{};

  if (g_state.actuators_enabled && !g_state.device_paused) {
    for (const auto& slot : g_slots) {
      if (!slot.running) {
        continue;
      }
      overlay.active = true;
      const uint8_t effective_gain =
          static_cast<uint8_t>((static_cast<uint16_t>(slot.gain) * g_state.global_gain) / 255U);
      switch (slot.type) {
        case kEffectTypeConstant:
          overlay.constant_torque += signedTorque(slot.magnitude, effective_gain);
          break;
        case kEffectTypeSpring:
          overlay.spring_center_deg = 0.0f;
          overlay.spring_gain =
              max(overlay.spring_gain, conditionGain(slot.condition_positive, effective_gain, app::kSpringMax));
          break;
        case kEffectTypeDamper:
          overlay.damper_gain =
              max(overlay.damper_gain, conditionGain(slot.condition_positive, effective_gain, app::kDamperMax));
          break;
        case kEffectTypeFriction:
          overlay.friction_gain =
              max(overlay.friction_gain, conditionGain(slot.condition_positive, effective_gain, app::kFrictionMax));
          break;
        default:
          break;
      }
    }
  }

  if (overlay.active) {
    control::setHostFfbOverlay(overlay);
  } else {
    control::clearHostFfbOverlay();
  }
}

DeviceState getState() { return g_state; }

}  // namespace hid_ffb
