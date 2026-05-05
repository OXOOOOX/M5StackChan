import time

import M5
from M5 import *


RESET_ON_EXIT = False
SERVO_UART_ID = 1
SERVO_TX_PIN = 6
SERVO_RX_PIN = 7
SERVO_BAUD = 1000000
UART_CANDIDATES = (
    (1, 6, 7, 1000000),
    (1, 7, 6, 1000000),
    (2, 6, 7, 1000000),
    (2, 7, 6, 1000000),
    (1, 6, 7, 115200),
    (1, 7, 6, 115200),
)
PY32_I2C_ADDR = 0x6F
I2C_SDA_PIN = 12
I2C_SCL_PIN = 11
REG_VERSION = 0x02
REG_GPIO_M_L = 0x03
REG_GPIO_O_L = 0x05
REG_GPIO_PU_L = 0x09
VM_EN_PIN = 0
YAW_SERVO_ID = 1
YAW_ZERO_POS = 460
SCSCL_GOAL_POSITION_L = 42
SCSCL_TORQUE_ENABLE = 40
INST_PING = 0x01
INST_WRITE = 0x03

START_RECT = (8, 156, 150, 44)
EXIT_RECT = (176, 156, 136, 44)


running = True
touch_was_down = False
touch_action_fired = False
touch_enabled_at_ms = 0
uart = None
uart_config_text = ""

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
    status_label = Widgets.Label("UI ready: yaw sequence test", 8, 44, 1.0, 0x8FE388, 0x101418, Widgets.FONTS.DejaVu18)
    step_label = Widgets.Label("tap Start to move yaw only", 8, 84, 1.0, 0xFFFFFF, 0x101418, Widgets.FONTS.DejaVu18)
    start_button = Widgets.Label("  Start test  ", 14, 166, 1.0, 0xFFFFFF, 0x2B6CB0, Widgets.FONTS.DejaVu18)
    exit_button = Widgets.Label("      Exit      ", 190, 166, 1.0, 0xFFFFFF, 0xB23A48, Widgets.FONTS.DejaVu18)
    hint_label = Widgets.Label("one UART write only", 8, 214, 1.0, 0x9AA4AF, 0x101418, Widgets.FONTS.DejaVu18)


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
    global running, touch_was_down, touch_action_fired

    if time.ticks_diff(time.ticks_ms(), touch_enabled_at_ms) < 0:
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
    if point_in_rect(x, y, START_RECT):
        touch_action_fired = True
        run_power_then_ping()
    elif point_in_rect(x, y, EXIT_RECT):
        touch_action_fired = True
        running = False


def init_uart_only():
    global uart, uart_config_text

    if uart:
        set_text(status_label, "UART already initialized")
        set_text(step_label, "no servo command sent")
        set_text(start_button, " UART ready  ")
        return

    set_text(status_label, "initializing UART...")
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
    uart_config_text = "u{} tx{} rx{} {}".format(SERVO_UART_ID, SERVO_TX_PIN, SERVO_RX_PIN, SERVO_BAUD)
    set_text(status_label, "UART initialized")
    set_text(step_label, "UART1 tx=6 rx=7 baud=1000000")
    set_text(start_button, " UART ready  ")


def init_uart_config(uart_id, tx_pin, rx_pin, baud):
    global uart, uart_config_text

    from machine import UART

    try:
        if uart:
            uart.deinit()
    except Exception:
        pass

    uart = UART(
        uart_id,
        baudrate=baud,
        tx=tx_pin,
        rx=rx_pin,
        bits=8,
        parity=None,
        stop=1,
    )
    uart_config_text = "u{} tx{} rx{} {}".format(uart_id, tx_pin, rx_pin, baud)


def i2c_write_reg(i2c, reg, value):
    i2c.writeto(PY32_I2C_ADDR, bytes([reg, value & 0xFF]))


def i2c_read_reg(i2c, reg):
    i2c.writeto(PY32_I2C_ADDR, bytes([reg]))
    data = i2c.readfrom(PY32_I2C_ADDR, 1)
    return data[0]


