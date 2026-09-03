"""
remote_servo_controller.py — StackChan ESP-NOW remote servo controller (v0.3.0).

Self-contained script — no external imports needed.
Paste directly into UIFlow2 and run.

Flow:
    1. Draw UI
    2. User taps [Start] → enable servo power → ping → enter control loop
    3. Control loop: receive packets → map → move servos → update UI
    4. [Stop] → disable torque → idle
    5. [Exit] → full shutdown → exit
"""

import struct
import time

import M5
from M5 import *
import espnow
import network


# ===================================================================
# Configuration — change these to match your remote
# ===================================================================

RECEIVER_ID = 1
WIFI_CHANNEL = 1
ACCEPT_BROADCAST_ID = True
AUTO_PAIR_REMOTE = False
PAIR_YAW_THRESHOLD = 120
PAIR_PITCH_THRESHOLD = 120
PACKET_IDLE_CENTER_MS = 3000
DROP_ABNORMAL_PACKET = True


# ===================================================================
# Inline Servo Driver (from lib/servo.py)
# ===================================================================

PY32_I2C_ADDR = 0x6F
I2C_SDA_PIN = 12
I2C_SCL_PIN = 11
REG_VERSION = 0x02
REG_GPIO_M_L = 0x03
REG_GPIO_O_L = 0x05
REG_GPIO_PU_L = 0x09
VM_EN_PIN = 0

SERVO_UART_ID = 1
SERVO_TX_PIN = 6
SERVO_RX_PIN = 7
SERVO_BAUD = 1000000

YAW_ID = 1
PITCH_ID = 2
YAW_ZERO = 510
PITCH_ZERO = 610
YAW_RAW_SPAN = 1024
YAW_STEPS_PER_DEGREE = YAW_RAW_SPAN / 360
PITCH_STEPS_PER_DEGREE = 3.41

# Device home pose. This is the power-on/no-packet/stop pose.
# It is intentionally separate from joystick mapping below.
HOME_YAW_DEG = 0
HOME_PITCH_DEG = 0

YAW_MIN_DEG = 0
YAW_MAX_DEG = 360
PITCH_MIN_DEG = 0
PITCH_MAX_DEG = 90

SCSCL_GOAL_POSITION_L = 42
SCSCL_TORQUE_ENABLE = 40
INST_PING = 0x01
INST_WRITE = 0x03

POWER_SETTLE_MS = 250
PING_TIMEOUT_MS = 180
DEFAULT_MOVE_TIME_MS = 200
MIN_COMMAND_INTERVAL_MS = 20


