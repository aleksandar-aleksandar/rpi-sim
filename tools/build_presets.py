"""
Regenerate the preset circuits in examples/*.json.

Each preset is described below with a few helper calls, so wiring stays
readable and consistent across examples. Run:

    python tools/build_presets.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "examples")

RED, BLACK, BLUE, GREEN, YELLOW, ORANGE = ("#d42020", "#1c1c1c", "#2a6bd6",
                                           "#17a03a", "#e8c400", "#f07a00")
PREFIX = {"sonar": "US", "servo": "SERVO", "led": "LED", "rgb": "RGB", "res": "R", "btn": "SW", "abuz": "BZ", "pbuz": "BZ", "pir": "PIR"}


class Circuit:
    def __init__(self):
        self.objects = {}
        self.counts = {}

    def _add(self, obj):
        oid = f"o{len(self.objects) + 1}"
        if obj["type"] != "wire":
            pref = PREFIX[obj["type"]]
            self.counts[pref] = self.counts.get(pref, 0) + 1
            obj["name"] = f"{pref}{self.counts[pref]}"
        self.objects[oid] = obj
        return oid

    def wire(self, a, b, color):
        return self._add({"type": "wire", "a": a, "b": b, "color": color})

    def part(self, kind, leg1, leg2, **extra):
        return self._add({"type": kind, "legs": [leg1, leg2], **extra})

    def pir(self, x, y):
        return self._add({"type": "pir", "x": x, "y": y})

    # --- building blocks -------------------------------------------------
    def ground(self):
        """Single common ground: Pi GND (pin 6) -> top GND rail."""
        self.wire("pi:6", "bb:T-:1", BLACK)

    def led(self, phys_pin, col, color="red", wire_color=GREEN):
        """GPIO -> LED anode (col), cathode (col+1) -> 220 ohm -> GND rail."""
        self.part("led", f"bb:a:{col}", f"bb:a:{col + 1}", color=color)
        self.wire(f"pi:{phys_pin}", f"bb:b:{col}", wire_color)
        self.part("res", f"bb:b:{col + 1}", f"bb:T-:{col + 1}", ohms=220)

    def button(self, phys_pin, col):
        """GPIO -> button (col .. col+2) -> GND rail."""
        self.part("btn", f"bb:a:{col}", f"bb:a:{col + 2}")
        self.wire(f"pi:{phys_pin}", f"bb:b:{col}", BLUE)
        self.wire(f"bb:b:{col + 2}", f"bb:T-:{col + 2}", BLACK)

    def buzzer(self, kind, phys_pin, col):
        """GPIO -> buzzer (+) at col, (-) at col+2 -> GND rail."""
        self.part(kind, f"bb:a:{col}", f"bb:a:{col + 2}")
        self.wire(f"pi:{phys_pin}", f"bb:b:{col}", YELLOW)
        self.wire(f"bb:b:{col + 2}", f"bb:T-:{col + 2}", BLACK)

    def rgb_led(self, r_pin, g_pin, b_pin, col):
        """Common-cathode RGB LED in a{col}..a{col+3} (R, K, G, B).
        Each colour: GPIO -> g{x} | 220 ohm f{x}..c{x} across the gap | leg. K -> GND rail."""
        self.part_n("rgb", [f"bb:a:{col + i}" for i in range(4)])
        for x, pin, color in ((col, r_pin, RED), (col + 2, g_pin, GREEN), (col + 3, b_pin, BLUE)):
            self.part("res", f"bb:c:{x}", f"bb:f:{x}", ohms=220)
            self.wire(f"pi:{pin}", f"bb:g:{x}", color)
        self.wire(f"bb:b:{col + 1}", f"bb:T-:{col + 1}", BLACK)

    def part_n(self, kind, legs, **extra):
        return self._add({"type": kind, "legs": list(legs), **extra})

    def pir_module(self, out_phys_pin, x=620, y=520):
        """PIR: VCC -> 5V (pin 2), GND -> GND rail, OUT -> GPIO."""
        oid = self.pir(x, y)
        self.wire(f"m:{oid}:VCC", "pi:2", RED)
        self.wire(f"m:{oid}:GND", "bb:T-:9", BLACK)
        self.wire(f"m:{oid}:OUT", f"pi:{out_phys_pin}", ORANGE)

    def servo_module(self, sig_phys_pin, x=760, y=520):
        """Servo: VCC -> 5V (pin 4), GND -> GND rail, SIG -> GPIO."""
        oid = self._add({"type": "servo", "x": x, "y": y})
        self.wire(f"m:{oid}:VCC", "pi:4", RED)
        self.wire(f"m:{oid}:GND", "bb:T-:20", BLACK)
        self.wire(f"m:{oid}:SIG", f"pi:{sig_phys_pin}", ORANGE)

    def sonar_module(self, trig_phys_pin, echo_phys_pin, x=640, y=520, cm=50):
        """HC-SR04: VCC -> 5V (pin 2), GND -> GND rail, TRIG/ECHO -> GPIOs."""
        oid = self._add({"type": "sonar", "x": x, "y": y, "cm": cm})
        self.wire(f"m:{oid}:VCC", "pi:2", RED)
        self.wire(f"m:{oid}:GND", "bb:T-:24", BLACK)
        self.wire(f"m:{oid}:TRIG", f"pi:{trig_phys_pin}", YELLOW)
        self.wire(f"m:{oid}:ECHO", f"pi:{echo_phys_pin}", GREEN)

    def save(self, name):
        path = os.path.join(OUT_DIR, f"{name}.json")
        data = {"format": "rpi-sim-1", "next": len(self.objects) + 1, "objects": self.objects}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
        print("wrote", os.path.relpath(path, ROOT))


def build():
    # Physical pins used: 11 = GPIO17, 12 = GPIO18, 13 = GPIO27,
    #                     15 = GPIO22, 16 = GPIO23, 7 = GPIO4

    c = Circuit(); c.ground(); c.led(11, 10)
    c.save("01_blink")

    for name in ("02_button_led", "03_button_callback"):
        c = Circuit(); c.ground(); c.led(11, 10); c.button(13, 20)
        c.save(name)

    c = Circuit(); c.ground(); c.led(12, 10, color="yellow")
    c.save("04_pwm_fade")

    c = Circuit(); c.ground(); c.buzzer("abuz", 15, 25)
    c.save("05_active_buzzer")

    c = Circuit(); c.ground(); c.buzzer("pbuz", 15, 25)
    c.save("06_passive_buzzer")

    c = Circuit(); c.ground(); c.led(11, 10); c.pir_module(7)
    c.save("07_pir_motion")

    c = Circuit(); c.ground(); c.led(11, 10); c.button(13, 20); c.buzzer("pbuz", 15, 25)
    c.save("08_reaction_game")

    c = Circuit(); c.ground(); c.led(11, 10); c.buzzer("abuz", 15, 25); c.pir_module(7)
    c.save("09_motion_alarm")

    # 10: deliberate mistakes
    c = Circuit(); c.ground()
    c.part("led", "bb:a:5", "bb:a:6", color="red")          # LED1: no resistor
    c.wire("pi:11", "bb:b:5", GREEN)
    c.wire("bb:b:6", "bb:T-:6", BLACK)
    c.part("led", "bb:a:12", "bb:c:12", color="green")      # LED2: same column
    c.wire("pi:15", "bb:e:12", GREEN)
    c.part("led", "bb:a:18", "bb:a:19", color="blue")       # LED3: reversed
    c.wire("pi:16", "bb:b:19", GREEN)
    c.part("res", "bb:b:18", "bb:T-:18", ohms=220)
    c.save("10_common_mistakes")

    c = Circuit(); c.ground(); c.rgb_led(11, 13, 15, 12)   # R=GPIO17, G=GPIO27, B=GPIO22
    c.save("11_rgb_led")

    c = Circuit(); c.ground(); c.servo_module(12)          # SIG = GPIO18
    c.save("12_servo")

    c = Circuit(); c.ground(); c.sonar_module(16, 18)      # TRIG = GPIO23, ECHO = GPIO24
    c.save("13_ultrasonic")


if __name__ == "__main__":
    build()