def py32_bit_on(i2c, reg, pin):
    value = i2c_read_reg(i2c, reg)
    value |= 1 << pin
    i2c_write_reg(i2c, reg, value)


def enable_servo_power():
    from machine import I2C, Pin

    i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=100000)
    version = i2c_read_reg(i2c, REG_VERSION)
    set_text(status_label, "PY32 version 0x{:02X}".format(version))
    if version == 0 or version == 0xFF:
        return False

    py32_bit_on(i2c, REG_GPIO_M_L, VM_EN_PIN)
    py32_bit_on(i2c, REG_GPIO_PU_L, VM_EN_PIN)
    py32_bit_on(i2c, REG_GPIO_O_L, VM_EN_PIN)
    delay_with_ui(250)
    return True


def scs_write(servo_id, address, data):
    if not uart:
        return

    params = bytes([address]) + bytes(data)
    length = len(params) + 2
    body = bytes([servo_id, length, INST_WRITE]) + params
    checksum = (~sum(body)) & 0xFF
    uart.write(b"\xff\xff" + body + bytes([checksum]))
    try:
        uart.flush()
    except Exception:
        pass


def scs_packet(servo_id, address, data, instruction):
    if data is None:
        length = 2
        body = bytes([servo_id, length, instruction])
        checksum = (~(servo_id + length + instruction + address)) & 0xFF
        return b"\xff\xff" + body + bytes([checksum])

    params = bytes([address]) + bytes(data)
    length = len(params) + 2
    body = bytes([servo_id, length, instruction]) + params
    checksum = (~sum(body)) & 0xFF
    return b"\xff\xff" + body + bytes([checksum])


def uart_write_packet(packet):
    if not uart:
        return
    try:
        while uart.any():
            uart.read()
    except Exception:
        pass
    uart.write(packet)
    try:
        uart.flush()
    except Exception:
        pass


def read_uart_response(timeout_ms=150):
    data = b""
    end_ms = time.ticks_add(time.ticks_ms(), timeout_ms)
    while time.ticks_diff(end_ms, time.ticks_ms()) > 0:
        M5.update()
        try:
            count = uart.any() if uart else 0
            if count:
                chunk = uart.read(count)
                if chunk:
                    data += chunk
        except Exception:
            pass
        time.sleep_ms(10)
    return data


def to_hex(data):
    if not data:
        return "none"
    text = ""
    for b in data[:12]:
        text += "{:02X} ".format(b)
    if len(data) > 12:
        text += "..."
    return text


def ping_servo(servo_id):
    packet = scs_packet(servo_id, 0, None, INST_PING)
    uart_write_packet(packet)
    return read_uart_response(180)


def word_to_scs(value):
    value = int(value) & 0xFFFF
    return [(value >> 8) & 0xFF, value & 0xFF]


def send_yaw_center_only():
    init_uart_only()
    set_text(status_label, "sending yaw center...")
    send_yaw_raw(YAW_ZERO_POS)
    set_text(status_label, "yaw center command sent")
    set_text(step_label, "servo id=1 raw=460")
    set_text(start_button, "    Sent     ")


def send_yaw_raw(raw_position):
    move_time = 20
    speed = 0
    scs_write(
        YAW_SERVO_ID,
        SCSCL_GOAL_POSITION_L,
        word_to_scs(raw_position) + word_to_scs(move_time) + word_to_scs(speed),
    )


