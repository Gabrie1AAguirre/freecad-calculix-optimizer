"""Slow tests: run the real optimize.py (FreeCAD + Gmsh + CalculiX)."""
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import FreeCAD as App

from optimizer import prepomax, split_screen
from tests.util import L_EXAMPLE, ORIGINAL_L, ROOT, sha256, visible_part

LAUNCHER = os.path.join(ROOT, "optimize.py")
PARAMETERS = {"corner_radius": (1, 20), "vertical_thickness": (20, 45), "horizontal_thickness": (20, 45)}


def _number(text):
    return float(text) if text else None


def _prepomax_processes(folder):
    """(pid, command line) of the PrePoMax instances opened with a file from this folder."""
    # UTF-8 output: otherwise the "ç" of the test folder arrives garbled and nothing matches.
    script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
              "Get-CimInstance Win32_Process -Filter \"Name='PrePoMax.exe'\" | "
              "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }")
    output = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                            encoding="utf-8", errors="replace").stdout
    lines = [l.split("|", 1) for l in output.splitlines() if "|" in l]
    return [(int(pid), cmd) for pid, cmd in lines if os.path.normcase(folder) in os.path.normcase(cmd)]


def _freecad_child(pid):
    """PID of the FreeCAD opened by the launcher."""
    script = ("Get-CimInstance Win32_Process -Filter \"ParentProcessId=%d AND Name='freecad.exe'\" | "
              "ForEach-Object { $_.ProcessId }" % pid)
    output = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True).stdout
    return int(output.split()[0])


def _freecad_saved_window():
    """Window size and state that FreeCAD saves when it closes (user.cfg)."""
    with open(os.path.join(App.getUserConfigDir(), "user.cfg"), encoding="utf-8") as f:
        text = f.read()
    return re.findall(r'<FC\w+ Name="(?:Geometry|Maximized)"[^>]*>(?:[^<]*</FC\w+>)?', text)


