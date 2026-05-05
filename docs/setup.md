# Setup

## Requirements

- StackChan with UIFlow2 firmware
- StickS3 + Unit Joystick2 remote
- UIFlow2 Web IDE

## Flash UIFlow2

1. Open M5Burner.
2. Select the StackChan/CoreS3 UIFlow2 firmware.
3. Burn the firmware and configure Wi-Fi.
4. Confirm the device appears online in UIFlow2 Web IDE.

## Run the v0.1.0 Receiver

Use:

```text
uiflow2/remote_countdown_monitor_safe.py
```

Important settings:

```python
RECEIVER_ID = 1
WIFI_CHANNEL = 1
RUN_SECONDS = 30
```

The remote and receiver must use the same Wi-Fi channel. `RECEIVER_ID` must match the packet target ID unless the remote broadcasts with target ID `0`.

## UI Controls

- `Stop timer`: stops the countdown and keeps listening.
- `Exit`: stops listening immediately.
- `BtnA`: hardware fallback for stopping the countdown.

## Upload Method

Paste the full script into UIFlow2 Python mode and use `Run` first. Use `Download` only after confirming the script is stable on your device.
