# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project_root = Path(SPEC).resolve().parent.parent

datas = [
    (str(project_root / "profiles"), "profiles"),
    (str(project_root / "docs"), "docs"),
    (str(project_root / ".research" / "ets2-telemetry-server" / "server"), "ets2_telemetry_server"),
]

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "hid",
    "serial",
    "serial.tools.list_ports",
    "vgamepad",
    "vgamepad.win.virtual_gamepad",
    "vgamepad.win.vigem_client",
    "vgamepad.win.vigem_commons",
]

vg_datas, vg_binaries, vg_hiddenimports = collect_all("vgamepad")
datas += vg_datas
hiddenimports += vg_hiddenimports
hid_datas, hid_binaries, hid_hiddenimports = collect_all("hid")
datas += hid_datas
hiddenimports += hid_hiddenimports

block_cipher = None

a = Analysis(
    [str(project_root / "pc_app" / "main.py")],
    pathex=[str(project_root / "pc_app")],
    binaries=vg_binaries + hid_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ETS2WheelTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ETS2WheelTool",
)
