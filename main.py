"""
rpi-sim - run a Raspberry Pi GPIO script on your PC.

Usage:
    python main.py                         open the editor (circuit.json in the current folder)
    python main.py my_script.py            run a script; circuit = my_script.json next to it
    python main.py -c board.json script.py run a script with a specific circuit file
    python main.py examples/01_blink.py    run a bundled example with its preset circuit
"""
import argparse
import os
import runpy
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(prog="rpi-sim", description="Raspberry Pi GPIO simulator")
    ap.add_argument("-c", "--circuit", help="circuit file to load / auto-save (.json)")
    ap.add_argument("script", nargs="?", help="Python script that uses RPi.GPIO")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the script")
    a = ap.parse_args()

    if a.circuit:
        circuit = a.circuit
    elif a.script:
        circuit = os.path.splitext(a.script)[0] + ".json"
    else:
        circuit = "circuit.json"
    os.environ["RPISIM_CIRCUIT"] = os.path.abspath(circuit)

    sys.path.insert(0, ROOT)  # makes `import RPi.GPIO` resolve to the simulator
    if a.script:
        script = os.path.abspath(a.script)
        if not os.path.exists(script):
            ap.error(f"script not found: {a.script}")
        sys.argv = [script] + a.args
        sys.path.insert(0, os.path.dirname(script))
        runpy.run_path(script, run_name="__main__")
    else:
        import RPi.GPIO  # noqa: F401 - opens the window; it stays open until closed


if __name__ == "__main__":
    main()
