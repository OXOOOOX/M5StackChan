"""
servo_center_calibration.py — StackChan servo center calibration tool.

中文说明：
    StackChan 舵机中心校准工具。
    用于确认 yaw(ID1) 与 pitch(ID2) 都能通信后，微调机械中心值。
    校准结果会显示为 YAW_ZERO 和 PITCH_ZERO，需要同步回控制脚本。

使用前提：
    先用 servo_bus_diagnostic.py 确认能扫到 ID1 和 ID2。
    如果刚更换 pitch 舵机，先确认其内部 ID 已改为 2。
    调整时优先使用小步进，避免再次顶到机械限位。

Paste directly into UIFlow2 and run.

Use:
    1. Tap Power to enable servo power and torque.
    2. Tap Y-/Y+ and P-/P+ until the device is mechanically centered.
    3. Copy the displayed YAW_ZERO and PITCH_ZERO values back to
       remote_servo_controller.py.
    4. Tap Exit to disable torque and power.
"""

import time

import M5
from M5 import *


# ===================================================================
# Current values from remote_servo_controller.py
# ===================================================================

YAW_ZERO = 510
PITCH_ZERO = 610


# ===================================================================
# Servo hardware config
# ===================================================================

PY32_I2C_ADDR = 0x6F
I2C_BUS_CANDIDATES = (0, 1)
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

RAW_MIN = 0
RAW_MAX = 1023
MOVE_TIME_MS = 180
MIN_COMMAND_INTERVAL_MS = 30

SCSCL_GOAL_POSITION_L = 42
SCSCL_TORQUE_ENABLE = 40
INST_PING = 0x01
INST_WRITE = 0x03
POWER_SETTLE_MS = 350
PING_TIMEOUT_MS = 220
PING_RETRIES = 3
DEBUG_LOG = True


# ===================================================================
# UI config
# ===================================================================

CLR_BG = 0x101418
CLR_TITLE_BG = 0x2B6CB0
CLR_WHITE = 0xFFFFFF
CLR_GREY = 0x9AA4AF
CLR_GREEN = 0x8FE388
CLR_CYAN = 0x48CAE4
CLR_BTN_GREEN = 0x2D6A4F
CLR_BTN = 0x2D6A4F
CLR_BTN_RED = 0xB23A48
CLR_BTN_BLUE = 0x2B6CB0

BTN_POWER = (8, 78, 96, 34)
BTN_STEP = (112, 78, 96, 34)
BTN_EXIT = (216, 78, 96, 34)
BTN_Y_MINUS = (8, 126, 70, 34)
BTN_Y_PLUS = (86, 126, 70, 34)
BTN_P_MINUS = (164, 126, 70, 34)
BTN_P_PLUS = (242, 126, 70, 34)
BTN_APPLY = (8, 176, 148, 34)
BTN_PRINT = (164, 176, 148, 34)

STEP_VALUES = [1, 5, 10, 25]


# ===================================================================
# Servo driver
# ===================================================================

