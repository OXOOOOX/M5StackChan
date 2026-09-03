# Servo Power Debug Notes

> 2026-09-03 evidence review: this is a historical experiment, not acceptance of
> both axes or the current remote controller. The user confirmed slight motion
> after VM_EN was enabled. See [the consolidated review](debugging_lessons_zh.md).

This note records why the UIFlow2 servo test did not move the StackChan motors until `VM_EN` was enabled.

## Summary

The ESP-NOW receiver and UI were working, and UART writes did not freeze the device, but the yaw motor did not move. The issue was not the remote protocol or the UART pins. The StackChan base servo power rail must be enabled through the PY32L020 IO expander before the serial servos can respond reliably.

The required sequence is:

1. Enable PY32L020 `VM_EN`.
2. Initialize UART1 on `G6/G7` at `1000000`.
3. Ping the servo bus.
4. Send servo position commands only after a valid `FF FF ...` response is seen.

## Official Hardware Clues

Official StackChan documentation:

- Product page: <https://docs.m5stack.com/en/stackchan>
- PinMap lists `G6` as `Servo_TX`.
- PinMap lists `G7` as `Servo_RX`.
- IO Expander section lists the PY32L020 expander and `VM_EN`, which controls the motor/base power rail.
- The PY32L020 I2C address is `0x6F`.

Official firmware evidence in this repository:

- `StackChan-official/firmware/main/hal/hal_servo.cpp`
  - Uses UART1 at `1000000` baud with pins `6` and `7`.
  - Configures yaw servo ID `1`, zero position `460`.
  - Configures pitch servo ID `2`, zero position `620`.
- `StackChan-official/firmware/main/hal/hal_io_expander.cpp`
  - Initializes the PY32 IO expander.
  - Sets IO expander pin `0` as output.
  - Calls `setServoPowerEnabled(true)`.
  - `setServoPowerEnabled(true)` writes pin `0` high.

Important correction: the official product page text led us to check `VM_EN`, but the firmware shows the actual pin used by this codebase is PY32 pin `0`.

## Debug Evidence

Observed sequence:

1. ESP-NOW monitor worked and displayed remote packets.
2. UI-only test worked, including touch `Start` and `Exit`.
3. UART initialization worked:

   ```text
   UART initialized
   ```

4. Sending one yaw position command did not freeze the device, but the motor did not move.
5. Sending yaw torque enable also did not move the motor.
6. Ping before enabling `VM_EN` returned invalid bytes:

   ```text
   C0 C0 00
   ```

   This is not a valid SCSCL servo response. A valid response should start with:

   ```text
   FF FF ...
   ```

7. After enabling PY32 `VM_EN`, the user transcribed:

   ```text
   0x41
   6 FF FF 01 02 00 FB
   6 FF FF 01 02 00 FC
   ```

   Both transcribed packets contain ID `1`. The first has an inconsistent
   checksum for that ID; the second is a valid ID1 status packet. Do not silently
   change the first ID to `2` or count this as proof that both servos passed ping.

8. After `VM_EN` was enabled, the user confirmed slight movement during the yaw sequence test. Later dual-ID recovery has separate evidence in [the replacement record](servo_replacement_debug_zh.md).

Conclusion: servo UART and SCSCL packet writes were basically correct, but the servo power rail was not enabled until PY32 `VM_EN` was set.

## Required UIFlow2 Initialization

The current UIFlow2 test uses these constants:

```python
PY32_I2C_ADDR = 0x6F
I2C_SDA_PIN = 12
I2C_SCL_PIN = 11
REG_VERSION = 0x02
REG_GPIO_M_L = 0x03
REG_GPIO_O_L = 0x05
REG_GPIO_PU_L = 0x09
VM_EN_PIN = 0
```

Minimal power enable logic:

```python
i2c = I2C(0, scl=Pin(11), sda=Pin(12), freq=100000)
version = read_reg(0x02)
set bit 0 in REG_GPIO_M_L   # pin 0 output
set bit 0 in REG_GPIO_PU_L  # pin 0 pull-up
set bit 0 in REG_GPIO_O_L   # pin 0 high, VM_EN on
```

Only after this should the code initialize:

```python
UART(1, baudrate=1000000, tx=6, rx=7, bits=8, parity=None, stop=1)
```

## SCSCL Packet Notes

The official `SCSCL` constructor sets `End = 1`. Therefore 16-bit values are sent high byte first.

Correct Python conversion:

```python
def word_to_scs(value):
    value = int(value) & 0xFFFF
    return [(value >> 8) & 0xFF, value & 0xFF]
```

Yaw raw positions used during the conservative test:

```text
460  center
524  small positive yaw
396  small negative yaw
460  center
```

## Implementation Rule

Do not integrate live remote servo control until the receiver script performs this order:

1. Draw UI.
2. Wait for user action.
3. Enable PY32 `VM_EN`.
4. Ping ID `1` and/or ID `2`.
5. Validate header, target ID, length, error code and checksum; a `FF FF` prefix alone is insufficient. If validation fails, show an error and do not send motion commands.
6. If valid, enable controlled motion.

This prevents confusing ESP-NOW, UI, UART, and motor power problems during future debugging.

This sequence is a design requirement. The current remote prototype still has
partial ping validation and unguarded home commands; see [known limitations](remote_control.md).
