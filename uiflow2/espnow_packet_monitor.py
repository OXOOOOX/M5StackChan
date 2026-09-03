import struct
import time

import M5
from M5 import *
import espnow
import network


WIFI_CHANNEL = 1


title = None
status = None
packet_label = None


def setup_screen():
    global title, status, packet_label
    M5.begin()
    Widgets.fillScreen(0x111111)
    title = Widgets.Title("ESP-NOW Monitor", 3, 0xFFFFFF, 0x2B5F9E, Widgets.FONTS.DejaVu18)
    status = Widgets.Label("starting...", 8, 42, 1.0, 0xFFFFFF, 0x111111, Widgets.FONTS.DejaVu18)
    packet_label = Widgets.Label("no packet", 8, 82, 1.0, 0x66FF99, 0x111111, Widgets.FONTS.DejaVu18)


def init_espnow():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.disconnect()
    try:
        wlan.config(channel=WIFI_CHANNEL)
    except Exception as e:
        print("channel config skipped:", e)

    esp = espnow.ESPNow()
    esp.active(True)
    return esp


def parse_packet(packet):
    if len(packet) != 8:
        return "ignore packet len={}".format(len(packet))
    target_id, yaw, pitch, speed, laser = struct.unpack("<BhhhB", packet)
    return "id:{} yaw:{} pitch:{} speed:{} laser:{}".format(target_id, yaw, pitch, speed, laser)


def main():
    setup_screen()
    status.setText("channel {}".format(WIFI_CHANNEL))
    esp = init_espnow()

    while True:
        M5.update()
        host, packet = esp.recv(50)
        if packet:
            text = parse_packet(packet)
            print(text)
            packet_label.setText(text)
        time.sleep_ms(20)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as e:
        try:
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print(e)
