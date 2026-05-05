import struct
import time

import espnow
import network
from machine import UART


# Match the remote controller settings.
RECEIVER_ID = 1
WIFI_CHANNEL = 1

# Official StackChan servo configuration.
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


uart = UART(
    SERVO_UART_ID,
    baudrate=SERVO_BAUD,
    tx=SERVO_TX_PIN,
    rx=SERVO_RX_PIN,
    bits=8,
    parity=None,
    stop=1,
)


def clamp(value, min_value, max_value):
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def scs_write(servo_id, address, data):
    params = bytes([address]) + bytes(data)
    length = len(params) + 2
    body = bytes([servo_id, length, INST_WRITE]) + params
    checksum = (~sum(body)) & 0xFF
    uart.write(b"\xff\xff" + body + bytes([checksum]))


def set_torque(servo_id, enabled):
    scs_write(servo_id, SCSCL_TORQUE_ENABLE, [1 if enabled else 0])


def angle_to_raw(angle, zero_pos):
    # Official firmware mapping:
    # raw = zero + angle * 16 / 5 / 10
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
    yaw_angle = clamp(yaw_angle, YAW_MIN_ANGLE, YAW_MAX_ANGLE)
    pitch_angle = clamp(pitch_angle, PITCH_MIN_ANGLE, PITCH_MAX_ANGLE)
    speed = clamp(speed, 0, 1000)

    yaw_raw = angle_to_raw(yaw_angle, YAW_ZERO_POS)
    pitch_raw = angle_to_raw(pitch_angle, PITCH_ZERO_POS)
    write_servo_position(YAW_SERVO_ID, yaw_raw, move_time=20, speed=speed)
    write_servo_position(PITCH_SERVO_ID, pitch_raw, move_time=20, speed=speed)


def init_espnow():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.disconnect()
    try:
        wlan.config(channel=WIFI_CHANNEL)
    except Exception:
        # Some UIFlow2 firmware builds do not expose channel config.
        pass

    esp = espnow.ESPNow()
    esp.active(True)
    return esp


def parse_remote_packet(packet):
    # Official remote packet:
    # [target-id uint8] [yaw int16 LE] [pitch int16 LE] [speed int16 LE] [laser uint8]
    if len(packet) < 8:
        return None
    target_id, yaw, pitch, speed, laser = struct.unpack("<BhhhB", packet[:8])
    if target_id != 0 and target_id != RECEIVER_ID:
        return None
    return yaw, pitch, speed, bool(laser)


def main():
    set_torque(YAW_SERVO_ID, True)
    set_torque(PITCH_SERVO_ID, True)
    move_stackchan(0, 0, 500)

    esp = init_espnow()
    last_packet_ms = time.ticks_ms()

    while True:
        host, packet = esp.recv(20)
        if packet:
            parsed = parse_remote_packet(packet)
            if parsed:
                yaw, pitch, speed, laser = parsed
                move_stackchan(yaw, pitch, speed)
                last_packet_ms = time.ticks_ms()

        # Return to center if the remote stops sending for 1.5s.
        if time.ticks_diff(time.ticks_ms(), last_packet_ms) > 1500:
            move_stackchan(0, 0, 400)
            last_packet_ms = time.ticks_ms()

        time.sleep_ms(10)


print("This script drives StackChan servos directly.")
print("Run uiflow2_espnow_packet_monitor.py first and confirm packets are received.")
print("After confirmation, remove the next line and call main().")
# main()
