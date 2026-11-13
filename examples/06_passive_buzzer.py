"""Play a scale on a PASSIVE buzzer: it needs a PWM signal, and the frequency is the pitch.

Wiring (preset 06_passive_buzzer.json):
    GPIO22 (pin 15) -> buzzer (+), buzzer (-) -> GND rail
    GND (pin 6)     -> GND rail
"""
import time

import RPi.GPIO as GPIO

BUZZER_PIN = 22
SCALE = [262, 294, 330, 349, 392, 440, 494, 523]   # C4 .. C5 in Hz

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)
buzzer = GPIO.PWM(BUZZER_PIN, 440)


def tone(freq, duration):
    buzzer.ChangeFrequency(freq)
    buzzer.start(50)          # 50 % duty cycle = loudest square wave
    time.sleep(duration)
    buzzer.stop()
    time.sleep(0.05)          # short gap so the notes stay distinct


try:
    while True:
        for note in SCALE:
            tone(note, 0.3)
        time.sleep(1)
except KeyboardInterrupt:
    buzzer.stop()
    GPIO.cleanup()
