# M5StackChan Remote Receiver for UIFlow2

UIFlow2/MicroPython scripts for receiving ESP-NOW remote-control packets from a StickS3 + Unit Joystick2 remote and monitoring them on StackChan.

`v0.1.0` is a safe receiver UI release. It receives and displays remote packets, provides a countdown auto-stop, and includes touch buttons for continuous listening and immediate exit. It does not drive StackChan servos yet.

## Features

- ESP-NOW packet receiver for StackChan remote-control packets
- Touch UI with packet status
- Countdown auto-stop
- `Stop timer` touch button for continuous listening
- `Exit` touch button for immediate stop
- `BtnA` fallback to stop the countdown
- Receiver ID diagnostics showing `rx` or `ignored`

## Hardware

- M5Stack StackChan running UIFlow2 firmware
- StickS3 + Unit Joystick2 remote firmware

Remote firmware used during development:

https://github.com/OXOOOOX/StackChan-Remote-StickS3-Joystick2

## Quick Start

1. Flash UIFlow2 firmware to StackChan with M5Burner.
2. Connect StackChan to UIFlow2 Web IDE.
3. Open [`uiflow2/remote_countdown_monitor_safe.py`](uiflow2/remote_countdown_monitor_safe.py).
4. Set these values if needed:

```python
RECEIVER_ID = 1
WIFI_CHANNEL = 1
RUN_SECONDS = 30
```

5. Run the script in UIFlow2.
6. Start the StickS3 remote in ESP-NOW running mode.

The screen should show packets like:

```text
rx id:0 yaw:12 pitch:450 speed:600 laser:0 #32
```

If it shows `ignored id:X`, set `RECEIVER_ID = X` or configure the remote to broadcast with ID `0`.

## Script Layout

```text
uiflow2/
  remote_countdown_monitor_safe.py  # v0.1.0 main script
  espnow_packet_monitor.py          # raw ESP-NOW packet monitor
  servo_minimal_test.py             # UI/touch test, servo code disabled
  experimental/
    espnow_remote_receiver.py       # experimental direct servo receiver
    stackchan_remote_receiver_ui.py # old UI experiment, not recommended
```

## Documentation

- [Setup](docs/setup.md)
- [ESP-NOW protocol](docs/protocol.md)
- [Troubleshooting](docs/troubleshooting.md)

## Release Plan

- `v0.1.0`: Safe ESP-NOW listener UI. Completed.
- `v0.2.0`: Minimal servo-control validation on UIFlow2.
- `v0.3.0`: Remote yaw/pitch/speed mapped to StackChan motion.

## Safety

Do not run scripts in `uiflow2/experimental/` unless you are debugging them. Earlier direct-control versions caused device freezes on some UIFlow2 firmware builds.
