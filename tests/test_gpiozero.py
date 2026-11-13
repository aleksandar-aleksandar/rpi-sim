"""gpiozero compatibility layer, exercised against the bundled preset circuits."""
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
os.environ["RPISIM_HEADLESS"] = "1"
os.environ.setdefault("RPISIM_CIRCUIT", os.path.join(tempfile.mkdtemp(), "circuit.json"))
sys.path.insert(0, ROOT)

import RPi.GPIO as GPIO  # noqa: E402
from RPi import _core as core  # noqa: E402
import gpiozero  # noqa: E402
from gpiozero import (LED, PWMLED, RGBLED, AngularServo, Button, Buzzer,  # noqa: E402
                      DistanceSensor, MotionSensor, Servo, TonalBuzzer)
from gpiozero.tones import Tone  # noqa: E402


def first(kind):
    return next(k for k, o in core.OBJ.items() if o["type"] == kind)


def settle(seconds=0.05):
    time.sleep(seconds)


class ZeroBase(unittest.TestCase):
    preset = None

    def setUp(self):
        GPIO.cleanup()
        gpiozero._USED.clear()
        core.MODE[0] = None
        core.load_preset(os.path.join(EXAMPLES, self.preset + ".json"))
        self.devices = []

    def tearDown(self):
        for d in self.devices:
            d.close()

    def dev(self, d):
        self.devices.append(d)
        return d

    def ev(self):
        return core.evaluate()


class OutputTest(ZeroBase):
    preset = "01_blink"

    def test_led(self):
        led = self.dev(LED(17))
        led_id = first("led")
        self.assertEqual(self.ev()["leds"][led_id][0], "off")
        led.on()
        self.assertTrue(led.is_lit)
        self.assertEqual(self.ev()["leds"][led_id][0], "on")
        led.toggle()
        self.assertEqual(self.ev()["leds"][led_id][0], "off")

    def test_blink_in_background(self):
        led = self.dev(LED("GPIO17"))
        led.blink(on_time=0.05, off_time=0.05, n=2)
        settle(0.02)
        self.assertTrue(led.is_lit)
        settle(0.25)
        self.assertFalse(led.is_lit)

    def test_pin_in_use(self):
        self.dev(LED(17))
        with self.assertRaises(gpiozero.GPIOPinInUse):
            LED("BOARD11")          # physical pin 11 == GPIO17


class PwmTest(ZeroBase):
    preset = "04_pwm_fade"

    def test_pwmled_brightness(self):
        led = self.dev(PWMLED(18))
        led.value = 0.25
        state, bright = self.ev()["leds"][first("led")]
        self.assertEqual(state, "on")
        self.assertAlmostEqual(bright, 0.25)
        with self.assertRaises(ValueError):
            led.value = 2


class BuzzerTest(ZeroBase):
    preset = "05_active_buzzer"

    def test_buzzer(self):
        bz = self.dev(Buzzer(22))
        bz.on()
        self.assertEqual(self.ev()["buz"][first("abuz")], 2000)


class TonalBuzzerTest(ZeroBase):
    preset = "06_passive_buzzer"

    def test_play_notes(self):
        bz = self.dev(TonalBuzzer(22))
        bz.play("A4")
        self.assertAlmostEqual(self.ev()["buz"][first("pbuz")], 440, places=3)
        bz.play(Tone("C5"))
        self.assertAlmostEqual(self.ev()["buz"][first("pbuz")], 523.25, places=1)
        bz.value = -1
        self.assertAlmostEqual(bz.tone, 220)
        bz.stop()
        self.assertIsNone(self.ev()["buz"][first("pbuz")])
        with self.assertRaises(ValueError):
            bz.play(2000)               # above max_tone (one octave over A4)

    def test_tone_parsing(self):
        self.assertAlmostEqual(Tone("A4"), 440)
        self.assertAlmostEqual(Tone("A#4"), 466.16, places=2)
        self.assertAlmostEqual(Tone(midi=60), 261.63, places=2)


class ButtonTest(ZeroBase):
    preset = "02_button_led"

    def test_button_drives_led(self):
        led, btn = self.dev(LED(17)), self.dev(Button(27))
        events = []
        btn.when_pressed = led.on
        btn.when_released = lambda: (led.off(), events.append("released"))
        sw = first("btn")
        self.assertFalse(btn.is_pressed)
        core.press(sw)
        settle()
        self.assertTrue(btn.is_pressed)
        self.assertEqual(self.ev()["leds"][first("led")][0], "on")
        core.release(sw)
        settle()
        self.assertEqual(self.ev()["leds"][first("led")][0], "off")
        self.assertEqual(events, ["released"])

    def test_hold(self):
        btn = self.dev(Button(27, hold_time=0.1))
        held = []
        btn.when_held = lambda b: held.append(b.is_held)
        core.press(first("btn"))
        settle(0.2)
        self.assertEqual(held, [True])
        core.release(first("btn"))
        settle()
        self.assertFalse(btn.is_held)

    def test_wait_for_press_timeout(self):
        btn = self.dev(Button(27))
        self.assertFalse(btn.wait_for_press(timeout=0.05))


class MotionTest(ZeroBase):
    preset = "07_pir_motion"

    def test_motion_sensor(self):
        pir = self.dev(MotionSensor(4))
        seen = []
        pir.when_motion = lambda: seen.append("motion")
        core.pir_hold(first("pir"), True)
        settle()
        self.assertTrue(pir.motion_detected)
        self.assertEqual(seen, ["motion"])
        core.pir_cancel(first("pir"))


class RgbTest(ZeroBase):
    preset = "11_rgb_led"

    def test_color(self):
        rgb = self.dev(RGBLED(17, 27, 22))
        rgb.color = (1, 0.5, 0)
        state, (r, g, b) = self.ev()["leds"][first("rgb")]
        self.assertEqual(state, "on")
        self.assertAlmostEqual(r, 1)
        self.assertAlmostEqual(g, 0.5)
        self.assertEqual(b, 0)
        rgb.off()
        self.assertEqual(self.ev()["leds"][first("rgb")][0], "off")


class ServoTest(ZeroBase):
    preset = "12_servo"

    def test_full_range_servo(self):
        s = self.dev(Servo(18, min_pulse_width=0.5 / 1000, max_pulse_width=2.5 / 1000))
        sid = first("servo")
        s.min()
        self.assertAlmostEqual(self.ev()["servo"][sid][1], 0)
        s.max()
        self.assertAlmostEqual(self.ev()["servo"][sid][1], 180)

    def test_default_pulses_cover_middle_90_degrees(self):
        s = self.dev(Servo(18))         # 1-2 ms, like real gpiozero defaults
        s.min()
        self.assertAlmostEqual(self.ev()["servo"][first("servo")][1], 45)

    def test_angular_servo(self):
        s = self.dev(AngularServo(18, min_angle=0, max_angle=180,
                                  min_pulse_width=0.5 / 1000, max_pulse_width=2.5 / 1000))
        s.angle = 135
        self.assertAlmostEqual(self.ev()["servo"][first("servo")][1], 135)


class DistanceTest(ZeroBase):
    preset = "13_ultrasonic"

    def test_distance(self):
        core.set_distance(first("sonar"), 40)
        ds = self.dev(DistanceSensor(echo=24, trigger=23, max_distance=2))
        self.assertAlmostEqual(ds.distance, 0.40, delta=0.02)
        core.set_distance(first("sonar"), 350)
        self.assertEqual(ds.distance, 2)             # capped at max_distance


if __name__ == "__main__":
    unittest.main()
