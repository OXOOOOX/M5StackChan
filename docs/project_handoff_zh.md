# 归档交接：从这里恢复项目

更新：2026-09-03。本文保存聊天归档后的继续开发入口、成果位置和未完成事项。它是项目交接，不是硬件验收报告。

## 当前可恢复的成果

本次归档前复核覆盖 [排错总集](debugging_lessons_zh.md) 中的 9 份历史记录，以及本次整理、上传和复核会话。历史记录共 7,402 行（含分叉继承内容）；分叉中重复的反馈没有当成独立实测。原始聊天不公开上传。

接收端源码、诊断工具、计划、固件清单和排错经验已经随 [284041f](https://github.com/OXOOOOX/M5StackChan/commit/284041f79cccf60552cc9f12d668c1bee2ac9fcc) 发布到 `codex/v0.1.0-safe-receiver`。归档前再次读取远端树，31 个普通文件与本地 Git 规范化内容全部一致，官方子模块指针为 `51a06177f7a820762c63c845bb4fe2a563be3eb4`。

归档前未发现接收端遗漏源码、配置或固件：

- 主仓库没有未跟踪文件；忽略内容只有 Python 缓存。
- 官方子模块没有未跟踪/忽略文件；7 个 dirty 条目只有空白/换行差异，没有功能改动。
- 根目录旧 bin 和子模块资源/构建配置均已跟踪；新增 `*.bin` 规则没有藏住另一份待发布固件。
- `.git/local-audit/` 是本地检查记录和临时索引，不包含只能靠它恢复的产品代码。

上述统计是添加本交接文档前的快照。后续内容是否同步，应重新比较远端提交。

## 三个开发位置不要混淆

| 位置 | 用途与基线 | 恢复时的注意事项 |
| --- | --- | --- |
| [本库接收端分支](https://github.com/OXOOOOX/M5StackChan/tree/codex/v0.1.0-safe-receiver) | Python 接收、诊断、校准、遥控原型和排错记录；源码基线 `284041f` | 默认 main 在检查时仍为初始 `93f2cfc`，从 main 克隆看不到这些内容 |
| [本库旧遥控器分支](https://github.com/OXOOOOX/M5StackChan/tree/codex/sticks3-joystick2-remote) | `2ce2b47` 的旧固件、完整适配补丁及原生 `esp_now_send` 路线 | 与接收端 README 有 add/add 冲突；不是兄弟仓库的最新源码 |
| [遥控器独立仓库](https://github.com/OXOOOOX/StackChan-Remote-StickS3-Joystick2) | 后续 StickS3 屏幕、Joystick2 和 X/Y 反转修复；固件发布基线 `b61fae0`，源码补全 `def7e75` | 归档复核发现并补齐了发布补丁遗漏的两个设置界面源码；以该库修复后的补丁为准 |

本次没有合并本库两条分支，也没有改默认分支或运行设备。PR #1 的 MERGEABLE 状态针对旧 main，不表示它与接收端分支无冲突；历史检查依据见[上传前快照](github_upload_review.md)。

### 遥控器源码补全与兼容性

此前独立仓库主补丁已引用 `ui_joystick_settings_screen.c/.h`，却没有包含这两个文件的新增内容；它们只存在于本地子模块未跟踪文件中。固件 bin 已上传不等于全部源码已保存。归档前将两份文件补入主补丁，并对固定官方基线做干净应用验证。

源码补全与说明已通过 [def7e75](https://github.com/OXOOOOX/StackChan-Remote-StickS3-Joystick2/commit/def7e75a6f4b4e5c17c6280af68288684a5d2546) 推送到独立仓库 main，已用 `ls-remote` 核对远端提交一致。

补全仅保存既有源码，未修改运动/发送逻辑，未重新构建或替换 bin。不能因此声称已完成干净环境的完整固件构建或硬件复验。

补全后的主补丁覆盖 23 个文件，与现有本地改动一致；隔离应用后 CMake 列出的 11 个源码文件和新增项目头文件均存在。子模块仍可显示本地修改或未跟踪源码，这是父仓库通过补丁发布的工作方式，不代表这两份源码仍未保存到 GitHub。

恢复时可核对以下产物标识；补丁是源码补全版本，bin 仍是既有固件，二者没有在本次重新编译建立逐字节复现证明：

| 产物 | 字节数 | SHA256 |
| --- | ---: | --- |
| `patches/stackchan-remote-sticks3-joystick2.patch`（`def7e75`） | 153,361 | `ebbda44b63a53645598cb229aff8a700d9a2eca4074cc28d0a01849b83f98c4b` |
| `StackChan-RemoteControl-StickS3-Joystick2_0x0.bin`（`b61fae0`） | 1,220,064 | `f4e8e341bc8586327c8122b3929a404666908f5c4879fb57725e39a4c0c2a856` |

本地另有旧增量补丁 `patches/fix-joystick-output-clamp.patch`。其填包/范围保护已被主补丁覆盖，旧补丁也无法直接应用于当前源码；它作为过时实验留在本地，不另行发布或叠加。

还有一项必须保留的分支差异：

- 旧 `2ce2b47` 补丁包含原生 `esp_now_send` 发送改动。
- 独立仓库 `b61fae0` 的补丁和本地工作树使用上层 `espnow_send(ESPNOW_DATA_TYPE_DATA, ...)`，并未保留旧分支的两个原生发送文件改动。
- 因此，最新显示/反转版对官方 `ESPNOW.REMOTE` 的成功反馈，不能自动视为 UIFlow2 裸 8 字节接收器的联调成功。需重新测发送载荷与接收长度；本次没有证明该 bin 实测一定产生 28 字节。

不要为“统一归档”而把旧补丁叠加到新版上，或把不同版本 bin 重命名成同一个文件。按具体目标选择一套源码/补丁/固件，再验证兼容性。

## 新工作副本的恢复入口

接收端：

```powershell
git clone --branch codex/v0.1.0-safe-receiver --recurse-submodules https://github.com/OXOOOOX/M5StackChan.git
```

遥控器：

```powershell
git clone --recurse-submodules https://github.com/OXOOOOX/StackChan-Remote-StickS3-Joystick2.git
```

进入遥控器新克隆的父仓库后，按其 README 对干净、固定版本的官方子模块应用主补丁。不要在已经打过补丁的旧工作副本重复应用。构建需要该仓库记录的 ESP-IDF 环境；源码恢复检查不等于已经完成构建。

继续工作时，先读：

1. 本文：仓库、分支和交接状态。
2. [排错经验总集](debugging_lessons_zh.md)：证据与失败方案。
3. [开发计划](../PLAN.md)：尚未完成的可靠性工作。
4. [API 版本说明](servo_api.md)：当前自包含脚本和旧 `lib/` 的差异。
5. [固件清单](firmware_inventory.md)：历史镜像身份与复现边界。

## 下一次实机从哪一步开始

**最后明确恢复的是双 ID 通信、小幅 Jog 和中心校准。连续 yaw 的最新实现没有完整验收。**

1. 先用 `remote_countdown_monitor_safe.py` 观察载荷长度、范围和 ID，不启用舵机。
2. 再用 `servo_bus_diagnostic.py` 的 Power/Ping/Scan；按轴确认，不把任一 ID 应答当成两轴正常。
3. 需要改 pitch ID 时，断电并只接待修改舵机，使用 `servo_id_recover_pitch.py`。
4. 小幅 Jog 正常后使用 `servo_center_calibration.py`，把校准值写入实际运行的脚本。
5. 先处理 PLAN 中的回包完整性、错误长度绕过超时、Home 单轴限制、旧 raw 越界等问题，再评估遥控和连续旋转。

`510/610` 只是当时本机配置，不应自动复用到新舵机。机械零点、Home 姿态与摇杆中位分别核对。界面、UART 写入、有效应答、真实动作、实际断电是不同验收点。

### 已知运行环境线索

历史用户日志 E3:L204 的完整横幅为：

```text
MicroPython v1.27.0-dirty on 2026-04-29;
M5STACK StackChan with ESP32S3
```

它比单独版本号更便于以后比对，但仍不能唯一确定 UIFlow2 下载镜像。固件构建来源和现场设备信息应重新记录。

若脚本导致启动故障，先停止运行并尝试复位；持续复现时按匹配设备的官方恢复流程处理。历史聊天中的重刷建议没有用户确认的恢复结果，本次也未执行重刷。

## 保留的 EzData 历史入口

这是 2026-05 官方 ESP-IDF 固件路线的历史操作线索，不是当前 UIFlow2 脚本功能，也不是保证网页至今不变的教程：

- USB 串口波特率 `115200`；用户当时成功打开过 miniterm。
- 打开官方固件的 `EZDATA`，从本机 `get token ...` 日志取得 Device Token。Token 留本机，不写进文档或公开日志。
- 当时网页路径是 `Data → Add Group → Token`，与设备屏幕 Pair Code 不同。
- 四个控制字段为 `SERVO.X.ANGLE`、`SERVO.X.SPEED`、`SERVO.Y.ANGLE`、`SERVO.Y.SPEED`。
- 当时有 `Received Cmd: 107`、`SERVO.X.ANGLE` 日志和至少一轴动作；没有双轴完整验收或重复字段治理完成记录。

来源 E2:L394–431、L464、L474。整数/浮点解析和串口占用仍只是历史候选原因，不能在恢复时直接当成已证实根因。

## 归档后不需要从聊天找回的内容

有效脚本、触摸参数、VM_EN/字节序、ID 恢复、校准值差异、构建经验与待修复项均有仓库文件。早期失败片段、临时 bin 分析命令和原始工具日志没有必要作为产品代码上传。原始聊天、凭据及带个人设备标识的截图继续保留在本机归档。

未来的新任务应以源码和本文为入口；需要追溯原话时，用排错总集的来源编号和会话 ID 前缀回查本地归档。
