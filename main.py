"""
rpi-sim - run a Raspberry Pi GPIO script on your PC.

Usage:
    python main.py                         open the editor (circuit.json in the current folder)
    python main.py my_script.py            run a script; circuit = my_script.json next to it
    python main.py -c board.json script.py run a script with a specific circuit file
    python main.py examples/01_blink.py    run a bundled example with its preset circuit

Bundled presets are never modified: an example starts from its preset every
run, and your edits are auto-saved to a working copy in ~/.rpi-sim/.
"""
import argparse
import os
import runpy
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PRESETS_DIR = os.path.join(ROOT, "examples")


def work_dir():
    return os.environ.get("RPISIM_HOME") or os.path.join(os.path.expanduser("~"), ".rpi-sim")


def is_preset(path):
    p = os.path.normcase(os.path.abspath(path))
    return os.path.dirname(p) == os.path.normcase(PRESETS_DIR) and p.endswith(".json")


def resolve_circuit(script=None, circuit=None):
    """-> (circuit file to use, note or None). Copies presets to a working file."""
    if circuit:                                   # explicit -c always wins, even for presets
        return os.path.abspath(circuit), None
    if script:
        path = os.path.splitext(os.path.abspath(script))[0] + ".json"
    else:
        path = os.path.abspath("circuit.json")
    if is_preset(path) and os.path.exists(path):
        copy = os.path.join(work_dir(), "examples", os.path.basename(path))
        os.makedirs(os.path.dirname(copy), exist_ok=True)
        shutil.copyfile(path, copy)
        return copy, (f"Started from preset {os.path.basename(path)}; "
                      f"your edits are saved to {copy}")
    return path, None


def main():
    ap = argparse.ArgumentParser(prog="rpi-sim", description="Raspberry Pi GPIO simulator")
    ap.add_argument("-c", "--circuit", help="circuit file to load / auto-save (.json)")
    ap.add_argument("script", nargs="?", help="Python script that uses RPi.GPIO")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the script")
    a = ap.parse_args()

    if a.script and not os.path.exists(a.script):
        ap.error(f"script not found: {a.script}")
    circuit, note = resolve_circuit(a.script, a.circuit)
    os.environ["RPISIM_CIRCUIT"] = circuit

    sys.path.insert(0, ROOT)  # makes `import RPi.GPIO` resolve to the simulator
    if note:
        from RPi import _core
        _core.log(note)
        print(f"[rpi-sim] {note}")
    if a.script:
        script = os.path.abspath(a.script)
        sys.argv = [script] + a.args
        sys.path.insert(0, os.path.dirname(script))
        runpy.run_path(script, run_name="__main__")
    else:
        import RPi.GPIO  # noqa: F401 - opens the window; it stays open until closed


if __name__ == "__main__":
    main()
