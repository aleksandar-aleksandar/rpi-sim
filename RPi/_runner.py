"""
Run user scripts inside the simulator, so they can be started, stopped and
restarted from the window without touching the terminal.

The script runs on its own thread against the circuit currently on the board.
Stopping is cooperative where possible and forced where needed:

* time.sleep() in the script thread wakes up every 50 ms to check for Stop,
* input() in the script waits until Stop (scripts use it to "stay alive"),
* otherwise a ScriptStopped exception is injected into the thread.

ScriptStopped is a KeyboardInterrupt, so a script's usual
`except KeyboardInterrupt: GPIO.cleanup()` still runs.
"""
import ctypes
import io
import os
import runpy
import sys
import threading
import time
import traceback

from . import _core as core


class ScriptStopped(KeyboardInterrupt):
    """Raised inside a running script when Stop is pressed."""


_orig_sleep = time.sleep
STATE = {"script": None, "args": [], "thread": None, "status": "idle", "stop": threading.Event()}
_lock = threading.RLock()


# ---------------------------------------------------------------- patches
def _is_script_thread():
    return threading.current_thread() is STATE["thread"]


def _sleep(secs):
    if not _is_script_thread():
        return _orig_sleep(secs)
    stop = STATE["stop"]
    if stop.is_set():
        raise ScriptStopped()
    if secs < 0.05:                       # short sleeps keep full precision (e.g. 10 µs triggers)
        return _orig_sleep(secs)
    end = time.perf_counter() + secs
    while True:
        left = end - time.perf_counter()
        if left <= 0:
            return
        _orig_sleep(min(left, 0.05))
        if stop.is_set():
            raise ScriptStopped()


def _input(prompt=""):
    """Replacement for input() inside scripts: waits until Stop."""
    if prompt:
        print(prompt, end="", flush=True)
    core.log("(script is waiting – press Stop to end it)")
    while not STATE["stop"].wait(0.1):
        pass
    raise ScriptStopped()


def _pause():
    while True:
        time.sleep(3600)


class _Tee(io.TextIOBase):
    """Mirror the script's print() output into the simulator log."""

    def __init__(self, orig):
        self._orig = orig
        self._buf = ""

    def write(self, s):
        try:
            self._orig.write(s)
        except Exception:
            pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            core.log("» " + line)
        return len(s)

    def flush(self):
        try:
            self._orig.flush()
        except Exception:
            pass


_installed = False


def _install_patches():
    global _installed
    if _installed:
        return
    time.sleep = _sleep
    try:
        import signal
        if hasattr(signal, "pause"):
            signal.pause = _pause
    except Exception:
        pass
    _installed = True


# ---------------------------------------------------------------- GPIO reset
def reset_gpio():
    """Return the Pi to a clean state: close gpiozero devices, stop PWM, free pins."""
    zero = sys.modules.get("gpiozero")
    if zero is not None and hasattr(zero, "_close_all"):
        try:
            zero._close_all()
        except Exception:
            pass
    with core.LOCK:
        for st in core.PINS.values():
            if st["pwm"] is not None:
                st["pwm"].running = False
        core.PINS.clear()
        core.ECHO_PINS.clear()
        core.MODE[0] = None
        while True:
            try:
                core.CB_Q.get_nowait()
            except Exception:
                break
    core.update_inputs()


# ---------------------------------------------------------------- run / stop
def status():
    return STATE["status"]


def script():
    return STATE["script"]


def is_running():
    t = STATE["thread"]
    return t is not None and t.is_alive()


def start(path, args=()):
    """Run `path` against the current board. Stops a running script first."""
    path = os.path.abspath(path)
    with _lock:
        if not stop():
            return False
        reset_gpio()
        _install_patches()
        STATE["stop"] = threading.Event()
        STATE["script"] = path
        STATE["args"] = list(args)
        STATE["status"] = "running"
        t = threading.Thread(target=_run, args=(path, list(args)), name="rpi-sim script", daemon=True)
        STATE["thread"] = t
        t.start()
        return True


def restart():
    if STATE["script"]:
        return start(STATE["script"], STATE["args"])
    return False


def stop(timeout=2.0):
    """Stop the running script. Returns False if it refuses to stop in time."""
    t = STATE["thread"]
    if t is None or not t.is_alive():
        return True
    STATE["stop"].set()
    t.join(0.3)
    if t.is_alive():                      # busy loop without sleep: inject the exception
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(t.ident), ctypes.py_object(ScriptStopped))
        t.join(timeout)
    if t.is_alive():
        core.log("⚠ The script did not stop (it may be blocked in a long system call).")
        return False
    return True


def _run(path, args):
    name = os.path.basename(path)
    old_argv, old_stdout = sys.argv, sys.stdout
    folder = os.path.dirname(path)
    sys.argv = [path] + args
    if folder not in sys.path:
        sys.path.insert(0, folder)
    sys.stdout = _Tee(old_stdout)
    core.log(f"▶ Running {name}")
    result = "finished"
    try:
        runpy.run_path(path, run_name="__main__", init_globals={"input": _input})
    except KeyboardInterrupt:             # includes ScriptStopped and the script's own Ctrl+C
        result = "stopped"
    except SystemExit:
        result = "finished"
    except BaseException as ex:
        result = "crashed"
        tb = traceback.format_exc()
        for line in tb.rstrip().splitlines():
            core.log("✖ " + line)
        try:
            old_stdout.write(tb)
        except Exception:
            pass
        core.log(f"✖ {name} crashed: {ex!r}")
    finally:
        if result == "finished" and STATE["stop"].is_set():
            result = "stopped"            # the script caught the interrupt and exited cleanly
        sys.stdout = old_stdout
        sys.argv = old_argv
        try:
            reset_gpio()
        except Exception:
            pass
        STATE["status"] = result
        icon = {"finished": "■", "stopped": "■", "crashed": "✖"}[result]
        core.log(f"{icon} {name} {result}")
