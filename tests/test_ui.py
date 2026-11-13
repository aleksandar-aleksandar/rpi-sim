"""Editor interaction tests. Skipped automatically when no display is available."""
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
os.environ["RPISIM_HEADLESS"] = "1"
os.environ.setdefault("RPISIM_CIRCUIT", os.path.join(tempfile.mkdtemp(), "circuit.json"))
sys.path.insert(0, ROOT)

import RPi.GPIO as GPIO  # noqa: E402
from RPi import _core as core  # noqa: E402

try:
    import tkinter as tk
    from RPi import _ui
    _root = tk.Tk()
    _root.withdraw()
except Exception as ex:  # no display / no tkinter
    _root = None
    _skip_reason = f"no GUI available: {ex}"


def ev(x, y):
    return types.SimpleNamespace(x=x, y=y)


def first(kind):
    return next(k for k, o in core.OBJ.items() if o["type"] == kind)


@unittest.skipIf(_root is None, "no GUI available")
class EditorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ui.App(_root)

    def setUp(self):
        GPIO.cleanup()
        core.MODE[0] = None
        self.app.mode.set("use")
        self.app.drag = None
        self.app.holding = None

    def load(self, name):
        core.load_preset(os.path.join(EXAMPLES, name + ".json"))

    def body(self, oid):
        return self.app._body_center(core.OBJ[oid])

    def drag(self, oid, dx, dy):
        x, y = self.body(oid)
        self.app._on_down(ev(x, y))
        self.app._on_drag(ev(x + dx / 2, y + dy / 2))
        self.app._on_drag(ev(x + dx, y + dy))
        self.app._on_up(ev(x + dx, y + dy))

    def test_drag_led_moves_both_legs(self):
        self.load("01_blink")
        led = first("led")
        self.drag(led, 5 * _ui.P, 0)
        self.assertEqual(core.OBJ[led]["legs"], ["bb:a:15", "bb:a:16"])
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(17, GPIO.OUT, initial=GPIO.HIGH)
        self.assertEqual(core.evaluate()["leds"][led][0], "off")   # wires stayed behind

    def test_undo_restores_drag(self):
        self.load("01_blink")
        led = first("led")
        before = list(core.OBJ[led]["legs"])
        self.drag(led, 5 * _ui.P, 0)
        self.app._undo()
        self.assertEqual(core.OBJ[led]["legs"], before)
        self.app._redo()
        self.assertEqual(core.OBJ[led]["legs"], ["bb:a:15", "bb:a:16"])

    def test_drag_onto_taken_holes_is_rejected(self):
        self.load("01_blink")
        led = first("led")
        before = list(core.OBJ[led]["legs"])
        self.drag(led, 0, _ui.P)          # a10/a11 -> b10/b11: wire + resistor are there
        self.assertEqual(core.OBJ[led]["legs"], before)
        self.assertIn("Can't move", self.app.hint.cget("text"))

    def test_drag_pir_wires_follow(self):
        self.load("07_pir_motion")
        pir = first("pir")
        x0 = core.OBJ[pir]["x"]
        self.drag(pir, 120, 0)
        self.assertEqual(core.OBJ[pir]["x"], x0 + 120)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(4, GPIO.IN)
        self.assertEqual(core.evaluate()["pir"][pir], (True, False))   # still wired + powered

    def test_place_and_move_modules(self):
        core.clear_all()
        self.app.mode.set("servo")
        self.app._on_down(ev(600, 520))
        self.app.mode.set("pir")
        self.app._on_down(ev(620, 540))            # overlaps the servo -> rejected
        self.assertIn("Too close", self.app.hint.cget("text"))
        self.app._on_down(ev(800, 520))
        types_ = sorted(o["type"] for o in core.OBJ.values())
        self.assertEqual(types_, ["pir", "servo"])
        servo = first("servo")
        self.assertEqual(_ui.point_at(*_ui.pt_pos(f"m:{servo}:SIG")), f"m:{servo}:SIG")
        self.app.mode.set("use")
        self.drag(servo, 0, 40)
        self.assertEqual(core.OBJ[servo]["y"], 560)

    def test_scroll_sets_sonar_distance(self):
        self.load("13_ultrasonic")
        us = first("sonar")
        x, y = self.body(us)
        self.app._on_wheel(types.SimpleNamespace(x=x, y=y, delta=120, state=0))
        self.assertEqual(core.OBJ[us]["cm"], 55)
        self.app._on_wheel(types.SimpleNamespace(x=x, y=y, delta=-120, state=0x1))   # Shift
        self.assertEqual(core.OBJ[us]["cm"], 54)
        self.app._on_wheel(types.SimpleNamespace(x=x, y=y), -1)                       # X11 button 5
        self.assertEqual(core.OBJ[us]["cm"], 49)

    def test_click_without_drag_still_presses(self):
        self.load("02_button_led")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        btn = first("btn")
        x, y = self.body(btn)
        self.app._on_down(ev(x, y))
        self.assertEqual(GPIO.input(27), 0)
        self.app._on_up(ev(x, y))
        self.assertEqual(GPIO.input(27), 1)
        self.assertEqual(core.OBJ[btn]["legs"], ["bb:a:20", "bb:a:22"])

    def test_picking_up_pressed_button_releases_it(self):
        self.load("02_button_led")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        btn = first("btn")
        x, y = self.body(btn)
        self.app._on_down(ev(x, y))
        self.app._on_drag(ev(x + 3 * _ui.P, y))
        self.assertEqual(GPIO.input(27), 1)
        self.app._on_up(ev(x + 3 * _ui.P, y))
        self.assertEqual(core.OBJ[btn]["legs"], ["bb:a:23", "bb:a:25"])


