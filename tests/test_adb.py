from companion.capture.adb import AdbCapture


def test_command_without_serial():
    assert AdbCapture()._cmd() == ["adb", "exec-out", "screencap", "-p"]


def test_command_with_serial():
    assert AdbCapture(serial="R3CN30XXXX")._cmd() == [
        "adb", "-s", "R3CN30XXXX", "exec-out", "screencap", "-p"]
