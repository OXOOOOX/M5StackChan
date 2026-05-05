# Troubleshooting

## Screen Shows `waiting for remote...`

Check:

- Remote is in ESP-NOW running mode.
- `WIFI_CHANNEL` matches the remote channel.
- StackChan and remote are close enough.
- Use `uiflow2/espnow_packet_monitor.py` to confirm raw packets.

## Screen Shows `ignored id:X`

The receiver is getting packets, but the target ID does not match.

Fix one side:

```python
RECEIVER_ID = X
```

or configure the remote target ID to `0` for broadcast.

## Device Stops Immediately

This usually means an old touch coordinate was interpreted as a button press, or the script was pasted partially.

Use the latest `remote_countdown_monitor_safe.py`, and paste the entire file including the final `try/except` block.

## `SyntaxError` Near `try: main()`

The script was not pasted completely. The end must include the matching `except` block:

```python
try:
    main()
except (Exception, KeyboardInterrupt) as e:
    ...
```

## Touch Button Does Not Respond

The current script reads `M5.Touch` and only triggers when the touch count is active. If the touch area feels off, adjust:

```python
STOP_TIMER_RECT = (8, 156, 150, 44)
EXIT_RECT = (176, 156, 136, 44)
```

## Black Screen or Freeze

Avoid `uiflow2/experimental/` scripts. Use M5Burner to re-flash UIFlow2 if a downloaded script causes boot-time freezes.
