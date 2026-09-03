"""
motion.py — Joystick-to-servo motion mapper for StackChan.

Maps ESP-NOW remote joystick values to servo degree commands with
deadzone filtering, sensitivity control, and exponential smoothing.

Usage:
    from lib.motion import MotionMapper
    mm = MotionMapper()
    yaw_deg, pitch_deg, move_ms = mm.update(yaw_raw, pitch_raw, speed_raw)
"""

import time


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Joystick input ranges (from ESP-NOW protocol)
YAW_INPUT_MIN = -1280
YAW_INPUT_MAX = 1280
PITCH_INPUT_MIN = 0
PITCH_INPUT_MAX = 900
SPEED_INPUT_MIN = 0
SPEED_INPUT_MAX = 1000

# Output degree ranges
YAW_OUTPUT_MIN = -120
YAW_OUTPUT_MAX = 120
PITCH_OUTPUT_MIN = -25
PITCH_OUTPUT_MAX = 40

# Deadzone (input values within this range from center are treated as zero)
DEFAULT_DEADZONE = 50

# Smoothing factor (0.0 = no smoothing / instant, 1.0 = never moves)
DEFAULT_SMOOTHING = 0.3

# Speed-to-move-time mapping
MOVE_TIME_MIN_MS = 50    # fastest
MOVE_TIME_MAX_MS = 400   # slowest (when speed is low)

# Auto-center timeout: if no update for this long, return to center
AUTO_CENTER_TIMEOUT_MS = 3000


# ---------------------------------------------------------------------------
# MotionMapper
# ---------------------------------------------------------------------------

class MotionMapper:
    """Maps joystick input to servo degrees with filtering."""

    def __init__(self,
                 deadzone=DEFAULT_DEADZONE,
                 smoothing=DEFAULT_SMOOTHING,
                 yaw_invert=False,
                 pitch_invert=False,
                 yaw_sensitivity=1.0,
                 pitch_sensitivity=1.0):
        self.deadzone = deadzone
        self.smoothing = smoothing
        self.yaw_invert = yaw_invert
        self.pitch_invert = pitch_invert
        self.yaw_sensitivity = yaw_sensitivity
        self.pitch_sensitivity = pitch_sensitivity

        # Smoothed output state
        self._yaw_smooth = 0.0
        self._pitch_smooth = 0.0
        self._last_update_ms = time.ticks_ms()

    # ------------------------------------------------------------------
    # Core mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_range(value, in_min, in_max, out_min, out_max):
        """Linear interpolation from input range to output range."""
        if in_max == in_min:
            return (out_min + out_max) / 2
        return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def _apply_deadzone(self, value, center=0):
        """Return 0 if value is within deadzone of center."""
        if abs(value - center) < self.deadzone:
            return center
        return value

    @staticmethod
    def _clamp(value, lo, hi):
        return max(lo, min(hi, value))

    def _speed_to_move_time(self, speed_raw):
        """Convert speed input (0-1000) to move time in ms.
        Higher speed → shorter move time (faster motion).
        """
        if speed_raw <= 0:
            return MOVE_TIME_MAX_MS
        ratio = self._clamp(speed_raw / SPEED_INPUT_MAX, 0.0, 1.0)
        return int(MOVE_TIME_MAX_MS - ratio * (MOVE_TIME_MAX_MS - MOVE_TIME_MIN_MS))

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, yaw_raw, pitch_raw, speed_raw):
        """Process one frame of joystick input.

        Args:
            yaw_raw: int from ESP-NOW packet (-1280 to 1280)
            pitch_raw: int from ESP-NOW packet (0 to 900)
            speed_raw: int from ESP-NOW packet (0 to 1000)

        Returns:
            (yaw_degrees, pitch_degrees, move_time_ms)
        """
        self._last_update_ms = time.ticks_ms()

        # Apply deadzone
        yaw_raw = self._apply_deadzone(yaw_raw, 0)
        pitch_center = (PITCH_INPUT_MIN + PITCH_INPUT_MAX) // 2
        pitch_raw = self._apply_deadzone(pitch_raw, pitch_center)

        # Map to degrees
        yaw_target = self._map_range(yaw_raw,
                                     YAW_INPUT_MIN, YAW_INPUT_MAX,
                                     YAW_OUTPUT_MIN, YAW_OUTPUT_MAX)
        pitch_target = self._map_range(pitch_raw,
                                       PITCH_INPUT_MIN, PITCH_INPUT_MAX,
                                       PITCH_OUTPUT_MIN, PITCH_OUTPUT_MAX)

        # Apply sensitivity
        yaw_target *= self.yaw_sensitivity
        pitch_target *= self.pitch_sensitivity

        # Apply inversion
        if self.yaw_invert:
            yaw_target = -yaw_target
        if self.pitch_invert:
            pitch_target = -pitch_target

        # Clamp
        yaw_target = self._clamp(yaw_target, YAW_OUTPUT_MIN, YAW_OUTPUT_MAX)
        pitch_target = self._clamp(pitch_target, PITCH_OUTPUT_MIN, PITCH_OUTPUT_MAX)

        # Exponential smoothing
        alpha = 1.0 - self.smoothing
        self._yaw_smooth = self._yaw_smooth * self.smoothing + yaw_target * alpha
        self._pitch_smooth = self._pitch_smooth * self.smoothing + pitch_target * alpha

        # Move time from speed
        move_time = self._speed_to_move_time(speed_raw)

        return self._yaw_smooth, self._pitch_smooth, move_time

    def should_auto_center(self):
        """Returns True if no update has been received within the timeout."""
        elapsed = time.ticks_diff(time.ticks_ms(), self._last_update_ms)
        return elapsed > AUTO_CENTER_TIMEOUT_MS

    def reset(self):
        """Reset smoothing state to center."""
        self._yaw_smooth = 0.0
        self._pitch_smooth = 0.0
        self._last_update_ms = time.ticks_ms()
