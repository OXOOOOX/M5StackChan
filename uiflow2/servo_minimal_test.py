import time

import M5
from M5 import *


RESET_ON_EXIT = False

START_RECT = (8, 154, 145, 42)
EXIT_RECT = (167, 154, 145, 42)


running = True
touch_was_down = False

status_label = None
step_label = None
hint_label = None
start_button = None
exit_button = None


def setup_screen():
    global status_label, step_label, hint_label, start_button, exit_button
    M5.begin()
    Widgets.fillScreen(0x101418)
    Widgets.Title("Servo UI Test", 3, 0xFFFFFF, 0x2B6CB0, Widgets.FONTS.DejaVu18)
    status_label = Widgets.Label("UI ready: servo code disabled", 8, 44, 1.0, 0x8FE388, 0x101418, Widgets.FONTS.DejaVu18)
    step_label = Widgets.Label("tap Start to test button only", 8, 84, 1.0, 0xFFFFFF, 0x101418, Widgets.FONTS.DejaVu18)
    start_button = Widgets.Label("  Start test  ", 14, 166, 1.0, 0xFFFFFF, 0x2B6CB0, Widgets.FONTS.DejaVu18)
    exit_button = Widgets.Label("      Exit      ", 190, 166, 1.0, 0xFFFFFF, 0xB23A48, Widgets.FONTS.DejaVu18)
    hint_label = Widgets.Label("no UART in this version", 8, 214, 1.0, 0x9AA4AF, 0x101418, Widgets.FONTS.DejaVu18)


def set_text(label, text):
    if label:
        label.setText(text)


def point_in_rect(x, y, rect):
    rx, ry, rw, rh = rect
    return x >= rx and x <= rx + rw and y >= ry and y <= ry + rh


def read_touch_point():
    touch = None
    if hasattr(M5, "Touch"):
        touch = M5.Touch
    elif "Touch" in globals():
        touch = Touch
    else:
        return None

    count = 0
    try:
        if hasattr(touch, "getCount"):
            count = touch.getCount()
    except Exception:
        count = 0

    try:
        detail = touch.getDetail()
        if hasattr(detail, "wasPressed") and detail.wasPressed():
            return detail.x, detail.y
        if count > 0 and hasattr(detail, "isPressed") and detail.isPressed():
            return detail.x, detail.y
    except Exception:
        pass

    if count <= 0:
        return None

    try:
        x = touch.getX()
        y = touch.getY()
        if x >= 0 and y >= 0:
            return x, y
    except Exception:
        pass

    return None


def handle_touch():
    global running, touch_was_down

    point = read_touch_point()
    if point is None:
        touch_was_down = False
        return

    if touch_was_down:
        return

    touch_was_down = True
    x, y = point
    if point_in_rect(x, y, START_RECT):
        set_text(status_label, "Start touched")
        set_text(step_label, "servo code still disabled")
        set_text(start_button, "   Touched    ")
    elif point_in_rect(x, y, EXIT_RECT):
        running = False


def finish():
    set_text(status_label, "stopped")
    set_text(step_label, "finished")
    if RESET_ON_EXIT:
        import machine

        machine.reset()


def main():
    setup_screen()
    while running:
        M5.update()
        handle_touch()
        time.sleep_ms(20)
    finish()


try:
    main()
except (Exception, KeyboardInterrupt) as e:
    try:
        from utility import print_error_msg

        print_error_msg(e)
    except ImportError:
        print(e)
