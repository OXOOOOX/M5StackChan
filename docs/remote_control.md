# StackChan 遥控使用与验收说明

本文对应 [`remote_servo_controller.py`](../uiflow2/remote_servo_controller.py)。这是开发中的自包含脚本，驱动和映射类都写在文件内，运行时使用 UIFlow2 自带的 `M5`、`espnow`、`network` 等模块，不依赖 `uiflow2/lib/`。编辑库文件不会改变它的行为。

**状态：代码已存在，本文已对照源码；当前组合尚需完整实机验收，不等同于已发布的稳定版本。** 过去验证过的供电、通信和 ID 恢复步骤见[舵机更换与排错记录](servo_replacement_debug_zh.md)。

## 运行前准备

1. StackChan 使用 UIFlow2 固件；StickS3 + Unit Joystick2 遥控器运行匹配的 ESP-NOW 固件。
2. 先运行[原始包监视器](../uiflow2/espnow_packet_monitor.py)或[倒计时接收器](../uiflow2/remote_countdown_monitor_safe.py)，确认包长、范围、频道和目标 ID。
3. 用[总线诊断脚本](../uiflow2/servo_bus_diagnostic.py)的 Power / Ping / Scan 确认 yaw 为 ID1、pitch 为 ID2。更换舵机后先核对 ID，再做[中心校准](../uiflow2/servo_center_calibration.py)。
4. 核对遥控脚本中的 `YAW_ZERO`、`PITCH_ZERO` 和 pitch 行程是否适合当前装配。源码数值是当前开发配置，不是每台设备的通用校准值。
5. 在 UIFlow2 Python 模式粘贴完整脚本，先使用 Run；实机验收完成后再考虑 Download 为开机程序。

脚本会断开 STA Wi-Fi 并尝试设置 ESP-NOW 频道，可能影响 UIFlow2 在线连接。频道设置失败会打印 `channel config skipped`，此时需确认设备实际频道。

## 频道、ID 与数据包

默认配置：

```python
RECEIVER_ID = 1
WIFI_CHANNEL = 1
ACCEPT_BROADCAST_ID = True
AUTO_PAIR_REMOTE = False
PACKET_IDLE_CENTER_MS = 3000
```

- 默认接受目标 ID1，以及目标 ID0 的广播包。ID0 是**发送包中的目标 ID**；将 `RECEIVER_ID` 改为 0 不会变成接收所有 ID。
- 出现 `ign id:X need:Y` 时，修改接收 ID 或遥控器目标 ID，使两者匹配；也可让发送端使用 ID0，并保留 `ACCEPT_BROADCAST_ID = True`。
- 自动配对默认关闭。打开后仅在未控制状态下，根据摇杆变化选择一个非零目标 ID；后续其他非零 ID 的动作也可能再次改变选择。此选择只保存在内存中。
- 配对判断使用的 pitch 中心为输入范围中点 450，与运动映射中心 350 不同，尚未统一。验收优先使用固定 ID。

有效数据包必须**恰好 8 字节**，按 `<BhhhB` 解包：

| 字段 | 范围 / 处理方式 |
| --- | --- |
| target_id | 0 为广播，其他值按接收 ID 匹配 |
| yaw | -1280～1280 |
| pitch | 0～900 |
| speed | 0～1000 |
| laser | 读取并显示，当前未驱动激光或 LED |

长度或运动字段越界的包会被丢弃。`DROP_ABNORMAL_PACKET` 目前没有接入判断逻辑；改为 `False` 也不会关闭范围校验。

## Start、Stop、Exit 与断流

| 操作 / 事件 | 当前代码行为 |
| --- | --- |
| 运行脚本 | 显示 UI 并监听数据包，等待 Start |
| Start | 打开 VM_EN、初始化 UART、ping 两轴，对检测到响应的轴发送扭矩使能；至少一轴响应即可进入控制状态，然后发送 Home |
| Stop | 退出控制状态，发送约 300 ms 的 Home 命令，等待约 400 ms，再尝试关闭扭矩和 VM_EN；继续监听 |
| Exit | 请求结束主循环；控制状态下发送 Home、等待并尝试关闭扭矩和 VM_EN，然后退出 |
| 超过 3 秒未接受匹配的有效控制包 | 若主循环执行到超时检查，重置映射并发送约 500 ms 的 Home；此动作不关闭扭矩或电源 |
| 捕获异常或 Ctrl+C | 外层异常处理尝试调用 `shutdown()` |

