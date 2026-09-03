"""
servo.py — StackChan SCSCL servo driver for UIFlow2/MicroPython.

Hardware:
    PY32L020 IO expander at I2C 0x6F (SDA=G12, SCL=G11) controls VM_EN (pin 0).
    Two SCSCL feedback servos on UART1 (TX=G6, RX=G7, 1 Mbaud):
        Yaw  — ID 1, zero position 460, 360° continuous rotation
        Pitch — ID 2, zero position 620, ~90° range

Usage:
    from lib.servo import ServoController
    sc = ServoController()
    sc.enable_power()       # PY32 VM_EN on
    sc.init_uart()          # UART1 at 1 Mbaud
    if sc.ping(1):          # check yaw servo alive
        sc.set_yaw(30)      # turn 30 degrees right
        sc.set_pitch(20)    # tilt up 20 degrees
    sc.shutdown()           # torque off, power off
"""

import time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

# Degree-to-raw conversion scale.
# SCSCL servos: ~1024 steps per 300 degrees → ~3.41 steps/degree.
# Official firmware uses these zero positions directly with raw offsets.
STEPS_PER_DEGREE = 3.41

# Safety limits (degrees from zero)
YAW_MIN_DEG = -180
YAW_MAX_DEG = 180
PITCH_MIN_DEG = -30  # tilt down
PITCH_MAX_DEG = 45   # tilt up

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


# ---------------------------------------------------------------------------
# ServoController
# ---------------------------------------------------------------------------

