# DIY ETS2 Force Feedback Wheel For STM32G4

This project builds a complete USB HID force-feedback wheel stack around an STM32G4 controller, a BTS7960 motor driver, a quadrature encoder, and two pedal potentiometers.

## Project structure

```text
.
|-- docs/
|-- include/
|-- pc_app/
|-- profiles/
|-- src/
|-- mouse-dodge.html
|-- platformio.ini
`-- PROJECT_SETUP.md
```

## What is implemented

- STM32 firmware for encoder, pedals, BTS7960 control, safety logic, and USB HID transport
- Integrated Windows PySide6 setup and runtime tool
- Virtual test mode for force tuning without ETS2
- ETS2 live runtime support through a local telemetry bridge server on `127.0.0.1:25555`
- Virtual Xbox controller output so ETS2 can detect a gaming controller on Windows
- Wiring documentation, protocol specification, sample profile, and bring-up procedure

## Safety warnings

- Start with the motor mechanically unloaded if possible.
- Keep `kPwmClamp` in [`include/app_config.h`](/d:/stmtest/include/app_config.h) low until direction is verified.
- Use a real motor power fuse and physical emergency stop.
- Do not hold the wheel during first torque tests.

## Build

### Firmware

```powershell
platformio run
platformio run -t upload
```

Native USB gamepad firmware for direct Windows/ETS2 detection:

```powershell
platformio run -e nucleo_g431kb_usb_gamepad
platformio run -e nucleo_g431kb_usb_gamepad -t upload
```

### Python app

```powershell
pip install -r pc_app/requirements.txt
python pc_app/main.py
```

### Windows EXE

Build a standalone Windows executable bundle:

```powershell
packaging\build_windows.ps1
```

Output:

```text
dist\ETS2WheelTool\ETS2WheelTool.exe
```

### Real ETS2 compatibility

The Windows app is compatible with the actual Euro Truck Simulator 2 game through its live telemetry path, not only through virtual test mode.

To use the real game:

1. Run an ETS2 telemetry bridge that exposes HTTP on `127.0.0.1:25555`.
2. Start ETS2 and make sure the bridge shows live game data.
3. Open `ETS2WheelTool.exe`.
4. Leave `Expose virtual Xbox controller` enabled so ETS2 sees a controller.
5. Uncheck `Virtual test mode`.
6. Confirm the `ETS2 Runtime` tab shows both the virtual controller and live telemetry before enabling torque.

If live telemetry is missing, the app now holds FFB output at zero in ETS2 mode instead of generating fallback forces.

### Install the software on a Windows PC

You have two ways to use the PC software.

#### Option 1: portable EXE bundle

Use this when you do not want an installer.

1. Copy the folder [dist/ETS2WheelTool](D:/stmtest/dist/ETS2WheelTool) to the target PC.
2. Run [dist/ETS2WheelTool/ETS2WheelTool.exe](D:/stmtest/dist/ETS2WheelTool/ETS2WheelTool.exe).
3. If Windows SmartScreen warns on first launch, use `More info` then `Run anyway` if you trust the build.
4. Connect the NUCLEO board's native USB wiring on `PA11/PA12` to the PC.
5. Select the detected HID device in the app and connect.

You can also copy the portable archive:

```text
dist\ETS2WheelTool-portable.zip
```

Extract it anywhere and run `ETS2WheelTool.exe`.

### Windows installer

1. Install `Inno Setup 6`.
2. Build the executable bundle first.
3. Build the installer:

```powershell
packaging\build_installer.ps1
```

Output:

```text
dist_installer\ETS2WheelToolSetup.exe
```

After building the installer:

1. Run `ETS2WheelToolSetup.exe`.
2. Follow the install wizard.
3. Launch the app from the Start menu or desktop shortcut.
4. Connect the board using the native USB connection on `PA11/PA12`.
5. Choose the detected HID device and connect.

## Communication mode recommendation

For native `USB HID` mode on `NUCLEO-G431KB`, the board can expose:

- a game controller for Windows and games
- a HID control/status link for the desktop app

That native mode uses one USB cable connected to the MCU `PA11/PA12` pins. In this mode the app no longer needs a COM port, and the built-in `ST-LINK` USB is only for flashing/debug when needed.

## First test procedure

1. Flash the STM32 firmware and leave torque disabled.
2. Open the desktop tool and connect to the detected HID device.
3. Verify encoder count, angle, and direction on the `Encoder` tab.
4. Verify brake and accelerator motion on the `Pedals` tab and capture calibration.
5. Enable the motor with a very small torque command on the `Motor Test` tab.
6. Confirm the commanded direction and stop immediately if it is reversed.
7. Use `Virtual Test Mode` before trying ETS2 telemetry.
8. When switching to the real game, disable `Virtual Test Mode` and verify the runtime status turns green for live ETS2 telemetry.

## Docs

- Protocol: [`docs/PROTOCOL.md`](/d:/stmtest/docs/PROTOCOL.md)
- Wiring: [`docs/WIRING.md`](/d:/stmtest/docs/WIRING.md)
- Packaging scripts: [`packaging/build_windows.ps1`](/d:/stmtest/packaging/build_windows.ps1), [`packaging/build_installer.ps1`](/d:/stmtest/packaging/build_installer.ps1)

## Assumptions

- The native USB environment uses a HID control/status path for the desktop app and HID gamepad reports for direct controller detection.
- The current board setup is preserved around the existing NUCLEO-G431KB PlatformIO project.
- Encoder decoding stays on the current `D3` and `D4` pins, which favors interrupt decoding now and leaves timer encoder mode as the next hardware-specific upgrade.