class ServoController:

    def __init__(self):
        self._uart = None
        self._i2c = None
        self._i2c_bus = -1
        self._power_on = False
        self._yaw_ready = False
        self._pitch_ready = False
        self._last_cmd_ms = 0

    def _log(self, msg):
        if DEBUG_LOG:
            print("[cal] " + str(msg))

    def enable_power(self):
        self._log("enable_power begin")
        self._i2c = self._open_py32_i2c()
        if self._i2c is None:
            self._log("enable_power failed: no PY32 I2C")
            return 0

        try:
            version = self._i2c_read_reg(REG_VERSION)
            self._log("PY32 version=0x{:02X}".format(version))
        except Exception as e:
            self._log("PY32 version read failed: {}".format(e))
            version = 1

        if version == 0 or version == 0xFF:
            self._log("invalid PY32 version=0x{:02X}".format(version))
            return 0

        try:
            before_m = self._i2c_read_reg(REG_GPIO_M_L)
            before_pu = self._i2c_read_reg(REG_GPIO_PU_L)
            before_o = self._i2c_read_reg(REG_GPIO_O_L)
            self._log("PY32 before M={:02X} PU={:02X} O={:02X}".format(
                before_m, before_pu, before_o))
            self._py32_bit_on(REG_GPIO_M_L, VM_EN_PIN)
            self._log("VM_EN mode bit set")
            self._py32_bit_on(REG_GPIO_PU_L, VM_EN_PIN)
            self._log("VM_EN pullup bit set")
            self._py32_bit_on(REG_GPIO_O_L, VM_EN_PIN)
            self._log("VM_EN output bit set")
        except Exception as e:
            # Some UIFlow2 builds intermittently fail PY32 reads after writes
            # even though VM_EN has already been set. Continue and let the
            # servo ping decide whether power is really available.
            self._log("VM_EN write/read warning: {}".format(e))

        time.sleep_ms(POWER_SETTLE_MS)
        try:
            after_m = self._i2c_read_reg(REG_GPIO_M_L)
            after_pu = self._i2c_read_reg(REG_GPIO_PU_L)
            after_o = self._i2c_read_reg(REG_GPIO_O_L)
            self._log("PY32 after M={:02X} PU={:02X} O={:02X}".format(
                after_m, after_pu, after_o))
        except Exception as e:
            self._log("PY32 post-write read warning: {}".format(e))
        self._power_on = True
        self._log("enable_power done")
        return version

    def disable_power(self):
        self._log("disable_power begin")
        if self._i2c is None:
            self._log("disable_power skipped: no i2c")
            return
        try:
            val = self._i2c_read_reg(REG_GPIO_O_L)
            val &= ~(1 << VM_EN_PIN)
            self._i2c_write_reg(REG_GPIO_O_L, val)
            self._log("VM_EN off written")
        except Exception:
            self._log("disable_power read/write failed")
            pass
        self._power_on = False

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
        self._log("UART{} tx={} rx={} baud={}".format(
            SERVO_UART_ID, SERVO_TX_PIN, SERVO_RX_PIN, SERVO_BAUD))

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
            self._log("send skipped: uart not ready")
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
        self._log("tx id={} inst=0x{:02X} addr={} len={}".format(
            servo_id, instruction, address, len(packet)))

    def _read_response(self, timeout_ms=PING_TIMEOUT_MS):
        data = b""
        end_ms = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(end_ms, time.ticks_ms()) > 0:
            try:
                count = 0
                if self._uart:
                    count = self._uart.any()
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
                length = data[i + 3]
                packet_len = length + 4
                if i + packet_len <= len(data):
                    body = data[i + 2:i + 3 + length]
                    checksum = data[i + 3 + length]
                    if ((sum(body) + checksum) & 0xFF) == 0xFF:
                        return True
        return False

    def ping(self, servo_id):
        best = b""
        for attempt in range(PING_RETRIES):
            self._send_packet(servo_id, INST_PING)
            resp = self._read_response()
            if resp:
                best = resp
            ok = self._is_valid_reply(resp, servo_id)
            self._log("ping id={} try={} ok={} len={} raw={}".format(
                servo_id, attempt + 1, ok, len(resp), self._to_hex(resp)))
            if ok:
                return True
            time.sleep_ms(60)
        if best:
            self._log("ping id={} best raw={}".format(servo_id, self._to_hex(best)))
        return False

    def set_torque(self, servo_id, enabled):
        self._log("set_torque id={} enabled={}".format(servo_id, enabled))
        self._send_packet(servo_id, INST_WRITE, SCSCL_TORQUE_ENABLE,
                          [1 if enabled else 0])

    def set_position_raw(self, servo_id, raw_pos, move_time_ms=MOVE_TIME_MS, speed=0):
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._last_cmd_ms)
        if elapsed < MIN_COMMAND_INTERVAL_MS:
            time.sleep_ms(MIN_COMMAND_INTERVAL_MS - elapsed)
        raw_pos = max(RAW_MIN, min(RAW_MAX, int(raw_pos)))
        self._log("set_position id={} raw={} time={} speed={}".format(
            servo_id, raw_pos, move_time_ms, speed))
        data = (self._word_to_scs(raw_pos) +
                self._word_to_scs(move_time_ms) +
                self._word_to_scs(speed))
        self._send_packet(servo_id, INST_WRITE, SCSCL_GOAL_POSITION_L, data)
        self._last_cmd_ms = time.ticks_ms()

    def move_both(self, yaw_raw, pitch_raw):
        if self._yaw_ready:
            self.set_position_raw(YAW_ID, yaw_raw)
        if self._pitch_ready:
            self.set_position_raw(PITCH_ID, pitch_raw)

    def startup(self):
        self._log("startup begin")
        version = self.enable_power()
        if not version:
            self._log("startup failed: servo power enable failed")
            return False, False
        self.init_uart()
        time.sleep_ms(120)
        self._yaw_ready = self.ping(YAW_ID)
        time.sleep_ms(80)
        self._pitch_ready = self.ping(PITCH_ID)
        self._log("startup ping result yaw={} pitch={}".format(
            self._yaw_ready, self._pitch_ready))
        if self._yaw_ready:
            self.set_torque(YAW_ID, True)
        if self._pitch_ready:
            self.set_torque(PITCH_ID, True)
        return self._yaw_ready, self._pitch_ready

    def shutdown(self):
        self._log("shutdown begin")
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

    def _open_py32_i2c(self):
        from machine import I2C, Pin

        last_error = None
        for bus_id in I2C_BUS_CANDIDATES:
            try:
                i2c = I2C(bus_id, scl=Pin(I2C_SCL_PIN),
                          sda=Pin(I2C_SDA_PIN), freq=100000)
                try:
                    devices = i2c.scan()
                    self._log("I2C{} scan: {}".format(bus_id, devices))
                    if PY32_I2C_ADDR in devices:
                        self._log("PY32 found on I2C{}".format(bus_id))
                        self._i2c_bus = bus_id
                        return i2c
                except Exception as e:
                    last_error = e
                    self._log("I2C{} scan failed: {}".format(bus_id, e))
                try:
                    i2c.writeto(PY32_I2C_ADDR, bytes([REG_VERSION]))
                    data = i2c.readfrom(PY32_I2C_ADDR, 1)
                    self._log("I2C{} direct PY32 read: {}".format(bus_id, data))
                    self._i2c_bus = bus_id
                    return i2c
                except Exception as e:
                    last_error = e
                    self._log("I2C{} direct PY32 read failed: {}".format(bus_id, e))
            except Exception as e:
                last_error = e
                self._log("I2C{} init failed: {}".format(bus_id, e))
        self._log("PY32 open failed: {}".format(last_error))
        return None

    @staticmethod
    def _to_hex(data):
        text = ""
        for b in data[:16]:
            text += "{:02X} ".format(b)
        if len(data) > 16:
            text += "..."
        return text


