"""
Simulator core: the electrical model of the circuit (Pi header, breadboard,
components, wires) plus the GPIO state driven by the user's script.

Model
-----
* Points:   pi:<physical pin>, bb:<row>:<column>, m:<object id>:<terminal>
* Net:      a set of points that are conductively connected (breadboard
            column strip, power rail, wire, pressed button, the Pi's
            internally connected GND / 3V3 / 5V pins).
* Sources:  3V3, 5V, GND, GPIO outputs, PIR OUT.
* Resistors connect two nets without shorting them; LEDs and buzzers are
  two-terminal devices that react to the voltage difference across them.
"""
import json
import os
import queue
import random
import sys
import threading
import time
import traceback
from collections import defaultdict, deque

LOCK = threading.RLock()
T0 = time.time()
LOG_Q = queue.Queue()


def log(msg):
    LOG_Q.put(f"[{time.time() - T0:7.2f}s] {msg}")


# ---------------- RPi.GPIO constants ----------------
BCM, BOARD = 11, 10
OUT, IN = 0, 1
LOW, HIGH = 0, 1
PUD_OFF, PUD_DOWN, PUD_UP = 20, 21, 22
RISING, FALLING, BOTH = 31, 32, 33

# ---------------- Raspberry Pi header ----------------
GPIO_OF_PHYS = {
    3: 2, 5: 3, 7: 4, 8: 14, 10: 15, 11: 17, 12: 18, 13: 27, 15: 22, 16: 23,
    18: 24, 19: 10, 21: 9, 22: 25, 23: 11, 24: 8, 26: 7, 27: 0, 28: 1, 29: 5,
    31: 6, 32: 12, 33: 13, 35: 19, 36: 16, 37: 26, 38: 20, 40: 21,
}
BCM_TO_PHYS = {b: p for p, b in GPIO_OF_PHYS.items()}
_SPECIAL = {2: "SDA", 3: "SCL", 4: "GPCLK0", 14: "TXD", 15: "RXD", 18: "PCM_CLK",
            10: "MOSI", 9: "MISO", 11: "SCLK", 8: "CE0", 7: "CE1", 0: "ID_SD",
            1: "ID_SC", 12: "PWM0", 13: "PWM1", 19: "PCM_FS", 20: "PCM_DIN", 21: "PCM_DOUT"}
PI_PINS = {}
for _p in range(1, 41):
    if _p in (1, 17):
        PI_PINS[_p] = ("3V3", None)
    elif _p in (2, 4):
        PI_PINS[_p] = ("5V", None)
    elif _p in (6, 9, 14, 20, 25, 30, 34, 39):
        PI_PINS[_p] = ("GND", None)
    else:
        PI_PINS[_p] = ("GPIO", GPIO_OF_PHYS[_p])


def pin_label(p):
    kind, b = PI_PINS[p]
    if kind != "GPIO":
        return {"3V3": "3V3 power", "5V": "5V power", "GND": "Ground"}[kind]
    s = _SPECIAL.get(b)
    return f"GPIO {b}" + (f" ({s})" if s else "")


# ---------------- breadboard ----------------
COLS = 30
TOP_ROWS = "abcde"
BOT_ROWS = "fghij"
RAILS = ("T-", "T+", "B-", "B+")
ALL_ROWS = ["T-", "T+", *TOP_ROWS, *BOT_ROWS, "B-", "B+"]
PIR_TERMS = ("GND", "OUT", "VCC")


def base(pt):
    """Point -> base node (before wires are taken into account)."""
    k = pt.split(":")
    if k[0] == "pi":
        kind = PI_PINS[int(k[1])][0]
        if kind == "3V3":
            return "N3V3"
        if kind == "5V":
            return "N5V"
        if kind == "GND":
            return "NGND"
        return pt
    if k[0] == "bb":
        row, col = k[1], k[2]
        if row in RAILS:
            return "rail" + row
        return f"col{col}{'T' if row in TOP_ROWS else 'B'}"
    return pt


