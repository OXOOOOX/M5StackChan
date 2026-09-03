# 环境搭建与首次运行

## 两端固件分清楚

- 接收端：StackChan + 匹配设备的 UIFlow2/MicroPython 固件，使用本仓库 `uiflow2/` 脚本。
- 发送端：StickS3 + Unit Joystick2，使用对应遥控器 ESP-IDF 固件；在 ESP-NOW Running 模式发送。
- 官方 StackChan ESP-IDF 固件内的 `ESPNOW.REMOTE` 应用是另一条运行路线，不会直接执行这些 Python 脚本。

固件版本需按测试现场记录。历史成功日志包含 MicroPython `v1.27.0-dirty`，但不足以唯一识别完整 UIFlow2 构建。本仓库根目录两份历史 bin 不是首次运行的默认选择，见[固件清单](firmware_inventory.md)。

## 先运行不运动的监听器

1. 用 M5Burner 安装匹配设备的 UIFlow2 固件并完成设备联网/绑定。
2. 在 UIFlow2 Web IDE 选择 StackChan，进入 Python 编辑模式。
3. 完整打开或粘贴 `uiflow2/remote_countdown_monitor_safe.py`，保留末尾异常处理。
4. 核对 `RECEIVER_ID = 1`、`WIFI_CHANNEL = 1`、`RUN_SECONDS = 30`。
5. 使用 `Run`。发送端和接收端需在同一信道；若输出 `channel config skipped`，不能认为请求的信道已生效。
6. 发送端进入 Running，观察 `rx`、字段和计数。异常按[速查表](troubleshooting.md)排查。

`Stop timer` 取消倒计时持续监听，`Exit` 退出，`BtnA` 备用取消倒计时。先确认脚本稳定，再决定是否 `Download` 为设备启动程序。

## 舵机恢复顺序

按[更换舵机记录](servo_replacement_debug_zh.md)执行 Power → Ping/Scan → 单轴小幅 Jog → 校准。需要改 pitch ID 时，断电并只保留目标舵机接入总线，再操作专用恢复脚本。

`servo_validation.py` 与 `lib/` 是旧原型；`remote_servo_controller.py` 是另一个自包含版本。它们的校准、角度和回包校验有区别，见[API 文档](servo_api.md)。不要跳过独立诊断直接启用遥控运动。

## 调试记录

每次至少记录设备、固件来源/版本、脚本 Git 提交、接线、信道/目标 ID、报文原文、舵机扫描结果、实际动作和最后正常配置。USB 终端与网页串口可能争用同一个端口；先关闭当前串口占用程序再重试，不要同时启动多个终端。

公开日志前移除 Token、Wi-Fi 凭据和个人设备标识。原始聊天留在本地，仓库保留[清洗后的经验](debugging_lessons_zh.md)。
