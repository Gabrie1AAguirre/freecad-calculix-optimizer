import os
import subprocess
import sys
import tempfile
import time
import unittest

import optimize
from tests.util import L_EXAMPLE, ROOT

LAUNCHER = os.path.join(ROOT, "optimize.py")


def run(*args):
    env = dict(os.environ, PYTHONIOENCODING="")
    proc = subprocess.run([sys.executable, LAUNCHER] + list(args), capture_output=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


class TestLauncher(unittest.TestCase):
    def test_missing_freecad(self):
        code, output = run(L_EXAMPLE, "--freecad", r"C:\does\not\exist")
        self.assertEqual(code, 1)
        self.assertIn("--freecad", output)
        self.assertIn("Could not find FreeCAD", output)

    def test_missing_part(self):
        code, output = run(os.path.join(tempfile.gettempdir(), "does_not_exist.FCStd"))
        self.assertEqual(code, 1)
        self.assertIn("Could not find the file", output)

    def test_end_code(self):
        self.assertEqual(optimize.read_end_code(["a", "### END code=0"]), 0)
        self.assertEqual(optimize.read_end_code(["### END code=2\n"]), 2)
        self.assertEqual(optimize.read_end_code(["### END code=1"]), 1)
        self.assertIsNone(optimize.read_end_code(["no end"]))

    def test_freecad_does_not_get_ctrl_c(self):
        # On Windows Ctrl+C goes to every process on the console; FreeCAD is in a group of
        # its own so it is not interrupted halfway — what stops it is the 'stop' file.
        options = optimize._process_options()
        self.assertTrue(options["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)

    def test_choose_prepomax(self):
        folder = tempfile.mkdtemp()
        exe = os.path.join(folder, "PrePoMax.exe")
        open(exe, "w").close()
        self.assertEqual(optimize._choose_prepomax(folder, no_prepomax=False, gui=True), (exe, None))
        # Without a window (--headless) or with --no-prepomax, PrePoMax does not open.
        self.assertEqual(optimize._choose_prepomax(folder, no_prepomax=True, gui=True), (None, None))
        self.assertEqual(optimize._choose_prepomax(folder, no_prepomax=False, gui=False), (None, None))

    def test_prepomax_not_found_warns(self):
        exe, warning = optimize._choose_prepomax(tempfile.mkdtemp(), no_prepomax=False, gui=True)
        self.assertIsNone(exe)
        self.assertIn("--prepomax", warning)

    def test_returns_to_terminal_without_waiting_for_freecad_to_close(self):
        # With the window open FreeCAD keeps running; the launcher must return
        # as soon as the log marks the end.
        folder = tempfile.mkdtemp()
        log = os.path.join(folder, "log.txt")
        with open(log, "w", encoding="utf-8") as f:
            f.write("line\n### END code=0\n")
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(process.kill)
        start = time.time()
        lines = optimize._follow(process, log, os.path.join(folder, "stop"))
        self.assertLess(time.time() - start, 5)
        self.assertEqual(optimize.read_end_code(lines), 0)


if __name__ == "__main__":
    unittest.main()