def all_points():
    pts = [f"pi:{p}" for p in range(1, 41)]
    pts += [f"bb:{r}:{c}" for r in ALL_ROWS for c in range(1, COLS + 1)]
    for oid, o in OBJ.items():
        if o["type"] == "pir":
            pts += [f"m:{oid}:{t}" for t in PIR_TERMS]
    return pts


# ---------------- circuit ----------------
OBJ = {}            # id -> object (wire / component)
_NEXT = [1]
VERSION = [0]       # bumped on every topology change
PRESSED = set()     # buttons currently held down
PIR_STATE = {}      # id -> [held, high_until]
PIR_TAIL = 1.5      # PIR keeps OUT high this many seconds after motion

NAME_PREFIX = {"led": "LED", "res": "R", "btn": "SW", "abuz": "BZ", "pbuz": "BZ", "pir": "PIR"}
TYPE_NAME = {"led": "LED", "res": "resistor", "btn": "button", "abuz": "active buzzer",
             "pbuz": "passive buzzer", "pir": "PIR sensor", "wire": "wire"}


def _default_file():
    env = os.environ.get("RPISIM_CIRCUIT")
    if env:
        return os.path.abspath(env)
    main = sys.modules.get("__main__")
    f = getattr(main, "__file__", None)
    d = os.path.dirname(os.path.abspath(f)) if f else os.getcwd()
    return os.path.join(d, "circuit.json")


CUR_FILE = [_default_file()]


def points_of(oid, o):
    if o["type"] == "wire":
        return [o["a"], o["b"]]
    if o["type"] == "pir":
        return [f"m:{oid}:{t}" for t in PIR_TERMS]
    return list(o["legs"])


def occupant(pt):
    """Object that physically occupies a hole / pin / terminal (one item per spot)."""
    for oid, o in OBJ.items():
        if o["type"] == "pir":  # PIR terminals belong to the module but are free for wires
            continue
        if pt in points_of(oid, o):
            return oid
    return None


def add_obj(o):
    with LOCK:
        oid = f"o{_NEXT[0]}"
        _NEXT[0] += 1
        if o["type"] != "wire" and "name" not in o:
            pref = NAME_PREFIX[o["type"]]
            used = {x.get("name") for x in OBJ.values()}
            i = 1
            while f"{pref}{i}" in used:
                i += 1
            o["name"] = f"{pref}{i}"
        OBJ[oid] = o
        _bump()
        return oid


def remove_obj(oid):
    with LOCK:
        o = OBJ.pop(oid, None)
        if o is None:
            return
        PRESSED.discard(oid)
        PIR_STATE.pop(oid, None)
        if o["type"] == "pir":  # wires attached to the module go with it
            terms = set(points_of(oid, o))
            for wid in [w for w, x in OBJ.items() if x["type"] == "wire" and ({x["a"], x["b"]} & terms)]:
                OBJ.pop(wid, None)
        _bump()


def move_obj(oid, changes):
    """Move a component: `changes` is {"legs": [...]} or {"x": .., "y": ..}."""
    with LOCK:
        o = OBJ.get(oid)
        if o is None:
            return
        o.update(changes)
        _bump()


def clear_all():
    with LOCK:
        OBJ.clear()
        PRESSED.clear()
        PIR_STATE.clear()
        _bump()


def save(path=None):
    path = path or CUR_FILE[0]
    with LOCK:
        data = {"format": "rpi-sim-1", "next": _NEXT[0], "objects": OBJ}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        CUR_FILE[0] = path


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _replace_objects(data):
    OBJ.clear()
    OBJ.update(data.get("objects", {}))
    nums = [int(k[1:]) for k in OBJ if k[1:].isdigit()]
    _NEXT[0] = max([data.get("next", 1)] + [n + 1 for n in nums])
    PRESSED.clear()
    PIR_STATE.clear()


