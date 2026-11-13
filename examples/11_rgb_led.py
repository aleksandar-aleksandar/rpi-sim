"""Cycle a common-cathode RGB LED through the rainbow with PWM.

Each colour channel gets its own PWM pin and its own resistor; mixing the
three duty cycles produces any colour.

Wiring (preset 11_rgb_led.json):
    RGB legs (left to right): R, K (longest), G, B
    GPIO17 (pin 11) -> 220 ohm -> R
    GPIO27 (pin 13) -> 220 ohm -> G
    GPIO22 (pin 15) -> 220 ohm -> B
    K -> GND rail,  GND (pin 6) -> GND rail
"""
import colorsys
import time

import RPi.GPIO as GPIO

PINS = {"R": 17, "G": 27, "B": 22}

GPIO.setmode(GPIO.BCM)
channels = {}
for name, pin in PINS.items():
    GPIO.setup(pin, GPIO.OUT)
    channels[name] = GPIO.PWM(pin, 100)
    channels[name].start(0)


def set_color(r, g, b):
    """r, g, b in 0..1"""
    for name, value in zip("RGB", (r, g, b)):
        channels[name].ChangeDutyCycle(value * 100)


try:
    hue = 0.0
    while True:
        set_color(*colorsys.hsv_to_rgb(hue, 1.0, 1.0))
        hue = (hue + 0.01) % 1.0
        time.sleep(0.05)
except KeyboardInterrupt:
    for ch in channels.values():
        ch.stop()
    GPIO.cleanup()