def delay_with_ui(ms):
    end_ms = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(end_ms, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(20)


def run_yaw_sequence_only():
    init_uart_only()
    set_text(start_button, "   Running    ")

    set_text(status_label, "yaw torque on")
    set_text(step_label, "servo id=1 addr=40 value=1")
    scs_write(YAW_SERVO_ID, SCSCL_TORQUE_ENABLE, [1])
    delay_with_ui(300)

    set_text(status_label, "yaw center")
    set_text(step_label, "raw=460")
    send_yaw_raw(460)
    delay_with_ui(700)

    set_text(status_label, "yaw +200")
    set_text(step_label, "raw=524")
    send_yaw_raw(524)
    delay_with_ui(900)

    set_text(status_label, "yaw -200")
    set_text(step_label, "raw=396")
    send_yaw_raw(396)
    delay_with_ui(900)

    set_text(status_label, "yaw center")
    set_text(step_label, "raw=460")
    send_yaw_raw(460)
    delay_with_ui(700)

    set_text(status_label, "done")
    set_text(step_label, "yaw sequence finished")
    set_text(start_button, "     Done     ")


def run_bus_diagnostic():
    init_uart_only()
    set_text(start_button, "   Ping...    ")

    set_text(status_label, "ping yaw id=1")
    resp1 = ping_servo(1)
    set_text(step_label, "id1 len={} {}".format(len(resp1), to_hex(resp1)))
    delay_with_ui(800)

    set_text(status_label, "ping pitch id=2")
    resp2 = ping_servo(2)
    set_text(step_label, "id2 len={} {}".format(len(resp2), to_hex(resp2)))
    delay_with_ui(800)

    if resp1 or resp2:
        set_text(status_label, "bus response received")
        set_text(start_button, "  Bus OK?    ")
    else:
        set_text(status_label, "no servo response")
        set_text(start_button, " No reply    ")


def looks_like_servo_reply(data, servo_id):
    if len(data) < 6:
        return False
    for i in range(0, len(data) - 5):
        if data[i] == 0xFF and data[i + 1] == 0xFF and data[i + 2] == servo_id:
            return True
    return False


def run_uart_scan():
    set_text(start_button, "  Scanning   ")
    best_text = "no valid reply"

    for cfg in UART_CANDIDATES:
        uart_id, tx_pin, rx_pin, baud = cfg
        init_uart_config(uart_id, tx_pin, rx_pin, baud)
        set_text(status_label, "scan {}".format(uart_config_text))

        resp1 = ping_servo(1)
        set_text(step_label, "id1 len={} {}".format(len(resp1), to_hex(resp1)))
        delay_with_ui(350)
        if looks_like_servo_reply(resp1, 1):
            best_text = "id1 ok {}".format(uart_config_text)
            break

        resp2 = ping_servo(2)
        set_text(step_label, "id2 len={} {}".format(len(resp2), to_hex(resp2)))
        delay_with_ui(350)
        if looks_like_servo_reply(resp2, 2):
            best_text = "id2 ok {}".format(uart_config_text)
            break

    set_text(status_label, best_text)
    set_text(start_button, " Scan done   ")


def run_power_then_ping():
    set_text(start_button, " Power on    ")
    set_text(status_label, "enabling VM_EN")
    ok = enable_servo_power()
    if not ok:
        set_text(status_label, "PY32 not found")
        set_text(step_label, "addr=0x6F sda=12 scl=11")
        set_text(start_button, "  No PY32    ")
        return

    init_uart_config(1, 6, 7, 1000000)
    set_text(status_label, "ping id1 after VM_EN")
    resp1 = ping_servo(1)
    set_text(step_label, "id1 len={} {}".format(len(resp1), to_hex(resp1)))
    delay_with_ui(800)

    set_text(status_label, "ping id2 after VM_EN")
    resp2 = ping_servo(2)
    set_text(step_label, "id2 len={} {}".format(len(resp2), to_hex(resp2)))
    delay_with_ui(800)

    if looks_like_servo_reply(resp1, 1) or looks_like_servo_reply(resp2, 2):
        set_text(status_label, "servo bus OK, running yaw")
        delay_with_ui(500)
        run_yaw_sequence_only()
    else:
        set_text(status_label, "no servo reply after VM_EN")
        set_text(start_button, " No reply    ")


def finish():
    set_text(status_label, "stopped")
    set_text(step_label, "finished")
    if RESET_ON_EXIT:
        import machine

        machine.reset()


def main():
    global touch_enabled_at_ms

    setup_screen()
    touch_enabled_at_ms = time.ticks_add(time.ticks_ms(), 1000)
    set_text(hint_label, "wait 1s, then tap")
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