class ServoController:

    def __init__(self):
        self._uart = None
        self._i2c = None
        self._power_on = False
        self._yaw_ready = False
        self._pitch_ready = False
        self._last_cmd_ms = 0

    def enable_power(self):
        from machine import I2C, Pin
        self._i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=100000)
        version = self._i2c_read_reg(REG_VERSION)
        if version == 0 or version == 0xFF:
            return 0
        self._py32_bit_on(REG_GPIO_M_L, VM_EN_PIN)
        self._py32_bit_on(REG_GPIO_PU_L, VM_EN_PIN)
        self._py32_bit_on(REG_GPIO_O_L, VM_EN_PIN)
        time.sleep_ms(POWER_SETTLE_MS)
        self._power_on = True
        return version

    def disable_power(self):
        if self._i2c is None:
            return
        try:
            val = self._i2c_read_reg(REG_GPIO_O_L)
            val &= ~(1 << VM_EN_PIN)
            self._i2c_write_reg(REG_GPIO_O_L, val)
        except Exception:
            pass
        self._power_on = False

    def is_power_on(self):
        return self._power_on

    def init_uart(self):
        from machine import UART
        if self._uart:
            try:
                self._uart.deinit()
            except Exception:
                pass
        self._uart = UART(
            SERVO_UART_ID, baudrate=SERVO_BAUD,
            tx=SERVO_TX_PIN, rx=SERVO_RX_PIN,
            bits=8, parity=None, stop=1,
        )

    def _flush_rx(self):
        if not self._uart:
            return
        try:
            while self._uart.any():
                self._uart.read()
        except Exception:
            pass

    def _send_packet(self, servo_id, instruction, address=0, data=None):
        if not self._uart:
            return
        self._flush_rx()
        if data is None:
            length = 2
            body = bytes([servo_id, length, instruction])
            checksum = (~(servo_id + length + instruction + address)) & 0xFF
            packet = b"\xff\xff" + body + bytes([checksum])
        else:
            params = bytes([address]) + bytes(data)
            length = len(params) + 2
            body = bytes([servo_id, length, instruction]) + params
            checksum = (~sum(body)) & 0xFF
            packet = b"\xff\xff" + body + bytes([checksum])
        self._uart.write(packet)
        try:
            self._uart.flush()
        except Exception:
            pass

    def _read_response(self, timeout_ms=PING_TIMEOUT_MS):
        data = b""
        end_ms = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(end_ms, time.ticks_ms()) > 0:
            try:
                count = self._uart.any() if self._uart else 0
                if count:
                    chunk = self._uart.read(count)
                    if chunk:
                        data += chunk
            except Exception:
                pass
            time.sleep_ms(5)
        return data

    @staticmethod
    def _word_to_scs(value):
        value = int(value) & 0xFFFF
        return [(value >> 8) & 0xFF, value & 0xFF]

    @staticmethod
    def _is_valid_reply(data, servo_id):
        if len(data) < 6:
            return False
        for i in range(0, len(data) - 5):
            if data[i] == 0xFF and data[i + 1] == 0xFF and data[i + 2] == servo_id:
                return True
        return False

    def ping(self, servo_id):
        self._send_packet(servo_id, INST_PING)
        resp = self._read_response()
        return self._is_valid_reply(resp, servo_id)

    def set_torque(self, servo_id, enabled):
        self._send_packet(servo_id, INST_WRITE, SCSCL_TORQUE_ENABLE,
                          [1 if enabled else 0])

    def set_position_raw(self, servo_id, raw_pos, move_time_ms=DEFAULT_MOVE_TIME_MS, speed=0):
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._last_cmd_ms)
        if elapsed < MIN_COMMAND_INTERVAL_MS:
            time.sleep_ms(MIN_COMMAND_INTERVAL_MS - elapsed)
        data = (self._word_to_scs(raw_pos) +
                self._word_to_scs(move_time_ms) +
                self._word_to_scs(speed))
        self._send_packet(servo_id, INST_WRITE, SCSCL_GOAL_POSITION_L, data)
        self._last_cmd_ms = time.ticks_ms()

    @staticmethod
    def _pitch_deg_to_raw(degrees, zero_pos, min_deg, max_deg):
        degrees = max(min_deg, min(max_deg, degrees))
        return int(zero_pos + degrees * PITCH_STEPS_PER_DEGREE)

    @staticmethod
    def _yaw_deg_to_raw(degrees):
        degrees = degrees % 360
        return int((YAW_ZERO + degrees * YAW_STEPS_PER_DEGREE) % YAW_RAW_SPAN)

    def set_yaw(self, degrees, move_time_ms=DEFAULT_MOVE_TIME_MS):
        raw = self._yaw_deg_to_raw(degrees)
        self.set_position_raw(YAW_ID, raw, move_time_ms)

    def yaw_deg_to_raw(self, degrees):
        return self._yaw_deg_to_raw(degrees)

    def set_yaw_raw(self, raw_pos, move_time_ms=DEFAULT_MOVE_TIME_MS):
        self.set_position_raw(YAW_ID, int(raw_pos) % YAW_RAW_SPAN, move_time_ms)

    def set_pitch(self, degrees, move_time_ms=DEFAULT_MOVE_TIME_MS):
        raw = self._pitch_deg_to_raw(degrees, PITCH_ZERO, PITCH_MIN_DEG, PITCH_MAX_DEG)
        self.set_position_raw(PITCH_ID, raw, move_time_ms)

    def center(self, move_time_ms=DEFAULT_MOVE_TIME_MS):
        self.set_yaw(0, move_time_ms)
        self.set_pitch(0, move_time_ms)

    def home(self, move_time_ms=DEFAULT_MOVE_TIME_MS):
        self.set_yaw(HOME_YAW_DEG, move_time_ms)
        self.set_pitch(HOME_PITCH_DEG, move_time_ms)

    def startup(self):
        version = self.enable_power()
        if not version:
            return False, False
        self.init_uart()
        self._yaw_ready = self.ping(YAW_ID)
        self._pitch_ready = self.ping(PITCH_ID)
        if self._yaw_ready:
            self.set_torque(YAW_ID, True)
        if self._pitch_ready:
            self.set_torque(PITCH_ID, True)
        return self._yaw_ready, self._pitch_ready

    def shutdown(self):
        try:
            self.set_torque(YAW_ID, False)
        except Exception:
            pass
        try:
            self.set_torque(PITCH_ID, False)
        except Exception:
            pass
        self.disable_power()
        self._yaw_ready = False
        self._pitch_ready = False

    @property
    def yaw_ready(self):
        return self._yaw_ready

    @property
    def pitch_ready(self):
        return self._pitch_ready

    def _i2c_write_reg(self, reg, value):
        self._i2c.writeto(PY32_I2C_ADDR, bytes([reg, value & 0xFF]))

    def _i2c_read_reg(self, reg):
        self._i2c.writeto(PY32_I2C_ADDR, bytes([reg]))
        data = self._i2c.readfrom(PY32_I2C_ADDR, 1)
        return data[0]

    def _py32_bit_on(self, reg, pin):
        value = self._i2c_read_reg(reg)
        value |= 1 << pin
        self._i2c_write_reg(reg, value)


