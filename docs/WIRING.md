# Wiring And Safety Notes

## Suggested STM32G4 pin map

Default target board in this repo is `NUCLEO-G431KB`.

| Function | Pin |
|---|---|
| Encoder A | `D3` |
| Encoder B | `D4` |
| BTS7960 `RPWM` | `D9` |
| BTS7960 `LPWM` | `D10` |
| BTS7960 `R_EN` | `D6` |
| BTS7960 `L_EN` | `D5` |
| Brake potentiometer wiper | `A0` |
| Accelerator potentiometer wiper | `A1` |
| PC connection for flashing/debug | NUCLEO `ST-LINK` Micro-USB port |
| PC connection for native HID runtime | MCU `PA11 / D10` and `PA12 / D2` USB data lines |

## PC connection options

### Development USB: built-in ST-LINK

On `NUCLEO-G431KB`, the built-in `ST-LINK/V3E` USB connector is the normal way to connect the board to the PC during development.

Use it for:

- flashing firmware
- debugging
- powering the board logic during setup and testing

It is useful during bring-up, but it is not the runtime game-controller link.

### Important distinction: ST-LINK serial is not the same as native USB HID

The built-in ST-LINK USB connection is not the target MCU directly behaving like a USB steering wheel.

It is:

- an on-board debug/programming interface
- a separate development/debug USB path, not the runtime HID controller link

If you later want true native `USB HID wheel` behavior, that is a different mode and usually requires:

- target USB device firmware on the STM32 itself
- USB D+ / D- support on the target MCU wiring
- HID descriptors and Windows game-controller compatibility work
- force-feedback HID implementation if you want native FFB

### Native USB HID mode in this repo

The `nucleo_g431kb_usb_gamepad` firmware environment turns the STM32 into a direct USB HID device over `PA11/PA12`.

In this mode, one USB cable can carry both:

- the HID game controller seen by Windows and ETS2
- the HID control/status link used by the desktop app

Important wiring changes for this mode:

- `PA12 / D2` becomes native `USB D+`
- `PA11 / D10` becomes native `USB D-`
- motor `LPWM` moves from `D10` to `D11`

This mode requires a native USB connection to the target MCU pins. The built-in ST-LINK USB connector still handles flashing/debug and is not the joystick connection.

## Wiring diagram

```text
PC USB
  |
  +----------------------------> NUCLEO-G431KB native USB on PA11/PA12
                                   |
                                   +--> HID game controller
                                   +--> HID link to PC app

C38S6G5 Encoder                    NUCLEO-G431KB
----------------                   ----------------
Channel A -----------------------> D3
Channel B -----------------------> D4
GND -----------------------------> GND
VCC -----------------------------> encoder supply matched to encoder spec
Index Z -------------------------> optional / not used by default firmware

Brake Potentiometer               NUCLEO-G431KB
-------------------               ----------------
One outer leg -------------------> 3V3
Other outer leg -----------------> GND
Wiper ---------------------------> A0

Accelerator Potentiometer         NUCLEO-G431KB
-------------------------         ----------------
One outer leg -------------------> 3V3
Other outer leg -----------------> GND
Wiper ---------------------------> A1

NUCLEO-G431KB                     BTS7960
-------------                     --------
D9 ------------------------------> RPWM
D10 -----------------------------> LPWM
D6 ------------------------------> R_EN
D5 ------------------------------> L_EN
GND -----------------------------> GND

BTS7960 Power Side
------------------
Motor supply + ------------------> BTS7960 B+
Motor supply - ------------------> BTS7960 B-
DC motor lead 1 -----------------> BTS7960 M+
DC motor lead 2 -----------------> BTS7960 M-
MCU GND and motor PSU GND ------- common ground
```

## Power notes

- The built-in ST-LINK USB can power the STM32 board logic during development.
- Do not power the motor from USB.
- The `BTS7960` motor stage must use a separate motor power supply sized for the motor.
- Keep the motor supply ground common with the STM32 ground.
- If the motor supply is noisy, keep wiring short and consider extra decoupling near the driver.

## Protection notes

- Keep the motor power supply separate from USB power.
- Common ground between STM32, BTS7960 logic side, pedals, and encoder is mandatory.
- Add a fuse on the motor supply.
- Add a physical emergency stop or power disconnect in series with the motor supply.
- Start testing with the wheel unloaded or the motor mechanically decoupled.
- Confirm encoder direction before enabling torque.
- If your encoder outputs `5V` push-pull signals, level-shift them before connecting to STM32 GPIO.

## Should you use HID mode instead?

Short answer: not for the first working version of this build.

`ST-LINK` is better when:

- you want easier debugging and logging
- you want safer bring-up and tuning
- you are only flashing and debugging

`Native HID mode` is better when:

- you want games to see the controller directly as a wheel or joystick
- you want the PC app and the controller to share one native USB cable
- you are ready to implement and debug HID descriptors and Windows compatibility

`Native HID force-feedback wheel mode` is only better if fully implemented correctly. It is still the more complex path, but it enables the single-cable setup.
