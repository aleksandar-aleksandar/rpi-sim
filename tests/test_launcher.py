"""Tests for main.py circuit resolution (presets are never modified)."""
import filecmp
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main  # noqa: E402


class ResolveCircuitTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["RPISIM_HOME"] = self.home

    def tearDown(self):
        os.environ.pop("RPISIM_HOME", None)

    def test_example_runs_on_a_copy_of_its_preset(self):
        script = os.path.join(ROOT, "examples", "01_blink.py")
        preset = os.path.join(ROOT, "examples", "01_blink.json")
        path, note = main.resolve_circuit(script)
        self.assertEqual(path, os.path.join(self.home, "examples", "01_blink.json"))
        self.assertTrue(filecmp.cmp(path, preset, shallow=False))
        self.assertIn("01_blink.json", note)

    def test_each_run_starts_fresh_from_the_preset(self):
        script = os.path.join(ROOT, "examples", "01_blink.py")
        path, _ = main.resolve_circuit(script)
        with open(path, "w") as f:
            f.write("{}")
        path, _ = main.resolve_circuit(script)
        self.assertTrue(filecmp.cmp(path, os.path.join(ROOT, "examples", "01_blink.json"), shallow=False))

    def test_own_script_uses_json_next_to_it(self):
        d = tempfile.mkdtemp()
        path, note = main.resolve_circuit(os.path.join(d, "robot.py"))
        self.assertEqual(path, os.path.join(d, "robot.json"))
        self.assertIsNone(note)

    def test_explicit_circuit_wins(self):
        target = os.path.join(ROOT, "examples", "01_blink.json")
        path, note = main.resolve_circuit(os.path.join(ROOT, "examples", "01_blink.py"), target)
        self.assertEqual(path, os.path.abspath(target))
        self.assertIsNone(note)


if __name__ == "__main__":
    unittest.main()
