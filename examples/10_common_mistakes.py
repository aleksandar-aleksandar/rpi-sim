"""A circuit full of classic beginner mistakes - watch the Warnings panel.

    LED1 (GPIO17): no resistor               -> "burning out"
    LED2 (GPIO22): both legs in one column   -> shorted, never lights
    LED3 (GPIO23): inserted backwards        -> stays dark
    GPIO27: input with no pull-up and nothing connected -> floating, random reads

Fix them one by one in the editor and watch the warnings disappear.
"""
import time

import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup([17, 22, 23], GPIO.OUT)
GPIO.setup(27, GPIO.IN)            # no pull_up_down -> floating

try:
    while True:
        GPIO.output([17, 22, 23], GPIO.HIGH)
        print("GPIO27 reads:", GPIO.input(27))
        time.sleep(1)
except KeyboardInterrupt:
    GPIO.cleanup()