# ===================================================================
# Inline Motion Mapper (from lib/motion.py)
# ===================================================================

YAW_INPUT_MIN = -1280
YAW_INPUT_MAX = 1280
PITCH_INPUT_MIN = 0
PITCH_INPUT_MAX = 900
SPEED_INPUT_MAX = 1000

YAW_INPUT_CENTER = 0
PITCH_INPUT_CENTER = 350

YAW_OUTPUT_MIN = -180
YAW_OUTPUT_MAX = 180
PITCH_OUTPUT_MIN = 0
PITCH_OUTPUT_MAX = 90

DEFAULT_DEADZONE = 50
PITCH_CENTER_DEADZONE = 100
DEFAULT_SMOOTHING = 0.3
YAW_INCREMENT_RAW_PER_SEC = 2048
YAW_MOVE_TIME_MS = 40

MOVE_TIME_MIN_MS = 50
MOVE_TIME_MAX_MS = 400
AUTO_CENTER_TIMEOUT_MS = PACKET_IDLE_CENTER_MS


class MotionMapper:

    def __init__(self, deadzone=DEFAULT_DEADZONE, smoothing=DEFAULT_SMOOTHING):
        self.deadzone = deadzone
        self.smoothing = smoothing
        self._yaw_raw_position = YAW_ZERO % YAW_RAW_SPAN
        self._pitch_smooth = 0.0
        self._last_update_ms = time.ticks_ms()

    @staticmethod
    def _map_range(value, in_min, in_max, out_min, out_max):
        if in_max == in_min:
            return (out_min + out_max) / 2
        return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def _apply_deadzone(self, value, center=0):
        if abs(value - center) < self.deadzone:
            return center
        return value

    @staticmethod
    def _clamp(value, lo, hi):
        return max(lo, min(hi, value))

    def _speed_to_move_time(self, speed_raw):
        if speed_raw <= 0:
            return MOVE_TIME_MAX_MS
        ratio = self._clamp(speed_raw / SPEED_INPUT_MAX, 0.0, 1.0)
        return int(MOVE_TIME_MAX_MS - ratio * (MOVE_TIME_MAX_MS - MOVE_TIME_MIN_MS))

    @staticmethod
    def _shortest_angle_delta(target, current):
        return ((target - current + 540) % 360) - 180

    @staticmethod
    def _map_centered(delta, min_delta, max_delta, out_min, out_max):
        if delta < 0:
            if min_delta == 0:
                return 0
            return delta * out_min / min_delta
        if max_delta == 0:
            return 0
        return delta * out_max / max_delta

    def _map_pitch_from_stick(self, pitch_raw):
        delta = pitch_raw - PITCH_INPUT_CENTER
        if abs(delta) < PITCH_CENTER_DEADZONE:
            return HOME_PITCH_DEG
        if delta <= 0:
            return HOME_PITCH_DEG
        span = PITCH_INPUT_MAX - PITCH_INPUT_CENTER
        if span <= 0:
            return HOME_PITCH_DEG
        ratio = self._clamp(delta / span, 0.0, 1.0)
        return HOME_PITCH_DEG + ratio * (PITCH_OUTPUT_MAX - HOME_PITCH_DEG)

    def update(self, yaw_raw, pitch_raw, speed_raw):
        now_ms = time.ticks_ms()
        elapsed_ms = time.ticks_diff(now_ms, self._last_update_ms)
        if elapsed_ms < 0 or elapsed_ms > 250:
            elapsed_ms = 20
        self._last_update_ms = now_ms

        yaw_raw = self._clamp(yaw_raw, YAW_INPUT_MIN, YAW_INPUT_MAX)
        pitch_raw = self._clamp(pitch_raw, PITCH_INPUT_MIN, PITCH_INPUT_MAX)
        speed_raw = self._clamp(speed_raw, 0, SPEED_INPUT_MAX)

        yaw_delta = self._apply_deadzone(yaw_raw - YAW_INPUT_CENTER, 0)

        if yaw_delta != 0:
            yaw_ratio = self._clamp(yaw_delta / max(abs(YAW_INPUT_MIN), abs(YAW_INPUT_MAX)),
                                    -1.0, 1.0)
            speed_ratio = self._clamp(speed_raw / SPEED_INPUT_MAX, 0.0, 1.0)
            yaw_raw_step = yaw_ratio * YAW_INCREMENT_RAW_PER_SEC * speed_ratio * elapsed_ms / 1000
            self._yaw_raw_position = (self._yaw_raw_position + yaw_raw_step) % YAW_RAW_SPAN

        pitch_target = self._map_pitch_from_stick(pitch_raw)

        pitch_target = self._clamp(pitch_target, PITCH_OUTPUT_MIN, PITCH_OUTPUT_MAX)

        alpha = 1.0 - self.smoothing
        self._pitch_smooth = self._pitch_smooth * self.smoothing + pitch_target * alpha

        move_time = self._speed_to_move_time(speed_raw)
        return int(self._yaw_raw_position), self._pitch_smooth, move_time

    def should_auto_center(self):
        elapsed = time.ticks_diff(time.ticks_ms(), self._last_update_ms)
        return elapsed > AUTO_CENTER_TIMEOUT_MS

    def reset(self):
        self._yaw_raw_position = YAW_ZERO % YAW_RAW_SPAN
        self._pitch_smooth = 0.0
        self._last_update_ms = time.ticks_ms()


