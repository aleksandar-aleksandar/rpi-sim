"""Reaction game.

The LED lights up after a random 3-10 s. Press the button within 2 s:
success -> high tone, too late -> low tone. Repeats forever.

Wiring (preset 08_reaction_game.json):
    GPIO17 (pin 11) -> LED (+), LED (-) -> 220 ohm -> GND rail
    GPIO27 (pin 13) -> button -> GND rail
    GPIO22 (pin 15) -> passive buzzer (+), (-) -> GND rail
    GND (pin 6)     -> GND rail
"""
import random
import time

import RPi.GPIO as GPIO

LED_PIN = 17
BUTTON_PIN = 27
BUZZER_PIN = 22

HIGH_TONE = 1000   # Hz - success
LOW_TONE = 200     # Hz - failure
REACTION_TIME = 2  # s

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUZZER_PIN, GPIO.OUT)
buzzer = GPIO.PWM(BUZZER_PIN, HIGH_TONE)


def tone(freq, duration):
    buzzer.ChangeFrequency(freq)
    buzzer.start(50)
    time.sleep(duration)
    buzzer.stop()


def wait_for_press(timeout):
    """True if the button is pressed within `timeout` seconds."""
    start = time.time()
    while time.time() - start < timeout:
        if GPIO.input(BUTTON_PIN) == 0:     # pressed = 0 (pull-up)
            return True
        time.sleep(0.01)
    return False


try:
    while True:
        GPIO.output(LED_PIN, GPIO.LOW)
        delay = random.randint(3, 10)
        print(f"Get ready... ({delay} s)")
        time.sleep(delay)

        GPIO.output(LED_PIN, GPIO.HIGH)
        if wait_for_press(REACTION_TIME):
            print("Success!")
            tone(HIGH_TONE, 0.5)
        else:
            print("Too late!")
            tone(LOW_TONE, 0.5)
        GPIO.output(LED_PIN, GPIO.LOW)
except KeyboardInterrupt:
    buzzer.stop()
    GPIO.cleanup()
