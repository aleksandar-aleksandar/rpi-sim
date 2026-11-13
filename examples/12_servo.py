"""Sweep a hobby servo (SG90) from 0° to 180° and back.

A servo reads the WIDTH of a pulse sent 50 times per second:
0.5 ms -> 0°, 1.5 ms -> 90°, 2.5 ms -> 180°.
At 50 Hz one period is 20 ms, so duty cycle = pulse / 20 ms:
0° -> 2.5 %, 90° -> 7.5 %, 180° -> 12.5 %.

Wiring (preset 12_servo.json):
    servo brown  (GND) -> GND rail
    servo red    (VCC) -> 5V (pin 4)    (servos need 5V)
    servo orange (SIG) -> GPIO18 (pin 12)
    GND (pin 6)        -> GND rail
"""
import time

import RPi.GPIO as GPIO

SERVO_PIN = 18

GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(7.5)                       # start centred


def set_angle(angle):
    pwm.ChangeDutyCycle(2.5 + angle / 18)   # 0..180 -> 2.5..12.5 %


try:
    while True:
        for angle in range(0, 181, 10):
            set_angle(angle)
            time.sleep(0.1)
        for angle in range(180, -1, -10):
            set_angle(angle)
            time.sleep(0.1)
except KeyboardInterrupt:
    pwm.stop()
    GPIO.cleanup()