# ===================================================================
# UI Layout
# ===================================================================

BTN_START = (8, 146, 140, 36)
BTN_EXIT = (164, 146, 140, 36)

CLR_BG = 0x101418
CLR_TITLE_BG = 0x2B6CB0
CLR_GREEN = 0x8FE388
CLR_WHITE = 0xFFFFFF
CLR_GREY = 0x9AA4AF
CLR_BTN_GREEN = 0x2D6A4F
CLR_BTN_RED = 0xB23A48
CLR_CYAN = 0x48CAE4


# ===================================================================
# Globals
# ===================================================================

sc = ServoController()
mm = MotionMapper()

running = True
controlling = False
touch_was_down = False
touch_action_fired = False
touch_enabled_ms = 0
packet_count = 0
active_receiver_id = RECEIVER_ID

status_label = None
servo_label = None
packet_label = None
motion_label = None
hint_label = None
btn_start_lbl = None
btn_exit_lbl = None


# ===================================================================
# Screen
# ===================================================================

def setup_screen():
    global status_label, servo_label, packet_label, motion_label, hint_label
    global btn_start_lbl, btn_exit_lbl

    M5.begin()
    Widgets.fillScreen(CLR_BG)
    Widgets.Title("Remote Control", 3, CLR_WHITE, CLR_TITLE_BG, Widgets.FONTS.DejaVu18)

    status_label = Widgets.Label("Tap Start", 8, 34, 1.0,
                                 CLR_GREEN, CLR_BG, Widgets.FONTS.DejaVu18)
    servo_label = Widgets.Label("M1 yaw:-- M2 pitch:--", 8, 56, 1.0,
                                CLR_GREY, CLR_BG, Widgets.FONTS.DejaVu18)
    packet_label = Widgets.Label("waiting remote...", 8, 80, 1.0,
                                 CLR_WHITE, CLR_BG, Widgets.FONTS.DejaVu18)
    motion_label = Widgets.Label("M1:--deg M2:--deg", 8, 104, 1.0,
                                 CLR_CYAN, CLR_BG, Widgets.FONTS.DejaVu18)

    btn_start_lbl = Widgets.Label("     Start      ", BTN_START[0] + 6, BTN_START[1] + 8,
                                  1.0, CLR_WHITE, CLR_BTN_GREEN, Widgets.FONTS.DejaVu18)
    btn_exit_lbl = Widgets.Label("      Exit      ", BTN_EXIT[0] + 6, BTN_EXIT[1] + 8,
                                 1.0, CLR_WHITE, CLR_BTN_RED, Widgets.FONTS.DejaVu18)

    hint_label = Widgets.Label("ch:{} id:{}".format(WIFI_CHANNEL, active_receiver_id),
                               8, 212, 1.0, CLR_GREY, CLR_BG, Widgets.FONTS.DejaVu18)


