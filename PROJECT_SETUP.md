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
- PC link during development and normal use: built-in `ST-LINK` USB Virtual COM Port

## Recommended bring-up order

1. Wire encoder and pedals first.
2. Flash firmware.
3. Confirm sensor readings in the Windows tool.
4. Wire BTS7960 logic next.
5. Apply very low motor power and verify direction.
6. Only then enable virtual FFB tests.
7. Add ETS2 telemetry last.

## ETS2 runtime note

For real Euro Truck Simulator 2 driving, the PC app expects a local telemetry bridge on `127.0.0.1:25555`.

Recommended order:

1. Start the telemetry bridge.
2. Launch ETS2 and confirm the bridge sees the game.
3. Open the wheel app.
4. Turn off `Virtual test mode`.
5. Verify the `ETS2 Runtime` tab reports live telemetry before enabling motor torque.

If the game telemetry is not available, the app now keeps FFB output at zero in live mode for safety.

## Important note

The repo keeps the safer serial architecture as the primary path, using the NUCLEO board's built-in `ST-LINK/V3E` USB connection for flashing, debugging, and COM-port communication.

Native `USB HID force-feedback wheel` mode is intentionally not the dependency for the first working system because it is much harder to implement robustly on Windows than the current PC-app-plus-serial approach.
