"""
servo_validation.py — StackChan servo validation UI (v0.2.0).

Self-contained script — no external imports needed.
Paste directly into UIFlow2 and run.

Buttons:
    [Power On]   — enable servo power + ping both servos
    [Center]     — move both servos to zero position
    [Yaw Test]   — sweep yaw left → center → right → center
    [Pitch Test] — sweep pitch down → center → up → center
    [Exit]       — disable torque, power off, exit
"""

import time

import M5
from M5 import *


# ===================================================================
# Inline Servo Driver (from lib/servo.py)
# ===================================================================

# PY32L020 IO expander
PY32_I2C_ADDR = 0x6F
I2C_SDA_PIN = 12
I2C_SCL_PIN = 11
REG_VERSION = 0x02
REG_GPIO_M_L = 0x03
REG_GPIO_O_L = 0x05
REG_GPIO_PU_L = 0x09
VM_EN_PIN = 0

# Servo UART
SERVO_UART_ID = 1
SERVO_TX_PIN = 6
SERVO_RX_PIN = 7
SERVO_BAUD = 1000000

# Servo IDs and calibration
YAW_ID = 1
PITCH_ID = 2
YAW_ZERO = 460
PITCH_ZERO = 620
STEPS_PER_DEGREE = 3.41

# Safety limits (degrees from zero)
YAW_MIN_DEG = -180
YAW_MAX_DEG = 180
PITCH_MIN_DEG = -30
PITCH_MAX_DEG = 45

# SCSCL protocol
SCSCL_GOAL_POSITION_L = 42
SCSCL_TORQUE_ENABLE = 40
INST_PING = 0x01
INST_WRITE = 0x03

# Timing
POWER_SETTLE_MS = 250
PING_TIMEOUT_MS = 180
DEFAULT_MOVE_TIME_MS = 200
MIN_COMMAND_INTERVAL_MS = 20


class ServoController:
    """High-level controller for StackChan's two SCSCL servos."""

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
    def _deg_to_raw(degrees, zero_pos, min_deg, max_deg):
        degrees = max(min_deg, min(max_deg, degrees))
        return int(zero_pos + degrees * STEPS_PER_DEGREE)

    def set_yaw(self, degrees, move_time_ms=DEFAULT_MOVE_TIME_MS):
        raw = self._deg_to_raw(degrees, YAW_ZERO, YAW_MIN_DEG, YAW_MAX_DEG)
        self.set_position_raw(YAW_ID, raw, move_time_ms)

    def set_pitch(self, degrees, move_time_ms=DEFAULT_MOVE_TIME_MS):
        raw = self._deg_to_raw(degrees, PITCH_ZERO, PITCH_MIN_DEG, PITCH_MAX_DEG)
        self.set_position_raw(PITCH_ID, raw, move_time_ms)

    def center(self, move_time_ms=DEFAULT_MOVE_TIME_MS):
        self.set_yaw(0, move_time_ms)
        self.set_pitch(0, move_time_ms)

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

    @staticmethod
    def to_hex(data, max_bytes=12):
        if not data:
            return "none"
        text = ""
        for b in data[:max_bytes]:
            text += "{:02X} ".format(b)
        if len(data) > max_bytes:
            text += "..."
        return text.strip()


# ===================================================================
# UI Layout
# ===================================================================

BTN_POWER = (8, 100, 140, 38)
BTN_CENTER = (164, 100, 140, 38)
BTN_YAW = (8, 148, 140, 38)
BTN_PITCH = (164, 148, 140, 38)
BTN_EXIT = (88, 200, 140, 30)

CLR_BG = 0x101418
CLR_TITLE_BG = 0x2B6CB0
CLR_GREEN = 0x8FE388
CLR_WHITE = 0xFFFFFF
CLR_GREY = 0x9AA4AF
CLR_BTN_BLUE = 0x2B6CB0
CLR_BTN_GREEN = 0x2D6A4F
CLR_BTN_ORANGE = 0xE76F51
CLR_BTN_RED = 0xB23A48
CLR_BTN_DISABLED = 0x3A3A3A


# ===================================================================
# Globals
# ===================================================================

sc = ServoController()
running = True
powered = False
touch_was_down = False
touch_action_fired = False
touch_enabled_ms = 0
busy = False

status_label = None
detail_label = None
hint_label = None

btn_power_lbl = None
btn_center_lbl = None
btn_yaw_lbl = None
btn_pitch_lbl = None
btn_exit_lbl = None


# ===================================================================
# Screen Setup
# ===================================================================

def setup_screen():
    global status_label, detail_label, hint_label
    global btn_power_lbl, btn_center_lbl, btn_yaw_lbl, btn_pitch_lbl, btn_exit_lbl

    M5.begin()
    Widgets.fillScreen(CLR_BG)
    Widgets.Title("Servo Validation", 3, CLR_WHITE, CLR_TITLE_BG, Widgets.FONTS.DejaVu18)

    status_label = Widgets.Label("tap Power On to start", 8, 36, 1.0,
                                 CLR_GREEN, CLR_BG, Widgets.FONTS.DejaVu18)
    detail_label = Widgets.Label("servos not powered", 8, 60, 1.0,
                                 CLR_GREY, CLR_BG, Widgets.FONTS.DejaVu18)

    btn_power_lbl = Widgets.Label("   Power On   ", BTN_POWER[0] + 6, BTN_POWER[1] + 8,
                                  1.0, CLR_WHITE, CLR_BTN_BLUE, Widgets.FONTS.DejaVu18)
    btn_center_lbl = Widgets.Label("    Center    ", BTN_CENTER[0] + 6, BTN_CENTER[1] + 8,
                                   1.0, CLR_GREY, CLR_BTN_DISABLED, Widgets.FONTS.DejaVu18)
    btn_yaw_lbl = Widgets.Label("  Yaw Test   ", BTN_YAW[0] + 6, BTN_YAW[1] + 8,
                                1.0, CLR_GREY, CLR_BTN_DISABLED, Widgets.FONTS.DejaVu18)
    btn_pitch_lbl = Widgets.Label(" Pitch Test  ", BTN_PITCH[0] + 6, BTN_PITCH[1] + 8,
                                  1.0, CLR_GREY, CLR_BTN_DISABLED, Widgets.FONTS.DejaVu18)
    btn_exit_lbl = Widgets.Label("      Exit      ", BTN_EXIT[0] + 6, BTN_EXIT[1] + 4,
                                 1.0, CLR_WHITE, CLR_BTN_RED, Widgets.FONTS.DejaVu18)

    hint_label = Widgets.Label("v0.2.0 servo validation", 8, 232, 1.0,
                               CLR_GREY, CLR_BG, Widgets.FONTS.DejaVu18)


