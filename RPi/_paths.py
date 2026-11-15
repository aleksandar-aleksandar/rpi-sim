"""Which circuit file belongs to which script (no side effects on import).

A script `foo.py` is paired with `foo.json` next to it. Bundled presets in
examples/ are never written to: running an example works on a copy in
~/.rpi-sim/examples/ (or $RPISIM_HOME/examples/).
"""
import os
import shutil


def presets_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def work_dir():
    return os.environ.get("RPISIM_HOME") or os.path.join(os.path.expanduser("~"), ".rpi-sim")


def is_preset(path):
    p = os.path.normcase(os.path.abspath(path))
    return os.path.dirname(p) == os.path.normcase(presets_dir()) and p.endswith(".json")


def circuit_for(script=None):
    """-> (circuit file to use, bundled preset it should start from or None)."""
    if script:
        path = os.path.splitext(os.path.abspath(script))[0] + ".json"
    else:
        path = os.path.abspath("circuit.json")
    if is_preset(path) and os.path.exists(path):
        return os.path.join(work_dir(), "examples", os.path.basename(path)), path
    return path, None


def copy_preset(preset, target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(preset, target)
