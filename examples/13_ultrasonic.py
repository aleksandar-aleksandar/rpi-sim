"""Measure distance with an HC-SR04 ultrasonic sensor.

Scroll the mouse wheel over the sensor to change the distance it "sees"
(hold Shift for 1 cm steps).

How it works: a 10 µs pulse on TRIG makes the sensor send an ultrasonic
burst; ECHO then stays HIGH for as long as the sound takes to travel to the
object and back. Sound travels 34300 cm/s, so distance = time * 34300 / 2.

The timing uses time.perf_counter(): it works the same on a Raspberry Pi,
and on Windows time.time() only ticks about once per millisecond (~17 cm).

Wiring (preset 13_ultrasonic.json):
    VCC  -> 5V (pin 2)
    TRIG -> GPIO23 (pin 16)
    ECHO -> GPIO24 (pin 18)   (on a real 5V HC-SR04, use a voltage divider here!)
    GND  -> GND rail,  GND (pin 6) -> GND rail
"""
import time

import RPi.GPIO as GPIO

TRIG_PIN = 23
ECHO_PIN = 24
TIMEOUT = 0.04          # s - no echo within 40 ms means "nothing in range"

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG_PIN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(ECHO_PIN, GPIO.IN)


def measure_cm():
    GPIO.output(TRIG_PIN, GPIO.HIGH)
    time.sleep(0.00001)                 # 10 µs trigger pulse
    GPIO.output(TRIG_PIN, GPIO.LOW)

    deadline = time.perf_counter() + TIMEOUT
    start = time.perf_counter()
    while GPIO.input(ECHO_PIN) == 0:    # wait for the echo to begin
        start = time.perf_counter()
        if start > deadline:
            return None
    end = time.perf_counter()
    while GPIO.input(ECHO_PIN) == 1:    # time how long it stays high
        end = time.perf_counter()
        if end > deadline:
            return None
    return (end - start) * 34300 / 2


try:
    while True:
        d = measure_cm()
        print("out of range" if d is None else f"{d:5.1f} cm")
        time.sleep(0.5)
except KeyboardInterrupt:
    GPIO.cleanup()