def load(path=None):
    """Open a circuit file; it becomes the file that changes are auto-saved to."""
    path = path or CUR_FILE[0]
    if not os.path.exists(path):
        return False
    try:
        data = _read(path)
    except Exception as ex:
        log(f"Cannot load {path}: {ex}")
        return False
    with LOCK:
        _replace_objects(data)
        CUR_FILE[0] = path
        _bump(persist=False)
    log(f"Loaded circuit: {os.path.basename(path)} ({len(OBJ)} items)")
    return True


def load_preset(path):
    """Copy a preset circuit into the current circuit file (the preset itself is untouched)."""
    try:
        data = _read(path)
    except Exception as ex:
        log(f"Cannot load preset {path}: {ex}")
        return False
    with LOCK:
        _replace_objects(data)
        _bump()
    log(f"Loaded preset: {os.path.basename(path)}")
    return True


def _bump(persist=True):
    VERSION[0] += 1
    if persist:
        try:
            save()
        except Exception as ex:
            log(f"Cannot save circuit: {ex}")
    update_inputs()


# ---------------- interaction (button, PIR) ----------------
def press(oid):
    with LOCK:
        if oid in OBJ and oid not in PRESSED:
            PRESSED.add(oid)
            _bump(persist=False)


def release(oid):
    with LOCK:
        if oid in PRESSED:
            PRESSED.discard(oid)
            _bump(persist=False)


def pir_hold(oid, held):
    with LOCK:
        s = PIR_STATE.setdefault(oid, [False, 0.0])
        s[0] = held
        if not held:
            s[1] = time.time() + PIR_TAIL
    update_inputs()


def pir_cancel(oid):
    """Drop any motion state immediately (no tail), e.g. when the module is picked up."""
    with LOCK:
        PIR_STATE.pop(oid, None)
    update_inputs()


def pir_motion(oid):
    s = PIR_STATE.get(oid)
    return bool(s and (s[0] or time.time() < s[1]))


# ---------------- topology ----------------
_UF = {"ver": -1, "par": {}}


def _find(par, x):
    while par.get(x, x) != x:
        x = par[x]
    return x


def _parents():
    if _UF["ver"] != VERSION[0]:
        par = {}

        def union(a, b):
            ra, rb = _find(par, a), _find(par, b)
            if ra != rb:
                par[ra] = rb

        for oid, o in OBJ.items():
            if o["type"] == "wire":
                union(base(o["a"]), base(o["b"]))
            elif o["type"] == "btn" and oid in PRESSED:
                union(base(o["legs"][0]), base(o["legs"][1]))
        _UF["ver"], _UF["par"] = VERSION[0], par
    return _UF["par"]


def net_of(pt):
    with LOCK:
        return _find(_parents(), base(pt))


def net_points(pt):
    with LOCK:
        par = _parents()
        n = _find(par, base(pt))
        return [q for q in all_points() if _find(par, base(q)) == n]


# ---------------- GPIO state ----------------
MODE = [None]
PINS = {}            # bcm -> dict
CB_Q = queue.Queue()


def new_pin(direction, pull=PUD_OFF, level=None):
    return dict(dir=direction, level=level, pull=pull, edge=None, cbs=[], bounce=0.0,
                last_cb=0.0, flag=False, pwm=None, trans=deque(maxlen=400),
                floating=False, n_rise=0, n_fall=0)


def wave(st):
    """(frequency, duty) if the pin oscillates (PWM or fast manual toggling)."""
    pw = st["pwm"]
    if pw is not None and pw.running:
        return (pw.freq, pw.duty) if 0 < pw.duty < 100 else None
    now = time.time()
    n = 0
    for t in reversed(st["trans"]):
        if now - t >= 0.1:
            break
        n += 1
    if n >= 8:
        return (n / 2 / 0.1, 50.0)
    return None


def _out_v(st):
    pw = st["pwm"]
    if pw is not None and pw.running:
        return 3.3 if pw.duty > 0 else 0.0
    if wave(st):
        return 3.3
    return 3.3 if st["level"] else 0.0


