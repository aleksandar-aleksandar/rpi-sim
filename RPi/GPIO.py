"""
Simulated RPi.GPIO - same API as on a real Raspberry Pi:

    import RPi.GPIO as GPIO

Importing it opens the simulator window (Pi header + breadboard). Input
levels are computed from the circuit you wire up, so a wiring mistake behaves
the way it would in real life.

Set RPISIM_HEADLESS=1 to run without a window (e.g. in tests).
"""
import atexit
import random
import time

from . import _core as core
from ._core import (BCM, BOARD, OUT, IN, LOW, HIGH, PUD_OFF, PUD_DOWN, PUD_UP,  # noqa: F401
                    RISING, FALLING, BOTH)

VERSION = "0.7.1-rpi-sim"
RPI_INFO = {"TYPE": "Pi 4 Model B (simulated)", "P1_REVISION": 3, "RAM": "4G"}
RPI_REVISION = 3

_PULL_TXT = {PUD_UP: "PUD_UP", PUD_DOWN: "PUD_DOWN", PUD_OFF: ""}
_EDGE_TXT = {RISING: "RISING", FALLING: "FALLING", BOTH: "BOTH"}


def _bcm(channel):
    if core.MODE[0] is None:
        raise RuntimeError(
            "Please set pin numbering mode using GPIO.setmode(GPIO.BOARD) or GPIO.setmode(GPIO.BCM)")
    if core.MODE[0] == BOARD:
        if channel not in core.GPIO_OF_PHYS:
            raise ValueError("The channel sent is invalid on a Raspberry Pi")
        return core.GPIO_OF_PHYS[channel]
    if not isinstance(channel, int) or not (0 <= channel <= 27):
        raise ValueError("The channel sent is invalid on a Raspberry Pi")
    return channel


def _name(b):
    return f"GPIO{b} (pin {core.BCM_TO_PHYS[b]})"


def setwarnings(flag):
    pass


def setmode(mode):
    if mode not in (BCM, BOARD):
        raise ValueError("An invalid mode was passed to setmode()")
    if core.MODE[0] is not None and core.MODE[0] != mode:
        raise ValueError("A different mode has already been set!")
    core.MODE[0] = mode
    core.log(f"setmode({'BCM' if mode == BCM else 'BOARD'})")


def getmode():
    return core.MODE[0]


def setup(channel, direction, pull_up_down=PUD_OFF, initial=None):
    if isinstance(channel, (list, tuple)):
        for c in channel:
            setup(c, direction, pull_up_down, initial)
        return
    b = _bcm(channel)
    if direction not in (IN, OUT):
        raise ValueError("An invalid direction was passed to setup()")
    if direction == OUT and pull_up_down != PUD_OFF:
        raise ValueError("pull_up_down parameter is not valid for outputs")
    with core.LOCK:
        old = core.PINS.get(b)
        if old and old["pwm"] is not None:
            old["pwm"].running = False
        if direction == OUT:
            core.PINS[b] = core.new_pin(OUT, level=HIGH if initial else LOW)
        else:
            core.PINS[b] = core.new_pin(IN, pull=pull_up_down)
    core.log(f"setup {_name(b)} as {'OUT' if direction == OUT else 'IN'} {_PULL_TXT.get(pull_up_down, '')}")
    core.update_inputs()


def output(channel, value):
    if isinstance(channel, (list, tuple)):
        vals = value if isinstance(value, (list, tuple)) else [value] * len(channel)
        if len(vals) != len(channel):
            raise RuntimeError("Number of channels != number of values")
        for c, v in zip(channel, vals):
            output(c, v)
        return
    b = _bcm(channel)
    with core.LOCK:
        st = core.PINS.get(b)
        if st is None or st["dir"] != OUT:
            raise RuntimeError("The GPIO channel has not been set up as an OUTPUT")
        new = HIGH if value else LOW
        if new == st["level"]:
            return
        st["level"] = new
        st["trans"].append(time.time())
        if not core.wave(st):
            core.log(f"{_name(b)} -> {'HIGH' if new else 'LOW'}")
    core.update_inputs()


def input(channel):  # noqa: A001 - same name as in RPi.GPIO
    b = _bcm(channel)
    with core.LOCK:
        st = core.PINS.get(b)
        if st is None:
            raise RuntimeError("You must setup() the GPIO channel first")
        sonar = core.ECHO_PINS.get(b) if st["dir"] == IN else None
        if sonar is not None:            # time-critical: read the echo pulse directly
            return HIGH if core.echo_high(sonar) else LOW
        if st["dir"] == IN and st["floating"]:
            return random.randint(0, 1)
        return HIGH if st["level"] else LOW


def add_event_detect(channel, edge, callback=None, bouncetime=None):
    b = _bcm(channel)
    with core.LOCK:
        st = core.PINS.get(b)
        if st is None or st["dir"] != IN:
            raise RuntimeError("You must setup() the GPIO channel as an input first")
        if edge not in (RISING, FALLING, BOTH):
            raise ValueError("The edge must be set to RISING, FALLING or BOTH")
        if st["edge"] is not None:
            raise RuntimeError("Conflicting edge detection already enabled for this GPIO channel")
        if bouncetime is not None and bouncetime <= 0:
            raise ValueError("Bouncetime must be greater than 0")
        st["edge"] = edge
        st["bounce"] = (bouncetime or 0) / 1000.0
        st["cbs"] = [callback] if callback else []
        st["flag"] = False
    core.log(f"add_event_detect {_name(b)} {_EDGE_TXT[edge]}")