# ===================================================================
# App state
# ===================================================================

sc = ServoController()
running = True
powered = False
touch_action_fired = False
touch_enabled_ms = 0
step_index = 1
yaw_zero = YAW_ZERO
pitch_zero = PITCH_ZERO

status_label = None
value_label = None
servo_label = None
hint_label = None
btn_power_lbl = None
btn_step_lbl = None
btn_exit_lbl = None
btn_y_minus_lbl = None
btn_y_plus_lbl = None
btn_p_minus_lbl = None
btn_p_plus_lbl = None
btn_apply_lbl = None
btn_print_lbl = None


def draw_button(text, rect, color):
    x, y, w, h = rect
    return Widgets.Label(text, x + 4, y + 8, 1.0,
                         CLR_WHITE, color, Widgets.FONTS.DejaVu18)


def setup_screen():
    global status_label, value_label, servo_label, hint_label
    global btn_power_lbl, btn_step_lbl, btn_exit_lbl
    global btn_y_minus_lbl, btn_y_plus_lbl, btn_p_minus_lbl, btn_p_plus_lbl
    global btn_apply_lbl, btn_print_lbl

    M5.begin()
    Widgets.fillScreen(CLR_BG)
    Widgets.Title("Center Cal", 3, CLR_WHITE, CLR_TITLE_BG, Widgets.FONTS.DejaVu18)

    status_label = Widgets.Label("Tap Power", 8, 32, 1.0,
                                 CLR_GREEN, CLR_BG, Widgets.FONTS.DejaVu18)
    servo_label = Widgets.Label("Y:-- P:--", 8, 52, 1.0,
                                CLR_GREY, CLR_BG, Widgets.FONTS.DejaVu18)
    value_label = Widgets.Label("", 8, 214, 1.0,
                                CLR_CYAN, CLR_BG, Widgets.FONTS.DejaVu18)
    hint_label = Widgets.Label("", 216, 52, 1.0,
                               CLR_GREY, CLR_BG, Widgets.FONTS.DejaVu18)

    btn_power_lbl = draw_button(" Power ", BTN_POWER, CLR_BTN_GREEN)
    btn_step_lbl = draw_button("Step 5", BTN_STEP, CLR_BTN_BLUE)
    btn_exit_lbl = draw_button(" Exit ", BTN_EXIT, CLR_BTN_RED)
    btn_y_minus_lbl = draw_button(" Y- ", BTN_Y_MINUS, CLR_BTN)
    btn_y_plus_lbl = draw_button(" Y+ ", BTN_Y_PLUS, CLR_BTN)
    btn_p_minus_lbl = draw_button(" P- ", BTN_P_MINUS, CLR_BTN)
    btn_p_plus_lbl = draw_button(" P+ ", BTN_P_PLUS, CLR_BTN)
    btn_apply_lbl = draw_button(" Apply ", BTN_APPLY, CLR_BTN_BLUE)
    btn_print_lbl = draw_button(" Print ", BTN_PRINT, CLR_BTN_BLUE)

    update_values()


