"""
servo_id_recover_pitch.py - recover a replacement pitch servo ID.

中文说明：
    替换 pitch 舵机后，如果新舵机默认 ID 仍是 1，本工具用于把
    单独接入总线的待修复舵机从 ID1 改成 ID2。

重要安全规则：
    改 ID 时总线上只能接一个舵机。
    必须断开或拆下底座 yaw 舵机后，才可以使用 Set2。
    否则两个 ID1 舵机可能同时被改成 ID2。

IMPORTANT:
    Use this only with ONE servo on the bus.
    Disconnect or remove the yaw/base servo before using Set2.

Why:
    StackChan expects yaw ID=1 and pitch ID=2.
    Many replacement SCSCL servos ship as ID=1. If the pitch servo is ID=1,
    calibration will not find ID=2.

Buttons:
    Scan  - ping IDs 1..10, no motion
    Set2  - two-tap guarded write: change the only found ID=1 to ID=2
    Exit  - torque off and servo power off
"""

import time

import M5
from M5 import *


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

INST_PING = 0x01
INST_READ = 0x02
INST_WRITE = 0x03
SCSCL_ID = 5
SCSCL_LOCK = 48
SCSCL_TORQUE_ENABLE = 40

OLD_ID = 1
NEW_ID = 2
PING_TIMEOUT_MS = 220

CLR_BG = 0x101418
CLR_TITLE_BG = 0x2B6CB0
CLR_WHITE = 0xFFFFFF
CLR_GREY = 0x9AA4AF
CLR_GREEN = 0x8FE388
CLR_YELLOW = 0xFFD166
CLR_CYAN = 0x48CAE4
CLR_BTN = 0x2B6CB0
CLR_BTN_RED = 0xB23A48

BTN_SCAN = (8, 74, 82, 36)
BTN_SET2 = (112, 74, 82, 36)
BTN_EXIT = (216, 74, 82, 36)

running = True
touch_action_fired = False
touch_enabled_ms = 0
uart = None
powered = False
found_ids = []
set2_armed = False

status_label = None
line1_label = None
line2_label = None
line3_label = None


def setup_screen():
    global status_label, line1_label, line2_label, line3_label
    M5.begin()
    Widgets.fillScreen(CLR_BG)
    Widgets.Title("Pitch ID Recover", 3, CLR_WHITE, CLR_TITLE_BG, Widgets.FONTS.DejaVu18)
    status_label = label("Disconnect yaw first", 8, 34, CLR_YELLOW)
    line1_label = label("Use with one servo only", 8, 124, CLR_GREY)
    line2_label = label("Scan before Set2", 8, 150, CLR_GREY)
    line3_label = label("Set2 requires two taps", 8, 176, CLR_CYAN)
    button("Scan", BTN_SCAN, CLR_BTN)
    button("Set2", BTN_SET2, CLR_BTN)
    button("Exit", BTN_EXIT, CLR_BTN_RED)


def label(text, x, y, color):
    return Widgets.Label(text, x, y, 1.0, color, CLR_BG, Widgets.FONTS.DejaVu18)


def button(text, rect, color):
    x, y, w, h = rect
    return Widgets.Label(text, x + 10, y + 9, 1.0, CLR_WHITE, color, Widgets.FONTS.DejaVu18)


def set_text(obj, text):
    if obj:
        obj.setText(str(text))


def point_in_rect(x, y, rect):
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def read_touch_point():
    touch = None
    if hasattr(M5, "Touch"):
        touch = M5.Touch
    if touch is None and "Touch" in globals():
        touch = Touch
    if touch is None:
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


def delay_ui(ms):
    end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(20)


def make_i2c(bus_id):
    from machine import I2C, Pin
    return I2C(bus_id, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=100000)


def i2c_read_reg(i2c, reg):
    i2c.writeto(PY32_I2C_ADDR, bytes([reg]))
    return i2c.readfrom(PY32_I2C_ADDR, 1)[0]


def i2c_write_reg(i2c, reg, value):
    i2c.writeto(PY32_I2C_ADDR, bytes([reg, value & 0xFF]))


def bit_on(i2c, reg, pin):
    value = i2c_read_reg(i2c, reg)
    i2c_write_reg(i2c, reg, value | (1 << pin))


def bit_off(i2c, reg, pin):
    value = i2c_read_reg(i2c, reg)
    i2c_write_reg(i2c, reg, value & ~(1 << pin))


def open_py32_i2c():
    last_error = None
    for bus_id in I2C_BUS_CANDIDATES:
        try:
            i2c = make_i2c(bus_id)
            devices = i2c.scan()
            print("I2C%d scan:" % bus_id, devices)
            if PY32_I2C_ADDR in devices:
                return i2c
            try:
                i2c_read_reg(i2c, REG_VERSION)
                return i2c
            except Exception as e:
                last_error = e
        except Exception as e:
            last_error = e
    print("PY32 open error:", last_error)
    return None


def enable_power():
    global powered
    i2c = open_py32_i2c()
    if i2c is None:
        set_text(status_label, "PY32 not found")
        return False
    try:
        bit_on(i2c, REG_GPIO_M_L, VM_EN_PIN)
        bit_on(i2c, REG_GPIO_PU_L, VM_EN_PIN)
        bit_on(i2c, REG_GPIO_O_L, VM_EN_PIN)
    except Exception as e:
        print("VM_EN write/read warning:", e)
    powered = True
    delay_ui(350)
    return True


