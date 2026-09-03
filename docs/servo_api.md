# 舵机 API 与实现版本说明

**本文按当前源码整理；软件角度、ready 标记和关闭电源的函数调用，不等同于已经过完整实机验收。** 操作步骤与已知限制见[遥控使用说明](remote_control.md)。

## 先确认正在使用哪套实现

| 文件 | 定位 | 主要差异 |
| --- | --- | --- |
| [`remote_servo_controller.py`](../uiflow2/remote_servo_controller.py) | 当前自包含遥控开发入口 | 内嵌驱动和映射；零位 510 / 610；yaw 按时间累计 raw 并回绕；pitch 单侧 0～90 |
| [`servo_validation.py`](../uiflow2/servo_validation.py) | 历史自包含测试原型 | 内嵌旧驱动；零位 460 / 620；两轴共用 3.41 换算，固定测试序列 |
| [`lib/servo.py`](../uiflow2/lib/servo.py) | 历史模块化驱动原型 | 零位 460 / 620；yaw ±180、pitch -30～45 的旧角度接口 |
| [`lib/motion.py`](../uiflow2/lib/motion.py) | 历史模块化映射原型 | 绝对角度映射，yaw ±120、pitch -25～40，双轴平滑 |

两个自包含脚本都不导入 `lib/`，编辑库文件不会改变它们。它们在文件末尾直接执行 `main()`；不要通过导入整个脚本来获取类定义，否则会启动设备逻辑。

`from lib.servo import ServoController` 仅用于已将对应库文件部署到设备的模块化开发方式。它不是当前遥控入口的实际依赖，也没有当前遥控脚本的新映射行为。

## 共用硬件与协议

| 项目 | 当前源码配置 |
| --- | --- |
| IO 扩展器 | PY32L020，I2C 地址 `0x6F` |
| I2C 引脚 | SDA=`G12`，SCL=`G11`，100 kHz |
| 舵机供电 | PY32 pin 0 的 `VM_EN` |
| UART | UART1，TX=`G6`，RX=`G7`，1,000,000 baud，8N1 |
| 舵机 ID | yaw=`1`，pitch=`2`；接口位置本身不决定 ID |
| SCSCL 16 位数据 | 高字节在前；不要和 ESP-NOW `<BhhhB` 的小端字段混淆 |
| 扭矩 / 目标位置寄存器 | 40 / 42 |

供电与字节序的排错证据见[舵机电源记录](servo_power_debug.md)，换舵机后的 ID 处理见[更换与恢复记录](servo_replacement_debug_zh.md)。

## 当前遥控入口内嵌的 ServoController

### 生命周期与状态

| 方法 / 属性 | 返回值 | 实际行为 |
| --- | --- | --- |
| `enable_power()` | PY32 版本整数或 0；I2C 异常可能抛出 | 配置 VM_EN，等待 250 ms，设置软件电源标记 |
| `init_uart()` | 无 | 初始化 UART1，存在旧 UART 时先尝试 deinit |
| `ping(servo_id)` | `bool` | 发送 ping，收集回包最多约 180 ms，再做有限的帧头 / ID 检查 |
| `startup()` | `(yaw_ready, pitch_ready)` | 电源 → UART → 两轴 ping → 向检测到响应的轴发送扭矩使能 |
| `yaw_ready` / `pitch_ready` | `bool` | 上次 startup 的检查结果，不是实时健康状态 |
| `is_power_on()` | `bool` | 软件保存的电源标记，不是读取或测量电源轨 |
| `shutdown()` | 无 | 分别尝试关闭两个 ID 的扭矩和 VM_EN，再清除 ready 标记 |
| `disable_power()` | 无 | 尝试写低 VM_EN；异常被忽略，软件电源标记设为 False |

`_is_valid_reply()` 只检查至少 6 字节以及 `FF FF + ID`，未验证完整包长、校验和或错误状态。关闭命令也没有反馈确认。因此 `ping() == True` 不代表完整验证舵机正常，`is_power_on() == False` 不代表已确认硬件断电。

### 位置与扭矩方法

| 方法 | 行为 |
| --- | --- |
| `set_torque(servo_id, enabled)` | 写扭矩开关；无响应确认 |
| `set_position_raw(servo_id, raw_pos, move_time_ms=200, speed=0)` | 写原始位置、时间和速度；16 位值编码时使用 `& 0xFFFF`，不做机械行程验证 |
| `set_yaw_raw(raw_pos, move_time_ms=200)` | 将 raw 整数按 1024 取模后发送到 ID1 |
| `yaw_deg_to_raw(degrees)` | 返回 yaw 软件角度到 raw 的换算值，不发包 |
| `set_yaw(degrees, move_time_ms=200)` | 按圆周角度换算后发送到 ID1 |
| `set_pitch(degrees, move_time_ms=200)` | 将输入限制为当前 0～90，再换算并发送到 ID2 |
| `center(move_time_ms=200)` | 发送 yaw=0、pitch=0 |
| `home(move_time_ms=200)` | 发送 `HOME_YAW_DEG`、`HOME_PITCH_DEG`；当前均为 0 |

