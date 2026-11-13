"""Fade an LED in and out with PWM (duty cycle = brightness).

Wiring (preset 04_pwm_fade.json):
    GPIO18 (pin 12) -> LED (+), LED (-) -> 220 ohm -> GND rail
    GND (pin 6)     -> GND rail
"""
import time

import RPi.GPIO as GPIO

LED_PIN = 18

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)

pwm = GPIO.PWM(LED_PIN, 100)   # 100 Hz is fast enough that the eye sees no flicker
pwm.start(0)

try:
    while True:
        for duty in range(0, 101, 5):
            pwm.ChangeDutyCycle(duty)
            time.sleep(0.05)
        for duty in range(100, -1, -5):
            pwm.ChangeDutyCycle(duty)
            time.sleep(0.05)
except KeyboardInterrupt:
    pwm.stop()
    GPIO.cleanup()