def _cb_worker():
    # Like RPi.GPIO: callbacks run sequentially on one background thread.
    while True:
        cb, ch = CB_Q.get()
        try:
            cb(ch)
        except Exception as ex:
            traceback.print_exc()
            log(f"ERROR in callback: {ex!r}")


threading.Thread(target=_cb_worker, daemon=True).start()


# ---------------- electrical analysis ----------------
def evaluate():
    with LOCK:
        par = _parents()

        def N(pt):
            return _find(par, base(pt))

        src = defaultdict(list)   # net -> [(V, label, wave)]
        for p, (kind, b) in PI_PINS.items():
            n = N(f"pi:{p}")
            if kind == "3V3":
                src[n].append((3.3, "3V3", None))
            elif kind == "5V":
                src[n].append((5.0, "5V", None))
            elif kind == "GND":
                src[n].append((0.0, "GND", None))
            else:
                st = PINS.get(b)
                if st and st["dir"] == OUT:
                    src[n].append((_out_v(st), f"GPIO{b}", wave(st)))

        res_adj = defaultdict(list)
        for oid, o in OBJ.items():
            if o["type"] == "res":
                a, b = N(o["legs"][0]), N(o["legs"][1])
                if a != b:
                    res_adj[a].append((b, o["ohms"]))
                    res_adj[b].append((a, o["ohms"]))

        def strong(n):
            s = src.get(n)
            if not s:
                return None
            if len({round(v, 1) for v, _, _ in s}) > 1:
                return "short"
            w = next((w for _, _, w in s if w), None)
            return (s[0][0], w)

        def resolve(n, visited=None):
            """-> (voltage, resistance to source, wave), or None if the net is undriven."""
            st = strong(n)
            if st == "short":
                return None
            if st:
                return (st[0], 0, st[1])
            visited = visited or {n}
            for m, r in res_adj.get(n, []):
                if m in visited:
                    continue
                rr = resolve(m, visited | {m})
                if rr:
                    return (rr[0], rr[1] + r, rr[2])
            return None

        warnings = []
        pir = {}
        for oid, o in OBJ.items():
            if o["type"] != "pir":
                continue
            vcc, gnd = resolve(N(f"m:{oid}:VCC")), resolve(N(f"m:{oid}:GND"))
            powered = bool(vcc and gnd and vcc[0] - gnd[0] >= 4.5)
            motion = pir_motion(oid)
            pir[oid] = (powered, motion)
            if powered:
                src[N(f"m:{oid}:OUT")].append((3.3 if motion else 0.0, f"{o['name']} OUT", None))
            elif vcc and gnd and vcc[0] - gnd[0] > 2:
                warnings.append(f"{o['name']}: VCC is at {vcc[0]:.1f}V – the PIR needs a 5V supply.")
            else:
                warnings.append(f"{o['name']}: not powered (VCC → 5V, GND → GND).")

        for n, s in src.items():
            if len({round(v, 1) for v, _, _ in s}) > 1:
                labels = sorted({f"{lbl}={v:.1f}V" for v, lbl, _ in s})
                warnings.append("SHORT CIRCUIT: " + " ↔ ".join(labels))
        for p, (kind, b) in PI_PINS.items():
            if kind == "GPIO":
                s = src.get(N(f"pi:{p}"), [])
                if any(v >= 4.5 for v, _, _ in s):
                    warnings.append(f"5V applied to GPIO{b} (pin {p}) – this damages a real Pi! GPIO pins are 3.3V max.")

        leds, buz = {}, {}
        for oid, o in OBJ.items():
            t = o["type"]
            if t not in ("led", "abuz", "pbuz", "btn"):
                continue
            n0, n1 = N(o["legs"][0]), N(o["legs"][1])
            if t == "btn":
                if base(o["legs"][0]) == base(o["legs"][1]):
                    warnings.append(f"{o['name']}: both legs are in the same column – the button is always 'pressed'.")
                continue
            if n0 == n1:
                warnings.append(f"{o['name']}: both legs are on the same net – it is shorted and cannot work.")
            a, k = (None, None) if n0 == n1 else (resolve(n0), resolve(n1))
            if t == "led":
                state, bright = "off", 0.0
                if a and k:
                    d = a[0] - k[0]
                    if d >= 1.8:
                        bright = a[2][1] / 100.0 if a[2] else 1.0
                        if a[1] + k[1] == 0:
                            state = "burn"
                            warnings.append(f"{o['name']}: no resistor in series – the LED is burning out!")
                        else:
                            state = "on"
                    elif d <= -1.8:
                        warnings.append(f"{o['name']}: reversed (the anode + must face the higher voltage).")
                leds[oid] = (state, bright)
            else:
                freq = None
                if a and k:
                    d = a[0] - k[0]
                    w = a[2]
                    if d >= 2.5:
                        if t == "abuz":
                            freq = w[0] if (w and w[0] >= 37) else 2000
                        elif w and w[0] >= 37:
                            freq = w[0]
                    elif d <= -2.5 and t == "abuz":
                        warnings.append(f"{o['name']}: active buzzer is reversed (+ must face the GPIO).")
                buz[oid] = freq

        inputs = {}
        for b, st in PINS.items():
            if st["dir"] != IN:
                continue
            r = resolve(N(f"pi:{BCM_TO_PHYS[b]}"))
            if r:
                lvl = 1 if r[0] > 1.65 else 0
            elif st["pull"] == PUD_UP:
                lvl = 1
            elif st["pull"] == PUD_DOWN:
                lvl = 0
            else:
                lvl = None
                warnings.append(f"GPIO{b} is a floating input (nothing drives it, no pull-up/down) – it reads random values.")
            inputs[b] = lvl

        gnd_wires = sum(1 for o in OBJ.values() if o["type"] == "wire"
                        and any(pt.startswith("pi:") and PI_PINS[int(pt[3:])][0] == "GND"
                                for pt in (o["a"], o["b"])))
        return {"leds": leds, "buz": buz, "pir": pir, "inputs": inputs,
                "warnings": list(dict.fromkeys(warnings)), "gnd_wires": gnd_wires}