def set_text(label, text):
    if label:
        label.setText(text)


def update_values():
    set_text(value_label, "YAW_ZERO={} PITCH_ZERO={}".format(yaw_zero, pitch_zero))
    set_text(hint_label, "step={}".format(STEP_VALUES[step_index]))


def print_values():
    print("YAW_ZERO =", yaw_zero)
    print("PITCH_ZERO =", pitch_zero)
    print("Set these in remote_servo_controller.py")


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


def apply_position():
    print("[cal-ui] apply_position powered={} yaw_zero={} pitch_zero={}".format(
        powered, yaw_zero, pitch_zero))
    if not powered:
        set_text(status_label, "Power first")
        return
    sc.move_both(yaw_zero, pitch_zero)
    set_text(status_label, "Applied")


def power_on():
    global powered
    print("[cal-ui] Power button pressed")
    set_text(status_label, "powering...")
    yaw_ok, pitch_ok = sc.startup()
    print("[cal-ui] startup returned yaw={} pitch={}".format(yaw_ok, pitch_ok))
    powered = yaw_ok or pitch_ok
    yaw_text = "FAIL"
    pitch_text = "FAIL"
    if yaw_ok:
        yaw_text = "OK"
    if pitch_ok:
        pitch_text = "OK"
    set_text(servo_label, "Y:{} P:{}".format(yaw_text, pitch_text))
    if not yaw_ok and not pitch_ok:
        set_text(status_label, "ping failed")
        print("[cal-ui] no servo ping succeeded; shutting down")
        sc.shutdown()
        return
    sc.move_both(yaw_zero, pitch_zero)
    if yaw_ok and pitch_ok:
        set_text(status_label, "Adjust center")
    else:
        set_text(status_label, "Partial servo OK")
    if btn_power_lbl:
        btn_power_lbl.setText("  On  ")


def handle_touch():
    global running, powered, touch_action_fired, step_index
    global yaw_zero, pitch_zero

    if time.ticks_diff(time.ticks_ms(), touch_enabled_ms) < 0:
        return

    point = read_touch_point()
    if point is None:
        touch_action_fired = False
        return

    if touch_action_fired:
        return
    touch_action_fired = True

    x, y = point
    step = STEP_VALUES[step_index]

    if point_in_rect(x, y, BTN_EXIT):
        print("[cal-ui] Exit pressed")
        running = False
        return

    if point_in_rect(x, y, BTN_POWER):
        if not powered:
            power_on()
        else:
            print("[cal-ui] Power off pressed")
            sc.shutdown()
            powered = False
            set_text(status_label, "Power off")
            set_text(servo_label, "Y:off P:off")
            if btn_power_lbl:
                btn_power_lbl.setText(" Power ")
        return

    if point_in_rect(x, y, BTN_STEP):
        step_index = (step_index + 1) % len(STEP_VALUES)
        print("[cal-ui] step changed to {}".format(STEP_VALUES[step_index]))
        set_text(btn_step_lbl, "Step {}".format(STEP_VALUES[step_index]))
        update_values()
        return

    changed = False
    if point_in_rect(x, y, BTN_Y_MINUS):
        yaw_zero = max(RAW_MIN, yaw_zero - step)
        changed = True
    elif point_in_rect(x, y, BTN_Y_PLUS):
        yaw_zero = min(RAW_MAX, yaw_zero + step)
        changed = True
    elif point_in_rect(x, y, BTN_P_MINUS):
        pitch_zero = max(RAW_MIN, pitch_zero - step)
        changed = True
    elif point_in_rect(x, y, BTN_P_PLUS):
        pitch_zero = min(RAW_MAX, pitch_zero + step)
        changed = True
    elif point_in_rect(x, y, BTN_APPLY):
        changed = True
    elif point_in_rect(x, y, BTN_PRINT):
        print_values()
        set_text(status_label, "Printed to log")

    if changed:
        print("[cal-ui] value changed yaw_zero={} pitch_zero={}".format(
            yaw_zero, pitch_zero))
        update_values()
        apply_position()


def delay_ui(ms):
    end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(20)


def main():
    global touch_enabled_ms
    setup_screen()
    touch_enabled_ms = time.ticks_add(time.ticks_ms(), 800)

    while running:
        M5.update()
        handle_touch()
        time.sleep_ms(10)

    set_text(status_label, "shutting down...")
    print_values()
    if powered:
        sc.shutdown()
    delay_ui(300)
    set_text(status_label, "stopped")


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
