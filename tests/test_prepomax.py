import os
import shutil
import sys
import tempfile
import time
import unittest

from optimizer import prepomax, split_screen
from tests.util import visible_part

FRD = """    1C
    2C                             2                                     1
 -1         1 0.00000E+00 0.00000E+00 0.00000E+00
 -3
    1PSTEP                         1           1           1
 -4  DISP        4    1
 -1         1 1.00000E-03 0.00000E+00 0.00000E+00
 -3
    1PSTEP                         2           1           1
 -4  STRESS      6    1
 -1         1 2.50000E+02 0.00000E+00 0.00000E+00
 -3
 9999
"""

# Arbitrary content in place of PrePoMax's recovery file (history.pmh).
FAKE_HISTORY = b"optimizer test history"

# Fake program in place of PrePoMax: records its arguments and stays open.
FAKE = """import os, sys, time
open(sys.argv[1], "w").write("\\n".join(sys.argv[2:] + [os.getcwd()]))
time.sleep(120)
"""


def _blocks(text):
    return [l.split()[1] for l in text.splitlines() if l.strip().startswith("-4")]


class TestFrd(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.source = os.path.join(self.folder, "a.frd")

    def test_stress_comes_first(self):
        # PrePoMax opens showing the first block of the .frd: this way it opens on the Von Mises.
        with open(self.source, "w") as f:
            f.write(FRD)
        destination = os.path.join(self.folder, "b.frd")
        prepomax.stress_first(self.source, destination)
        with open(destination) as f:
            text = f.read()
        self.assertEqual(_blocks(text), ["STRESS", "DISP"])
        self.assertEqual(sorted(text.splitlines()), sorted(FRD.splitlines()))
        self.assertTrue(text.startswith("    1C\n"))
        self.assertEqual(text.splitlines()[-1].strip(), "9999")

    def test_without_stress_copies_unchanged(self):
        without_stress = FRD.replace("STRESS", "TOSTRAIN")
        with open(self.source, "w") as f:
            f.write(without_stress)
        destination = os.path.join(self.folder, "b.frd")
        prepomax.stress_first(self.source, destination)
        with open(destination) as f:
            self.assertEqual(f.read(), without_stress)


class TestFind(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, True)

    def _install(self, name):
        folder = os.path.join(self.base, name)
        os.makedirs(folder)
        open(os.path.join(folder, "PrePoMax.exe"), "w").close()
        return folder

    def test_given_folder(self):
        folder = self._install("anything")
        self.assertEqual(prepomax.find(folder, environment={}, locations=[]), os.path.join(folder, "PrePoMax.exe"))

    def test_given_folder_without_exe(self):
        self.assertIsNone(prepomax.find(self.base, environment={}, locations=[]))

    def test_environment_variable(self):
        folder = self._install("env")
        self.assertEqual(prepomax.find(None, environment={"PREPOMAX_BIN": folder}, locations=[]),
                         os.path.join(folder, "PrePoMax.exe"))

    def test_finds_newest_version(self):
        self._install("PrePoMax v2.5.10")
        self._install("PrePoMax v2.6.0")
        self._install("PrePoMax v2.10.1")
        found = prepomax.find(None, environment={}, locations=[os.path.join(self.base, "PrePoMax*")])
        self.assertEqual(found, os.path.join(self.base, "PrePoMax v2.10.1", "PrePoMax.exe"))

    def test_not_found(self):
        self.assertIsNone(prepomax.find(None, environment={}, locations=[os.path.join(self.base, "PrePoMax*")]))


class _Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.copies = os.path.join(self.folder, "copies")
        self.frd = os.path.join(self.folder, "ccx.frd")
        with open(self.frd, "w") as f:
            f.write(FRD)


class TestViewerWithoutWindow(_Base):
    """With a fake program in place of PrePoMax (no window to drive)."""

    def setUp(self):
        super().setUp()
        self.fake = os.path.join(self.folder, "fake.py")
        with open(self.fake, "w") as f:
            f.write(FAKE)
        self.record = os.path.join(self.folder, "record.txt")
        self.viewer = prepomax.Viewer([sys.executable, self.fake, self.record], self.copies, drive_window=False)
        self.addCleanup(self.viewer.close)

    def _arguments(self):
        for _ in range(100):
            if os.path.exists(self.record) and os.path.getsize(self.record):
                with open(self.record) as f:
                    return f.read().splitlines()
            time.sleep(0.1)
        self.fail("the program was not started")

    def test_opens_copy_with_stress_first(self):
        self.viewer.show(self.frd)
        args = self._arguments()
        self.assertEqual(args[0], "-f")
        self.assertEqual(os.path.dirname(args[1]), self.copies)  # a copy: CalculiX overwrites the original
        self.assertEqual(args[2:4], ["-u", "MM_TON_S_C"])
        # Opened by FreeCAD, with FreeCAD's working folder, PrePoMax does not load the .frd.
        self.assertEqual(os.path.normcase(args[4]), os.path.normcase(os.path.dirname(sys.executable)))
        with open(args[1]) as f:
            self.assertEqual(_blocks(f.read()), ["STRESS", "DISP"])

    def test_without_driving_the_window_reopens(self):
        self.viewer.show(self.frd)
        first = self.viewer.process
        self.viewer.show(self.frd)
        self.assertIsNotNone(first.wait(timeout=10))  # the previous window was closed
        self.assertIsNone(self.viewer.process.poll())
        self.assertEqual(len(os.listdir(self.copies)), 1)  # the previous copy was deleted

    def test_final_file_is_not_deleted(self):
        final = os.path.join(self.folder, "final.frd")
        shutil.copy(self.frd, final)
        self.viewer.show(self.frd)
        self.viewer.show_file(final)
        self.assertTrue(os.path.exists(final))
        self.assertEqual(os.listdir(self.copies), [])


@unittest.skipUnless(prepomax.find(), "PrePoMax not installed")
class TestViewerPrePoMax(_Base):
    def setUp(self):
        super().setUp()
        self.recovery = prepomax.recovery_file(prepomax.find())
        if os.path.exists(self.recovery):
            self.skipTest("there is a PrePoMax recovery file from one of your sessions; leaving it alone")
        self.addCleanup(lambda: os.path.exists(self.recovery) and os.remove(self.recovery))
        from optimizer.fea import frd_file, run_fea
        from optimizer.model import find_model
        from tests.util import L_EXAMPLE, open_copy
        ccx = os.path.join(self.folder, "ccx")
        run_fea(find_model(open_copy(L_EXAMPLE, self)), ccx)
        self.frd = frd_file(ccx)

    def test_updates_the_same_window(self):
        viewer = prepomax.Viewer([prepomax.find()], self.copies)
        self.addCleanup(viewer.close)
        viewer.show(self.frd)
        viewer.wait()
        self.assertTrue(viewer.last_drive_ok, "did not turn to the isometric view")
        pid = viewer.process.pid
        # Split screen: FreeCAD takes the left half.
        self.assertEqual(visible_part(pid), split_screen.half(split_screen.work_area(), split_screen.RIGHT))

        viewer.show(self.frd)
        viewer.wait()
        self.assertTrue(viewer.last_drive_ok, "did not open the new result in the window")
        self.assertEqual(viewer.process.pid, pid)       # same window
        self.assertEqual(visible_part(pid), split_screen.half(split_screen.work_area(), split_screen.RIGHT))
        self.assertIsNone(viewer.process.poll())
        self.assertEqual(len(os.listdir(self.copies)), 1)

        # When killed, PrePoMax leaves a recovery file and asks about it on the next
        # start (and does not load the .frd): it must be closed as if by the X.
        self.assertTrue(prepomax.close_like_x(viewer.process.pid))
        self.assertFalse(os.path.exists(self.recovery))

    def test_recovery_question_does_not_hang(self):
        # A recovery file from another session: kept, and the question answered "no".
        with open(self.recovery, "wb") as f:
            f.write(FAKE_HISTORY)
        viewer = prepomax.Viewer([prepomax.find()], self.copies)
        self.addCleanup(viewer.close)
        viewer.show(self.frd)
        viewer.wait()
        self.assertTrue(viewer.last_drive_ok)
        kept = [n for n in os.listdir(self.folder) if n.startswith("prepomax_recovery")]
        self.assertEqual(len(kept), 1)
        with open(os.path.join(self.folder, kept[0]), "rb") as f:
            self.assertEqual(f.read(), FAKE_HISTORY)


if __name__ == "__main__":
    unittest.main()
