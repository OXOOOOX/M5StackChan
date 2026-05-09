"""
servo_bus_diagnostic.py - conservative StackChan servo bus diagnostic.

中文说明：
    StackChan 串行舵机总线诊断工具。
    用于 calibration 显示 no servo、舵机卡死后更换舵机、或怀疑
    VM_EN 电源/UART/舵机 ID 异常时排查。

安全规则：
    Power、Ping、Scan 不发送运动命令。
    Jog1 只小幅测试 ID1/yaw，Jog2 只小幅测试 ID2/pitch。
    Jog 前必须先通过 Ping 或 Scan 找到对应舵机 ID。

Paste into UIFlow2 and run on the StackChan CoreS3.

Use this when calibration says "no servo" after a jam or servo swap.
The script does not move any motor during Power, Ping, or Scan. The only
movement is the Jog button, and it is locked until a valid servo reply is seen.
"""

import time

import M5
from M5 import *


# PY32L020 IO expander: VM_EN controls the StackChan servo power rail.
PY32_I2C_ADDR = 0x6F
I2C_BUS_CANDIDATES = (0, 1)
I2C_SDA_PIN = 12
I2C_SCL_PIN = 11
REG_VERSION = 0x02
REG_GPIO_M_L = 0x03
REG_GPIO_O_L = 0x05
REG_GPIO_PU_L = 0x09
VM_EN_PIN = 0

# Official StackChan servo bus.
DEFAULT_UART = (1, 6, 7, 1000000)  # uart_id, tx, rx, baud
UART_CANDIDATES = (
    (1, 6, 7, 1000000),
    (1, 7, 6, 1000000),
    (2, 6, 7, 1000000),
    (2, 7, 6, 1000000),
    (1, 6, 7, 115200),
    (1, 7, 6, 115200),
    (2, 6, 7, 115200),
    (2, 7, 6, 115200),
)

YAW_ID = 1
PITCH_ID = 2
YAW_ZERO = 510
PITCH_ZERO = 610
RAW_STEP = 18

# SCSCL protocol.
INST_PING = 0x01
INST_WRITE = 0x03
SCSCL_TORQUE_ENABLE = 40
SCSCL_GOAL_POSITION_L = 42

PING_TIMEOUT_MS = 220
POWER_SETTLE_MS = 350
PING_RETRIES = 3


CLR_BG = 0x101418
CLR_TITLE_BG = 0x2B6CB0
CLR_WHITE = 0xFFFFFF
CLR_GREY = 0x9AA4AF
CLR_GREEN = 0x8FE388
CLR_YELLOW = 0xFFD166
CLR_CYAN = 0x48CAE4
CLR_RED = 0xB23A48
CLR_BTN = 0x2D6A4F
CLR_BTN_BLUE = 0x2B6CB0
CLR_BTN_RED = 0xB23A48

BTN_POWER = (8, 68, 70, 34)
BTN_PING = (86, 68, 70, 34)
BTN_SCAN = (164, 68, 70, 34)
BTN_EXIT = (242, 68, 70, 34)
BTN_JOG1 = (86, 112, 70, 34)
BTN_JOG2 = (164, 112, 70, 34)


running = True
powered = False
touch_action_fired = False
touch_enabled_ms = 0
uart = None
uart_config = DEFAULT_UART
found_ids = []

status_label = None
line1_label = None
line2_label = None
line3_label = None
hint_label = None
btn_power_lbl = None


def setup_screen():
    global status_label, line1_label, line2_label, line3_label, hint_label
    global btn_power_lbl

    M5.begin()
    Widgets.fillScreen(CLR_BG)
    Widgets.Title("Servo Bus Diag", 3, CLR_WHITE, CLR_TITLE_BG, Widgets.FONTS.DejaVu18)
    status_label = make_label("Tap Power first", 8, 34, CLR_GREEN)
    line1_label = make_label("Power/Ping/Scan: no movement", 8, 160, CLR_GREY)
    line2_label = make_label("Jog1=yaw  Jog2=pitch", 8, 184, CLR_GREY)
    line3_label = make_label("Ready", 8, 208, CLR_CYAN)
    hint_label = make_label("", 8, 230, CLR_YELLOW)

    btn_power_lbl = draw_button("Power", BTN_POWER, CLR_BTN)
    draw_button("Ping", BTN_PING, CLR_BTN_BLUE)
    draw_button("Scan", BTN_SCAN, CLR_BTN_BLUE)
    draw_button("Exit", BTN_EXIT, CLR_BTN_RED)
    draw_button("Jog1", BTN_JOG1, CLR_BTN_BLUE)
    draw_button("Jog2", BTN_JOG2, CLR_BTN_BLUE)


