"""Turn the LED on while the PIR sensor sees motion.

Hold the PIR with the mouse (in "Use" mode) to simulate motion.

Wiring (preset 07_pir_motion.json):
    PIR VCC -> 5V (pin 2)   (the PIR needs 5V!)
    PIR GND -> GND rail
    PIR OUT -> GPIO4 (pin 7)
    GPIO17 (pin 11) -> LED (+), LED (-) -> 220 ohm -> GND rail
    GND (pin 6)     -> GND rail
"""
import RPi.GPIO as GPIO

PIR_PIN = 4
LED_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)      # the PIR drives its output itself, no pull-up needed
GPIO.setup(LED_PIN, GPIO.OUT)


def pir_changed(channel):
    motion = GPIO.input(channel)
    GPIO.output(LED_PIN, motion)
    print("Motion!" if motion else "Still.")


GPIO.add_event_detect(PIR_PIN, GPIO.BOTH, callback=pir_changed)

try:
    input("Press Enter to exit...\n")
finally:
    GPIO.cleanup()
