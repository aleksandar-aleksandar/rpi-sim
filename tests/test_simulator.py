"""Headless tests for the electrical model and the RPi.GPIO API.

Run from the repository root:
    python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
os.environ["RPISIM_HEADLESS"] = "1"
os.environ["RPISIM_CIRCUIT"] = os.path.join(tempfile.mkdtemp(), "circuit.json")
sys.path.insert(0, ROOT)

import RPi.GPIO as GPIO  # noqa: E402
from RPi import _core as core  # noqa: E402


def first(kind):
    return next(k for k, o in core.OBJ.items() if o["type"] == kind)


class Base(unittest.TestCase):
    preset = None

    def setUp(self):
        GPIO.cleanup()
        core.MODE[0] = None
        if self.preset:
            self.assertTrue(core.load_preset(os.path.join(EXAMPLES, self.preset + ".json")))
        else:
            core.clear_all()
        GPIO.setmode(GPIO.BCM)

    def ev(self):
        return core.evaluate()


class BlinkTest(Base):
    preset = "01_blink"

    def test_led_follows_gpio(self):
        GPIO.setup(17, GPIO.OUT)
        led = first("led")
        self.assertEqual(self.ev()["leds"][led][0], "off")
        GPIO.output(17, GPIO.HIGH)
        self.assertEqual(self.ev()["leds"][led][0], "on")
        self.assertEqual(self.ev()["warnings"], [])
        self.assertEqual(self.ev()["gnd_wires"], 1)

    def test_removing_resistor_burns_led(self):
        GPIO.setup(17, GPIO.OUT, initial=GPIO.HIGH)
        res = first("res")
        legs = core.OBJ[res]["legs"]
        core.remove_obj(res)
        core.add_obj({"type": "wire", "a": legs[0], "b": legs[1], "color": "#000000"})
        self.assertEqual(self.ev()["leds"][first("led")][0], "burn")


class ButtonTest(Base):
    preset = "02_button_led"

    def test_pull_up_and_callback(self):
        GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        hits = []
        GPIO.add_event_detect(27, GPIO.FALLING, callback=hits.append, bouncetime=50)
        btn = first("btn")
        self.assertEqual(GPIO.input(27), 1)
        core.press(btn)
        self.assertEqual(GPIO.input(27), 0)
        core.release(btn)
        time.sleep(0.1)
        self.assertEqual(hits, [27])

    def test_wait_for_edge_timeout(self):
        GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        t = time.time()
        self.assertIsNone(GPIO.wait_for_edge(27, GPIO.FALLING, timeout=200))
        self.assertGreaterEqual(time.time() - t, 0.19)

    def test_floating_without_pull(self):
        GPIO.setup(27, GPIO.IN)
        self.assertTrue(any("floating" in w for w in self.ev()["warnings"]))


class PwmTest(Base):
    preset = "04_pwm_fade"

    def test_brightness_follows_duty(self):
        GPIO.setup(18, GPIO.OUT)
        pwm = GPIO.PWM(18, 100)
        pwm.start(30)
        state, bright = self.ev()["leds"][first("led")]
        self.assertEqual(state, "on")
        self.assertAlmostEqual(bright, 0.3)
        pwm.stop()


class BuzzerTest(Base):
    def test_active_buzzer_sounds_on_high(self):
        core.load_preset(os.path.join(EXAMPLES, "05_active_buzzer.json"))
        GPIO.setup(22, GPIO.OUT, initial=GPIO.HIGH)
        self.assertEqual(self.ev()["buz"][first("abuz")], 2000)

    def test_passive_buzzer_needs_pwm(self):
        core.load_preset(os.path.join(EXAMPLES, "06_passive_buzzer.json"))
        GPIO.setup(22, GPIO.OUT, initial=GPIO.HIGH)
        bz = first("pbuz")
        self.assertIsNone(self.ev()["buz"][bz])          # plain HIGH: silent
        GPIO.output(22, GPIO.LOW)
        pwm = GPIO.PWM(22, 440)
        pwm.start(50)
        self.assertEqual(self.ev()["buz"][bz], 440)
        pwm.stop()


class PirTest(Base):
    preset = "07_pir_motion"

    def test_motion(self):
        GPIO.setup(4, GPIO.IN)
        pir = first("pir")
        self.assertEqual(self.ev()["pir"][pir], (True, False))
        self.assertEqual(GPIO.input(4), 0)
        core.pir_hold(pir, True)
        self.assertEqual(GPIO.input(4), 1)
        core.pir_hold(pir, False)
        time.sleep(core.PIR_TAIL + 0.1)
        core.update_inputs()
        self.assertEqual(GPIO.input(4), 0)


class PresetsTest(Base):
    def test_full_presets_have_no_warnings(self):
        setups = {
            "08_reaction_game": lambda: (GPIO.setup([17, 22], GPIO.OUT),
                                         GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)),
            "09_motion_alarm": lambda: (GPIO.setup([17, 22], GPIO.OUT), GPIO.setup(4, GPIO.IN)),
        }
        for name, setup in setups.items():
            with self.subTest(name):
                GPIO.cleanup()
                core.load_preset(os.path.join(EXAMPLES, name + ".json"))
                setup()
                self.assertEqual(self.ev()["warnings"], [])
                self.assertEqual(self.ev()["gnd_wires"], 1)

    def test_common_mistakes_are_reported(self):
        core.load_preset(os.path.join(EXAMPLES, "10_common_mistakes.json"))
        GPIO.setup([17, 22, 23], GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(27, GPIO.IN)
        text = "\n".join(self.ev()["warnings"])
        for needle in ("burning out", "same net", "reversed", "floating"):
            self.assertIn(needle, text)


class RgbLedTest(Base):
    preset = "11_rgb_led"

    def setUp(self):
        super().setUp()
        GPIO.setup([17, 27, 22], GPIO.OUT)
        self.rgb = first("rgb")

    def color(self):
        return self.ev()["leds"][self.rgb]

    def test_single_channels(self):
        self.assertEqual(self.color(), ("off", (0.0, 0.0, 0.0)))
        GPIO.output(17, GPIO.HIGH)
        self.assertEqual(self.color(), ("on", (1.0, 0.0, 0.0)))
        GPIO.output(22, GPIO.HIGH)
        self.assertEqual(self.color(), ("on", (1.0, 0.0, 1.0)))
        self.assertEqual(self.ev()["warnings"], [])

    def test_pwm_mixing(self):
        g = GPIO.PWM(27, 100)
        g.start(40)
        state, (r, gg, b) = self.color()
        self.assertEqual(state, "on")
        self.assertAlmostEqual(gg, 0.4)
        g.stop()

    def test_missing_resistor_burns(self):
        res = next(k for k, o in core.OBJ.items() if o["type"] == "res" and o["legs"][0] == "bb:c:12")
        legs = core.OBJ[res]["legs"]
        core.remove_obj(res)
        core.add_obj({"type": "wire", "a": legs[0], "b": legs[1], "color": "#000000"})
        GPIO.output(17, GPIO.HIGH)
        self.assertEqual(self.color()[0], "burn")
        self.assertTrue(any("R channel" in w for w in self.ev()["warnings"]))


class UndoTest(Base):
    def test_undo_redo_edits(self):
        core.clear_history()
        a = core.add_obj({"type": "led", "legs": ["bb:a:1", "bb:a:2"], "color": "red"})
        core.move_obj(a, {"legs": ["bb:a:5", "bb:a:6"]})
        core.remove_obj(a)
        self.assertNotIn(a, core.OBJ)
        self.assertTrue(core.undo())
        self.assertEqual(core.OBJ[a]["legs"], ["bb:a:5", "bb:a:6"])
        self.assertTrue(core.undo())
        self.assertEqual(core.OBJ[a]["legs"], ["bb:a:1", "bb:a:2"])
        self.assertTrue(core.redo())
        self.assertEqual(core.OBJ[a]["legs"], ["bb:a:5", "bb:a:6"])
        core.add_obj({"type": "wire", "a": "pi:1", "b": "bb:T+:1", "color": "#d42020"})
        self.assertFalse(core.redo())          # a new edit drops the redo branch

    def test_presses_are_not_edits(self):
        core.load_preset(os.path.join(EXAMPLES, "02_button_led.json"))
        core.clear_history()
        btn = first("btn")
        core.press(btn)
        core.release(btn)
        self.assertFalse(core.undo())

    def test_preset_load_is_undoable(self):
        core.load_preset(os.path.join(EXAMPLES, "01_blink.json"))
        n = len(core.OBJ)
        core.load_preset(os.path.join(EXAMPLES, "09_motion_alarm.json"))
        self.assertTrue(core.undo())
        self.assertEqual(len(core.OBJ), n)

    def test_history_is_bounded(self):
        core.clear_history()
        for i in range(core.HISTORY_LIMIT + 20):
            core.add_obj({"type": "wire", "a": "pi:1", "b": f"bb:T+:{i % 30 + 1}", "color": "#d42020"})
        undone = 0
        while core.undo():
            undone += 1
        self.assertEqual(undone, core.HISTORY_LIMIT)


class ApiErrorsTest(Base):
    def test_errors_match_rpi_gpio(self):
        core.MODE[0] = None
        with self.assertRaisesRegex(RuntimeError, "setmode"):
            GPIO.setup(17, GPIO.OUT)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(17, GPIO.IN)
        with self.assertRaisesRegex(RuntimeError, "OUTPUT"):
            GPIO.output(17, 1)
        GPIO.add_event_detect(17, GPIO.RISING)
        with self.assertRaisesRegex(RuntimeError, "Conflicting"):
            GPIO.add_event_detect(17, GPIO.BOTH)

    def test_short_circuit(self):
        core.add_obj({"type": "wire", "a": "pi:1", "b": "pi:6", "color": "#d42020"})
        self.assertTrue(any("SHORT CIRCUIT" in w for w in self.ev()["warnings"]))


if __name__ == "__main__":
    unittest.main()
