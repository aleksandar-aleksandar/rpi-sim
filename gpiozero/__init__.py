"""
Simulated subset of gpiozero, built on the simulated RPi.GPIO so the circuit
model still applies (a mis-wired LED stays dark here too).

Supported: LED, PWMLED, RGBLED, Buzzer, TonalBuzzer, OutputDevice,
PWMOutputDevice, DigitalOutputDevice, InputDevice, DigitalInputDevice,
Button, MotionSensor, Servo, AngularServo, DistanceSensor, pause().
Pins are BCM numbers (17) or strings ("GPIO17", "BCM17", "BOARD11").
"""
import inspect
import threading
import time

import RPi.GPIO as GPIO
from RPi import _core as _sim

from .tones import Tone

__all__ = ["LED", "PWMLED", "RGBLED", "Buzzer", "TonalBuzzer", "OutputDevice",
           "DigitalOutputDevice", "PWMOutputDevice", "InputDevice", "DigitalInputDevice",
           "Button", "MotionSensor", "Servo", "AngularServo", "DistanceSensor",
           "Device", "GPIOZeroError", "BadPinFactory", "pause", "Tone"]


class GPIOZeroError(Exception):
    pass


class BadPinFactory(GPIOZeroError):
    pass


class GPIOPinInUse(GPIOZeroError):
    pass


_USED = set()


def _bcm(pin):
    """gpiozero pin spec -> BCM number."""
    if isinstance(pin, int):
        return pin
    s = str(pin).strip().upper()
    for prefix in ("GPIO", "BCM"):
        if s.startswith(prefix) and s[len(prefix):].isdigit():
            return int(s[len(prefix):])
    if s.startswith("BOARD") and s[5:].isdigit():
        phys = int(s[5:])
        if phys not in _sim.GPIO_OF_PHYS:
            raise GPIOZeroError(f"BOARD{phys} is not a GPIO pin")
        return _sim.GPIO_OF_PHYS[phys]
    if s.isdigit():
        return int(s)
    raise GPIOZeroError(f"invalid pin {pin!r}")


def _channel(bcm):
    """BCM number -> channel in whatever numbering mode RPi.GPIO is using."""
    if GPIO.getmode() is None:
        GPIO.setmode(GPIO.BCM)
    return _sim.BCM_TO_PHYS[bcm] if GPIO.getmode() == GPIO.BOARD else bcm


def _call(fn, device):
    if fn is None:
        return
    try:
        nparams = len(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        nparams = 0
    fn(device) if nparams else fn()


class Device:
    def __init__(self, *pins):
        self._pins = [_bcm(p) for p in pins]
        for b in self._pins:
            if b in _USED:
                raise GPIOPinInUse(f"pin GPIO{b} is already in use")
        _USED.update(self._pins)
        self._closed = False

    @property
    def closed(self):
        return self._closed

    def close(self):
        if self._closed:
            return
        self._closed = True
        for b in self._pins:
            _USED.discard(b)
            try:
                GPIO.cleanup(_channel(b))
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self):
        pins = ", ".join(f"GPIO{b}" for b in self._pins)
        return f"<gpiozero.{type(self).__name__} on {pins}{' closed' if self._closed else ''}>"


class _Background:
    """A cancellable background loop (blink, beep, pulse)."""

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()

    def start(self, target, background):
        self.stop()
        self._stop = threading.Event()
        if background:
            self._thread = threading.Thread(target=target, args=(self._stop,), daemon=True)
            self._thread.start()
        else:
            target(self._stop)

    def stop(self):
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(1)
        self._thread = None


# ---------------------------------------------------------------- outputs
class OutputDevice(Device):
    def __init__(self, pin, active_high=True, initial_value=False):
        super().__init__(pin)
        self.active_high = active_high
        self._ch = _channel(self._pins[0])
        self._bg = _Background()
        GPIO.setup(self._ch, GPIO.OUT)
        self._state = None
        self._write(bool(initial_value))

    def _write(self, active):
        self._state = bool(active)
        GPIO.output(self._ch, self._state == self.active_high)

    def on(self):
        self._bg.stop()
        self._write(True)

    def off(self):
        self._bg.stop()
        self._write(False)

    def toggle(self):
        self._bg.stop()
        self._write(not self._state)

    @property
    def value(self):
        return int(self._state)

    @value.setter
    def value(self, v):
        self.on() if v else self.off()

    @property
    def is_active(self):
        return bool(self._state)

    is_lit = is_active

    def blink(self, on_time=1, off_time=1, n=None, background=True):
        def run(stop):
            i = 0
            while n is None or i < n:
                self._write(True)
                if stop.wait(on_time):
                    return
                self._write(False)
                if stop.wait(off_time):
                    return
                i += 1
        self._bg.start(run, background)

    def close(self):
        self._bg.stop()
        super().close()


