"""
rpi-sim - run a Raspberry Pi GPIO script on your PC.

Usage (`rpi-sim` when installed, `python main.py` from a clone):
    rpi-sim                                open the editor (circuit.json in the current folder)
    rpi-sim my_script.py                   run a script; circuit = my_script.json next to it
    rpi-sim -c board.json my_script.py     run a script with a specific circuit file
    rpi-sim examples/01_blink.py           run a bundled example with its preset circuit

The script runs inside the simulator window: Run / Restart (F5) / Stop
(Shift+F5) are in the toolbar, and Ctrl+C in the terminal stops the script
while keeping the window open. Bundled presets are never modified: an example
starts from its preset every run, and edits are saved to ~/.rpi-sim/.
"""
import argparse
import os
import runpy
import sys
import time

from . import __version__

# repository root (the folder that contains RPi/, gpiozero/ and examples/)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # makes `import RPi.GPIO` / `gpiozero` resolve to the simulator

from RPi import _paths  # noqa: E402  (side-effect free)

PRESETS_DIR = _paths.presets_dir()
work_dir = _paths.work_dir
is_preset = _paths.is_preset


def resolve_circuit(script=None, circuit=None):
    """-> (circuit file to use, note or None). Copies presets to a working file."""
    if circuit:                                   # explicit -c always wins, even for presets
        return os.path.abspath(circuit), None
    path, preset = _paths.circuit_for(script)
    if preset:
        _paths.copy_preset(preset, path)
        return path, (f"Started from preset {os.path.basename(preset)}; "
                      f"your edits are saved to {path}")
    return path, None


def _wait_for_window(runner, core):
    """Keep the process alive while the window is open; Ctrl+C stops the script first."""
    while True:
        try:
            while core.ui_alive():
                time.sleep(0.2)
            return
        except KeyboardInterrupt:
            if runner.is_running():
                runner.stop()
                print("\n[rpi-sim] Script stopped. Press F5 in the window to run it again, "
                      "or Ctrl+C / close the window to quit.")
            else:
                return


def main():
    ap = argparse.ArgumentParser(prog="rpi-sim", description="Raspberry Pi GPIO simulator")
    ap.add_argument("--version", action="version", version=f"rpi-sim {__version__}")
    ap.add_argument("-c", "--circuit", help="circuit file to load / auto-save (.json)")
    ap.add_argument("script", nargs="?", help="Python script that uses RPi.GPIO or gpiozero")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the script")
    a = ap.parse_args()

    if a.script and not os.path.exists(a.script):
        ap.error(f"script not found: {a.script}")
    circuit, note = resolve_circuit(a.script, a.circuit)
    os.environ["RPISIM_CIRCUIT"] = circuit

    from RPi import _core as core
    if note:
        core.log(note)
        print(f"[rpi-sim] {note}")

    headless = bool(os.environ.get("RPISIM_HEADLESS"))
    if a.script and headless:                     # no window: run the script directly, as before
        script = os.path.abspath(a.script)
        sys.argv = [script] + a.args
        sys.path.insert(0, os.path.dirname(script))
        runpy.run_path(script, run_name="__main__")
        return

    import RPi.GPIO  # noqa: F401 - opens the window
    from RPi import _runner as runner
    if a.script:
        runner.start(a.script, a.args)
    _wait_for_window(runner, core)
    os._exit(0)


if __name__ == "__main__":
    main()
