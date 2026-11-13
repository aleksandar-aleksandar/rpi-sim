"""Parking sensor with gpiozero: distance -> colour + beeping.

Scroll over the ultrasonic sensor to move the "car". The RGB LED goes green
-> yellow -> red as you get closer, and the beeps speed up like a real
parking sensor; below 10 cm the tone is continuous.

Wiring (preset 15_parking_sensor.json):
    HC-SR04: VCC -> 5V, TRIG -> GPIO23, ECHO -> GPIO24, GND -> GND rail
    RGB LED (common cathode): R/G/B <- 220 ohm <- GPIO17 / GPIO27 / GPIO22, K -> GND
    passive buzzer: GPIO25 (pin 22) -> (+), (-) -> GND rail
"""
import time

from gpiozero import RGBLED, DistanceSensor, TonalBuzzer

sensor = DistanceSensor(echo=24, trigger=23, max_distance=1.5)
light = RGBLED(red=17, green=27, blue=22)
buzzer = TonalBuzzer(25)

try:
    while True:
        cm = sensor.distance * 100
        closeness = max(0.0, min(1.0, (100 - cm) / 90))      # 0 far (>=100 cm) .. 1 near (10 cm)
        light.color = (min(1, 2 * closeness), min(1, 2 * (1 - closeness)), 0)
        print(f"{cm:5.1f} cm")
        if cm < 10:
            buzzer.play("A5")
            time.sleep(0.2)
        elif cm < 100:
            buzzer.play("A5")
            time.sleep(0.08)
            buzzer.stop()
            time.sleep(0.05 + 0.6 * (1 - closeness))
        else:
            buzzer.stop()
            time.sleep(0.3)
except KeyboardInterrupt:
    buzzer.stop()