def set_text(label, text):
    if label:
        label.setText(text)


def receiver_id_text():
    if active_receiver_id is None:
        return "auto"
    return str(active_receiver_id)


# ===================================================================
# Touch
# ===================================================================

def point_in_rect(x, y, rect):
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


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
    global running, controlling, touch_was_down, touch_action_fired

    if time.ticks_diff(time.ticks_ms(), touch_enabled_ms) < 0:
        return

    point = read_touch_point()
    if point is None:
        touch_was_down = False
        touch_action_fired = False
        return

    touch_was_down = True
    if touch_action_fired:
        return

    x, y = point

    if point_in_rect(x, y, BTN_EXIT):
        touch_action_fired = True
        running = False
    elif point_in_rect(x, y, BTN_START):
        touch_action_fired = True
        if controlling:
            do_stop()
        else:
            do_start()


# ===================================================================
# ESP-NOW
# ===================================================================

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


def parse_packet(packet):
    if len(packet) != 8:
        return None
    target_id, yaw, pitch, speed, laser = struct.unpack("<BhhhB", packet)
    if packet_is_abnormal(yaw, pitch, speed):
        return None
    return target_id, yaw, pitch, speed, laser


def packet_hex(packet):
    text = ""
    for b in packet:
        if text:
            text += " "
        text += "{:02X}".format(b)
    return text