def disable_power():
    global powered
    torque_off_all()
    try:
        i2c = open_py32_i2c()
        if i2c:
            bit_off(i2c, REG_GPIO_O_L, VM_EN_PIN)
    except Exception as e:
        print("disable power error:", e)
    powered = False


def init_uart():
    global uart
    from machine import UART
    if uart:
        try:
            uart.deinit()
        except Exception:
            pass
    uart = UART(SERVO_UART_ID, baudrate=SERVO_BAUD,
                tx=SERVO_TX_PIN, rx=SERVO_RX_PIN,
                bits=8, parity=None, stop=1)


def flush_rx():
    try:
        while uart and uart.any():
            uart.read()
    except Exception:
        pass


def read_response(timeout_ms=PING_TIMEOUT_MS):
    data = b""
    end = time.ticks_add(time.ticks_ms(), timeout_ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        M5.update()
        try:
            count = 0
            if uart:
                count = uart.any()
            if count:
                chunk = uart.read(count)
                if chunk:
                    data += chunk
        except Exception:
            pass
        time.sleep_ms(5)
    return data


def packet(servo_id, instruction, address=0, data=None):
    if data is None:
        body = bytes([servo_id, 2, instruction])
    else:
        params = bytes([address]) + bytes(data)
        body = bytes([servo_id, len(params) + 2, instruction]) + params
    checksum = (~sum(body)) & 0xFF
    return b"\xff\xff" + body + bytes([checksum])


def write_packet(data):
    flush_rx()
    uart.write(data)
    try:
        uart.flush()
    except Exception:
        pass


def to_hex(data):
    if not data:
        return "none"
    text = ""
    for b in data[:16]:
        text += "%02X " % b
    if len(data) > 16:
        text += "..."
    return text


def valid_reply(data, servo_id):
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


def ping_id(servo_id):
    write_packet(packet(servo_id, INST_PING))
    return read_response()


def scan_ids():
    global found_ids, set2_armed
    set2_armed = False
    found_ids = []
    if not powered and not enable_power():
        return
    init_uart()
    set_text(status_label, "Scanning IDs...")
    print("=== single servo ID scan ===")
    for servo_id in range(1, 11):
        best = b""
        ok = False
        for _ in range(3):
            resp = ping_id(servo_id)
            if resp:
                best = resp
            if valid_reply(resp, servo_id):
                ok = True
                break
            delay_ui(60)
        if ok:
            found_ids.append(servo_id)
            print("id=%d OK %s" % (servo_id, to_hex(best)))
        elif best:
            print("id=%d RAW %s" % (servo_id, to_hex(best)))
    set_text(line1_label, "Found IDs: %s" % found_ids)
    if found_ids == [OLD_ID]:
        set_text(status_label, "Only ID1 found")
        set_text(line2_label, "If this is pitch, tap Set2 twice")
    elif found_ids == [NEW_ID]:
        set_text(status_label, "Already ID2")
        set_text(line2_label, "Reinstall as pitch")
    else:
        set_text(status_label, "Do not Set2")
        set_text(line2_label, "Need exactly one servo, ID1 only")


def write_reg(servo_id, address, value):
    write_packet(packet(servo_id, INST_WRITE, address, [value]))
    return read_response(180)


def change_id_1_to_2():
    global set2_armed
    if found_ids != [OLD_ID]:
        set_text(status_label, "Set2 blocked")
        set_text(line2_label, "Scan must show exactly [1]")
        return
    if not set2_armed:
        set2_armed = True
        set_text(status_label, "Armed: tap Set2 again")
        set_text(line2_label, "Only if yaw is disconnected")
        return

    set_text(status_label, "Writing ID 1 > 2")
    print("Changing servo ID 1 to 2")
    write_reg(OLD_ID, SCSCL_TORQUE_ENABLE, 0)
    delay_ui(100)
    resp_unlock = write_reg(OLD_ID, SCSCL_LOCK, 0)
    delay_ui(150)
    resp_id = write_reg(OLD_ID, SCSCL_ID, NEW_ID)
    delay_ui(350)
    resp_lock = write_reg(NEW_ID, SCSCL_LOCK, 1)
    delay_ui(350)
    print("unlock:", to_hex(resp_unlock))
    print("write id:", to_hex(resp_id))
    print("lock:", to_hex(resp_lock))
    set_text(line2_label, "Write sent; rescanning")
    scan_ids()


def torque_off_all():
    try:
        if not uart:
            init_uart()
        for servo_id in range(1, 11):
            write_packet(packet(servo_id, INST_WRITE, SCSCL_TORQUE_ENABLE, [0]))
            time.sleep_ms(10)
    except Exception as e:
        print("torque off error:", e)


def handle_touch():
    global running, touch_action_fired
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
    if point_in_rect(x, y, BTN_SCAN):
        scan_ids()
    elif point_in_rect(x, y, BTN_SET2):
        change_id_1_to_2()
    elif point_in_rect(x, y, BTN_EXIT):
        running = False


def main():
    global touch_enabled_ms
    setup_screen()
    touch_enabled_ms = time.ticks_add(time.ticks_ms(), 800)
    while running:
        M5.update()
        handle_touch()
        time.sleep_ms(10)
    set_text(status_label, "Power off")
    disable_power()
    delay_ui(300)


try:
    main()
except KeyboardInterrupt as e:
    try:
        disable_power()
    except Exception:
        pass
    print(e)
except Exception as e:
    try:
        disable_power()
    except Exception:
        pass
    try:
        from utility import print_error_msg
        print_error_msg(e)
    except ImportError:
        print(e)
