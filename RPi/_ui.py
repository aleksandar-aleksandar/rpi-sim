"""Simulator window: Raspberry Pi header + breadboard + components + wires."""
import glob
import math
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import _core as core

try:
    import winsound
except ImportError:  # sound is only available on Windows
    winsound = None

PRESETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

# ---------------- geometry ----------------
CW, CH = 1100, 650
P = 20                      # breadboard hole pitch
BB_X0 = 470                 # x of column 1
ROW_Y = {"T-": 78, "T+": 98}
for _i, _r in enumerate(core.TOP_ROWS):
    ROW_Y[_r] = 140 + _i * P
for _i, _r in enumerate(core.BOT_ROWS):
    ROW_Y[_r] = 262 + _i * P
ROW_Y["B-"] = 384
ROW_Y["B+"] = 404
BB_RECT = (440, 55, BB_X0 + (core.COLS - 1) * P + 30, 425)
PI_RECT = (15, 40, 415, 630)
PI_X = (262, 288)           # odd / even pins
PI_Y0, PI_DY = 82, 26
MOD_TOP = 440               # module area (PIR)

LED_COLORS = {"red": ("#5c1a1a", "#ff2a2a"), "green": ("#1a4a24", "#2bff5a"),
              "yellow": ("#5c5418", "#ffe82a"), "blue": ("#1a2a5c", "#3a8bff"),
              "white": ("#6b6b6b", "#ffffff")}
WIRE_COLORS = {"red": "#d42020", "black": "#1c1c1c", "blue": "#2a6bd6", "green": "#17a03a",
               "yellow": "#e8c400", "orange": "#f07a00", "purple": "#8a2be2", "white": "#f4f4f4"}
RES_BANDS = {220: ["#d00", "#d00", "#111", "#111", "#8b4513"],
             1000: ["#8b4513", "#111", "#111", "#8b4513", "#8b4513"],
             10000: ["#8b4513", "#111", "#111", "#d00", "#8b4513"]}
MAX_SPAN = {"led": 90, "abuz": 90, "pbuz": 90, "btn": 90, "res": 175}

MODES = [("use", "🖐 Use"), ("wire", "Wire"), ("led", "LED"), ("rgb", "RGB LED"), ("res", "Resistor"),
         ("btn", "Button"), ("abuz", "Active buzzer"), ("pbuz", "Passive buzzer"),
         ("pir", "PIR"), ("servo", "Servo"), ("del", "✖ Delete")]
FIRST_HINT = {
    "wire": "Wire: click the first end (Pi pin, breadboard hole or PIR terminal).",
    "led": "LED: click the hole for the ANODE (+, longer leg).",
    "rgb": "RGB LED (common cathode): click the hole for the R leg – legs R, K, G, B fill 4 holes in a row.",
    "res": "Resistor: click the hole for the first leg.",
    "btn": "Button: click the hole for the first leg.",
    "abuz": "Active buzzer: click the hole for the + leg.",
    "pbuz": "Passive buzzer: click the hole for the + leg.",
    "pir": "PIR: click an empty spot in the grey area below the breadboard.",
    "servo": "Servo: click an empty spot in the grey area. Wires: GND, VCC (5V), SIG (50 Hz PWM).",
    "use": "Hold a button / PIR (or its number key 1-9) to activate it, drag any part to move it. Right-click deletes. "
           "Hover a hole to see everything connected to it.",
    "del": "Click a component or wire to delete it (right-click deletes in any mode).",
}
SECOND_HINT = {
    "wire": "Click the other end of the wire. (Esc = cancel)",
    "led": "Click the hole for the CATHODE (−, shorter leg). (Esc = cancel)",
    "res": "Click the hole for the second leg. (Esc = cancel)",
    "btn": "Click the hole for the second leg. (Esc = cancel)",
    "abuz": "Click the hole for the − leg. (Esc = cancel)",
    "pbuz": "Click the hole for the − leg. (Esc = cancel)",
}