@unittest.skipIf(_root is None, "no GUI available")
class DrawingTest(unittest.TestCase):
    """Render every preset with all outputs driven, to catch drawing errors."""

    @classmethod
    def setUpClass(cls):
        cls.app = _ui.App(_root)

    def test_every_preset_renders(self):
        import glob
        for path in sorted(glob.glob(os.path.join(EXAMPLES, "*.json"))):
            with self.subTest(os.path.basename(path)):
                GPIO.cleanup()
                core.MODE[0] = None
                core.load_preset(path)
                GPIO.setmode(GPIO.BCM)
                for b in (4, 17, 18, 22, 23, 27):
                    GPIO.setup(b, GPIO.OUT, initial=GPIO.HIGH)
                for oid, o in core.OBJ.items():
                    if o["type"] == "pir":
                        core.pir_hold(oid, True)
                objs = [(k, dict(v)) for k, v in core.OBJ.items()]
                self.app._draw_dynamic(core.evaluate(), objs)
                self.app._update_status(core.evaluate())
                self.assertTrue(self.app.cv.find_withtag("dyn"))
                for oid in list(core.PIR_STATE):
                    core.pir_cancel(oid)


@unittest.skipIf(_root is None, "no GUI available")
class KeyboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ui.App(_root)

    def setUp(self):
        GPIO.cleanup()
        core.MODE[0] = None
        core.load_preset(os.path.join(EXAMPLES, "09_motion_alarm.json"))
        btn = core.add_obj({"type": "btn", "legs": ["bb:j:3", "bb:j:5"]})
        core.add_obj({"type": "wire", "a": "pi:13", "b": "bb:i:3", "color": "#2a6bd6"})
        core.add_obj({"type": "wire", "a": "bb:i:5", "b": "bb:B-:5", "color": "#1c1c1c"})
        core.add_obj({"type": "wire", "a": "bb:B-:30", "b": "bb:T-:30", "color": "#1c1c1c"})
        self.btn, self.pir = btn, first("pir")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(4, GPIO.IN)

    def key(self, ch, down=True):
        e = types.SimpleNamespace(char=ch, state=0)
        (self.app._key_down if down else self.app._key_up)(e)

    def settle(self):
        import time
        time.sleep(0.08)
        _root.update()

    def test_order_buttons_then_pirs(self):
        self.assertEqual(self.app.input_order(), [self.btn, self.pir])

    def test_key_holds_button(self):
        self.key("1")
        self.assertEqual(GPIO.input(27), 0)
        self.key("1")                     # Windows auto-repeat
        self.key("1", down=False)
        self.settle()
        self.assertEqual(GPIO.input(27), 1)

    def test_x11_style_autorepeat_does_not_release(self):
        self.key("1")
        self.key("1", down=False)         # X11 sends release+press pairs while held
        self.key("1")
        self.settle()
        self.assertEqual(GPIO.input(27), 0)
        self.key("1", down=False)
        self.settle()
        self.assertEqual(GPIO.input(27), 1)

    def test_key_triggers_pir(self):
        self.key("2")
        self.assertEqual(GPIO.input(4), 1)
        self.key("2", down=False)
        self.settle()
        core.pir_cancel(self.pir)

    def test_unassigned_key_is_ignored(self):
        self.key("7")
        self.assertEqual(self.app._keys_held, {})


if __name__ == "__main__":
    unittest.main()
