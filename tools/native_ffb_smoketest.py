import sys
import time

import hid


VID = 0x0483
PID = 0x57FF


def find_wheel_path():
    for dev in hid.enumerate(VID, PID):
        usage_page = dev.get("usage_page")
        usage = dev.get("usage")
        if (usage_page, usage) in ((0x0002, 0x0002), (0x0001, 0x0004)):
            return dev["path"]
    return None


def feature(dev, payload):
    packet = bytes(payload + [0] * (64 - len(payload)))
    return dev.send_feature_report(packet)


def output(dev, payload):
    packet = bytes(payload + [0] * (64 - len(payload)))
    return dev.write(packet)


def main():
    path = find_wheel_path()
    if path is None:
        print("Native FFB wheel collection not found.", file=sys.stderr)
        return 1

    wheel = hid.device()
    wheel.open_path(path)
    wheel.set_nonblocking(1)

    try:
        print("Enable actuators")
        feature(wheel, [0x15, 1])
        time.sleep(0.1)

        print("Set constant-force effect")
        feature(wheel, [0x11, 1, 1, 0, 0, 0, 0, 0, 0, 255, 0, 1, 0, 0])
        feature(wheel, [0x12, 1, 0xFF, 0x7F])
        output(wheel, [0x14, 1, 1, 1])
        time.sleep(1.0)

        print("Reverse force")
        feature(wheel, [0x12, 1, 0x01, 0x80])
        output(wheel, [0x14, 1, 1, 1])
        time.sleep(0.8)

        print("Stop")
        output(wheel, [0x14, 1, 3, 0])
        feature(wheel, [0x15, 2])
        return 0
    finally:
        wheel.close()


if __name__ == "__main__":
    raise SystemExit(main())