def make_label(text, x, y, color):
    return Widgets.Label(text, x, y, 1.0, color, CLR_BG, Widgets.FONTS.DejaVu18)


def draw_button(text, rect, color):
    x, y, w, h = rect
    return Widgets.Label(text, x + 7, y + 8, 1.0, CLR_WHITE, color, Widgets.FONTS.DejaVu18)


def set_text(label, text):
    if label:
        label.setText(str(text))


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


def i2c_write_reg(i2c, reg, value):
    i2c.writeto(PY32_I2C_ADDR, bytes([reg, value & 0xFF]))


def i2c_read_reg(i2c, reg):
    i2c.writeto(PY32_I2C_ADDR, bytes([reg]))
    return i2c.readfrom(PY32_I2C_ADDR, 1)[0]


def bit_on(i2c, reg, pin):
    value = i2c_read_reg(i2c, reg)
    i2c_write_reg(i2c, reg, value | (1 << pin))


def bit_off(i2c, reg, pin):
    value = i2c_read_reg(i2c, reg)
    i2c_write_reg(i2c, reg, value & ~(1 << pin))


def make_i2c(bus_id):
    from machine import I2C, Pin
    return I2C(bus_id, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=100000)


def try_i2c_scan(i2c):
    try:
        return i2c.scan()
    except Exception as e:
        print("i2c scan error:", e)
    return []


def open_py32_i2c():
    last_error = None
    for bus_id in I2C_BUS_CANDIDATES:
        try:
            i2c = make_i2c(bus_id)
            devices = try_i2c_scan(i2c)
            print("I2C%d scan:" % bus_id, devices)
            if PY32_I2C_ADDR in devices:
                return i2c, bus_id, devices, None
            try:
                version = i2c_read_reg(i2c, REG_VERSION)
                print("I2C%d direct read version=0x%02X" % (bus_id, version))
                return i2c, bus_id, devices, None
            except Exception as e:
                last_error = e
                print("I2C%d py32 read error:" % bus_id, e)
        except Exception as e:
            last_error = e
            print("I2C%d init error:" % bus_id, e)
    return None, -1, [], last_error


def enable_power():
    global powered

    set_text(status_label, "Enabling VM_EN...")
    i2c, bus_id, devices, err = open_py32_i2c()
    if i2c is None:
        powered = False
        set_text(status_label, "I2C/PY32 error")
        set_text(line1_label, "No PY32 at addr 0x6F on I2C0/1")
        set_text(line2_label, "Last err: %s" % err)
        set_text(line3_label, "Check CoreS3 seated, base board, power")
        print("PY32 open failed, last error:", err)
        return False

    try:
        version = i2c_read_reg(i2c, REG_VERSION)
        before_m = i2c_read_reg(i2c, REG_GPIO_M_L)
        before_o = i2c_read_reg(i2c, REG_GPIO_O_L)
        before_pu = i2c_read_reg(i2c, REG_GPIO_PU_L)
    except Exception as e:
        powered = False
        set_text(status_label, "PY32 read failed")
        set_text(line1_label, "I2C%d addr 0x6F read error" % bus_id)
        set_text(line2_label, "err: %s" % e)
        set_text(line3_label, "Likely base/connector/I2C issue")
        print("PY32 register read failed:", e)
        return False

    if version == 0 or version == 0xFF:
        powered = False
        set_text(status_label, "PY32 not found")
        set_text(line1_label, "I2C%d scan=%s" % (bus_id, devices))
        set_text(line2_label, "If stock firmware also fails, base board may be damaged")
        print("PY32 not found: version=0x%02X" % version)
        return False

    try:
        bit_on(i2c, REG_GPIO_M_L, VM_EN_PIN)
        bit_on(i2c, REG_GPIO_PU_L, VM_EN_PIN)
        bit_on(i2c, REG_GPIO_O_L, VM_EN_PIN)
    except Exception as e:
        powered = False
        set_text(status_label, "VM_EN write failed")
        set_text(line1_label, "I2C%d PY32 version=0x%02X" % (bus_id, version))
        set_text(line2_label, "err: %s" % e)
        set_text(line3_label, "Cannot enable servo power rail")
        print("PY32 VM_EN write failed:", e)
        return False

    delay_ui(POWER_SETTLE_MS)

    try:
        after_m = i2c_read_reg(i2c, REG_GPIO_M_L)
        after_o = i2c_read_reg(i2c, REG_GPIO_O_L)
        after_pu = i2c_read_reg(i2c, REG_GPIO_PU_L)
    except Exception as e:
        set_text(status_label, "VM_EN on, verify failed")
        set_text(line1_label, "I2C%d PY32 version=0x%02X" % (bus_id, version))
        set_text(line2_label, "post-read err: %s" % e)
        set_text(line3_label, "Try Ping, but power state uncertain")
        print("PY32 post-write read failed:", e)
        powered = True
        return True

    powered = True
    set_text(btn_power_lbl, "On")
    set_text(status_label, "PY32 OK, VM_EN on")
    set_text(line1_label, "I2C%d ver=0x%02X M:%02X>%02X" % (bus_id, version, before_m, after_m))
    set_text(line2_label, "PU:%02X>%02X. Now tap Ping." % (before_pu, after_pu))
    set_text(line3_label, "No movement command has been sent")
    print("PY32 I2C%d version=0x%02X M %02X->%02X O %02X->%02X PU %02X->%02X" %
          (bus_id, version, before_m, after_m, before_o, after_o, before_pu, after_pu))
    return True