Home 默认为 `HOME_YAW_DEG = 0`、`HOME_PITCH_DEG = 0`，目前对应 yaw raw 510、pitch raw 610。停止和断流回位本身会产生运动。

这些动作由软件执行，不构成已验证的硬件断电保证。当前实现未反馈确认断电结果；UI 阻塞、串口或 I2C 失败、主控失去响应时，不能仅凭屏幕状态推断电机已经停止。

## 当前摇杆映射

### Yaw：按时间累计 raw 目标

左右摇杆控制目标 raw 位置的增量。摇杆回到中心且仍有有效包时，yaw 保持累计目标，不因松开摇杆立即回到 Home。

```text
yaw_ratio = yaw / 1280
speed_ratio = speed / 1000
raw_step = yaw_ratio × 2048 × speed_ratio × elapsed_seconds
next_raw = (previous_raw + raw_step) % 1024
```

- 输入绝对值小于 50 时视为中心；speed 为 0 时不增加 yaw 目标。
- 两次更新的间隔为负或大于 250 ms 时，使用 20 ms，避免长间隔被累计成一次大跳变。
- raw 按 1024 回绕，位置命令使用 `YAW_MOVE_TIME_MS = 40`；2048 是软件目标增长系数，不是实测机械转速。
- `YAW_OUTPUT_MIN/MAX` 等旧角度常量不参与当前 yaw 增量路径，更改它们不会限制累计 yaw 行程。
- raw 1023 / 0 边界的实际方向、是否跳变及线缆约束仍需实机验收，取模计算不能保证机械运动路径。

### Pitch：单侧抬头映射

当前 `PITCH_INPUT_CENTER = 350`，死区为 100，软件角度为 0～90。输入低于 450 时目标为 Home；从 450 起按 `(pitch - 350) / 550 × 90` 映射到抬头目标。这不是以 450 为中心的对称俯仰映射。

因此，输入恰为 450 时未平滑目标约为 16.36°，并非 0°。先观察遥控器松手值，再核对这一配置。源码中的 90°也不代表已证明适合当前装配的机械行程。

Pitch 的平滑公式为 `new = old × 0.3 + target × 0.7`。提高 `DEFAULT_SMOOTHING` 会让变化更慢，目前只影响 pitch。speed 将 pitch 的指令时间从 400 ms 映射到 50 ms；yaw 使用固定的 40 ms。

## 已知限制与验收项目

- **持续非 8 字节包会跳过超时检查。** 当前长度错误分支提前进入下一次循环，持续杂包可能阻止 3 秒回位；它不是独立于主循环的失联保护。
- **ping 判断不完整。** 目前只检查回包包含 `FF FF` 和目标 ID，未完整验证长度、校验和、错误码。屏幕上的 OK 只反映这一有限判断。
- **Home 不按单轴 ready 过滤。** 逐包驱动会检查对应轴是否 ready，但 Start、Stop、断流等 Home 路径都会向两个 ID 发送位置命令。
- **校准不会自动同步。** 当前遥控脚本为 510 / 610；历史库和 `servo_validation.py` 仍为 460 / 620，不应混用两套零位与运动范围。

当前版本发布前至少记录以下实机结果：

1. 固件版本、遥控器固件来源、ID、频道和本机零位。
2. 两轴分别 ping / 小幅运动的结果，以及只接单轴时的行为。
3. yaw 松手保持、正反方向、raw 回绕；pitch 松手值、死区与实际行程。
4. 正常断流、错误 ID、越界包、持续错误长度包时的结果。
5. Start、Stop、Exit 和异常退出后的实际电机与电源状态。

底层方法与旧原型差异见 [Servo API](servo_api.md)。
