"""Beep an ACTIVE buzzer: it has its own oscillator, so HIGH = sound.

Wiring (preset 05_active_buzzer.json):
    GPIO22 (pin 15) -> buzzer (+), buzzer (-) -> GND rail
    GND (pin 6)     -> GND rail
"""
import time

import RPi.GPIO as GPIO

BUZZER_PIN = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

try:
    while True:
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        time.sleep(0.2)
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        time.sleep(1)
except KeyboardInterrupt:
    GPIO.cleanup()
