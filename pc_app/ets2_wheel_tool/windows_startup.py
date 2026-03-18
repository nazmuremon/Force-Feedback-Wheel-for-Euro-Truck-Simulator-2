from __future__ import annotations

import sys


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "ETS2DIYFFBWheel"


def _open_run_key():
    import winreg

    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_ALL_ACCESS)


def app_command() -> str:
    executable = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{executable}"'
    return f'"{executable}" -m pc_app.main'


def is_enabled() -> bool:
    try:
        import winreg

        with _open_run_key() as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    import winreg

    with _open_run_key() as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, app_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass
