# M5StackChan StickS3 Remote

This repository contains firmware assets and source patches for using an M5StickS3 with a Unit Joystick2 as an ESP-NOW remote controller for StackChan.

The physical controller enclosure is based on this MakerWorld model:

[M5 StickC 遥控附件摇杆灯 - MakerWorld](https://makerworld.com.cn/zh/models/2418504-m5-stickc-yao-kong-fu-jian-yao-gan-deng#profileId-2752841)

## What This Adds

The patch adapts the upstream StackChan remote firmware for:

* M5StickS3 target (`esp32s3`)
* Unit Joystick2 on StickS3 PORT.A
* ESP-NOW control packet compatibility with StackChan's `ESPNOW.REMOTE` app
* M5Burner-friendly merged `0x0` firmware packaging
* 8MB StickS3 flash partition layout
* Joystick X/Y inversion settings
* NVS persistence for joystick inversion after reboot

## Files

```text
patches/stackchan-remote-sticks3-joystick2.patch
```

This is the source patch to apply inside the `StackChan-official` submodule.

## Apply Patch

From this repository root:

```cmd
cd /d StackChan-official
git apply ..\patches\stackchan-remote-sticks3-joystick2.patch
```

## Build M5Burner Firmware

Open an ESP-IDF 5.4 Command Prompt, then run:

```cmd
cd /d C:\Users\23479\Documents\GitHub\M5StackChan\StackChan-official\remote\code
package_sticks3_m5burner.cmd
```

The generated M5Burner image is:

```text
C:\Users\23479\Documents\GitHub\M5StackChan\StackChan-official\remote\code\StackChan-RemoteControl-StickS3-Joystick2_0x0.bin
```

Burn this merged `0x0` image to the StickS3 with M5Burner `User Custom`.

## Hardware

* M5StickS3
* Unit Joystick2 connected to PORT.A
* StackChan running firmware with the `ESPNOW.REMOTE` app

The remote defaults to receiver ID `0`, which broadcasts to any StackChan receiver on the same ESP-NOW channel.

## Controls

* `BtnA` click: switch `Setup -> Running -> IMU`
* `BtnA` hold on `Running`: open joystick settings
* `BtnA` click in joystick settings: return to `Running`
* `BtnB` in `Setup`: select Channel or Receiver ID
* `BtnB` in `Running` / `IMU`: toggle the laser flag
* `BtnB` in joystick settings: select `Invert X` or `Invert Y`
* Joystick up/down in joystick settings: toggle the selected inversion option

Joystick inversion settings are saved to NVS and restored after reboot.

## StackChan Setup

On StackChan:

1. Open `ESPNOW.REMOTE`.
2. Choose `Receiver`.
3. Use the same Wi-Fi channel as the StickS3 remote.
4. Use receiver ID `0` for broadcast, or match the remote's configured receiver ID.