def update_inputs():
    """Recompute input pin levels and fire edge callbacks."""
    with LOCK:
        ins = [b for b, s in PINS.items() if s["dir"] == IN]
        if not ins:
            return
        ev = evaluate()
        for b in ins:
            st = PINS[b]
            lvl = ev["inputs"].get(b)
            st["floating"] = lvl is None
            if lvl is None:
                if st["level"] is None:
                    st["level"] = random.randint(0, 1)
                continue
            old = st["level"]
            if old is None:
                st["level"] = lvl
                continue
            if lvl == old:
                continue
            st["level"] = lvl
            if lvl:
                st["n_rise"] += 1
            else:
                st["n_fall"] += 1
            log(f"GPIO{b} (input) -> {'HIGH' if lvl else 'LOW'}")
            e = st["edge"]
            if e and (e == BOTH or (e == RISING and lvl) or (e == FALLING and not lvl)):
                now = time.time()
                if now - st["last_cb"] >= st["bounce"]:
                    st["last_cb"] = now
                    st["flag"] = True
                    ch = BCM_TO_PHYS[b] if MODE[0] == BOARD else b
                    for cb in st["cbs"]:
                        CB_Q.put((cb, ch))


# ---------------- GUI ----------------
_UI = {"thread": None, "ready": threading.Event()}


def ensure_ui():
    if _UI["thread"] is not None or os.environ.get("RPISIM_HEADLESS"):
        return
    from . import _ui
    t = threading.Thread(target=_ui.run, args=(_UI["ready"],), daemon=True)
    _UI["thread"] = t
    t.start()
    _UI["ready"].wait(10)


def ui_alive():
    t = _UI["thread"]
    return t is not None and t.is_alive()


load()