`set_position_raw()` 为位置命令设置至少 20 ms 的软件间隔。该间隔在两轴之间共享，并非两轴同时更新；ping、扭矩命令不受此位置命令间隔限制。

这些方法本身不检查 ready。逐包控制在调用前检查对应轴的 ready，但 `center()` / `home()` 会向两个 ID 发位置命令。

### 当前零位与换算

```python
YAW_ZERO = 510
PITCH_ZERO = 610
YAW_RAW_SPAN = 1024
YAW_STEPS_PER_DEGREE = 1024 / 360
PITCH_STEPS_PER_DEGREE = 3.41
```

```text
yaw_raw = int((510 + (degrees % 360) × 1024 / 360) % 1024)
pitch_raw = int(610 + clamp(degrees, 0, 90) × 3.41)
```

默认 Home 对应 raw 510 / 610；pitch 的源码范围对应 raw 610～916。它们是软件配置，不是对所有装配有效的安全范围。更换舵机或调整安装角度后，先用[校准工具](../uiflow2/servo_center_calibration.py)确认，再修改实际运行的脚本。

## 当前遥控入口内嵌的 MotionMapper

```python
MotionMapper(deadzone=50, smoothing=0.3)
```

| 方法 | 返回值 / 行为 |
| --- | --- |
| `update(yaw_raw, pitch_raw, speed_raw)` | `(yaw_servo_raw, pitch_deg, move_ms)`；第一个值是舵机 raw 目标，不是角度 |
| `should_auto_center()` | 距离上次 update 超过 3000 ms 时为 True；本方法不发送命令 |
| `reset()` | yaw 累计值重设为 `YAW_ZERO % 1024`，pitch 平滑值归零，同时重设时间戳 |

Yaw 在死区外按摇杆偏移、speed 和更新间隔累计 raw。系数为 `YAW_INCREMENT_RAW_PER_SEC = 2048`，累计值按 1024 回绕；speed 为 0 时累计值不变。更新间隔超过 250 ms 或为负时回退为 20 ms。Yaw 当前没有指数平滑，发送位置时固定使用 `YAW_MOVE_TIME_MS = 40`。

Pitch 使用中心 350、死区 100 和单侧 0～90 映射，再按 `old × smoothing + target × (1 - smoothing)` 平滑。speed 对应返回的 `move_ms`，从 400 ms 到 50 ms，用于 pitch。精确边界与输入 450 时的非零目标见[遥控映射说明](remote_control.md#当前摇杆映射)。

脚本的超时处理发送 Home 并重置映射，不断电。非 8 字节包的分支会提前跳过超时检查，因此 `should_auto_center()` 本身不能保证断流后一定回位。

## 历史库的兼容边界

`lib/servo.py` 仍提供 `startup()`、`shutdown()`、`set_yaw()`、`set_pitch()`、`center()`、`ping_verbose()`、`to_hex()` 等接口。它没有当前遥控脚本的 `home()`、`set_yaw_raw()` 或 `yaw_deg_to_raw()`。

旧库两轴均使用 `raw = int(zero + degrees × 3.41)`：yaw 零位 460、声明范围 -180～180；pitch 零位 620、范围 -30～45。**旧 yaw 范围不能称为安全限幅**：-180° 得到 raw -153，编码为无符号 16 位后变成 65383；+180° 得到 raw 1073。范围端点未按 0～1023 做限制或回绕。`servo_validation.py` 保留同类换算，虽然当前内置 yaw 测试序列只使用 0、±40、±80。

`lib/motion.py` 的 `update()` 返回 `(yaw_deg, pitch_deg, move_ms)`。它对 yaw 做 ±120 的绝对角度映射，对 pitch 做 -25～40 的线性映射，并平滑两轴。输入 pitch 450 对应目标 7.5°；由于上下范围不对称，死区不会自动使其成为 0°。其构造函数还接受方向反转和灵敏度参数，这些参数不属于当前自包含遥控脚本的构造接口。

历史原型保留用于比较和后续整理。完整验收前，不应把它们与当前脚本宣称为同一套已验证驱动，也不应根据旧文档把运行脚本的零位、行程或 yaw 映射改回旧值。