def pt_pos(pt):
    k = pt.split(":")
    if k[0] == "pi":
        p = int(k[1])
        return PI_X[(p - 1) % 2], PI_Y0 + ((p - 1) // 2) * PI_DY
    if k[0] == "bb":
        return BB_X0 + (int(k[2]) - 1) * P, ROW_Y[k[1]]
    o = core.OBJ.get(k[1])
    if o is None:
        return -100, -100
    terms = core.MODULE_TERMS[o["type"]]
    off = (terms.index(k[2]) - (len(terms) - 1) / 2) * 24
    return o["x"] + off, o["y"] + 44


def point_at(x, y):
    for p in range(1, 41):
        px, py = pt_pos(f"pi:{p}")
        if math.hypot(x - px, y - py) <= 10:
            return f"pi:{p}"
    col = round((x - BB_X0) / P) + 1
    if 1 <= col <= core.COLS and abs(x - (BB_X0 + (col - 1) * P)) <= 8:
        for r, yy in ROW_Y.items():
            if abs(y - yy) <= 8:
                return f"bb:{r}:{col}"
    for oid, o in list(core.OBJ.items()):
        if o["type"] in core.MODULES:
            for t in core.MODULE_TERMS[o["type"]]:
                px, py = pt_pos(f"m:{oid}:{t}")
                if math.hypot(x - px, y - py) <= 8:
                    return f"m:{oid}:{t}"
    return None


def snap_hole(x, y):
    """Nearest breadboard hole to (x, y), or None if off the board."""
    col = round((x - BB_X0) / P) + 1
    if not 1 <= col <= core.COLS:
        return None
    row, best = None, P / 2 + 1
    for r, yy in ROW_Y.items():
        if abs(y - yy) < best:
            row, best = r, abs(y - yy)
    return f"bb:{row}:{col}" if row else None


def module_spot_free(x, y, ignore=None):
    """Modules need ~85 x 90 px of room each."""
    return all(not (abs(o["x"] - x) < 85 and abs(o["y"] - y) < 90)
               for k, o in core.OBJ.items() if o["type"] in core.MODULES and k != ignore)


def describe(pt):
    k = pt.split(":")
    if k[0] == "pi":
        return f"Pi pin {k[1]} – {core.pin_label(int(k[1]))}"
    if k[0] == "bb":
        r = k[1]
        if r in core.RAILS:
            return f"{'Top' if r[0] == 'T' else 'Bottom'} rail {r[1]}"
        return f"Hole {r}{k[2]}"
    o = core.OBJ.get(k[1], {})
    return f"{o.get('name', '?')} terminal {k[2]}"


def _wire_ctrl(a, b):
    (x1, y1), (x2, y2) = a, b
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    L = math.hypot(x2 - x1, y2 - y1) or 1
    off = min(35, L * 0.15)
    return mx - (y2 - y1) / L * off, my + (x2 - x1) / L * off


def _bezier(a, c, b, t):
    u = 1 - t
    return (u * u * a[0] + 2 * u * t * c[0] + t * t * b[0],
            u * u * a[1] + 2 * u * t * c[1] + t * t * b[1])


def _mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def list_presets():
    files = sorted(glob.glob(os.path.join(PRESETS_DIR, "*.json")))
    return {os.path.splitext(os.path.basename(f))[0]: f for f in files}


class App:
    def __init__(self, root):
        self.root = root
        root.title("Raspberry Pi simulator")
        root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
        self.mode = tk.StringVar(value="use")
        self.wire_color = tk.StringVar(value="red")
        self.led_color = tk.StringVar(value="red")
        self.ohms = tk.StringVar(value="220")
        self.presets = list_presets()
        self.preset = tk.StringVar(value=next(iter(self.presets), ""))
        self.pending = None
        self.mouse = (0, 0)
        self.hover_pt = None
        self.hover_pts = []
        self.hover_ver = -1
        self.holding = None
        self.drag = None            # {"oid", "x0", "y0", "active", "target", "valid"}
        self._keys_held = {}        # key char -> oid held via keyboard
        self.servo_disp = {}        # oid -> displayed angle (eased toward the target)
        self._key_release_jobs = {}
        self.last_eval = None
        self._status_txt = ""
        self._build()
        self._draw_static()
        self.mode.trace_add("write", lambda *a: self._mode_changed())
        self._mode_changed()
        threading.Thread(target=self._sound_loop, daemon=True).start()
        self._tick()

    # ---------- layout ----------
    def _build(self):
        st = ttk.Style()
        st.configure("Toolbutton", padding=(8, 4))
        bar = ttk.Frame(self.root, padding=(6, 4))
        bar.pack(fill="x")
        for val, txt in MODES:
            ttk.Radiobutton(bar, text=txt, value=val, variable=self.mode,
                            style="Toolbutton").pack(side="left", padx=1)
        bar2 = ttk.Frame(self.root, padding=(6, 0))
        bar2.pack(fill="x")
        ttk.Label(bar2, text="Wire:").pack(side="left")
        ttk.Combobox(bar2, textvariable=self.wire_color, values=list(WIRE_COLORS), width=7,
                     state="readonly").pack(side="left", padx=(2, 10))
        ttk.Label(bar2, text="LED:").pack(side="left")
        ttk.Combobox(bar2, textvariable=self.led_color, values=list(LED_COLORS), width=7,
                     state="readonly").pack(side="left", padx=(2, 10))
        ttk.Label(bar2, text="Resistor (Ω):").pack(side="left")
        ttk.Combobox(bar2, textvariable=self.ohms, values=["220", "1000", "10000"], width=6,
                     state="readonly").pack(side="left", padx=(2, 10))
        if self.presets:
            ttk.Label(bar2, text="Preset:").pack(side="left")
            ttk.Combobox(bar2, textvariable=self.preset, values=list(self.presets), width=22,
                         state="readonly").pack(side="left", padx=(2, 2))
            ttk.Button(bar2, text="Load", command=self._load_preset).pack(side="left", padx=(0, 10))
        ttk.Button(bar2, text="Clear", command=self._clear).pack(side="right", padx=2)
        ttk.Button(bar2, text="↷ Redo", width=7, command=self._redo).pack(side="right", padx=2)
        ttk.Button(bar2, text="↶ Undo", width=7, command=self._undo).pack(side="right", padx=2)
        ttk.Button(bar2, text="Save as…", command=self._save_as).pack(side="right", padx=2)
        ttk.Button(bar2, text="Open…", command=self._open).pack(side="right", padx=2)

        self.cv = tk.Canvas(self.root, width=CW, height=CH, bg="#2b2f36", highlightthickness=0)
        self.cv.pack(padx=6, pady=4)
        self.hint = tk.Label(self.root, text="", anchor="w", font=("Segoe UI", 10), fg="#0b4f9c")
        self.hint.pack(fill="x", padx=8)
        self.info = tk.Label(self.root, text="", anchor="w", font=("Segoe UI", 9), fg="#555")
        self.info.pack(fill="x", padx=8)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        self.status = tk.Text(bottom, height=10, width=60, font=("Consolas", 9), wrap="word")
        self.status.pack(side="left", fill="both", expand=True)
        self.status.tag_configure("warn", foreground="#c00000")
        self.status.tag_configure("ok", foreground="#167a2c")
        self.status.tag_configure("h", font=("Consolas", 9, "bold"))
        self.log = tk.Text(bottom, height=10, width=58, font=("Consolas", 9), bg="#15171b", fg="#d6d6d6")
        self.log.pack(side="left", fill="both", expand=True, padx=(6, 0))

        c = self.cv
        c.bind("<ButtonPress-1>", self._on_down)
        c.bind("<ButtonRelease-1>", self._on_up)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<Button-3>", self._on_right)
        c.bind("<Motion>", self._on_motion)
        self.root.bind("<Escape>", lambda e: self._cancel())
        self.root.bind("<KeyPress>", self._key_down)
        self.root.bind("<KeyRelease>", self._key_up)
        for seq in ("<Control-z>", "<Control-Z>"):
            self.root.bind(seq, self._undo_key)
        for seq in ("<Control-y>", "<Control-Y>", "<Control-Shift-z>", "<Control-Shift-Z>"):
            self.root.bind(seq, lambda e: self._redo())

    # ---------- keyboard-held inputs (1..9) ----------
    @staticmethod
    def input_order():
        """Buttons, then PIRs, in name order. Key N holds input N."""
        def key(item):
            oid, o = item
            name = o.get("name", "")
            num = int("".join(ch for ch in name if ch.isdigit()) or 0)
            return (0 if o["type"] == "btn" else 1, num, name)
        items = [(k, o) for k, o in core.OBJ.items() if o["type"] in ("btn", "pir")]
        return [k for k, _ in sorted(items, key=key)][:9]

    def _key_down(self, e):
        ch = getattr(e, "char", "")
        if not ch or ch not in "123456789" or (getattr(e, "state", 0) & 0x4):
            return
        pending = self._key_release_jobs.pop(ch, None)
        if pending:                       # X11 auto-repeat: release+press pair
            self.root.after_cancel(pending)
            return
        if ch in self._keys_held:         # Windows auto-repeat: repeated press
            return
        order = self.input_order()
        idx = int(ch) - 1
        if idx >= len(order):
            return
        oid = order[idx]
        self._keys_held[ch] = oid
        if core.OBJ[oid]["type"] == "btn":
            core.press(oid)
        else:
            core.pir_hold(oid, True)

    def _key_up(self, e):
        ch = getattr(e, "char", "")
        if ch in self._keys_held and ch not in self._key_release_jobs:
            self._key_release_jobs[ch] = self.root.after(40, lambda: self._release_key(ch))

    def _release_key(self, ch):
        self._key_release_jobs.pop(ch, None)
        oid = self._keys_held.pop(ch, None)
        o = core.OBJ.get(oid) if oid else None
        if o and o["type"] == "btn":
            core.release(oid)
        elif o and o["type"] == "pir":
            core.pir_hold(oid, False)

    def _undo_key(self, e):
        if e.state & 0x1:      # Shift held -> redo
            self._redo()
        else:
            self._undo()

    def _undo(self):
        self.pending = self.drag = None
        self._hint("Undone." if core.undo() else "Nothing to undo.")

    def _redo(self):
        self.pending = self.drag = None
        self._hint("Redone." if core.redo() else "Nothing to redo.")

    def _draw_static(self):
        c = self.cv
        # Raspberry Pi board
        x1, y1, x2, y2 = PI_RECT
        c.create_rectangle(x1, y1, x2, y2, fill="#1f7a3e", outline="#0f4d24", width=2)
        for hx, hy in ((x1 + 18, y1 + 18), (x2 - 18, y1 + 18), (x1 + 18, y2 - 18), (x2 - 18, y2 - 18)):
            c.create_oval(hx - 9, hy - 9, hx + 9, hy + 9, fill="#f2c200", outline="")
            c.create_oval(hx - 4, hy - 4, hx + 4, hy + 4, fill="#2b2f36", outline="")
        c.create_text((x1 + x2) / 2, y1 + 18, text="Raspberry Pi 4 Model B", fill="#e8f5e9",
                      font=("Segoe UI", 11, "bold"))
        c.create_rectangle(PI_X[0] - 13, PI_Y0 - 14, PI_X[1] + 13, PI_Y0 + 19 * PI_DY + 14,
                           fill="#141414", outline="#000")
        col = {"3V3": "#f0a000", "5V": "#e02020", "GND": "#7a7a7a", "GPIO": "#5ec24a"}
        for p in range(1, 41):
            px, py = pt_pos(f"pi:{p}")
            kind, _ = core.PI_PINS[p]
            c.create_oval(px - 8, py - 8, px + 8, py + 8, fill=col[kind], outline="#000")
            c.create_text(px, py, text=str(p), font=("Segoe UI", 6, "bold"), fill="#000")
            lbl = core.pin_label(p)
            fg = {"3V3": "#ffcf5a", "5V": "#ff8080", "GND": "#cfcfcf"}.get(kind, "#ffffff")
            if p % 2:
                c.create_text(px - 16, py, text=lbl, anchor="e", fill=fg, font=("Segoe UI", 8))
            else:
                c.create_text(px + 16, py, text=lbl, anchor="w", fill=fg, font=("Segoe UI", 8))
        # breadboard
        x1, y1, x2, y2 = BB_RECT
        c.create_rectangle(x1, y1, x2, y2, fill="#f1ede0", outline="#bdb69f", width=2)
        gy1, gy2 = ROW_Y["e"] + 11, ROW_Y["f"] - 11
        c.create_rectangle(x1 + 4, gy1, x2 - 4, gy2, fill="#d9d2bd", outline="")
        for r, color, dy in (("T-", "#2a5bd6", -10), ("T+", "#d42020", 10),
                             ("B-", "#2a5bd6", -10), ("B+", "#d42020", 10)):
            y = ROW_Y[r] + dy
            c.create_line(x1 + 22, y, x2 - 22, y, fill=color, width=2)
            sign = "−" if r[1] == "-" else "+"
            c.create_text(x1 + 12, ROW_Y[r], text=sign, fill=color, font=("Segoe UI", 11, "bold"))
            c.create_text(x2 - 12, ROW_Y[r], text=sign, fill=color, font=("Segoe UI", 11, "bold"))
        for r in core.TOP_ROWS + core.BOT_ROWS:
            c.create_text(x1 + 14, ROW_Y[r], text=r, fill="#8a8370", font=("Segoe UI", 8))
            c.create_text(x2 - 14, ROW_Y[r], text=r, fill="#8a8370", font=("Segoe UI", 8))
        for col_n in range(1, core.COLS + 1):
            x = BB_X0 + (col_n - 1) * P
            if col_n == 1 or col_n % 5 == 0:
                c.create_text(x, ROW_Y["a"] - 15, text=str(col_n), fill="#8a8370", font=("Segoe UI", 7))
                c.create_text(x, ROW_Y["j"] + 15, text=str(col_n), fill="#8a8370", font=("Segoe UI", 7))
            for r in core.ALL_ROWS:
                y = ROW_Y[r]
                c.create_rectangle(x - 3, y - 3, x + 3, y + 3, fill="#3d3a33", outline="")
        # module area
        c.create_rectangle(BB_RECT[0], MOD_TOP, BB_RECT[2], CH - 10, outline="#4a505a", dash=(4, 4))
        c.create_text(BB_RECT[0] + 8, MOD_TOP + 10, anchor="w", fill="#7d8590",
                      text="Module area (PIR) – connect modules to the Pi or breadboard with wires",
                      font=("Segoe UI", 8))

    # ---------- files ----------
    def _clear(self):
        if messagebox.askyesno("Clear", "Delete the whole circuit?", parent=self.root):
            core.clear_all()

    def _save_as(self):
        p = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json",
                                         initialdir=os.path.dirname(core.CUR_FILE[0]),
                                         filetypes=[("Circuit", "*.json")])
        if p:
            core.save(p)
            core.log(f"Saved to {os.path.basename(p)} (auto-saving there from now on)")

    def _open(self):
        p = filedialog.askopenfilename(parent=self.root, initialdir=os.path.dirname(core.CUR_FILE[0]),
                                       filetypes=[("Circuit", "*.json")])
        if p:
            core.load(p)

    def _load_preset(self):
        path = self.presets.get(self.preset.get())
        if not path:
            return
        if core.OBJ and not messagebox.askyesno(
                "Load preset", f"Replace the current circuit with '{self.preset.get()}'?", parent=self.root):
            return
        core.load_preset(path)

    # ---------- events ----------
    def _mode_changed(self):
        self.pending = None
        self._hint(FIRST_HINT.get(self.mode.get(), ""))

    def _hint(self, txt, err=False):
        self.hint.config(text=txt, fg="#c00000" if err else "#0b4f9c")

    def _cancel(self):
        self.pending = None
        self._hint(FIRST_HINT.get(self.mode.get(), ""))

    def _body_center(self, o):
        if o["type"] in core.MODULES:
            return o["x"], o["y"]
        pts = [pt_pos(q) for q in o["legs"]]
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    def obj_at(self, x, y):
        best, bd = None, 1e9
        for oid, o in list(core.OBJ.items()):
            if o["type"] == "wire":
                continue
            cx, cy = self._body_center(o)
            if o["type"] in core.MODULES:
                if abs(x - cx) <= 38 and abs(y - cy) <= 34:
                    return oid
                continue
            d = math.hypot(x - cx, y - cy)
            if d < 15 and d < bd:
                best, bd = oid, d
        if best:
            return best
        for oid, o in reversed(list(core.OBJ.items())):
            if o["type"] != "wire":
                continue
            a, b = pt_pos(o["a"]), pt_pos(o["b"])
            ctrl = _wire_ctrl(a, b)
            for i in range(21):
                px, py = _bezier(a, ctrl, b, i / 20)
                if math.hypot(x - px, y - py) <= 6:
                    return oid
        return None

    def _on_down(self, e):
        x, y = e.x, e.y
        m = self.mode.get()
        if m == "use":
            oid = self.obj_at(x, y)
            o = core.OBJ.get(oid) if oid else None
            if o and o["type"] != "wire":
                self.drag = {"oid": oid, "x0": x, "y0": y, "active": False, "target": None, "valid": False}
            if o and o["type"] == "btn":
                self.holding = oid
                core.press(oid)
            elif o and o["type"] == "pir":
                self.holding = oid
                core.pir_hold(oid, True)
            return
        if m == "del":
            oid = self.obj_at(x, y)
            if oid:
                core.remove_obj(oid)
            return
        if m in core.MODULES:
            label = core.TYPE_NAME[m]
            if not (BB_RECT[0] + 40 <= x <= BB_RECT[2] - 40 and MOD_TOP + 35 <= y <= CH - 60):
                self._hint(f"Place the {label} in the grey area below the breadboard.", err=True)
                return
            if not module_spot_free(x, y):
                self._hint("Too close to another module.", err=True)
                return
            core.add_obj({"type": m, "x": x, "y": y})
            terms = ", ".join(core.MODULE_TERMS[m])
            self._hint(f"{label[0].upper() + label[1:]} placed. Connect {terms} with wires.")
            return
        pt = point_at(x, y)
        if pt is None:
            self._hint("Click exactly on a hole, pin or terminal.", err=True)
            return
        if m == "rgb":
            self._place_rgb(pt)
            return
        if m != "wire" and not pt.startswith("bb:"):
            self._hint("Component legs go into breadboard holes – connect them to the Pi with a wire.", err=True)
            return
        if core.occupant(pt):
            self._hint(f"{describe(pt)} is already taken – only one thing fits in a hole/pin.", err=True)
            return
        if self.pending is None:
            self.pending = pt
            self._hint(SECOND_HINT[m])
            return
        a = self.pending
        if pt == a:
            self._cancel()
            return
        if m != "wire":
            (x1, y1), (x2, y2) = pt_pos(a), pt_pos(pt)
            if math.hypot(x2 - x1, y2 - y1) > MAX_SPAN[m]:
                self._hint(f"Legs are too far apart for a {core.TYPE_NAME[m]}.", err=True)
                return
        if m == "wire":
            o = {"type": "wire", "a": a, "b": pt, "color": WIRE_COLORS[self.wire_color.get()]}
        elif m == "led":
            o = {"type": "led", "legs": [a, pt], "color": self.led_color.get()}
        elif m == "res":
            o = {"type": "res", "legs": [a, pt], "ohms": int(self.ohms.get())}
        else:
            o = {"type": m, "legs": [a, pt]}
        core.add_obj(o)
        self.pending = None
        self._hint(FIRST_HINT[m])

    def _place_rgb(self, pt):
        k = pt.split(":")
        if k[0] != "bb" or k[1] in core.RAILS:
            self._hint("Put the RGB LED in the main area of the breadboard (rows a–j).", err=True)
            return
        row, col = k[1], int(k[2])
        legs = [f"bb:{row}:{col + i}" for i in range(4)]
        if col + 3 > core.COLS:
            self._hint("Not enough room – the RGB LED needs 4 holes in a row.", err=True)
            return
        taken = [q for q in legs if core.occupant(q)]
        if taken:
            self._hint(f"{describe(taken[0])} is already taken.", err=True)
            return
        core.add_obj({"type": "rgb", "legs": legs})
        self._hint("RGB LED placed (R, K, G, B). Give each colour its own resistor; K goes to GND.")

    def _drag_target(self, oid, dx, dy):
        """-> (changes, valid) for moving object `oid` by (dx, dy) pixels."""
        o = core.OBJ.get(oid)
        if o is None:
            return None, False
        if o["type"] in core.MODULES:
            nx = min(max(o["x"] + dx, BB_RECT[0] + 40), BB_RECT[2] - 40)
            ny = min(max(o["y"] + dy, MOD_TOP + 35), CH - 60)
            return {"x": nx, "y": ny}, module_spot_free(nx, ny, ignore=oid)
        legs = []
        for leg in o["legs"]:
            lx, ly = pt_pos(leg)
            h = snap_hole(lx + dx, ly + dy)
            if h is None:
                return None, False
            legs.append(h)
        ok = len(set(legs)) == len(legs) and all(core.occupant(h) in (None, oid) for h in legs)
        if ok and len(legs) == 2 and o["type"] in MAX_SPAN:
            (x1, y1), (x2, y2) = pt_pos(legs[0]), pt_pos(legs[1])
            ok = math.hypot(x2 - x1, y2 - y1) <= MAX_SPAN[o["type"]]
        return {"legs": legs}, ok

    def _on_drag(self, e):
        self._on_motion(e)
        d = self.drag
        if not d:
            return
        dx, dy = e.x - d["x0"], e.y - d["y0"]
        if not d["active"]:
            if math.hypot(dx, dy) < 6:
                return
            d["active"] = True
            o = core.OBJ.get(d["oid"])
            if self.holding and o:          # picking a part up cancels the press
                if o["type"] == "btn":
                    core.release(self.holding)
                elif o["type"] == "pir":
                    core.pir_cancel(self.holding)
                self.holding = None
        d["target"], d["valid"] = self._drag_target(d["oid"], dx, dy)

    def _on_up(self, e):
        d, self.drag = self.drag, None
        if d and d["active"]:
            o = core.OBJ.get(d["oid"])
            if d["valid"] and d["target"]:
                core.move_obj(d["oid"], d["target"])
                self._hint(f"Moved {o.get('name', 'part')}.")
            elif o:
                self._hint(f"Can't move {o.get('name', 'part')} there (off the board or holes taken).", err=True)
            return
        if self.holding:
            o = core.OBJ.get(self.holding)
            if o and o["type"] == "btn":
                core.release(self.holding)
            elif o and o["type"] == "pir":
                core.pir_hold(self.holding, False)
            self.holding = None

    def _on_right(self, e):
        if self.pending:
            self._cancel()
            return
        oid = self.obj_at(e.x, e.y)
        if oid:
            core.remove_obj(oid)

    def _on_motion(self, e):
        self.mouse = (e.x, e.y)
        pt = point_at(e.x, e.y)
        if pt != self.hover_pt:
            self.hover_pt = pt
            self.hover_ver = -1

    # ---------- drawing ----------
    def _draw_dynamic(self, ev, objs):
        c = self.cv
        c.delete("dyn")
        # GPIO pin state rings
        for b, st in list(core.PINS.items()):
            px, py = pt_pos(f"pi:{core.BCM_TO_PHYS[b]}")
            if st["dir"] == core.OUT:
                w = core.wave(st)
                pw = st["pwm"]
                on = w or (pw is not None and pw.running and pw.duty > 0) or (
                    (pw is None or not pw.running) and st["level"])
                if on:
                    c.create_oval(px - 11, py - 11, px + 11, py + 11, outline="#ffb000" if w else "#ffe600",
                                  width=3, tags="dyn")
            else:
                c.create_oval(px - 11, py - 11, px + 11, py + 11,
                              outline="#4fc3f7" if st["level"] else "#1e5f80", width=2, dash=(2, 2), tags="dyn")
        # components
        for oid, o in objs:
            t = o["type"]
            if t == "wire":
                continue
            if t == "pir":
                self._draw_pir(oid, o, ev)
                continue
            if t == "rgb":
                self._draw_rgb(oid, o, ev)
                continue
            if t == "servo":
                self._draw_servo(oid, o, ev)
                continue
            (x1, y1), (x2, y2) = pt_pos(o["legs"][0]), pt_pos(o["legs"][1])
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if t == "res":
                c.create_line(x1, y1, x2, y2, fill="#9a9a9a", width=2, tags="dyn")
                ax, ay = x1 + (x2 - x1) * 0.22, y1 + (y2 - y1) * 0.22
                bx, by = x1 + (x2 - x1) * 0.78, y1 + (y2 - y1) * 0.78
                c.create_line(ax, ay, bx, by, fill="#d8c08f", width=10, capstyle="round", tags="dyn")
                L = math.hypot(x2 - x1, y2 - y1) or 1
                ux, uy = (x2 - x1) / L, (y2 - y1) / L
                for i, bc in enumerate(RES_BANDS.get(o["ohms"], RES_BANDS[220])):
                    f = 0.30 + i * 0.1 + (0.04 if i == 4 else 0)
                    cx, cy = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
                    c.create_line(cx - ux * 1.5, cy - uy * 1.5, cx + ux * 1.5, cy + uy * 1.5,
                                  fill=bc, width=10, tags="dyn")
                continue
            for (lx, ly) in ((x1, y1), (x2, y2)):
                c.create_line(lx, ly, mx, my, fill="#9a9a9a", width=2, tags="dyn")
                c.create_oval(lx - 2, ly - 2, lx + 2, ly + 2, fill="#9a9a9a", outline="", tags="dyn")
            if t == "led":
                off, on = LED_COLORS.get(o["color"], LED_COLORS["red"])
                state, bright = ev["leds"].get(oid, ("off", 0))
                if state == "off" or bright <= 0:
                    fill = off
                else:
                    fill = _mix(off, on, max(0.25, bright))
                    r = 12 + 6 * bright
                    c.create_oval(mx - r, my - r, mx + r, my + r, outline=on, width=2, tags="dyn")
                if state == "burn":
                    fill = "#ff8c00" if int(time.time() * 6) % 2 else "#552200"
                    c.create_text(mx, my - 20, text="burning!", fill="#ff5050",
                                  font=("Segoe UI", 8, "bold"), tags="dyn")
                c.create_oval(mx - 9, my - 9, mx + 9, my + 9, fill=fill, outline="#222", tags="dyn")
                c.create_text(x1 + (mx - x1) * 0.4 - 6, y1 + (my - y1) * 0.4 - 6, text="+",
                              fill="#d42020", font=("Segoe UI", 8, "bold"), tags="dyn")
            elif t == "btn":
                pressed = oid in core.PRESSED
                c.create_rectangle(mx - 11, my - 11, mx + 11, my + 11, fill="#2c2c2c", outline="#000", tags="dyn")
                r = 6 if pressed else 7
                c.create_oval(mx - r, my - r, mx + r, my + r, fill="#7a0d0d" if pressed else "#e02424",
                              outline="#300", tags="dyn")
            elif t in ("abuz", "pbuz"):
                freq = ev["buz"].get(oid)
                if freq:
                    for rr in (19, 24):
                        c.create_arc(mx - rr, my - rr, mx + rr, my + rr, start=-35, extent=70,
                                     style="arc", outline="#ffb000", width=2, tags="dyn")
                        c.create_arc(mx - rr, my - rr, mx + rr, my + rr, start=145, extent=70,
                                     style="arc", outline="#ffb000", width=2, tags="dyn")
                c.create_oval(mx - 14, my - 14, mx + 14, my + 14, fill="#151515", outline="#000", tags="dyn")
                c.create_oval(mx - 3, my - 3, mx + 3, my + 3, fill="#555", outline="", tags="dyn")
                c.create_text(mx, my + 8, text="A" if t == "abuz" else "P", fill="#bbb",
                              font=("Segoe UI", 7, "bold"), tags="dyn")
                c.create_text(x1 + (mx - x1) * 0.4 - 7, y1 + (my - y1) * 0.4 - 7, text="+",
                              fill="#d42020", font=("Segoe UI", 8, "bold"), tags="dyn")
                if freq:
                    c.create_text(mx, my - 22, text=f"{freq:.0f} Hz", fill="#ffb000",
                                  font=("Segoe UI", 8), tags="dyn")
        # wires
        for oid, o in objs:
            if o["type"] != "wire":
                continue
            a, b = pt_pos(o["a"]), pt_pos(o["b"])
            ctrl = _wire_ctrl(a, b)
            outline = "#000" if o["color"] != "#1c1c1c" else "#666"
            c.create_line(a[0], a[1], ctrl[0], ctrl[1], b[0], b[1], smooth=True, width=6,
                          fill=outline, capstyle="round", tags="dyn")
            c.create_line(a[0], a[1], ctrl[0], ctrl[1], b[0], b[1], smooth=True, width=4,
                          fill=o["color"], capstyle="round", tags="dyn")
            for (ex, ey) in (a, b):
                c.create_oval(ex - 4, ey - 4, ex + 4, ey + 4, fill=o["color"], outline="#000", tags="dyn")
        # hover: everything on the same net
        for q in self.hover_pts:
            qx, qy = pt_pos(q)
            c.create_oval(qx - 6, qy - 6, qx + 6, qy + 6, outline="#00e5ff", width=2, tags="dyn")
        # keyboard shortcut badges for inputs
        for i, oid in enumerate(self.input_order()):
            o = core.OBJ.get(oid)
            if not o:
                continue
            if o["type"] == "pir":
                bx, by = o["x"] - 28, o["y"] - 24
            else:
                cx, cy = self._body_center(o)
                bx, by = cx + 15, cy - 15
            held = oid in self._keys_held.values()
            c.create_rectangle(bx - 7, by - 7, bx + 7, by + 7, fill="#ffd54a" if held else "#e8e8e8",
                               outline="#555", tags="dyn")
            c.create_text(bx, by, text=str(i + 1), font=("Segoe UI", 7, "bold"), fill="#222", tags="dyn")
        # drag preview
        d = self.drag
        if d and d["active"] and d["target"]:
            col = "#3ddc84" if d["valid"] else "#ff4d4d"
            if "legs" in d["target"]:
                pts = [pt_pos(q) for q in d["target"]["legs"]]
                for qx, qy in pts:
                    c.create_oval(qx - 7, qy - 7, qx + 7, qy + 7, outline=col, width=3, tags="dyn")
                if len(pts) == 2:
                    c.create_line(*pts[0], *pts[1], fill=col, dash=(4, 3), width=2, tags="dyn")
            else:
                tx, ty = d["target"]["x"], d["target"]["y"]
                c.create_rectangle(tx - 36, ty - 32, tx + 36, ty + 30, outline=col, width=2,
                                   dash=(4, 3), tags="dyn")
        # placement in progress
        if self.pending:
            px, py = pt_pos(self.pending)
            c.create_oval(px - 7, py - 7, px + 7, py + 7, outline="#ff3df2", width=3, tags="dyn")
            c.create_line(px, py, *self.mouse, fill="#ff3df2", dash=(4, 3), tags="dyn")

    def _draw_rgb(self, oid, o, ev):
        c = self.cv
        pts = [pt_pos(q) for q in o["legs"]]
        mx, my = self._body_center(o)
        by = my - 16                                   # body sits above the leg row
        for (lx, ly), lbl in zip(pts, core.RGB_LEGS):
            c.create_line(lx, ly, mx + (lx - mx) * 0.35, by + 8, fill="#9a9a9a", width=2, tags="dyn")
            c.create_text(lx, ly + 11, text=lbl, font=("Segoe UI", 6, "bold"),
                          fill={"R": "#d42020", "G": "#17a03a", "B": "#2a6bd6"}.get(lbl, "#444"), tags="dyn")
        state, (r, g, b) = ev["leds"].get(oid, ("off", (0, 0, 0)))
        if state == "off" or max(r, g, b) == 0:
            fill = "#d9d9d9"
        else:
            fill = "#%02x%02x%02x" % tuple(int(70 + 185 * v) if v else 40 for v in (r, g, b))
            c.create_oval(mx - 19, by - 19, mx + 19, by + 19, outline=fill, width=3, tags="dyn")
        if state == "burn":
            c.create_text(mx, by - 24, text="burning!", fill="#ff5050", font=("Segoe UI", 8, "bold"), tags="dyn")
        c.create_oval(mx - 13, by - 13, mx + 13, by + 13, fill=fill, outline="#888", tags="dyn")

    SERVO_SPEED = 15.0   # degrees per frame (~375°/s, about an SG90 at 5V)

    def _draw_servo(self, oid, o, ev):
        c = self.cv
        x, y = o["x"], o["y"]
        powered, target = ev.get("servo", {}).get(oid, (False, None))
        shown = self.servo_disp.get(oid, 90.0 if target is None else target)
        if target is not None and powered:
            step = max(-self.SERVO_SPEED, min(self.SERVO_SPEED, target - shown))
            shown += step
        self.servo_disp[oid] = shown
        # body + mounting tabs
        c.create_rectangle(x - 46, y - 6, x + 46, y + 4, fill="#1f4fb8", outline="#123070", tags="dyn")
        c.create_rectangle(x - 34, y - 22, x + 34, y + 26, fill="#2a63d6", outline="#123070", width=2, tags="dyn")
        c.create_text(x + 10, y + 14, text=o["name"], fill="#cfe0ff", font=("Segoe UI", 7, "bold"), tags="dyn")
        # horn: 0° points left, 90° up, 180° right
        hx, hy = x - 12, y - 4
        rad = math.radians(180.0 - shown)
        ex, ey = hx + 30 * math.cos(rad), hy - 30 * math.sin(rad)
        c.create_line(hx, hy, ex, ey, fill="#f4f4f4", width=7, capstyle="round", tags="dyn")
        c.create_oval(hx - 8, hy - 8, hx + 8, hy + 8, fill="#f4f4f4", outline="#999", tags="dyn")
        c.create_oval(hx - 2, hy - 2, hx + 2, hy + 2, fill="#666", outline="", tags="dyn")
        label = f"{shown:.0f}°" if target is not None else "?°"
        c.create_text(x + 22, y - 10, text=label, fill="#ffffff" if powered else "#8fa6d6",
                      font=("Segoe UI", 8, "bold"), tags="dyn")
        # SG90 lead colours: brown GND, red VCC, orange SIG
        for t, lead in zip(core.MODULE_TERMS["servo"], ("#7a4a1e", "#d42020", "#f07a00")):
            tx, ty = pt_pos(f"m:{oid}:{t}")
            c.create_line(tx, y + 26, tx, ty, fill=lead, width=3, tags="dyn")
            c.create_rectangle(tx - 4, ty - 4, tx + 4, ty + 4, fill="#e0b830", outline="#000", tags="dyn")
            c.create_text(tx, ty + 13, text=t, fill="#cfd3da", font=("Segoe UI", 7), tags="dyn")

    def _draw_pir(self, oid, o, ev):
        c = self.cv
        x, y = o["x"], o["y"]
        powered, motion = ev["pir"].get(oid, (False, False))
        c.create_rectangle(x - 36, y - 32, x + 36, y + 30, fill="#1f8a3a", outline="#0d4d1e", width=2, tags="dyn")
        c.create_oval(x - 26, y - 28, x + 26, y + 24, fill="#fff3b0" if motion else "#f4f4f4",
                      outline="#cfcfcf", width=2, tags="dyn")
        c.create_text(x, y - 2, text=o["name"], fill="#666", font=("Segoe UI", 8, "bold"), tags="dyn")
        c.create_oval(x + 26, y + 20, x + 32, y + 26, fill="#ff4040" if powered else "#401010",
                      outline="", tags="dyn")
        if motion:
            c.create_text(x, y - 40, text="MOTION", fill="#ffd54a", font=("Segoe UI", 8, "bold"), tags="dyn")
        for t in core.PIR_TERMS:
            tx, ty = pt_pos(f"m:{oid}:{t}")
            c.create_line(tx, y + 30, tx, ty, fill="#c9a227", width=3, tags="dyn")
            c.create_rectangle(tx - 4, ty - 4, tx + 4, ty + 4, fill="#e0b830", outline="#000", tags="dyn")
            c.create_text(tx, ty + 13, text=t, fill="#cfd3da", font=("Segoe UI", 7), tags="dyn")

    # ---------- status ----------
    def _update_status(self, ev):
        lines = [("h", f"Circuit: {os.path.basename(core.CUR_FILE[0])} (auto-saved)\n")]
        n = ev["gnd_wires"]
        if n == 1:
            lines.append(("ok", "GND wires to the Pi: 1 – OK (single common ground)\n"))
        else:
            lines.append(("warn" if n > 1 else "", f"GND wires to the Pi: {n} (tip: use exactly 1 + a GND rail)\n"))
        mode = {core.BCM: "BCM", core.BOARD: "BOARD", None: "not set"}[core.MODE[0]]
        lines.append(("h", f"\nGPIO (setmode: {mode})\n"))
        if not core.PINS:
            lines.append(("", "  (no pins set up by the script yet)\n"))
        for b in sorted(core.PINS):
            st = core.PINS[b]
            nm = f"GPIO{b:<2} pin {core.BCM_TO_PHYS[b]:<2}"
            if st["dir"] == core.OUT:
                pw = st["pwm"]
                if pw is not None and pw.running:
                    s = f"OUT PWM {pw.freq:g}Hz duty {pw.duty:g}%"
                else:
                    w = core.wave(st)
                    s = f"OUT toggling ~{w[0]:.0f}Hz" if w else f"OUT {'HIGH' if st['level'] else 'LOW'}"
            else:
                pull = {core.PUD_UP: "PUD_UP", core.PUD_DOWN: "PUD_DOWN"}.get(st["pull"], "no pull")
                lvl = "floating!" if st["floating"] else ("HIGH" if st["level"] else "LOW")
                edge = {core.RISING: " RISING", core.FALLING: " FALLING", core.BOTH: " BOTH"}.get(st["edge"], "")
                s = f"IN  {pull} -> {lvl}{edge}"
            lines.append(("", f"  {nm} {s}\n"))
        if ev["warnings"]:
            lines.append(("h", "\nWarnings\n"))
            for w in ev["warnings"]:
                lines.append(("warn", f"  ⚠ {w}\n"))
        txt = "".join(t for _, t in lines)
        if txt != self._status_txt:
            self._status_txt = txt
            self.status.delete("1.0", "end")
            for tag, t in lines:
                self.status.insert("end", t, tag)

    def _tick(self):
        try:
            core.update_inputs()
            with core.LOCK:
                ev = core.evaluate()
                objs = [(k, dict(v)) for k, v in core.OBJ.items()]
                if self.hover_pt and self.hover_ver != core.VERSION[0]:
                    if self.hover_pt.startswith("m:") and self.hover_pt.split(":")[1] not in core.OBJ:
                        self.hover_pt = None
                    self.hover_pts = core.net_points(self.hover_pt) if self.hover_pt else []
                    self.hover_ver = core.VERSION[0]
                    if self.hover_pt:
                        names = [describe(q) for q in self.hover_pts if q.startswith(("pi:", "m:"))]
                        self.info.config(text=describe(self.hover_pt) + (
                            "   ⟶ connected to: " + ", ".join(names) if names else ""))
                if not self.hover_pt:
                    self.hover_pts = []
                    self.info.config(text="")
            self.last_eval = ev
            self._draw_dynamic(ev, objs)
            self._update_status(ev)
            while True:
                try:
                    m = core.LOG_Q.get_nowait()
                except Exception:
                    break
                self.log.insert("end", m + "\n")
                self.log.see("end")
        except Exception as ex:  # the GUI must never die
            import traceback
            traceback.print_exc()
            self._hint(f"Internal simulator error: {ex}", err=True)
        self.root.after(40, self._tick)

    def _sound_loop(self):
        while True:
            ev = self.last_eval
            freq = None
            if ev:
                freq = next((f for f in ev["buz"].values() if f), None)
            if freq and winsound:
                winsound.Beep(int(min(max(freq, 37), 32767)), 60)
            else:
                time.sleep(0.02)


def run(ready=None):
    root = tk.Tk()
    App(root)
    if ready is not None:
        root.after(50, ready.set)
    root.mainloop()