def packet_is_abnormal(yaw_raw, pitch_raw, speed_raw):
    return (yaw_raw < YAW_INPUT_MIN or yaw_raw > YAW_INPUT_MAX or
            pitch_raw < PITCH_INPUT_MIN or pitch_raw > PITCH_INPUT_MAX or
            speed_raw < 0 or speed_raw > SPEED_INPUT_MAX)


def packet_matches_receiver(target_id):
    if active_receiver_id is None:
        return False
    return target_id == active_receiver_id or (ACCEPT_BROADCAST_ID and target_id == 0)


def joystick_moved_for_pairing(yaw_raw, pitch_raw):
    pitch_center = (PITCH_INPUT_MIN + PITCH_INPUT_MAX) // 2
    return (abs(yaw_raw) >= PAIR_YAW_THRESHOLD or
            abs(pitch_raw - pitch_center) >= PAIR_PITCH_THRESHOLD)


def pair_remote_if_needed(target_id, yaw_raw, pitch_raw):
    global active_receiver_id

    if not AUTO_PAIR_REMOTE:
        return False
    if target_id == 0 or target_id == active_receiver_id:
        return False
    if not joystick_moved_for_pairing(yaw_raw, pitch_raw):
        return False

    active_receiver_id = target_id
    set_text(status_label, "Paired id {}".format(active_receiver_id))
    set_text(hint_label, "ch:{} id:{} paired".format(WIFI_CHANNEL, active_receiver_id))
    return True


# ===================================================================
# Actions
# ===================================================================

def do_start():
    global controlling

    set_text(status_label, "powering servos...")
    set_text(btn_start_lbl, "  Starting...  ")

    yaw_ok, pitch_ok = sc.startup()

    if not sc.is_power_on():
        set_text(status_label, "PY32 not found!")
        set_text(servo_label, "check hardware")
        set_text(btn_start_lbl, "     Start      ")
        return

    yaw_str = "OK" if yaw_ok else "FAIL"
    pitch_str = "OK" if pitch_ok else "FAIL"
    set_text(servo_label, "M1 yaw:{} M2 pitch:{}".format(yaw_str, pitch_str))

    if not yaw_ok and not pitch_ok:
        set_text(status_label, "no servos responding")
        set_text(btn_start_lbl, "     Start      ")
        sc.shutdown()
        return

    sc.home(move_time_ms=300)

    controlling = True
    mm.reset()
    set_text(status_label, "Run id {}".format(receiver_id_text()))
    set_text(hint_label, "Stop=power off  Exit=quit")
    set_text(btn_start_lbl, "      Stop      ")
    if btn_start_lbl:
        btn_start_lbl.setColor(CLR_WHITE, CLR_BTN_RED)


def do_stop():
    global controlling
    controlling = False

    set_text(status_label, "stopping...")
    sc.home(move_time_ms=300)
    time.sleep_ms(400)
    sc.shutdown()

    set_text(status_label, "Stopped")
    set_text(servo_label, "M1 yaw:off M2 pitch:off")
    set_text(motion_label, "M1:--deg M2:--deg")
    set_text(hint_label, "ch:{} id:{}".format(WIFI_CHANNEL, receiver_id_text()))
    set_text(btn_start_lbl, "     Start      ")
    if btn_start_lbl:
        btn_start_lbl.setColor(CLR_WHITE, CLR_BTN_GREEN)


def delay_ui(ms):
    end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(20)


# ===================================================================
# Main
# ===================================================================

