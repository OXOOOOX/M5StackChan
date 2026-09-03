# M5StackChan：UIFlow2 接收与舵机排错

使用 **StackChan + UIFlow2/MicroPython** 接收 **StickS3 + Unit Joystick2** 的 ESP-NOW 数据，逐步验证通信、舵机供电、ID 和中心校准。日常修改 Python 脚本后通过 UIFlow2 `Run` 调试。

**当前可靠入口是报文监听和分步诊断。遥控舵机代码已实现，但连续旋转曾出现异响、失控和 `no servo`，仍待修复与实机验收，不能视为稳定控制固件。** 换舵机后已经有双 ID 通信、小幅 Jog 和中心校准成功的聊天证据；这不等于遥控闭环已恢复。

## 从哪里开始

1. 使用匹配设备的 UIFlow2 固件，连接 Web IDE，按 [环境搭建](docs/setup.md) 操作。
2. 首先运行 [带倒计时的监听器](uiflow2/remote_countdown_monitor_safe.py)，默认 `RECEIVER_ID = 1`、`WIFI_CHANNEL = 1`、`RUN_SECONDS = 30`；该脚本不驱动舵机。
3. 确认收到恰好 8 字节的数据，显示 `rx`，且 yaw/pitch/speed 在 [协议范围](docs/protocol.md) 内。`ignored id:X` 表示目标 ID 不匹配；发送端目标 ID `0` 才表示广播。
4. 如需处理舵机，依次使用 [总线诊断](uiflow2/servo_bus_diagnostic.py)、必要时的 [pitch ID 恢复](uiflow2/servo_id_recover_pitch.py)、[中心校准](uiflow2/servo_center_calibration.py)。先阅读 [更换舵机记录](docs/servo_replacement_debug_zh.md)。
5. 完成上述检查后再评估 [遥控原型](docs/remote_control.md) 的待修复项。先 `Run`，确认稳定后再考虑 `Download`。

监听器的 `Stop timer` 取消倒计时、持续监听；`Exit` 退出；`BtnA` 可取消倒计时。舵机异常时先切断供电，保留日志，再恢复到不运动的诊断步骤。

## 文件与验证状态

| 文件/目录 | 用途 | 当前状态 |
| --- | --- | --- |
| `uiflow2/remote_countdown_monitor_safe.py` | 监听、倒计时、触摸退出、长度/范围过滤 | 历史实机成功；本次仅静态核对 |
| `uiflow2/espnow_packet_monitor.py` | 低层长度与字段观察 | 不驱动舵机；不做字段范围过滤 |
| `uiflow2/servo_bus_diagnostic.py` | Power/Ping/Scan 与明确触发的小幅 Jog | 双 ID、Jog 有实机证据 |
| `uiflow2/servo_id_recover_pitch.py` | 单独连接新 pitch 舵机，将 ID1 改成 ID2 | 恢复成功；改 ID 时总线上只留目标舵机 |
| `uiflow2/servo_center_calibration.py` | 分步找机械中心并打印配置 | 有实机成功反馈；中心值需逐台确认 |
| `uiflow2/remote_servo_controller.py` | 自包含遥控原型，内嵌驱动与增量 yaw 映射 | 待修复、待实机验收 |
| `uiflow2/servo_validation.py`、`uiflow2/lib/` | 早期验证 UI 与可复用驱动原型 | 与遥控脚本已有分歧，不能直接互换 |
| `uiflow2/servo_minimal_test.py` | VM_EN 发现过程的历史实验 | 用于复查早期过程 |
| `uiflow2/experimental/` | 早期直接控制方案 | 历史归档，曾出现黑屏/卡死 |
| `StackChan-official/` | 官方源码子模块 | 固定提交 `51a0617`，作为硬件/协议参考 |

`v0.1.0`、`v0.2.0`、`v0.3.0` 是开发阶段标识；本次检查未发现 Git tag，后两者不代表已验证的正式发布。

## 遥控器端与远端分支

本分支整理接收端。遥控器固件、源码补丁和打包说明在远端 [codex/sticks3-joystick2-remote 分支](https://github.com/OXOOOOX/M5StackChan/tree/codex/sticks3-joystick2-remote)，对应 [PR #1](https://github.com/OXOOOOX/M5StackChan/pull/1)。另有开发时使用的 [遥控器独立仓库](https://github.com/OXOOOOX/StackChan-Remote-StickS3-Joystick2)；其后续修复不应自动视为本仓库远端分支已包含。

合并双方内容时需保留接收端和遥控器端两个入口。远端遥控器分支的 README 与本分支有冲突，具体见 [GitHub 上传清单与冲突检查](docs/github_upload_review.md)。

获取已推送的接收端分支及官方参考子模块：

```powershell
git clone --branch codex/v0.1.0-safe-receiver --recurse-submodules https://github.com/OXOOOOX/M5StackChan.git
```

接收端源码、开发原型和排错文档位于上述分支；截至 2026-09-03 检查时，默认 main 仍只有初始上传内容。主库仅保存子模块提交指针，子模块中的本地改动不会随主库自动上传。根目录两个哈希命名 `.bin` 已核验版本元数据，但精确构建来源和复现条件不完整，见 [固件清单](docs/firmware_inventory.md)，不要凭文件名选择刷写。

## 文档导航

- [排错经验总集与聊天证据](docs/debugging_lessons_zh.md)：过程、失败方案、已确认结果、后续验收。
- [常见故障速查](docs/troubleshooting.md)、[环境搭建](docs/setup.md)、[ESP-NOW 协议](docs/protocol.md)。
- [舵机供电发现过程](docs/servo_power_debug.md)、[更换舵机与 ID 恢复](docs/servo_replacement_debug_zh.md)。
- [遥控原型使用说明](docs/remote_control.md)、[驱动 API 与版本差异](docs/servo_api.md)。
- [官方资料摘录](docs/m5stackchan_official_docs.md)：2026-05 的参考快照，接线/初始化需与固定源码及诊断结果交叉核对。
- [开发计划](PLAN.md)、[变更记录](CHANGELOG.md)、[上传清单](docs/github_upload_review.md)。