def set_text(label, text):
    if label:
        label.setText(text)


def enable_motion_buttons():
    if btn_center_lbl:
        btn_center_lbl.setColor(CLR_WHITE, CLR_BTN_GREEN)
    if btn_yaw_lbl:
        btn_yaw_lbl.setColor(CLR_WHITE, CLR_BTN_ORANGE)
    if btn_pitch_lbl:
        btn_pitch_lbl.setColor(CLR_WHITE, CLR_BTN_ORANGE)


# ===================================================================
# Touch Handling
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
    global running, touch_was_down, touch_action_fired, busy

    if busy:
        return
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
    elif point_in_rect(x, y, BTN_POWER):
        touch_action_fired = True
        do_power_on()
    elif powered and point_in_rect(x, y, BTN_CENTER):
        touch_action_fired = True
        do_center()
    elif powered and point_in_rect(x, y, BTN_YAW):
        touch_action_fired = True
        do_yaw_test()
    elif powered and point_in_rect(x, y, BTN_PITCH):
        touch_action_fired = True
        do_pitch_test()


# ===================================================================
# Delay Helper
# ===================================================================

def delay_ui(ms):
    end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(20)


# ===================================================================
# Actions
# ===================================================================

def do_power_on():
    global powered, busy
    busy = True

    set_text(status_label, "enabling servo power...")
    set_text(detail_label, "PY32 I2C 0x6F SDA=12 SCL=11")
    set_text(btn_power_lbl, " Powering... ")

    yaw_ok, pitch_ok = sc.startup()

    if not sc.is_power_on():
        set_text(status_label, "PY32 not found!")
        set_text(detail_label, "check I2C wiring")
        set_text(btn_power_lbl, "  FAILED     ")
        busy = False
        return

    yaw_str = "OK" if yaw_ok else "FAIL"
    pitch_str = "OK" if pitch_ok else "FAIL"
    set_text(detail_label, "yaw:{} pitch:{}".format(yaw_str, pitch_str))

    if yaw_ok or pitch_ok:
        powered = True
        set_text(status_label, "servos ready!")
        set_text(btn_power_lbl, "  Powered ON ")
        enable_motion_buttons()
    else:
        set_text(status_label, "no servo response")
        set_text(btn_power_lbl, " No servos   ")

    busy = False


def do_center():
    global busy
    busy = True
    set_text(status_label, "centering...")
    set_text(detail_label, "yaw=0 pitch=0")
    sc.center(move_time_ms=400)
    delay_ui(500)
    set_text(status_label, "centered")
    busy = False


def do_yaw_test():
    global busy
    busy = True

    steps = [
        ("yaw center", 0),
        ("yaw right +40", 40),
        ("yaw left -40", -40),
        ("yaw right +80", 80),
        ("yaw left -80", -80),
        ("yaw center", 0),
    ]

    set_text(btn_yaw_lbl, "  Running... ")

    for label_text, deg in steps:
        set_text(status_label, label_text)
        set_text(detail_label, "raw={}".format(int(YAW_ZERO + deg * STEPS_PER_DEGREE)))
        sc.set_yaw(deg, move_time_ms=350)
        delay_ui(700)

    set_text(status_label, "yaw test done")
    set_text(detail_label, "returned to center")
    set_text(btn_yaw_lbl, "  Yaw Test   ")
    busy = False


def do_pitch_test():
    global busy
    busy = True

    steps = [
        ("pitch center", 0),
        ("pitch up +25", 25),
        ("pitch down -20", -20),
        ("pitch up +40", 40),
        ("pitch down -25", -25),
        ("pitch center", 0),
    ]

    set_text(btn_pitch_lbl, "  Running... ")

    for label_text, deg in steps:
        set_text(status_label, label_text)
        set_text(detail_label, "raw={}".format(int(PITCH_ZERO + deg * STEPS_PER_DEGREE)))
        sc.set_pitch(deg, move_time_ms=350)
        delay_ui(700)

    set_text(status_label, "pitch test done")
    set_text(detail_label, "returned to center")
    set_text(btn_pitch_lbl, " Pitch Test  ")
    busy = False


# ===================================================================
# Main
# ===================================================================

def main():
    global touch_enabled_ms

    setup_screen()
    touch_enabled_ms = time.ticks_add(time.ticks_ms(), 800)

    while running:
        M5.update()
        handle_touch()
        time.sleep_ms(20)

    # Clean shutdown
    set_text(status_label, "shutting down...")
    set_text(detail_label, "torque off, power off")
    if powered:
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
