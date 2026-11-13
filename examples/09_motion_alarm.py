"""Motion alarm.

The LED is off for a random 3-10 s, then on for a random 3-5 s. While the LED
is on, motion seen by the PIR sounds the active buzzer. Repeats forever.

Wiring (preset 09_motion_alarm.json):
    GPIO17 (pin 11) -> LED (+), LED (-) -> 220 ohm -> GND rail
    PIR VCC -> 5V (pin 2), PIR GND -> GND rail, PIR OUT -> GPIO4 (pin 7)
    GPIO22 (pin 15) -> active buzzer (+), (-) -> GND rail
    GND (pin 6)     -> GND rail
"""
import random
import time

import RPi.GPIO as GPIO

LED_PIN = 17
PIR_PIN = 4
BUZZER_PIN = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(BUZZER_PIN, GPIO.OUT)


def watch_for_motion(duration):
    """For `duration` seconds: buzz while the PIR reports motion."""
    start = time.time()
    while time.time() - start < duration:
        GPIO.output(BUZZER_PIN, GPIO.input(PIR_PIN))
        time.sleep(0.05)
    GPIO.output(BUZZER_PIN, GPIO.LOW)


try:
    while True:
        off_time = random.randint(3, 10)
        print(f"LED off for {off_time} s")
        GPIO.output(LED_PIN, GPIO.LOW)
        time.sleep(off_time)

        on_time = random.randint(3, 5)
        print(f"LED on for {on_time} s - watching for motion")
        GPIO.output(LED_PIN, GPIO.HIGH)
        watch_for_motion(on_time)
except KeyboardInterrupt:
    GPIO.cleanup()
