import struct
import time

import M5
from M5 import *
import espnow
import network


RECEIVER_ID = 1
WIFI_CHANNEL = 1
RUN_SECONDS = 30

# Keep this False until the UI runs reliably on the device.
ENABLE_SERVO_CONTROL = False

SERVO_UART_ID = 1
SERVO_TX_PIN = 6
SERVO_RX_PIN = 7
SERVO_BAUD = 1000000

YAW_SERVO_ID = 1
PITCH_SERVO_ID = 2
YAW_ZERO_POS = 460
PITCH_ZERO_POS = 620

YAW_MIN_ANGLE = -1280
YAW_MAX_ANGLE = 1280
PITCH_MIN_ANGLE = 0
PITCH_MAX_ANGLE = 900
RAW_MIN_POS = 0
RAW_MAX_POS = 1000

SCSCL_TORQUE_ENABLE = 40
SCSCL_GOAL_POSITION_L = 42
INST_WRITE = 0x03


running = True
countdown_enabled = True
last_packet_text = "waiting for remote..."
uart = None

status_label = None
timer_label = None
packet_label = None
button_label = None


def clamp(value, min_value, max_value):
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def setup_screen():
    global status_label, timer_label, packet_label, button_label
    M5.begin()
    Widgets.fillScreen(0x101418)
    Widgets.Title("StackChan Remote", 3, 0xFFFFFF, 0x2B6CB0, Widgets.FONTS.DejaVu18)
    status_label = Widgets.Label("", 8, 42, 1.0, 0x8FE388, 0x101418, Widgets.FONTS.DejaVu18)
    timer_label = Widgets.Label("", 8, 76, 1.0, 0xFFD166, 0x101418, Widgets.FONTS.DejaVu18)
    packet_label = Widgets.Label(last_packet_text, 8, 112, 1.0, 0xFFFFFF, 0x101418, Widgets.FONTS.DejaVu18)
    button_label = Widgets.Label("BtnA: stop timer   PWR: exit", 8, 204, 1.0, 0x9AA4AF, 0x101418, Widgets.FONTS.DejaVu18)


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


def init_servo_uart():
    global uart
    if uart:
        return
    from machine import UART

    uart = UART(
        SERVO_UART_ID,
        baudrate=SERVO_BAUD,
        tx=SERVO_TX_PIN,
        rx=SERVO_RX_PIN,
        bits=8,
        parity=None,
        stop=1,
    )


def scs_write(servo_id, address, data):
    if not uart:
        return
    params = bytes([address]) + bytes(data)
    length = len(params) + 2
    body = bytes([servo_id, length, INST_WRITE]) + params
    checksum = (~sum(body)) & 0xFF
    uart.write(b"\xff\xff" + body + bytes([checksum]))


def set_torque(servo_id, enabled):
    scs_write(servo_id, SCSCL_TORQUE_ENABLE, [1 if enabled else 0])


def angle_to_raw(angle, zero_pos):
    raw = int(zero_pos + angle * 16 / 50)
    return clamp(raw, RAW_MIN_POS, RAW_MAX_POS)


def write_servo_position(servo_id, raw_position, move_time=20, speed=0):
    raw_position = clamp(raw_position, RAW_MIN_POS, RAW_MAX_POS)
    move_time = clamp(int(move_time), 0, 1000)
    speed = clamp(int(speed), 0, 1000)
    scs_write(
        servo_id,
        SCSCL_GOAL_POSITION_L,
        [
            raw_position & 0xFF,
            (raw_position >> 8) & 0xFF,
            move_time & 0xFF,
            (move_time >> 8) & 0xFF,
            speed & 0xFF,
            (speed >> 8) & 0xFF,
        ],
    )


def move_stackchan(yaw_angle, pitch_angle, speed):
    if not ENABLE_SERVO_CONTROL:
        return
    yaw_angle = clamp(yaw_angle, YAW_MIN_ANGLE, YAW_MAX_ANGLE)
    pitch_angle = clamp(pitch_angle, PITCH_MIN_ANGLE, PITCH_MAX_ANGLE)
    speed = clamp(speed, 0, 1000)
    write_servo_position(YAW_SERVO_ID, angle_to_raw(yaw_angle, YAW_ZERO_POS), 20, speed)
    write_servo_position(PITCH_SERVO_ID, angle_to_raw(pitch_angle, PITCH_ZERO_POS), 20, speed)


def stop_motion():
    if not ENABLE_SERVO_CONTROL:
        return
    move_stackchan(0, 0, 400)
    time.sleep_ms(80)
    set_torque(YAW_SERVO_ID, False)
    set_torque(PITCH_SERVO_ID, False)


def parse_remote_packet(packet):
    if len(packet) < 8:
        return None
    target_id, yaw, pitch, speed, laser = struct.unpack("<BhhhB", packet[:8])
    if target_id != 0 and target_id != RECEIVER_ID:
        return None
    return target_id, yaw, pitch, speed, laser


def handle_buttons():
    global running, countdown_enabled
    if "BtnA" in globals() and BtnA.wasClicked():
        countdown_enabled = False
        set_text(button_label, "timer stopped   PWR: exit")
    if "BtnPWR" in globals() and BtnPWR.wasClicked():
        running = False


def main():
    global last_packet_text

    setup_screen()
    mode = "servo ON" if ENABLE_SERVO_CONTROL else "monitor only"
    set_text(status_label, "channel {} / id {} / {}".format(WIFI_CHANNEL, RECEIVER_ID, mode))

    if ENABLE_SERVO_CONTROL:
        init_servo_uart()
        set_torque(YAW_SERVO_ID, True)
        set_torque(PITCH_SERVO_ID, True)
        move_stackchan(0, 0, 500)

    esp = init_espnow()
    start_ms = time.ticks_ms()
    last_ui_ms = 0
    last_packet_ms = time.ticks_ms()

    while running:
        M5.update()
        handle_buttons()

        host, packet = esp.recv(20)
        if packet:
            parsed = parse_remote_packet(packet)
            if parsed:
                target_id, yaw, pitch, speed, laser = parsed
                move_stackchan(yaw, pitch, speed)
                last_packet_text = "id:{} yaw:{} pitch:{} speed:{} laser:{}".format(
                    target_id, yaw, pitch, speed, laser
                )
                last_packet_ms = time.ticks_ms()

        now_ms = time.ticks_ms()
        if ENABLE_SERVO_CONTROL and time.ticks_diff(now_ms, last_packet_ms) > 1500:
            move_stackchan(0, 0, 400)
            last_packet_ms = now_ms

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

    set_text(status_label, "exiting...")
    set_text(timer_label, "servo stopped")
    stop_motion()
    set_text(status_label, "stopped")


try:
    main()
except (Exception, KeyboardInterrupt) as e:
    try:
        from utility import print_error_msg

        print_error_msg(e)
    except ImportError:
        print(e)