DigitalOutputDevice = OutputDevice


class LED(OutputDevice):
    pass


class Buzzer(OutputDevice):
    def beep(self, on_time=1, off_time=1, n=None, background=True):
        self.blink(on_time, off_time, n, background)


class PWMOutputDevice(Device):
    def __init__(self, pin, active_high=True, initial_value=0, frequency=100):
        super().__init__(pin)
        self.active_high = active_high
        self._ch = _channel(self._pins[0])
        self._bg = _Background()
        GPIO.setup(self._ch, GPIO.OUT)
        self._pwm = GPIO.PWM(self._ch, frequency)
        self._pwm.start(0 if active_high else 100)
        self._value = 0.0
        self._write(initial_value)

    def _write(self, v):
        v = float(v)
        if not 0.0 <= v <= 1.0:
            raise ValueError("PWM value must be between 0 and 1")
        self._value = v
        duty = v * 100 if self.active_high else (1 - v) * 100
        self._pwm.ChangeDutyCycle(duty)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._bg.stop()
        self._write(v)

    @property
    def frequency(self):
        return self._pwm.freq

    @frequency.setter
    def frequency(self, hz):
        self._pwm.ChangeFrequency(hz)

    @property
    def is_active(self):
        return self._value > 0

    is_lit = is_active

    def on(self):
        self.value = 1

    def off(self):
        self.value = 0

    def toggle(self):
        self.value = 1 - self._value

    def blink(self, on_time=1, off_time=1, fade_in_time=0, fade_out_time=0, n=None, background=True):
        def ramp(stop, a, b, duration):
            steps = max(1, int(duration * 25))
            for i in range(1, steps + 1):
                self._write(a + (b - a) * i / steps)
                if stop.wait(duration / steps):
                    return True
            return False

        def run(stop):
            i = 0
            while n is None or i < n:
                if fade_in_time and ramp(stop, 0, 1, fade_in_time):
                    return
                self._write(1)
                if stop.wait(on_time):
                    return
                if fade_out_time and ramp(stop, 1, 0, fade_out_time):
                    return
                self._write(0)
                if stop.wait(off_time):
                    return
                i += 1
        self._bg.start(run, background)

    def pulse(self, fade_in_time=1, fade_out_time=1, n=None, background=True):
        self.blink(0, 0, fade_in_time, fade_out_time, n, background)

    def close(self):
        self._bg.stop()
        if not self._closed:
            self._pwm.stop()
        super().close()


class PWMLED(PWMOutputDevice):
    pass


class RGBLED(Device):
    def __init__(self, red, green, blue, active_high=True, initial_value=(0, 0, 0), pwm=True):
        super().__init__(red, green, blue)
        cls = PWMLED if pwm else LED
        _USED.difference_update(self._pins)            # the child LEDs claim the pins
        self._leds = tuple(cls(p, active_high=active_high) for p in self._pins)
        self._pwm = pwm
        self.color = initial_value

    @property
    def value(self):
        return tuple(led.value for led in self._leds)

    @value.setter
    def value(self, rgb):
        for led, v in zip(self._leds, rgb):
            led.value = v

    color = value

    @property
    def red(self):
        return self._leds[0].value

    @red.setter
    def red(self, v):
        self._leds[0].value = v

    @property
    def green(self):
        return self._leds[1].value

    @green.setter
    def green(self, v):
        self._leds[1].value = v

    @property
    def blue(self):
        return self._leds[2].value

    @blue.setter
    def blue(self, v):
        self._leds[2].value = v

    @property
    def is_active(self):
        return any(self.value)

    is_lit = is_active

    def on(self):
        self.value = (1, 1, 1)

    def off(self):
        self.value = (0, 0, 0)

    def toggle(self):
        self.value = tuple(1 - v for v in self.value)

    def close(self):
        for led in self._leds:
            led.close()
        self._closed = True


class TonalBuzzer(Device):
    def __init__(self, pin, initial_value=None, mid_tone=Tone("A4"), octaves=1):
        super().__init__(pin)
        self._ch = _channel(self._pins[0])
        GPIO.setup(self._ch, GPIO.OUT)
        self._pwm = GPIO.PWM(self._ch, float(mid_tone))
        self.mid_tone = Tone(mid_tone)
        self.octaves = octaves
        self._tone = None
        if initial_value is not None:
            self.value = initial_value

    @property
    def min_tone(self):
        return Tone(frequency=self.mid_tone / 2 ** self.octaves)

    @property
    def max_tone(self):
        return Tone(frequency=self.mid_tone * 2 ** self.octaves)

    def play(self, tone):
        tone = Tone(tone)
        if not self.min_tone * 0.999 <= tone <= self.max_tone * 1.001:
            raise ValueError(f"tone {tone!r} is outside the range {self.min_tone!r} – {self.max_tone!r}")
        self._tone = tone
        self._pwm.ChangeFrequency(float(tone))
        self._pwm.start(50)

    def stop(self):
        self._tone = None
        self._pwm.stop()

    @property
    def tone(self):
        return self._tone

    @property
    def is_active(self):
        return self._tone is not None

    @property
    def value(self):
        """-1 (min_tone) .. 0 (mid_tone) .. 1 (max_tone), None when silent."""
        if self._tone is None:
            return None
        import math
        return math.log2(self._tone / self.mid_tone) / self.octaves

    @value.setter
    def value(self, v):
        if v is None:
            self.stop()
        else:
            self.play(Tone(frequency=self.mid_tone * 2 ** (v * self.octaves)))

    def close(self):
        if not self._closed:
            self._pwm.stop()
        super().close()