def disable_power():
    global powered

    torque_off_all()
    try:
        i2c, bus_id, devices, err = open_py32_i2c()
        if i2c is None:
            print("disable_power: no PY32 I2C:", err)
            powered = False
            return
        bit_off(i2c, REG_GPIO_O_L, VM_EN_PIN)
    except Exception as e:
        print("disable_power error:", e)
    powered = False


def init_uart(config):
    global uart, uart_config
    from machine import UART

    try:
        if uart:
            uart.deinit()
    except Exception:
        pass

    uart_id, tx_pin, rx_pin, baud = config
    uart = UART(uart_id, baudrate=baud, tx=tx_pin, rx=rx_pin, bits=8, parity=None, stop=1)
    uart_config = config


def config_text(config=None):
    if config is None:
        config = uart_config
    uart_id, tx_pin, rx_pin, baud = config
    return "u%d tx%d rx%d %d" % (uart_id, tx_pin, rx_pin, baud)


def flush_rx():
    try:
        while uart and uart.any():
            uart.read()
    except Exception:
        pass


def write_packet(packet):
    if not uart:
        return
    flush_rx()
    uart.write(packet)
    try:
        uart.flush()
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


def scs_packet(servo_id, instruction, address=0, data=None):
    if data is None:
        body = bytes([servo_id, 2, instruction])
    else:
        params = bytes([address]) + bytes(data)
        body = bytes([servo_id, len(params) + 2, instruction]) + params
    checksum = (~sum(body)) & 0xFF
    return b"\xff\xff" + body + bytes([checksum])


def word_to_scs(value):
    value = int(value) & 0xFFFF
    return [(value >> 8) & 0xFF, value & 0xFF]


def to_hex(data, limit=16):
    if not data:
        return "none"
    text = ""
    for b in data[:limit]:
        text += "%02X " % b
    if len(data) > limit:
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
    write_packet(scs_packet(servo_id, INST_PING))
    return read_response()


def ping_id_retry(servo_id):
    best = b""
    for retry in range(PING_RETRIES):
        resp = ping_id(servo_id)
        if resp:
            best = resp
        if valid_reply(resp, servo_id):
            return True, resp, retry + 1
        delay_ui(60)
    return False, best, PING_RETRIES


def ping_default():
    global found_ids
    if not powered and not enable_power():
        return
    init_uart(DEFAULT_UART)
    set_text(status_label, "Pinging id 1 and 2...")
    found_ids = []
    ok1, resp1, tries1 = ping_id_retry(YAW_ID)
    if ok1:
        found_ids.append(YAW_ID)
    ok1_text = "FAIL"
    if ok1:
        ok1_text = "OK"
    set_text(line1_label, "id1 %s try=%d len=%d %s" % (ok1_text, tries1, len(resp1), to_hex(resp1)))
    print("ping id=1 %s try=%d len=%d %s" % (ok1_text, tries1, len(resp1), to_hex(resp1, 64)))
    delay_ui(250)

    ok2, resp2, tries2 = ping_id_retry(PITCH_ID)
    if ok2:
        found_ids.append(PITCH_ID)
    ok2_text = "FAIL"
    if ok2:
        ok2_text = "OK"
    set_text(line2_label, "id2 %s try=%d len=%d %s" % (ok2_text, tries2, len(resp2), to_hex(resp2)))
    print("ping id=2 %s try=%d len=%d %s" % (ok2_text, tries2, len(resp2), to_hex(resp2, 64)))

    if found_ids:
        set_text(status_label, "Servo reply found")
        set_text(line3_label, "Found IDs: %s" % found_ids)
    else:
        set_text(status_label, "No servo on default bus")
        set_text(line3_label, "Tap Scan. Also inspect cable/power/base board.")


