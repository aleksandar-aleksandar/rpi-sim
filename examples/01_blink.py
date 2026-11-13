"""Blink an LED once per second.

Wiring (preset 01_blink.json):
    GPIO17 (pin 11) -> LED anode (+)
    LED cathode (-) -> 220 ohm resistor -> GND rail
    GND (pin 6)     -> GND rail
"""
import time

import RPi.GPIO as GPIO

LED_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)

try:
    while True:
        GPIO.output(LED_PIN, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(LED_PIN, GPIO.LOW)
        time.sleep(1)
except KeyboardInterrupt:
    GPIO.cleanup()