# ---------------------------------------------------------------- inputs
class InputDevice(Device):
    def __init__(self, pin, pull_up=False, active_state=None, bounce_time=None):
        super().__init__(pin)
        self._ch = _channel(self._pins[0])
        if pull_up is None:
            if active_state is None:
                raise GPIOZeroError("active_state must be set when pull_up is None")
            pud = GPIO.PUD_OFF
            self._active_level = 1 if active_state else 0
        else:
            pud = GPIO.PUD_UP if pull_up else GPIO.PUD_DOWN
            self._active_level = 0 if pull_up else 1
        self.pull_up = pull_up
        GPIO.setup(self._ch, GPIO.IN, pull_up_down=pud)
        self.when_activated = None
        self.when_deactivated = None
        self._last_active = None
        kw = {"bouncetime": int(bounce_time * 1000)} if bounce_time else {}
        GPIO.add_event_detect(self._ch, GPIO.BOTH, callback=self._edge, **kw)
        self._last_active = self.is_active

    @property
    def value(self):
        return int(GPIO.input(self._ch) == self._active_level)

    @property
    def is_active(self):
        return bool(self.value)

    def _edge(self, channel):
        if self._closed:                # a queued edge may arrive after close()
            return
        try:
            active = self.is_active
        except RuntimeError:
            return
        if active == self._last_active:
            return
        self._last_active = active
        self._on_change(active)

    def _on_change(self, active):
        _call(self.when_activated if active else self.when_deactivated, self)

    def wait_for_active(self, timeout=None):
        return self._wait(True, timeout)

    def wait_for_inactive(self, timeout=None):
        return self._wait(False, timeout)

    def _wait(self, state, timeout):
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.is_active != state:
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        return True


DigitalInputDevice = InputDevice


class Button(InputDevice):
    def __init__(self, pin, pull_up=True, active_state=None, bounce_time=None,
                 hold_time=1, hold_repeat=False):
        self.hold_time = hold_time
        self.hold_repeat = hold_repeat
        self.when_held = None
        self._hold_timer = None
        self._held_since = None
        super().__init__(pin, pull_up, active_state, bounce_time)

    is_pressed = InputDevice.is_active

    @property
    def is_held(self):
        return self._held_since is not None

    @property
    def held_time(self):
        return None if self._held_since is None else time.monotonic() - self._held_since

    def _on_change(self, active):
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        self._held_since = None
        if active:
            self._schedule_hold(self.hold_time)
        super()._on_change(active)

    def _schedule_hold(self, delay):
        t = threading.Timer(delay, self._hold_fired)
        t.daemon = True
        self._hold_timer = t
        t.start()

    def _hold_fired(self):
        if not self.is_pressed:
            return
        if self._held_since is None:
            self._held_since = time.monotonic() - self.hold_time
        _call(self.when_held, self)
        if self.hold_repeat and self.is_pressed:
            self._schedule_hold(self.hold_time)

    when_pressed = property(lambda s: s.when_activated, lambda s, f: setattr(s, "when_activated", f))
    when_released = property(lambda s: s.when_deactivated, lambda s, f: setattr(s, "when_deactivated", f))

    def wait_for_press(self, timeout=None):
        return self.wait_for_active(timeout)

    def wait_for_release(self, timeout=None):
        return self.wait_for_inactive(timeout)


class MotionSensor(InputDevice):
    def __init__(self, pin, pull_up=False, active_state=None, queue_len=1, sample_rate=10,
                 threshold=0.5, partial=False):
        super().__init__(pin, pull_up, active_state)

    motion_detected = InputDevice.is_active
    when_motion = property(lambda s: s.when_activated, lambda s, f: setattr(s, "when_activated", f))
    when_no_motion = property(lambda s: s.when_deactivated, lambda s, f: setattr(s, "when_deactivated", f))

    def wait_for_motion(self, timeout=None):
        return self.wait_for_active(timeout)

    def wait_for_no_motion(self, timeout=None):
        return self.wait_for_inactive(timeout)


