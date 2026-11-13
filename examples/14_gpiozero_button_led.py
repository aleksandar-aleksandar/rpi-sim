"""The gpiozero version of 02_button_led: no polling, no setup boilerplate.

gpiozero numbers pins by BCM (GPIO17), exactly like on a real Pi.

Wiring (preset 14_gpiozero_button_led.json): same as 02_button_led.
    GPIO17 (pin 11) -> LED (+), LED (-) -> 220 ohm -> GND rail
    GPIO27 (pin 13) -> button -> GND rail
"""
from gpiozero import LED, Button, pause

led = LED(17)
button = Button(27)

button.when_pressed = led.on
button.when_released = led.off
button.when_held = lambda: print("Still holding...")

print("Press the button (or key 1). Ctrl+C to quit.")
pause()
