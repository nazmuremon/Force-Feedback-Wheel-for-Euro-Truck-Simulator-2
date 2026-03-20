# Project Setup

This repo now targets a DIY Euro Truck Simulator 2 force-feedback wheel built around an STM32G4.

## Main parts

- STM32 firmware in [`src/main.cpp`](/d:/stmtest/src/main.cpp) and the supporting modules under [`src`](/d:/stmtest/src)
- Windows setup and runtime GUI in [`pc_app/main.py`](/d:/stmtest/pc_app/main.py)
- Protocol documentation in [`docs/PROTOCOL.md`](/d:/stmtest/docs/PROTOCOL.md)
- Wiring documentation and diagram in [`docs/WIRING.md`](/d:/stmtest/docs/WIRING.md)

## Current hardware assumptions

- Board: `NUCLEO-G431KB`
- Encoder: `C38S6G5 2000Z`
- Driver: `BTS7960`
- Pedals: two `100k` potentiometers
- Standard runtime PC link: native USB HID on `PA11/PA12`
- Flashing and debug link: built-in `ST-LINK/V3E` USB

## Recommended bring-up order

1. Wire encoder and pedals first.
2. Flash firmware.
3. Confirm sensor readings in the Windows tool.
4. Wire BTS7960 logic next.
5. Apply very low motor power and verify direction.
6. Only then enable virtual FFB tests.
7. Add ETS2 telemetry last.

## ETS2 runtime note

For real Euro Truck Simulator 2 driving, the PC app expects the bundled ETS2 telemetry/shared-memory plugin, with optional HTTP bridge fallback on `127.0.0.1:25555`.

The SCS forum `FFB plugin v2.6` is a separate Logitech-wheel plugin. For this DIY STM32 wheel, we keep ETS2 in-game FFB off and let the helper app generate the wheel torque from telemetry instead.

Recommended order:

1. Launch the wheel app so it can install the bundled ETS2 telemetry plugin if needed.
2. Keep ETS2 in-game force feedback disabled.
3. Launch ETS2. Optionally start an HTTP telemetry bridge on `127.0.0.1:25555` as a fallback path.
4. Turn off `Virtual test mode`.
5. Verify the `ETS2 Runtime` tab reports live telemetry before enabling motor torque.

If the game telemetry is not available, the app now keeps FFB output at zero in live mode for safety.

## Current app build

For the current portable Windows test build in this workspace, use:

- [`dist_game_targeted/ETS2WheelTool/ETS2WheelTool.exe`](/d:/stmtest/dist_game_targeted/ETS2WheelTool/ETS2WheelTool.exe)

Older `dist_*` and `build_*` folders are generated test artifacts and can be deleted.

## Important note

The standard project configuration in this repo is the native USB HID build. The STM32 exposes:

- a HID game controller for Windows and ETS2
- a vendor-defined HID transport channel for the desktop app

This uses one runtime USB cable on `PA11/PA12`, while the built-in `ST-LINK/V3E` USB remains the recommended path for flashing and debugging.