def main():
    global running, controlling, packet_count, touch_enabled_ms

    setup_screen()
    esp = init_espnow()
    touch_enabled_ms = time.ticks_add(time.ticks_ms(), 800)

    last_ui_ms = 0
    auto_centered = False

    while running:
        M5.update()
        handle_touch()

        host, packet = esp.recv(10)

        if packet and len(packet) != 8:
            now_ms = time.ticks_ms()
            if time.ticks_diff(now_ms, last_ui_ms) > 250:
                set_text(packet_label, "ignore len:{} {}".format(len(packet), packet_hex(packet[:4])))
                set_text(motion_label, "need exactly 8 bytes")
                last_ui_ms = now_ms
            time.sleep_ms(5)
            continue

        if controlling and packet:
            parsed = parse_packet(packet)
            if not parsed:
                now_ms = time.ticks_ms()
                if time.ticks_diff(now_ms, last_ui_ms) > 250:
                    set_text(status_label, "Drop invalid packet")
                    set_text(packet_label, packet_hex(packet))
                    set_text(motion_label, "range check failed")
                    last_ui_ms = now_ms
            else:
                target_id, yaw_raw, pitch_raw, speed_raw, laser = parsed
                match = packet_matches_receiver(target_id)
                if match:
                    packet_count += 1
                    auto_centered = False

                    yaw_servo_raw, pitch_deg, move_ms = mm.update(yaw_raw, pitch_raw, speed_raw)

                    if sc.yaw_ready:
                        sc.set_yaw_raw(yaw_servo_raw, YAW_MOVE_TIME_MS)
                    if sc.pitch_ready:
                        sc.set_pitch(pitch_deg, move_ms)

                    now_ms = time.ticks_ms()
                    if time.ticks_diff(now_ms, last_ui_ms) > 200:
                        set_text(packet_label,
                                 "id:{} y:{} p:{} #{}".format(
                                     target_id, yaw_raw, pitch_raw, packet_count))
                        set_text(motion_label,
                                 "yr:{} P:{:.0f} t:{}".format(
                                     yaw_servo_raw, pitch_deg, move_ms))
                        last_ui_ms = now_ms
                else:
                    now_ms = time.ticks_ms()
                    if time.ticks_diff(now_ms, last_ui_ms) > 200:
                        set_text(packet_label,
                                 "ign id:{} need:{}".format(
                                     target_id, receiver_id_text()))
                        set_text(motion_label,
                                 "raw y:{} p:{}".format(yaw_raw, pitch_raw))
                        set_text(status_label, "ID mismatch")
                        last_ui_ms = now_ms

        if controlling and not auto_centered and mm.should_auto_center():
            mm.reset()
            sc.home(move_time_ms=500)
            set_text(status_label, "Home: no packet")
            set_text(motion_label, "M1:{} M2:{} idle".format(HOME_YAW_DEG, HOME_PITCH_DEG))
            auto_centered = True

        if not controlling and packet:
            parsed = parse_packet(packet)
            if not parsed:
                now_ms = time.ticks_ms()
                if time.ticks_diff(now_ms, last_ui_ms) > 250:
                    set_text(packet_label, "invalid 8-byte packet")
                    set_text(motion_label, packet_hex(packet))
                    last_ui_ms = now_ms
            else:
                tid, y, p, s, l = parsed
                paired = pair_remote_if_needed(tid, y, p)
                prefix = "rx" if packet_matches_receiver(tid) else "ign"
                if paired:
                    prefix = "paired"
                    set_text(status_label, "Paired. Tap Start")
                set_text(packet_label,
                         "{} id:{} y:{} p:{}".format(prefix, tid, y, p))
                set_text(motion_label,
                         "raw speed:{} laser:{}".format(s, l))

        time.sleep_ms(5)

    set_text(status_label, "shutting down...")
    if controlling:
        sc.home(move_time_ms=300)
        delay_ui(400)
        sc.shutdown()
    set_text(status_label, "stopped")
    set_text(hint_label, "safe to close")


try:
    main()
except (Exception, KeyboardInterrupt) as e:
    try:
        sc.shutdown()
    except Exception:
        pass
    try:
        from utility import print_error_msg
        print_error_msg(e)
    except ImportError:
        print(e)
