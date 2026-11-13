"""Light the LED while the button is held (polling).

Wiring (preset 02_button_led.json):
    GPIO17 (pin 11) -> LED (+), LED (-) -> 220 ohm -> GND rail
    GPIO27 (pin 13) -> button -> GND rail   (internal pull-up: pressed = 0)
    GND (pin 6)     -> GND rail
"""
import time

import RPi.GPIO as GPIO

LED_PIN = 17
BUTTON_PIN = 27

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

try:
    while True:
        pressed = GPIO.input(BUTTON_PIN) == 0
        GPIO.output(LED_PIN, GPIO.HIGH if pressed else GPIO.LOW)
        time.sleep(0.02)
except KeyboardInterrupt:
    GPIO.cleanup()