class ServoController:
    """High-level controller for StackChan's two SCSCL servos."""

    def __init__(self):
        self._uart = None
        self._i2c = None
        self._power_on = False
        self._yaw_ready = False
        self._pitch_ready = False
        self._last_cmd_ms = 0

    # ------------------------------------------------------------------
    # Power management (PY32 IO expander)
    # ------------------------------------------------------------------

    def enable_power(self):
        """Enable the servo power rail via PY32 VM_EN. Returns PY32 version or 0 on failure."""
        from machine import I2C, Pin

        self._i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=100000)
        version = self._i2c_read_reg(REG_VERSION)
        if version == 0 or version == 0xFF:
            return 0

        self._py32_bit_on(REG_GPIO_M_L, VM_EN_PIN)   # pin 0 output
        self._py32_bit_on(REG_GPIO_PU_L, VM_EN_PIN)   # pin 0 pull-up
        self._py32_bit_on(REG_GPIO_O_L, VM_EN_PIN)    # pin 0 high → VM_EN on
        time.sleep_ms(POWER_SETTLE_MS)
        self._power_on = True
        return version

    def disable_power(self):
        """Disable the servo power rail."""
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

    # ------------------------------------------------------------------
    # UART management
    # ------------------------------------------------------------------

    def init_uart(self):
        """Initialize UART1 for SCSCL servo communication."""
        from machine import UART

        if self._uart:
            try:
                self._uart.deinit()
            except Exception:
                pass

        self._uart = UART(
            SERVO_UART_ID,
            baudrate=SERVO_BAUD,
            tx=SERVO_TX_PIN,
            rx=SERVO_RX_PIN,
            bits=8,
            parity=None,
            stop=1,
        )

    # ------------------------------------------------------------------
    # SCSCL low-level protocol
    # ------------------------------------------------------------------

    def _flush_rx(self):
        """Discard any pending bytes in the UART RX buffer."""
        if not self._uart:
            return
        try:
            while self._uart.any():
                self._uart.read()
        except Exception:
            pass

    def _send_packet(self, servo_id, instruction, address=0, data=None):
        """Build and send an SCSCL packet."""
        if not self._uart:
            return

        self._flush_rx()

        if data is None:
            # Ping-style packet (no address/data payload)
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
        """Read bytes from UART within timeout. Returns bytes."""
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
        """Convert a 16-bit value to SCSCL big-endian byte pair."""
        value = int(value) & 0xFFFF
        return [(value >> 8) & 0xFF, value & 0xFF]

    @staticmethod
    def _is_valid_reply(data, servo_id):
        """Check if data contains a valid SCSCL FF FF <id> ... response."""
        if len(data) < 6:
            return False
        for i in range(0, len(data) - 5):
            if data[i] == 0xFF and data[i + 1] == 0xFF and data[i + 2] == servo_id:
                return True
        return False

    # ------------------------------------------------------------------
    # Servo commands
    # ------------------------------------------------------------------

    def ping(self, servo_id):
        """Ping a servo. Returns True if a valid response is received."""
        self._send_packet(servo_id, INST_PING)
        resp = self._read_response()
        return self._is_valid_reply(resp, servo_id)

    def set_torque(self, servo_id, enabled):
        """Enable or disable torque on a servo."""
        self._send_packet(servo_id, INST_WRITE, SCSCL_TORQUE_ENABLE,
                          [1 if enabled else 0])

    def set_position_raw(self, servo_id, raw_pos, move_time_ms=DEFAULT_MOVE_TIME_MS, speed=0):
        """Send a raw goal position command to a servo."""
        # Rate limit
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._last_cmd_ms)
        if elapsed < MIN_COMMAND_INTERVAL_MS:
            time.sleep_ms(MIN_COMMAND_INTERVAL_MS - elapsed)

        data = (self._word_to_scs(raw_pos) +
                self._word_to_scs(move_time_ms) +
                self._word_to_scs(speed))
        self._send_packet(servo_id, INST_WRITE, SCSCL_GOAL_POSITION_L, data)
        self._last_cmd_ms = time.ticks_ms()

    # ------------------------------------------------------------------
    # High-level degree-based control
    # ------------------------------------------------------------------

    @staticmethod
    def _deg_to_raw(degrees, zero_pos, min_deg, max_deg):
        """Convert degrees to raw SCSCL position, clamped to safe range."""
        degrees = max(min_deg, min(max_deg, degrees))
        return int(zero_pos + degrees * STEPS_PER_DEGREE)

    def set_yaw(self, degrees, move_time_ms=DEFAULT_MOVE_TIME_MS):
        """Set yaw position in degrees from center. Positive = right."""
        raw = self._deg_to_raw(degrees, YAW_ZERO, YAW_MIN_DEG, YAW_MAX_DEG)
        self.set_position_raw(YAW_ID, raw, move_time_ms)

    def set_pitch(self, degrees, move_time_ms=DEFAULT_MOVE_TIME_MS):
        """Set pitch position in degrees from center. Positive = up."""
        raw = self._deg_to_raw(degrees, PITCH_ZERO, PITCH_MIN_DEG, PITCH_MAX_DEG)
        self.set_position_raw(PITCH_ID, raw, move_time_ms)

    def center(self, move_time_ms=DEFAULT_MOVE_TIME_MS):
        """Move both servos to center position."""
        self.set_yaw(0, move_time_ms)
        self.set_pitch(0, move_time_ms)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self):
        """Full startup sequence: power on → UART init → ping both servos.

        Returns (yaw_ok, pitch_ok) tuple.
        """
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
        """Disable torque on both servos and turn off power."""
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

    # ------------------------------------------------------------------
    # PY32 I2C helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Debug helpers
    # ------------------------------------------------------------------

    @staticmethod
    def to_hex(data, max_bytes=12):
        """Format bytes as hex string for debug display."""
        if not data:
            return "none"
        text = ""
        for b in data[:max_bytes]:
            text += "{:02X} ".format(b)
        if len(data) > max_bytes:
            text += "..."
        return text.strip()

    def ping_verbose(self, servo_id):
        """Ping a servo and return (ok, hex_string) for debug display."""
        self._send_packet(servo_id, INST_PING)
        resp = self._read_response()
        ok = self._is_valid_reply(resp, servo_id)
        return ok, "len={} {}".format(len(resp), self.to_hex(resp))