# ---------------------------------------------------------------- servos
class Servo(Device):
    """value -1 (min pulse) .. 0 (mid) .. 1 (max pulse); None = detached."""

    def __init__(self, pin, initial_value=0.0, min_pulse_width=1 / 1000,
                 max_pulse_width=2 / 1000, frame_width=20 / 1000):
        super().__init__(pin)
        self.min_pulse_width = min_pulse_width
        self.max_pulse_width = max_pulse_width
        self.frame_width = frame_width
        self._ch = _channel(self._pins[0])
        GPIO.setup(self._ch, GPIO.OUT)
        self._pwm = GPIO.PWM(self._ch, 1 / frame_width)
        self._value = None
        self.value = initial_value

    @property
    def pulse_width(self):
        if self._value is None:
            return None
        return self.min_pulse_width + (self._value + 1) / 2 * (self.max_pulse_width - self.min_pulse_width)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        if v is None:
            self.detach()
            return
        if not -1 <= v <= 1:
            raise ValueError("Servo value must be between -1 and 1, or None")
        start = self._value is None
        self._value = float(v)
        duty = self.pulse_width / self.frame_width * 100
        self._pwm.start(duty) if start else self._pwm.ChangeDutyCycle(duty)

    def min(self):
        self.value = -1

    def mid(self):
        self.value = 0

    def max(self):
        self.value = 1

    def detach(self):
        self._value = None
        self._pwm.stop()

    @property
    def is_active(self):
        return self._value is not None

    def close(self):
        if not self._closed:
            self._pwm.stop()
        super().close()


class AngularServo(Servo):
    def __init__(self, pin, initial_angle=0.0, min_angle=-90, max_angle=90,
                 min_pulse_width=1 / 1000, max_pulse_width=2 / 1000, frame_width=20 / 1000):
        self.min_angle, self.max_angle = min_angle, max_angle
        super().__init__(pin, None, min_pulse_width, max_pulse_width, frame_width)
        if initial_angle is not None:
            self.angle = initial_angle

    @property
    def angle(self):
        v = self.value
        if v is None:
            return None
        return self.min_angle + (v + 1) / 2 * (self.max_angle - self.min_angle)

    @angle.setter
    def angle(self, a):
        if a is None:
            self.detach()
            return
        lo, hi = sorted((self.min_angle, self.max_angle))
        if not lo <= a <= hi:
            raise ValueError(f"angle must be between {lo} and {hi}")
        self.value = (a - self.min_angle) / (self.max_angle - self.min_angle) * 2 - 1


# ---------------------------------------------------------------- distance
class DistanceSensor(Device):
    """HC-SR04. distance in metres (capped at max_distance); value = distance / max_distance."""

    SPEED_OF_SOUND = 343.26  # m/s

    def __init__(self, echo=None, trigger=None, queue_len=9, max_distance=1, threshold_distance=0.3,
                 partial=False):
        if echo is None or trigger is None:
            raise GPIOZeroError("you must specify echo and trigger pins")
        super().__init__(echo, trigger)
        self.max_distance = max_distance
        self.threshold_distance = threshold_distance
        self._echo = _channel(self._pins[0])
        self._trig = _channel(self._pins[1])
        GPIO.setup(self._trig, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self._echo, GPIO.IN)
        self.when_in_range = None
        self.when_out_of_range = None
        self._watcher = None
        self._in_range = None

    def _measure(self):
        clock = time.perf_counter
        GPIO.output(self._trig, GPIO.HIGH)
        time.sleep(0.00001)
        GPIO.output(self._trig, GPIO.LOW)
        timeout = 2 * self.max_distance / self.SPEED_OF_SOUND + 0.01
        deadline = clock() + timeout
        start = clock()
        while GPIO.input(self._echo) == 0:
            start = clock()
            if start > deadline:
                return self.max_distance
        end = start
        while GPIO.input(self._echo) == 1:
            end = clock()
            if end > deadline:
                return self.max_distance
        return min(self.max_distance, (end - start) * self.SPEED_OF_SOUND / 2)

    @property
    def distance(self):
        return self._measure()

    @property
    def value(self):
        return self.distance / self.max_distance

    @property
    def in_range(self):
        return self.distance < self.threshold_distance

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in ("when_in_range", "when_out_of_range") and value is not None:
            self._start_watcher()

    def _start_watcher(self):
        if getattr(self, "_watcher", None) is not None:
            return

        def watch():
            while not self._closed:
                now = self.in_range
                if now != self._in_range:
                    prev, self._in_range = self._in_range, now
                    if prev is not None:
                        _call(self.when_in_range if now else self.when_out_of_range, self)
                time.sleep(0.06)
        self._watcher = threading.Thread(target=watch, daemon=True)
        self._watcher.start()


def pause():
    """Sleep forever (until Ctrl+C) - like signal.pause(), which Windows lacks."""
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        raise
