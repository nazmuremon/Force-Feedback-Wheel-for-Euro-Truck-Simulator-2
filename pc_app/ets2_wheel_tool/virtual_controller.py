from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VirtualControllerStatus:
    active: bool
    message: str


class VirtualControllerBridge:
    def __init__(self) -> None:
        self._controller = None
        self._enabled = False
        self._available = False
        self._error_message = ""
        self._last_state = (None, None, None)
        self._load_backend()

    def _load_backend(self) -> None:
        try:
            import vgamepad as vg
        except Exception as exc:
            self._vg = None
            self._available = False
            self._error_message = f"Virtual controller backend unavailable: {exc}"
            return
        self._vg = vg
        self._available = True

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self._detach()
            return
        self._ensure_attached()

    def _ensure_attached(self) -> None:
        if self._controller is not None or not self._available:
            return
        try:
            self._controller = self._vg.VX360Gamepad()
            self._error_message = ""
        except Exception as exc:
            self._controller = None
            self._available = False
            self._error_message = (
                "Virtual Xbox controller unavailable. Install or repair the ViGEmBus driver, "
                f"then restart the app. Details: {exc}"
            )

    def _detach(self) -> None:
        if self._controller is None:
            return
        try:
            self._controller.reset()
            self._controller.update()
        except Exception:
            pass
        self._controller = None
        self._last_state = (None, None, None)

    def update_inputs(self, steer: float, brake: float, throttle: float) -> None:
        if not self._enabled:
            return
        self._ensure_attached()
        if self._controller is None:
            return
        steer = max(-1.0, min(1.0, steer))
        brake = max(0.0, min(1.0, brake))
        throttle = max(0.0, min(1.0, throttle))
        state = (round(steer, 4), round(brake, 4), round(throttle, 4))
        if state == self._last_state:
            return
        self._controller.left_joystick_float(steer, 0.0)
        self._controller.left_trigger_float(brake)
        self._controller.right_trigger_float(throttle)
        self._controller.update()
        self._last_state = state

    def reset_inputs(self) -> None:
        if self._controller is None:
            return
        self._controller.reset()
        self._controller.update()
        self._last_state = (0.0, 0.0, 0.0)

    def close(self) -> None:
        self._detach()

    def status(self) -> VirtualControllerStatus:
        if not self._enabled:
            return VirtualControllerStatus(False, "Virtual Xbox controller disabled.")
        if self._controller is not None:
            return VirtualControllerStatus(True, "Virtual Xbox controller is active for ETS2.")
        if self._error_message:
            return VirtualControllerStatus(False, self._error_message)
        if not self._available:
            return VirtualControllerStatus(False, "Virtual Xbox controller backend is not available.")
        return VirtualControllerStatus(False, "Preparing virtual Xbox controller...")