def _close_prepomax(folder):
    # Through the X: when killed, PrePoMax would leave a recovery file.
    for pid, _ in _prepomax_processes(folder):
        if not prepomax.close_like_x(pid):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        self.folder = os.path.join(base, "folder with space ç")
        os.makedirs(self.folder)
        self.results = os.path.join(self.folder, "res")

    def _part(self, max_iterations):
        destination = os.path.join(self.folder, "L_part.FCStd")
        shutil.copy(L_EXAMPLE, destination)
        doc = App.openDocument(destination)
        sheet = doc.getObject("Parameters")
        sheet.set(sheet.getCellFromAlias("max_iterations"), str(max_iterations))
        doc.recompute()
        doc.save()
        App.closeDocument(doc.Name)
        return destination

    def _run(self, *args, timeout=900):
        proc = subprocess.run([sys.executable, LAUNCHER] + list(args), capture_output=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        return proc.returncode, proc.stdout + proc.stderr

    def _no_backups(self):
        backups = [os.path.join(r, n) for r, _, ns in os.walk(self.results) for n in ns if n.endswith(".FCBak")]
        self.assertEqual(backups, [])

    def _history(self):
        with open(os.path.join(self.results, "history.csv"), encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def test_headless(self):
        part = self._part(6)
        before = sha256(part)
        code, output = self._run(part, "--headless", "--results", self.results)
        self.assertIn(code, (0, 2), output)
        for name in ("L_part_optimized.FCStd", "L_part_optimized.frd", "history.csv", "chart.png", "log.txt"):
            self.assertTrue(os.path.exists(os.path.join(self.results, name)), name)
        with open(os.path.join(self.results, "L_part_optimized.frd"), encoding="latin-1") as f:
            blocks = [l.split()[1] for l in f if l.strip().startswith("-4")]
        self.assertEqual(blocks[0], "STRESS")  # PrePoMax opens directly on the Von Mises
        rows = self._history()
        self.assertEqual(len(rows), 6)
        valid = [r for r in rows if r["von_mises_mpa"]]
        base = _number(rows[0]["von_mises_mpa"])
        self.assertLess(min(_number(r["von_mises_mpa"]) for r in valid), base)
        for row in rows:
            for alias, (minimum, maximum) in PARAMETERS.items():
                self.assertTrue(minimum - 1e-6 <= _number(row[alias]) <= maximum + 1e-6, row)
        self.assertEqual(sha256(part), before)
        self._no_backups()
        self.assertIn("Baseline", output)
        self.assertIn("VonMises_max", output)

    def test_check_ok(self):
        code, output = self._run(self._part(30), "--check")
        self.assertEqual(code, 0, output)
        self.assertIn("ready", output)

    def test_check_error(self):
        code, output = self._run(ORIGINAL_L, "--check")
        self.assertEqual(code, 1, output)
        self.assertIn("Parameters", output)

    def test_stop(self):
        part = self._part(30)
        os.makedirs(self.results)
        open(os.path.join(self.results, "stop"), "w").close()
        code, output = self._run(part, "--headless", "--results", self.results)
        self.assertIn(code, (0, 2), output)
        self.assertEqual(len(self._history()), 1)
        self.assertTrue(os.path.exists(os.path.join(self.results, "L_part_optimized.FCStd")))
        self.assertIn("Stop requested by the user", output)

    def test_gui_smoke(self):
        part = self._part(2)
        code, output = self._run(part, "--results", self.results, "--close-when-done", "--no-prepomax")
        self.assertIn(code, (0, 2), output)
        self.assertEqual(len(self._history()), 2)
        self.assertTrue(os.path.exists(os.path.join(self.results, "view.png")))
        self._no_backups()

    @unittest.skipUnless(prepomax.find(), "PrePoMax not installed")
    def test_gui_with_prepomax(self):
        part = self._part(2)
        self.addCleanup(_close_prepomax, self.results)
        saved_window = _freecad_saved_window()
        launcher = subprocess.Popen([sys.executable, LAUNCHER, part, "--results", self.results,
                                     "--close-when-done"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    encoding="utf-8", errors="replace")
        self.addCleanup(lambda: launcher.poll() is None and launcher.kill())
        # Split screen, measured while optimizing (FreeCAD closes at the end): it is on the left.
        freecad, freecad_pid, end = None, None, time.time() + 600
        while freecad is None and launcher.poll() is None and time.time() < end:
            time.sleep(1)
            try:
                with open(os.path.join(self.results, "log.txt"), encoding="utf-8") as f:
                    iterated = re.search(r"^\s+1\s+\d", f.read(), re.M)
            except OSError:
                iterated = None
            if iterated:
                freecad_pid = _freecad_child(launcher.pid)
                freecad = visible_part(freecad_pid)
        output = launcher.communicate(timeout=900)[0]
        while freecad_pid and prepomax._process_alive(freecad_pid) and time.time() < end:
            time.sleep(0.5)  # the terminal returns before FreeCAD closes (and saves its settings)
        self.assertIn(launcher.returncode, (0, 2), output)
        self.assertEqual(freecad, split_screen.half(split_screen.work_area(), split_screen.LEFT))
        # The split screen is only this time: the user's FreeCAD keeps opening as before.
        self.assertEqual(_freecad_saved_window(), saved_window)
        self.assertNotIn("Could not find PrePoMax", output)
        # A single window, updated at every iteration, stays open at the end with the best one;
        # the iteration copies were deleted.
        self.assertEqual(len(_prepomax_processes(self.results)), 1)
        self.assertEqual(os.listdir(os.path.join(self.results, "work", "prepomax")), [])
        self.assertTrue(os.path.exists(os.path.join(self.results, "L_part_optimized.frd")))
        self.assertIn("opened in PrePoMax", output)
        with open(os.path.join(self.results, "work", "prepomax_window.log"), encoding="utf-8") as f:
            window_log = f.read()
        self.assertNotIn("failed", window_log)  # every swap in the same window worked
        _close_prepomax(self.results)
        self.assertFalse(os.path.exists(prepomax.recovery_file(prepomax.find())))


if __name__ == "__main__":
    unittest.main()
