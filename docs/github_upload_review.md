# GitHub 上传清单与远端冲突检查

检查日期：2026-09-03（北京时间）。本文保留上传前的审阅快照，下列 SHA、提交差异和 PR 状态均以检查时为准，不是仓库实时状态。审阅阶段只整理内容、检查与模拟合并，没有改动运动逻辑、合并分支、刷写设备或删除文件。

后续发布和归档前补漏见[归档交接说明](project_handoff_zh.md)；22 个候选文件已随 `284041f` 上传。

本次上传范围为清单中的 22 个文件，目标是 `codex/v0.1.0-safe-receiver` 接收端分支。官方子模块指针、历史 bin 和另一条遥控器分支不在本次修改范围内；实际上传结果以远端分支提交记录为准。

## 上传前远端快照

仓库：[OXOOOOX/M5StackChan](https://github.com/OXOOOOX/M5StackChan)。审阅分支为 `codex/v0.1.0-safe-receiver`，上传前 HEAD 为 `959e3af1f5eed99adfa119ba5633cc8f05a18105`。已实际执行 `git fetch origin`，不是只查看旧缓存。

| 比较目标 | 远端 SHA | 本地独有 / 远端独有提交 | 提交级合并结果 |
| --- | --- | --- | --- |
| `origin/codex/v0.1.0-safe-receiver` | `959e3af` | 0 / 0 | 完全同步；本地未提交文件尚未上传 |
| `origin/main` | `93f2cfc` | 3 / 0 | main 是本地祖先，无内容冲突 |
| `origin/codex/sticks3-joystick2-remote` | `2ce2b47` | 3 / 4 | README.md 存在 add/add 冲突 |

`git merge-tree --write-tree` 的提交级模拟只报告 **README.md** 冲突。随后用 22 个候选文件构建临时索引和无分支引用的快照对象，模拟结果相同：与同名分支及 main 均无冲突，与遥控器分支仅 README.md 冲突。真实索引、HEAD 和工作分支均未改变；审计记录保存在本地 `.git/local-audit/`，不纳入上传。

[PR #1 — [codex] Publish raw ESP-NOW StickS3 Joystick2 firmware](https://github.com/OXOOOOX/M5StackChan/pull/1) 当前为 OPEN，base 为 main，head 为遥控器分支，GitHub 返回 MERGEABLE。这个结果只针对当前 main；一旦先把接收分支合入 main，就应重新检查双方 README。

## 冲突实质及处理方案

共同祖先 `93f2cfc` 没有 README。双方分别新增了接收端说明和遥控器说明，因此 Git 报 add/add。当前整理后的 README 已按“接收入口、遥控器分支入口、验证状态、排错文档”组织，适合作为后续整合基础。

后续真正合并时：

- 保留本分支 `uiflow2/`、诊断工具、校准指南和经验文档。
- 保留遥控器分支的 `patches/stackchan-remote-sticks3-joystick2.patch`、命名 bin 和 `JOYSTICK_YAW_PITCH_DEBUG.md`。
- 将遥控器 README 中的硬件、按键、构建/打包说明移入独立遥控器文档，主 README 同时链接两端；将个人绝对路径改成相对示例。
- 遥控器分支还删除了两份旧 bin。这不是 Git 冲突，而是合并内容变化；本次仅做模拟，没有执行这些删除。若决定批量移除文件，按项目约束交给用户手动处理。
- 遥控器独立仓库的 05-10 后续修复不等同于 `2ce2b47` 已包含。确认源码、patch 和 bin 对应关系后再描述为同一套可复现固件。

上传前同名分支与 HEAD 相同，不需要 rebase 或强推；发布时再次 fetch 核对。后续应以最新远端结果判断，不能沿用这份快照作为实时同步依据。

## 建议上传的内容

| 组 | 文件 | 目的/状态 |
| --- | --- | --- |
| 项目入口 | `README.md`、`CHANGELOG.md`、`PLAN.md`、`.gitignore` | 统一项目范围、开发阶段、待验收项与忽略规则 |
| 现有说明更新 | `docs/setup.md`、`protocol.md`、`troubleshooting.md`、`servo_power_debug.md`、`servo_replacement_debug_zh.md` | 修正协议、应答证据与排查顺序 |
| 新增使用说明 | `docs/remote_control.md`、`servo_api.md`、`m5stackchan_official_docs.md` | 内嵌/旧库差异及历史官方资料 |
| 本次审计文档 | `docs/debugging_lessons_zh.md`、`firmware_inventory.md`、`github_upload_review.md` | 清洗后的经验、固件来源和上传依据 |
| 监听器修改 | `uiflow2/espnow_packet_monitor.py`、`remote_countdown_monitor_safe.py` | 非 8 字节拒绝；倒计时版增加范围检查 |
| 开发原型 | `uiflow2/remote_servo_controller.py`、`servo_validation.py`、`lib/__init__.py`、`lib/servo.py`、`lib/motion.py` | 可上传源码，但必须保留开发中/未完整验收状态 |

已提交的总线诊断、ID 恢复、中心校准、最小实验、experimental 目录和 `.gitmodules` 继续保留，不重复生成或复制。

提交可按“监听保护”“开发原型及对应说明”“经验与发布整理”组织。不要把历史实机通过写成当前所有代码的验收结论。

## 保留但不新增上传的内容

- **官方子模块**：gitlink 保持 `51a06177f7a820762c63c845bb4fe2a563be3eb4`。本地 7 个文件显示修改，`git diff --ignore-all-space --ignore-blank-lines --exit-code` 返回 0，差异仅为空白/换行。父仓库不会上传这些工作树改动，本次不改指针、不恢复或删除文件。
- **两份旧 bin**：当前分支已经跟踪且字节未变；来源、版本、SHA256 见[固件清单](firmware_inventory.md)。`*.bin` 只防止新文件误加，不能移除已跟踪文件或 Git 历史。
- **原始聊天/本地日志/凭据**：留在本机；仅清洗后的经验入库。新规则忽略 `chat_exports/`、`local_notes/`、`logs/`、`.env*`、本机配置等；保留 `.env.example` 例外。
- **构建与缓存**：忽略 Python 缓存、虚拟环境、根 build/dist、PlatformIO 产物。上游子模块自己的构建排除规则独立管理。

没有新增 LICENSE：本项目自有代码的许可选择未明确，不应替用户猜定；官方源码和未来发布补丁继续核对上游许可。

## 复查与显式暂存示例

以下命令展示发布前检查方法；上面的模拟阶段使用临时索引，正式发布再按明确路径暂存、提交和推送：

```powershell
git fetch origin
git status --short --branch
git diff --check
git diff --submodule=short
git ls-files --others --exclude-standard
git -C StackChan-official diff --ignore-all-space --ignore-blank-lines --exit-code
```

按明确路径暂存，避免把子模块或未知固件一并加进去：

```powershell
git add -- .gitignore README.md CHANGELOG.md PLAN.md
git add -- docs/setup.md docs/protocol.md docs/troubleshooting.md docs/servo_power_debug.md docs/servo_replacement_debug_zh.md
git add -- docs/remote_control.md docs/servo_api.md docs/m5stackchan_official_docs.md docs/debugging_lessons_zh.md docs/firmware_inventory.md docs/github_upload_review.md
git add -- uiflow2/espnow_packet_monitor.py uiflow2/remote_countdown_monitor_safe.py
git add -- uiflow2/remote_servo_controller.py uiflow2/servo_validation.py uiflow2/lib/__init__.py uiflow2/lib/servo.py uiflow2/lib/motion.py
git diff --cached --stat
git diff --cached --check
git diff --cached
```

## 验证

- 13 个 Python 文件 AST 解析通过，未导入 M5 或运行硬件入口。
- 106 项纯函数/静态断言核对当前行为，**其中包括已知缺陷复现**，不是 106 项安全验收通过。
- 解析器覆盖空/短/长包、合法边界、越界、广播和其他 ID；原始监听器有意不做范围/ID过滤。
- 已复现原型接受坏 checksum/错误长度声明、旧驱动 yaw raw 越界；静态确认杂包 continue 可跳过超时，但触摸处理仍在该分支之前。
- 14 份 Markdown 的 67 个本地链接、代码围栏、个人绝对路径及冲突标记检查通过；22 个候选文件的临时暂存空白检查通过。
- 候选快照与远端的合并模拟已完成；模拟阶段没有改变实际分支和暂存区。
- 忽略规则已验证覆盖本机配置、日志、聊天导出、环境、缓存及新 bin，`.env.example` 保留例外。
- 文本扫描未发现实际密钥；这个检查不代表二进制或完整历史已通过全面隐私审计。
- 未做硬件验收、重新构建固件或确认断电状态；未上传任何原始聊天。