def scan_bus():
    global found_ids
    if not powered and not enable_power():
        return

    found_ids = []
    set_text(status_label, "Scanning UART configs...")
    print("=== servo bus scan start ===")
    for cfg in UART_CANDIDATES:
        init_uart(cfg)
        cfg_name = config_text(cfg)
        set_text(line1_label, cfg_name)
        print("config", cfg_name)
        ids_here = []
        for servo_id in range(1, 11):
            ok, resp, tries = ping_id_retry(servo_id)
            if resp or ok:
                state_text = "RAW"
                if ok:
                    state_text = "OK"
                print(" id=%d %s try=%d len=%d %s" % (servo_id, state_text, tries, len(resp), to_hex(resp, 64)))
            if ok:
                ids_here.append(servo_id)
                if servo_id not in found_ids:
                    found_ids.append(servo_id)
            if servo_id in (2, 5, 8):
                set_text(line2_label, "scanning id %d..." % servo_id)
                delay_ui(20)
        if ids_here:
            set_text(status_label, "Found on " + cfg_name)
            set_text(line2_label, "IDs: %s" % ids_here)
            set_text(line3_label, "Jog1 yaw, Jog2 pitch")
            print("found config", cfg_name, "ids", ids_here)
            print("=== servo bus scan end ===")
            return
    set_text(status_label, "Scan found no valid servo")
    set_text(line2_label, "No FF FF <id> reply on tested configs")
    set_text(line3_label, "Likely power rail, cable, port, or damaged bus")
    print("no valid servo reply")
    print("=== servo bus scan end ===")


def send_write(servo_id, address, data):
    write_packet(scs_packet(servo_id, INST_WRITE, address, data))


def torque_off_all():
    try:
        if not uart:
            init_uart(DEFAULT_UART)
        for servo_id in range(1, 11):
            send_write(servo_id, SCSCL_TORQUE_ENABLE, [0])
            time.sleep_ms(10)
    except Exception as e:
        print("torque_off_all error:", e)


def set_position_raw(servo_id, raw_pos, move_time_ms=250, speed=0):
    raw_pos = max(0, min(1023, int(raw_pos)))
    data = word_to_scs(raw_pos) + word_to_scs(move_time_ms) + word_to_scs(speed)
    send_write(servo_id, SCSCL_GOAL_POSITION_L, data)


def jog_test(servo_id):
    if servo_id not in found_ids:
        set_text(status_label, "Ping/Scan first")
        set_text(line3_label, "Jog%d locked: ID not found" % servo_id)
        return

    zero = PITCH_ZERO
    if servo_id == YAW_ID:
        zero = YAW_ZERO
    init_uart(uart_config)
    set_text(status_label, "Small jog id=%d" % servo_id)
    set_text(line1_label, "If it binds, tap Exit immediately")
    print("jog id=%d zero=%d step=%d cfg=%s" % (servo_id, zero, RAW_STEP, config_text()))

    send_write(servo_id, SCSCL_TORQUE_ENABLE, [1])
    delay_ui(200)
    set_position_raw(servo_id, zero, 280)
    delay_ui(450)
    set_position_raw(servo_id, zero + RAW_STEP, 280)
    delay_ui(550)
    set_position_raw(servo_id, zero - RAW_STEP, 280)
    delay_ui(550)
    set_position_raw(servo_id, zero, 280)
    delay_ui(450)
    send_write(servo_id, SCSCL_TORQUE_ENABLE, [0])
    set_text(status_label, "Jog done, torque off")
    set_text(line2_label, "id=%d moved only +/- %d raw" % (servo_id, RAW_STEP))


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
    if point_in_rect(x, y, BTN_POWER):
        if powered:
            disable_power()
            set_text(status_label, "Power off")
            set_text(btn_power_lbl, "Power")
        else:
            enable_power()
    elif point_in_rect(x, y, BTN_PING):
        ping_default()
    elif point_in_rect(x, y, BTN_SCAN):
        scan_bus()
    elif point_in_rect(x, y, BTN_JOG1):
        jog_test(YAW_ID)
    elif point_in_rect(x, y, BTN_JOG2):
        jog_test(PITCH_ID)
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

    set_text(status_label, "Stopping...")
    disable_power()
    set_text(status_label, "Stopped, power off")
    delay_ui(300)


try:
    main()
except KeyboardInterrupt as e:
    try:
        disable_power()
    except Exception:
        pass
    try:
        from utility import print_error_msg
        print_error_msg(e)
    except ImportError:
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
