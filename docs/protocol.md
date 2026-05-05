# ESP-NOW Protocol

The receiver expects the same 8-byte packet format used by the StackChan ESP-NOW remote firmware:

```text
[target-id][yaw int16][pitch int16][speed int16][laser uint8]
```

Fields:

| Offset | Size | Type | Description |
| --- | ---: | --- | --- |
| 0 | 1 | uint8 | Target receiver ID. `0` means broadcast. |
| 1 | 2 | int16 little-endian | Yaw angle. Typical range: `-1280` to `1280`. |
| 3 | 2 | int16 little-endian | Pitch angle. Typical range: `0` to `900`. |
| 5 | 2 | int16 little-endian | Speed. Typical range: `0` to `1000`. |
| 7 | 1 | uint8 | Laser or extra button flag. `0` off, non-zero on. |

The v0.1.0 receiver only displays these values. Servo motion is intentionally not enabled in this release.

Example parser:

```python
target_id, yaw, pitch, speed, laser = struct.unpack("<BhhhB", packet[:8])
```

Packet display prefixes:

- `rx`: packet matches `RECEIVER_ID` or broadcast ID `0`.
- `ignored`: packet was received, but target ID did not match.
- `rx short`: packet was shorter than 8 bytes.
