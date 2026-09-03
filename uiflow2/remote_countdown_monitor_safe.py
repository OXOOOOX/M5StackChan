import struct
import time

import M5
from M5 import *
import espnow
import network


RECEIVER_ID = 1
WIFI_CHANNEL = 1
RUN_SECONDS = 30
RESET_ON_EXIT = False
YAW_MIN = -1280
YAW_MAX = 1280
PITCH_MIN = 0
PITCH_MAX = 900
SPEED_MIN = 0
SPEED_MAX = 1000


running = True
countdown_enabled = True
last_packet_text = "waiting for remote..."
packet_count = 0

status_label = None
timer_label = None
packet_label = None
button_label = None
stop_timer_button = None
exit_button = None
touch_was_down = False
touch_action_fired = False

STOP_TIMER_RECT = (8, 156, 150, 44)
EXIT_RECT = (176, 156, 136, 44)


def setup_screen():
    global status_label, timer_label, packet_label, button_label
    global stop_timer_button, exit_button
    M5.begin()
    Widgets.fillScreen(0x101418)
    Widgets.Title("StackChan Remote", 3, 0xFFFFFF, 0x2B6CB0, Widgets.FONTS.DejaVu18)
    status_label = Widgets.Label("", 8, 42, 1.0, 0x8FE388, 0x101418, Widgets.FONTS.DejaVu18)
    timer_label = Widgets.Label("", 8, 76, 1.0, 0xFFD166, 0x101418, Widgets.FONTS.DejaVu18)
    packet_label = Widgets.Label(last_packet_text, 8, 112, 1.0, 0xFFFFFF, 0x101418, Widgets.FONTS.DejaVu18)
    stop_timer_button = Widgets.Label("  Stop timer  ", 14, 166, 1.0, 0xFFFFFF, 0x2B6CB0, Widgets.FONTS.DejaVu18)
    exit_button = Widgets.Label("      Exit      ", 190, 166, 1.0, 0xFFFFFF, 0xB23A48, Widgets.FONTS.DejaVu18)
    button_label = Widgets.Label("BtnA also stops timer", 8, 214, 1.0, 0x9AA4AF, 0x101418, Widgets.FONTS.DejaVu18)


def set_text(label, text):
    if label:
        label.setText(text)


def init_espnow():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.disconnect()
    try:
        wlan.config(channel=WIFI_CHANNEL)
    except Exception as e:
        print("channel config skipped:", e)

    esp = espnow.ESPNow()
    esp.active(True)
    return esp


def parse_remote_packet(packet):
    if len(packet) != 8:
        return "ignore len={}".format(len(packet))
    target_id, yaw, pitch, speed, laser = struct.unpack("<BhhhB", packet)
    if (yaw < YAW_MIN or yaw > YAW_MAX or
            pitch < PITCH_MIN or pitch > PITCH_MAX or
            speed < SPEED_MIN or speed > SPEED_MAX):
        return "invalid id:{} yaw:{} pitch:{} speed:{}".format(
            target_id, yaw, pitch, speed
        )
    match = target_id == 0 or target_id == RECEIVER_ID
    prefix = "rx" if match else "ignored"
    return "{} id:{} yaw:{} pitch:{} speed:{} laser:{}".format(
        prefix, target_id, yaw, pitch, speed, laser
    )


def handle_buttons():
    global running, countdown_enabled
    if "BtnA" in globals() and BtnA.wasClicked():
        stop_countdown()


def stop_countdown():
    global countdown_enabled
    countdown_enabled = False
    set_text(button_label, "timer stopped: listening continuously")
    set_text(stop_timer_button, " Timer stopped ")


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
    global running, touch_was_down, touch_action_fired

    point = read_touch_point()
    if point is None:
        touch_was_down = False
        touch_action_fired = False
        return

    touch_was_down = True
    if touch_action_fired:
        return

    x, y = point
    if point_in_rect(x, y, STOP_TIMER_RECT):
        touch_action_fired = True
        stop_countdown()
    elif point_in_rect(x, y, EXIT_RECT):
        touch_action_fired = True
        running = False


def main():
    global last_packet_text, packet_count

    setup_screen()
    set_text(status_label, "channel {} / id {} / monitor only".format(WIFI_CHANNEL, RECEIVER_ID))

    esp = init_espnow()
    start_ms = time.ticks_ms()
    last_ui_ms = 0

    while running:
        M5.update()
        handle_buttons()
        handle_touch()

        host, packet = esp.recv(20)
        if packet:
            parsed = parse_remote_packet(packet)
            if parsed:
                packet_count += 1
                last_packet_text = "{} #{}".format(parsed, packet_count)

        now_ms = time.ticks_ms()
        elapsed = time.ticks_diff(now_ms, start_ms) // 1000
        seconds_left = RUN_SECONDS - elapsed
        if countdown_enabled and seconds_left <= 0:
            break

        if time.ticks_diff(now_ms, last_ui_ms) > 250:
            if countdown_enabled:
                set_text(timer_label, "auto exit in {}s".format(max(0, seconds_left)))
            else:
                set_text(timer_label, "timer stopped: continuous run")
            set_text(packet_label, last_packet_text)
            last_ui_ms = now_ms

        time.sleep_ms(10)

    set_text(status_label, "stopped")
    set_text(timer_label, "finished")
    if RESET_ON_EXIT:
        import machine

        machine.reset()


try:
    main()
except (Exception, KeyboardInterrupt) as e:
    try:
        from utility import print_error_msg

        print_error_msg(e)
    except ImportError:
        print(e)
