"""Toggle the LED on every button press using an interrupt-style callback.

Wiring (preset 03_button_callback.json): same as 02_button_led.
"""
import RPi.GPIO as GPIO

LED_PIN = 17
BUTTON_PIN = 27

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

led_on = False


def on_press(channel):
    global led_on
    led_on = not led_on
    GPIO.output(LED_PIN, led_on)
    print("Button pressed -> LED", "ON" if led_on else "OFF")


# FALLING = the moment the pin goes from 1 to 0, i.e. the button is pressed
GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=on_press, bouncetime=100)

try:
    input("Press Enter to exit...\n")
finally:
    GPIO.cleanup()