def add_event_callback(channel, callback):
    b = _bcm(channel)
    with core.LOCK:
        st = core.PINS.get(b)
        if st is None or st["edge"] is None:
            raise RuntimeError("Add event detection using add_event_detect first before adding a callback")
        st["cbs"].append(callback)


def remove_event_detect(channel):
    b = _bcm(channel)
    with core.LOCK:
        st = core.PINS.get(b)
        if st:
            st["edge"] = None
            st["cbs"] = []
            st["flag"] = False


def event_detected(channel):
    b = _bcm(channel)
    with core.LOCK:
        st = core.PINS.get(b)
        if st and st["flag"]:
            st["flag"] = False
            return True
    return False


def wait_for_edge(channel, edge, bouncetime=None, timeout=None):
    """Block until an edge occurs. timeout is in ms. Returns channel, or None on timeout."""
    b = _bcm(channel)
    if edge not in (RISING, FALLING, BOTH):
        raise ValueError("The edge must be set to RISING, FALLING or BOTH")
    with core.LOCK:
        st = core.PINS.get(b)
        if st is None or st["dir"] != IN:
            raise RuntimeError("You must setup() the GPIO channel as an input first")
        if st["edge"] is not None:
            raise RuntimeError("Conflicting edge detection events already exist for this GPIO channel")
        r0, f0 = st["n_rise"], st["n_fall"]
        st["waiters"] = st.get("waiters", 0) + 1
    deadline = None if timeout is None else time.time() + timeout / 1000.0
    try:
        while True:
            with core.LOCK:
                st = core.PINS.get(b)
                if st is None:
                    return None
                rose, fell = st["n_rise"] > r0, st["n_fall"] > f0
            if (edge in (RISING, BOTH) and rose) or (edge in (FALLING, BOTH) and fell):
                return channel
            if deadline is not None and time.time() >= deadline:
                return None
            time.sleep(0.001)
    finally:
        with core.LOCK:
            st = core.PINS.get(b)
            if st is not None:
                st["waiters"] = max(0, st.get("waiters", 1) - 1)


def gpio_function(channel):
    b = _bcm(channel)
    st = core.PINS.get(b)
    return st["dir"] if st else IN


def cleanup(channel=None):
    with core.LOCK:
        if channel is None:
            targets = list(core.PINS)
        else:
            chs = channel if isinstance(channel, (list, tuple)) else [channel]
            targets = [_bcm(c) for c in chs]
        for b in targets:
            st = core.PINS.pop(b, None)
            if st and st["pwm"] is not None:
                st["pwm"].running = False
    core.log("cleanup()" if channel is None else f"cleanup({channel})")
    core.update_inputs()


class PWM:
    def __init__(self, channel, frequency):
        b = _bcm(channel)
        with core.LOCK:
            st = core.PINS.get(b)
            if st is None or st["dir"] != OUT:
                raise RuntimeError("You must setup() the GPIO channel as an output first")
            if st["pwm"] is not None:
                raise RuntimeError("A PWM object already exists for this GPIO channel")
            if frequency <= 0.0:
                raise ValueError("frequency must be greater than 0.0")
            st["pwm"] = self
        self._b = b
        self.freq = float(frequency)
        self.duty = 0.0
        self.running = False

    def _changed(self, msg=None):
        if msg:
            core.log(f"PWM {_name(self._b)}: {msg}")
        core.update_inputs()

    def start(self, dutycycle):
        if not 0.0 <= dutycycle <= 100.0:
            raise ValueError("dutycycle must have a value from 0.0 to 100.0")
        self.duty = float(dutycycle)
        self.running = True
        self._changed(f"start f={self.freq:g}Hz duty={self.duty:g}%")

    def ChangeDutyCycle(self, dutycycle):  # noqa: N802 - RPi.GPIO naming
        if not 0.0 <= dutycycle <= 100.0:
            raise ValueError("dutycycle must have a value from 0.0 to 100.0")
        self.duty = float(dutycycle)
        self._changed()

    def ChangeFrequency(self, frequency):  # noqa: N802 - RPi.GPIO naming
        if frequency <= 0.0:
            raise ValueError("frequency must be greater than 0.0")
        self.freq = float(frequency)
        self._changed()

    def stop(self):
        self.running = False
        self._changed("stop")

    def __del__(self):
        try:
            st = core.PINS.get(self._b)
            if st and st["pwm"] is self:
                st["pwm"] = None
        except Exception:
            pass


# The window opens on import and stays open after the script finishes.
core.ensure_ui()


@atexit.register
def _keep_window():
    if core.ui_alive():
        core.log("Script finished. Close the window to exit.")
        print("[rpi-sim] Script finished - close the simulator window to exit.")
        try:
            while core.ui_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
