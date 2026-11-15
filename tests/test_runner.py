"""Running, stopping and restarting scripts inside the simulator."""
import os
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["RPISIM_HEADLESS"] = "1"
os.environ.setdefault("RPISIM_CIRCUIT", os.path.join(tempfile.mkdtemp(), "circuit.json"))
sys.path.insert(0, ROOT)

import RPi.GPIO as GPIO  # noqa: E402,F401
from RPi import _core as core  # noqa: E402
from RPi import _runner as runner  # noqa: E402

TMP = tempfile.mkdtemp()


def script(name, body):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))
    return path


def drain_log():
    lines = []
    while not core.LOG_Q.empty():
        lines.append(core.LOG_Q.get_nowait())
    return "\n".join(lines)


def wait_for(pred, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


BLINK = """
    import time
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(17, GPIO.OUT)
    try:
        while True:
            GPIO.output(17, 1)
            time.sleep(0.4)
            GPIO.output(17, 0)
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("cleanup ran")
        GPIO.cleanup()
"""


class RunnerTest(unittest.TestCase):
    def setUp(self):
        runner.stop()
        drain_log()

    def tearDown(self):
        runner.stop()

    def test_stop_interrupts_sleep_and_runs_cleanup(self):
        runner.start(script("blink.py", BLINK))
        self.assertTrue(wait_for(lambda: 17 in core.PINS))
        t = time.perf_counter()
        self.assertTrue(runner.stop())
        self.assertLess(time.perf_counter() - t, 0.5)
        self.assertEqual(runner.status(), "stopped")
        self.assertEqual(core.PINS, {})
        self.assertIsNone(core.MODE[0])
        self.assertIn("» cleanup ran", drain_log())

    def test_busy_loop_is_stopped(self):
        runner.start(script("busy.py", "x = 0\nwhile True:\n    x += 1\n"))
        time.sleep(0.1)
        self.assertTrue(runner.stop())
        self.assertEqual(runner.status(), "stopped")

    def test_input_waits_for_stop(self):
        runner.start(script("wait.py", 'input("Press Enter to exit...")\n'))
        time.sleep(0.2)
        self.assertTrue(runner.is_running())
        self.assertTrue(runner.stop())
        self.assertEqual(runner.status(), "stopped")

    def test_crash_is_reported(self):
        runner.start(script("crash.py", "raise ValueError('boom')\n"))
        self.assertTrue(wait_for(lambda: not runner.is_running()))
        self.assertEqual(runner.status(), "crashed")
        self.assertIn("ValueError: boom", drain_log())

    def test_finished_script_resets_pins(self):
        runner.start(script("once.py", """
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(17, GPIO.OUT, initial=1)
            print("done")
        """))
        self.assertTrue(wait_for(lambda: not runner.is_running()))
        self.assertEqual(runner.status(), "finished")
        self.assertEqual(core.PINS, {})
        self.assertIn("» done", drain_log())

    def test_restart_with_gpiozero_frees_pins(self):
        runner.start(script("zero.py", """
            from gpiozero import LED, pause
            led = LED(17)
            led.blink(0.05, 0.05)
            pause()
        """))
        self.assertTrue(wait_for(lambda: 17 in core.PINS))
        self.assertTrue(runner.restart())
        time.sleep(0.2)
        self.assertEqual(runner.status(), "running")      # no GPIOPinInUse on the second run
        self.assertNotIn("crashed", drain_log())

    def test_short_sleeps_keep_precision(self):
        runner.start(script("precise.py", """
            import time
            t = time.perf_counter()
            for _ in range(20):
                time.sleep(0.001)
            print("elapsed", round(time.perf_counter() - t, 3))
        """))
        self.assertTrue(wait_for(lambda: not runner.is_running()))
        elapsed = float(drain_log().split("elapsed ")[1].split()[0])
        self.assertLess(elapsed, 0.2)

    def test_core_threads_keep_real_sleep(self):
        import time as t
        self.assertIs(t.sleep, runner._sleep if runner._installed else t.sleep)
        start = t.perf_counter()
        t.sleep(0.12)                                     # not the script thread: one plain sleep
        self.assertGreaterEqual(t.perf_counter() - start, 0.11)


if __name__ == "__main__":
    unittest.main()
