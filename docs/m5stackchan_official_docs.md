# M5Stack StackChan – Official Documentation Reference

> **Source**: [docs.m5stack.com/en/stackchan](https://docs.m5stack.com/en/stackchan) + [StackChan-official repo](https://github.com/m5stack/StackChan)
>
> Compiled on 2026-05-05. Check the original sources for the latest updates.

> 2026-09-03 review: this is a historical reference, not a current device or
> firmware acceptance report. Cross-check hardware initialization against the
> pinned submodule `51a06177f7a820762c63c845bb4fe2a563be3eb4` and measured behavior.
> In particular, the firmware uses PY32 API pin **0** for VM_EN; source defaults
> `460/620` are not universal calibration values. A yaw “360°” specification
> does not prove that the current MicroPython raw-position wrap produces safe
> continuous rotation. See [debugging lessons](debugging_lessons_zh.md).

---

## 1. Product Overview

**StackChan** is a super-kawaii AI desktop robot co-created by **M5Stack** and the user community. It uses the M5Stack flagship IoT development kit **CoreS3** as its main controller.

- **Purchase**: [M5Stack Store](https://shop.m5stack.com/products/stackchan-kawaii-co-created-open-source-ai-desktop-robot) · [淘宝 Taobao](https://item.taobao.com/item.htm?id=1042238294510)
- **Board Support Package**: <https://github.com/m5stack/StackChan-BSP>
- **Open-Source Repo**: <https://github.com/m5stack/StackChan>

> ⚠️ **Do not forcibly rotate any movable parts connected to the motors by hand** when you are unsure whether the motors are powered and under control — this may cause hardware damage.

---

## 2. Hardware Specifications

### 2.1 Main Controller (CoreS3)

| Item | Specification |
| --- | --- |
| **SoC** | ESP32-S3, dual-core Xtensa LX7, 240 MHz |
| **Flash** | 16 MB |
| **PSRAM** | 8 MB (SPIRAM, 80 MHz OPI) |
| **Connectivity** | Wi-Fi 802.11 b/g/n, Bluetooth LE 5.0 |
| **Display** | 2.0″ IPS capacitive touch LCD (320 × 240), high-strength glass cover |
| **Camera** | 0.3 MP (GC0308, DVP YUV422, 320 × 240 @ 20 fps) |
| **Sensors** | 9-axis IMU (accelerometer + gyroscope + magnetometer), proximity & ambient light sensor |
| **Audio** | 1 W speaker, dual microphones |
| **Storage** | microSD card slot |
| **Buttons** | Power / Reset |

### 2.2 Robot Body

| Item | Specification |
| --- | --- |
| **Interface** | USB-C (power & data) |
| **Battery** | 550 mAh |
| **Servos** | 2 × feedback servos: **yaw** (360° continuous rotation), **pitch** (90° range) |
| **RGB LEDs** | 12 × RGB LEDs (2 rows of 6) |
| **IR** | Infrared transmitter + receiver |
| **Touch** | 3-zone head touch panel |
| **NFC** | Full-featured NFC module |

### 2.3 Firmware SDK Configuration Highlights

From `sdkconfig.defaults`:

```
CONFIG_IDF_TARGET="esp32s3"
CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y
CONFIG_SPIRAM=y
CONFIG_SPIRAM_SPEED_80M=y
CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y
CONFIG_BT_ENABLED=y
CONFIG_BT_NIMBLE_ENABLED=y
CONFIG_BT_NIMBLE_ATT_PREFERRED_MTU=512
CONFIG_CAMERA_GC0308=y
CONFIG_BOARD_TYPE_M5STACK_STACK_CHAN=y
```

### 2.4 Flash Partition Table

| Name | Type | SubType | Offset | Size |
| --- | --- | --- | --- | --- |
| nvs | data | nvs | 0x9000 | 16 KB |
| otadata | data | ota | 0xD000 | 8 KB |
| phy_init | data | phy | 0xF000 | 4 KB |
| ota_0 | app | ota_0 | 0x20000 | ~5 MB |
| ota_1 | app | ota_1 | auto | ~5 MB |
| assets | data | spiffs | 0xA00000 | 4 MB |
| coredump | data | coredump | auto | 64 KB |

---

## 3. Factory Firmware Features

The factory firmware is feature-rich:

- **AI Agent** (XiaoZhi / 小智 integration)
- **Lively, expressive face animations** (avatar system with emotes)
- **ESP-NOW wireless remote control**
- **Online App Downloads** (App Center)
- **Mobile App connectivity** (video, remote avatar control, dance choreography)
- **OTA updates**
- **Wake word detection** ("Hi StackChan" — configurable)
- **Multi-language support** (30+ languages including Chinese, English, Japanese, Korean, etc.)
- **WiFi provisioning** via Hotspot, Acoustic signal, or ESP BluFi

### 3.1 Supported Wake Word Modes

| Mode | Requirement |
| --- | --- |
| Wakenet without AFE | ESP32-C3 / C5 / C6, or ESP32 + PSRAM |
| Wakenet with AFE (AEC) | ESP32-S3 + PSRAM |
| Multinet (Custom Wake Word) | ESP32-S3 + PSRAM |

### 3.2 Display Styles

- **Default message style** (single-line scrolling or multiline chat)
- **WeChat message style**
- **Emote animation style** (select boards)

---

## 4. Software Architecture

### 4.1 Firmware (ESP-IDF / C++)

**Toolchain**: [ESP-IDF v5.5.4](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32s3/index.html)

**Build & Flash**:

```bash
# Fetch dependencies
python3 ./fetch_repos.py

# Build
idf.py build

# Flash
idf.py flash
```

**Key Dependencies** (from `repos.json`):

| Component | Version | Purpose |
| --- | --- | --- |
| [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) | v2.2.4 | XiaoZhi AI assistant core |
| [mooncake](https://github.com/Forairaaaaa/mooncake) | v2.3.3 | App framework |
| [smooth_ui_toolkit](https://github.com/Forairaaaaa/smooth_ui_toolkit) | v2.12.0 | UI toolkit |
| [ArduinoJson](https://github.com/bblanchon/ArduinoJson) | v7.4.2 | JSON parsing |
| [esp-now](https://github.com/espressif/esp-now) | (commit hash) | ESP-NOW protocol |

**Additional ESP-IDF Components** (from `idf_component.yml`):

- LVGL v9.4.x + esp_lvgl_port v2.7.x
- esp-sr v2.3.x (speech recognition)
- esp_audio_codec v2.4.x, esp_audio_effects v1.2.x
- esp32-camera v2.1.x
- Various LCD drivers (ST7789, ILI9341, GC9A01, etc.)
- Touch drivers (FT5x06, GT911, CST816S, etc.)
- led_strip, button, knob peripherals

#### Firmware Source Structure

```
firmware/main/
├── main.cpp                  # Entry point
├── Kconfig.projbuild         # Build configuration menu
├── idf_component.yml         # ESP-IDF component dependencies
├── hal/                      # Hardware Abstraction Layer
│   ├── hal.h                 # HAL interface header
│   ├── hal.cpp               # HAL implementation
│   ├── hal_servo.cpp         # Servo control
│   ├── hal_ble.cpp           # BLE server
│   ├── hal_espnow.cpp        # ESP-NOW communication
│   ├── hal_head_touch.cpp    # Head touch panel
│   ├── hal_imu.cpp           # IMU sensor
│   ├── hal_ws_avatar.cpp     # WebSocket avatar service
│   ├── hal_network.cpp       # Network management
│   ├── hal_ota.cpp           # OTA updates
│   ├── hal_rtc.cpp           # Real-time clock
│   ├── hal_io_expander.cpp   # IO expander
│   ├── hal_mcp.cpp           # MCP protocol
│   ├── hal_account.cpp       # User account
│   ├── hal_app_center.cpp    # App center
│   ├── hal_ezdata.cpp        # EzData service
│   ├── board/                # Board-specific drivers
│   ├── drivers/              # Peripheral drivers
│   └── utils/                # Utility functions
├── stackchan/                # StackChan robot logic
│   ├── stackchan.h           # Main StackChan class
│   ├── stackchan.cpp
│   ├── avatar/               # Face/expression rendering
│   ├── animation/            # Animation engine
│   ├── motion/               # Servo motion control
│   ├── modifiers/            # Behavior modifiers
│   ├── addons/               # Addon features (NeonLight, etc.)
│   ├── json/                 # JSON helper
│   └── utils/                # Utilities
└── apps/                     # Built-in applications
```

### 4.2 HAL API Reference

The Hardware Abstraction Layer (`Hal` class) provides the following interfaces:

#### System

```cpp
void init();
void delay(uint32_t ms);
uint32_t millis();
void feedTheDog();
std::array<uint8_t, 6> getFactoryMac();
std::string getFactoryMacString(std::string divider = "");
void reboot();
uint8_t getBatteryLevel();
bool isBatteryCharging();
void factoryReset();
```

#### Display

```cpp
void lvglLock();
void lvglUnlock();
void setBackLightBrightness(uint8_t brightness, bool permanent = false);
uint8_t getBackLightBrightness();
```

#### Audio

```cpp
void setSpeakerVolume(uint8_t volume, bool permanent = false);
uint8_t getSpeakerVolume();
```

#### Servo & Power

```cpp
void setServoPowerEnabled(bool enabled);
```

#### RGB LEDs

```cpp
void setRgbColor(uint8_t index, uint8_t r, uint8_t g, uint8_t b);
void showRgbColor(uint8_t r, uint8_t g, uint8_t b);
void refreshRgb();
```

#### BLE

```cpp
void startBleServer();
bool isBleConnected();
void startAppConfigServer();
bool isAppConfiged();
// Signals: onBleMotionData, onBleAvatarData, onBleConfigData, onBleRgbData
```

#### ESP-NOW

```cpp
void startEspNow(int channel);
bool espNowSend(const std::vector<uint8_t>& data, const uint8_t* destAddr = nullptr);
void setLaserEnabled(bool enabled);
// Signal: onEspNowData
```

#### Network & OTA

```cpp
void startNetwork(std::function<void(std::string_view)> onLog);
WifiStatus getWifiStatus();
void startSntp();
bool updateFirmware(std::function<void(std::string_view)> onLog);
```

#### WebSocket Avatar Service

```cpp
void startWebSocketAvatarService(std::function<void(std::string_view)> onStartLog);
// Signals: onWsMotionData, onWsAvatarData, onWsCallRequest, onWsVideoFrame, onWsDanceData, etc.
```

#### IMU & Head Touch

```cpp
// Signal: onImuMotionEvent (None, Shake, PickUp)
// Signal: onHeadPetGesture (None, Press, Release, SwipeForward, SwipeBackward)
```

#### Time

```cpp
void syncRtcTimeToSystem();
void syncSystemTimeToRtc();
void setTimezone(std::string_view tz);
std::string getTimezone();
```

### 4.3 StackChan Class API

The core robot class (`stackchan::StackChan`) provides:

```cpp
// Motion (servo) control
void attachMotion(std::unique_ptr<motion::Motion> motion);
void resetMotion();
motion::Motion& motion();

// Avatar (face) control
void attachAvatar(std::unique_ptr<avatar::Avatar> avatar);
void resetAvatar();
avatar::Avatar& avatar();
bool hasAvatar();

// Neon lights
addon::NeonLight& leftNeonLight();
addon::NeonLight& rightNeonLight();

// Modifier system (behavior plugins)
int addModifier(std::unique_ptr<Modifier> modifier);
Modifier* getModifier(int id);
bool removeModifier(int id);
void clearModifiers();

// Update loop
void update();

// JSON-driven updates
void updateAvatarFromJson(const char* jsonContent);
void updateMotionFromJson(const char* jsonContent);
void updateNeonLightFromJson(const char* jsonContent);
```

---

## 5. Mobile App (Flutter)

A cross-platform Flutter app for controlling StackChan.

**Requirements**: Flutter 3.0+, Dart 3.0+

### 5.1 Features

- 🤖 **BLE device management** — connect and control via Bluetooth
- 💬 **AI conversation** — powered by XiaoZhi AI
- 🎭 **Facial expression rendering** — real-time 3D face animation (Three.js)
- 🎵 **Music & dance** — create and play dance choreographies
- 📷 **Camera integration** — AR features and face detection
- 🔐 **Secure communication** — RSA encryption

### 5.2 Backend Services

| Service | Base URL | Purpose |
| --- | --- | --- |
| StackChan Backend | `http://<server-ip>:<port>/stackChan/` | Device management, dance storage, auth |
| XiaoZhi AI | `https://XiaoZhi.me/` | AI conversation, TTS voice, agent config |

### 5.3 App Structure

```
lib/
├── main.dart                    # Entry point
├── app_state.dart               # Global state
├── model/                       # Data models
│   ├── XiaoZhi/                 # AI service models
│   ├── blue_device_info.dart    # BLE device models
│   └── dance_list.dart          # Dance models
├── network/                     # Network layer
│   ├── http.dart                # HTTP client
│   ├── urls.dart                # API endpoints
│   └── web_socket_util.dart     # WebSocket
├── util/                        # Utilities
│   ├── value_constant.dart      # Constants & keys
│   ├── rsa_util.dart            # RSA encryption
│   ├── blue_util.dart           # BLE utilities
│   └── music_util.dart          # Audio processing
└── view/                        # UI layer
    ├── home/                    # Home screens
    ├── popup/                   # Modals
    └── util/                    # UI components
```

---

## 6. Backend Server (Go)

A RESTful backend built with the **GoFrame** framework.

**Requirements**: Go 1.24+, MySQL 8.0+

### 6.1 API Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/device/bind` | POST | Bind device to user |
| `/api/device/unbind` | POST | Unbind device |
| `/api/device/update` | PUT | Update device info |
| `/api/devices` | GET | List devices |
| `/api/user/login` | POST | User login |
| `/api/user/registration` | POST | User registration |
| `/api/user` | GET | Get user info |
| `/api/dance` | POST/GET/PUT/DELETE | Dance CRUD |
| `/api/post/get` | GET | Get post details |
| `/api/admin/*` | various | Admin operations |

### 6.2 Configuration

Edit `manifest/config/config.yaml`:

```yaml
database:
  default:
    link: "mysql:user:pass@tcp(127.0.0.1:3306)/stackChan?charset=utf8mb4"

jwt:
  secret: "<your-secret>"

xiaozhi:
  secret_key: "<your-xiaozhi-key>"
  generate_license_token: "<your-token>"
```

### 6.3 Build & Run

```bash
cd server
go mod download
go run main.go          # dev
# or
go build -o stackchan-server main.go
./stackchan-server      # production
```

---

## 7. ESP-NOW Remote Control

The **ESP-NOW remote controller** firmware allows wireless servo control of StackChan.

### 7.1 Packet Format (8 bytes)

```
[target-id][yaw int16][pitch int16][speed int16][laser uint8]
```

| Offset | Size | Type | Description |
| --- | --- | --- | --- |
| 0 | 1 | uint8 | Target receiver ID (`0` = broadcast) |
| 1 | 2 | int16 LE | Yaw angle (`-1280` to `1280`) |
| 3 | 2 | int16 LE | Pitch angle (`0` to `900`) |
| 5 | 2 | int16 LE | Speed (`0` to `1000`) |
| 7 | 1 | uint8 | Laser / button flag |

```python
target_id, yaw, pitch, speed, laser = struct.unpack("<BhhhB", packet[:8])
```

---

## 8. Programming Options

StackChan supports multiple programming methods:

| Method | Description |
| --- | --- |
| **Arduino** | Use StackChan-BSP + Arduino IDE |
| **UIFlow2** | Visual / MicroPython programming via UIFlow2 Web IDE |
| **ESP-IDF** | Native C/C++ development (v5.5.4+) |
| **Custom Firmware** | Flash via `idf.py flash` or M5Burner |

### 8.1 UIFlow2 Quick Start

1. Flash UIFlow2 firmware with **M5Burner**
2. Connect StackChan to UIFlow2 Web IDE
3. Write Python scripts and run/download

### 8.2 Arduino / ESP-IDF

- Install the [StackChan-BSP](https://github.com/m5stack/StackChan-BSP) board support package
- Use ESP-IDF v5.5.4 toolchain
- Build: `idf.py build` → Flash: `idf.py flash`

---

## 9. Community & Credits

StackChan was created by the community with key contributions from:

| Avatar | Contributor |
| --- | --- |
| [@stack_chan](https://x.com/stack_chan) | **Shinya Ishikawa** — Original Stack-chan creator |
| [@mongonta555](https://x.com/mongonta555) | **Takao Akaki** — Major contributor |

---

## 10. Useful Links

| Resource | URL |
| --- | --- |
| Official Docs (EN) | <https://docs.m5stack.com/en/StackChan> |
| Official Docs (JA) | <https://docs.m5stack.com/ja/StackChan> |
| Official Docs (ZH) | <https://docs.m5stack.com/zh_CN/StackChan> |
| Open-Source Repo | <https://github.com/m5stack/StackChan> |
| Board Support Package | <https://github.com/m5stack/StackChan-BSP> |
| XiaoZhi ESP32 | <https://github.com/78/xiaozhi-esp32> |
| CoreS3 Docs | <https://docs.m5stack.com/en/core/CoreS3> |
| ESP-IDF v5.5.4 | <https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32s3/index.html> |
| M5Stack Shop | <https://shop.m5stack.com/products/stackchan-kawaii-co-created-open-source-ai-desktop-robot> |
