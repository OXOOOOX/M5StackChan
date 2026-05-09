# StackChan 舵机更换与 no servo 排查记录

本文整理本次排查过程、换舵机注意事项，以及 StackChan 串行舵机的通信规则。适用于 UIFlow2 脚本环境。

## 相关脚本

- `uiflow2/servo_bus_diagnostic.py`
  - 总线诊断脚本。
  - 检查 PY32/VM_EN、UART、舵机 ID。
  - `Power`、`Ping`、`Scan` 不会让舵机运动。
  - `Jog1` 小幅测试 yaw/ID1。
  - `Jog2` 小幅测试 pitch/ID2。

- `uiflow2/servo_id_recover_pitch.py`
  - 替换 pitch 舵机后恢复 ID 的工具。
  - 只在总线上接一个待修改舵机时使用。
  - 将单独接入的 ID1 舵机改成 ID2。

- `uiflow2/servo_center_calibration.py`
  - 中心校准工具。
  - 在 ID1 和 ID2 都能通信、Jog 都正常后使用。
  - 输出 `YAW_ZERO` 和 `PITCH_ZERO`，需要同步到控制脚本。

## 本次排查结论

最初现象：

- 程序错误导致舵机向一个方向持续运动并卡死。
- calibration 中显示 `no servo`。
- 更换舵机后仍然不能正常识别 pitch。

最终确认：

- VM_EN 舵机电源能打开。
- UART1 `TX=G6`、`RX=G7`、`1000000` baud 正常。
- 底座 yaw 舵机是 ID1，能通信也能运动。
- 新换的 pitch 舵机默认也是 ID1，不是 ID2。
- 将 pitch 舵机单独接入总线并改为 ID2 后，诊断脚本能扫到 `[1, 2]`，calibration 恢复正常。

## 通信规则

StackChan 使用 SCSCL 串行舵机，总线规则如下：

- 多个舵机共享同一条 UART 总线。
- 物理接口不决定 yaw 或 pitch。
- 每个舵机内部 EEPROM 保存自己的 ID。
- 主控发送命令时，数据包里包含目标 ID。
- 舵机只响应发给自己 ID 的命令。

StackChan 期望的 ID：

| 位置 | 舵机 ID | 说明 |
| --- | --- | --- |
| yaw / 底座左右旋转 | `1` | 底座舵机 |
| pitch / 头部俯仰 | `2` | 头部俯仰舵机 |

典型 ping 回包：

```text
FF FF 01 02 00 FC   # ID1 有效回包
FF FF 02 02 00 FB   # ID2 有效回包
```

如果两个舵机都是 ID1，主控无法区分它们。此时 calibration 会找不到 ID2，表现为 pitch fail 或 no servo。

## 排查流程

### 1. 先运行总线诊断

运行：

```text
uiflow2/servo_bus_diagnostic.py
```

操作顺序：

1. 点 `Power`
2. 点 `Scan`
3. 查看 Console 输出

正常结果应包含：

```text
found config u1 tx6 rx7 1000000 ids [1, 2]
```

如果只看到：

```text
ids [1]
```

说明只发现 yaw/ID1，pitch/ID2 没有出现在总线上。

### 2. 分别 Jog

在诊断脚本中：

- `Jog1` 应该让底座左右小幅运动。
- `Jog2` 应该让头部俯仰小幅运动。

如果 `Jog1` 正常但 `Jog2` 锁定或不动，优先检查 pitch 舵机 ID、线缆和接口。

### 3. 替换舵机后的 ID 恢复

很多替换舵机默认 ID 是 `1`。如果要把它作为 pitch 使用，需要改成 `2`。

运行：

```text
uiflow2/servo_id_recover_pitch.py
```

重要步骤：

1. 断电。
2. 断开或拆下底座 yaw 舵机。
3. 总线上只保留要作为 pitch 的那个舵机。
4. 上电运行脚本。
5. 点 `Scan`。
6. 如果显示 `Found IDs: [1]`，点 `Set2` 两次。
7. 再点 `Scan`，确认变成 `Found IDs: [2]`。
8. 断电，把 yaw 和 pitch 都接回。
9. 回到 `servo_bus_diagnostic.py`，确认能扫到 `[1, 2]`。

不要在两个 ID1 舵机同时接入总线时使用 `Set2`，否则两个舵机可能一起变成 ID2。

## calibration 使用流程

确认诊断脚本能扫到 `[1, 2]` 后，再运行：

```text
uiflow2/servo_center_calibration.py
```

操作顺序：

1. 点 `Power`。
2. 确认屏幕显示 `Y:OK P:OK`。
3. 使用 `Step` 选择步进，建议先用 `1` 或 `5`。
4. 使用 `Y-` / `Y+` 调底座中心。
5. 使用 `P-` / `P+` 调头部俯仰中心。
6. 点 `Print`，在 Console 查看：

```text
YAW_ZERO = ...
PITCH_ZERO = ...
```

7. 将这两个值同步到实际控制脚本。

## 注意事项

- 舵机卡死后，先断电，避免持续堵转烧坏舵机或电源。
- 不要一开始就运行大幅运动脚本，先用 diagnostic 小幅 Jog。
- 改 ID 前必须确保总线上只有一个舵机。
- 新舵机默认 ID 不一定符合 StackChan 需要。
- `PY32 post-write read failed: 259` 不一定代表 VM_EN 失败；如果后续能 ping 到 ID1/ID2，说明舵机电源实际已经打开。
- `Power`、`Ping`、`Scan` 应保持不发运动命令，只有明确的 Jog/校准按钮才允许运动。

## 已知正常日志示例

```text
I2C0 scan: [33, 35, 52, 54, 56, 64, 65, 81, 88, 105, 111]
PY32 post-write read failed: 259
ping id=1 OK try=1 len=6 FF FF 01 02 00 FC
ping id=2 OK try=1 len=6 FF FF 02 02 00 FB
=== servo bus scan start ===
config u1 tx6 rx7 1000000
 id=1 OK try=1 len=6 FF FF 01 02 00 FC
 id=2 OK try=1 len=6 FF FF 02 02 00 FB
found config u1 tx6 rx7 1000000 ids [1, 2]
=== servo bus scan end ===
```

看到 `ids [1, 2]` 后，说明通信、ID 和电源链路已经恢复，可以进入中心校准。
