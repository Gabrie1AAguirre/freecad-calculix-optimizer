"""Tests of the FreeCAD window (opens the real freecad.exe, which closes by itself)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import FreeCAD as App

from optimizer import split_screen
from tests.util import FREECAD_BIN, ROOT

# Runs inside FreeCAD: splits the screen as in an optimization with PrePoMax and records the result.
SCRIPT = """import json, sys
sys.path.insert(0, %(root)r)
import FreeCADGui as Gui
from PySide import QtWidgets
from optimizer import gui
gui.keep_saved_window()
gui.left_half()
window = Gui.getMainWindow()
panels = [d.width() for d in window.findChildren(QtWidgets.QDockWidget) if d.isVisible() and not d.isFloating()]
with open(%(output)r, "w") as f:
    json.dump({"window": window.width(), "panels": panels}, f)
gui.close()
"""


def _saved_window():
    """What FreeCAD saves of the window when it closes (user.cfg): size, maximized and panels."""
    with open(os.path.join(App.getUserConfigDir(), "user.cfg"), encoding="utf-8") as f:
        text = f.read()
    return re.findall(r'<FC\w+ Name="(?:Geometry|Maximized|MainWindowState)"[^>]*>(?:[^<]*</FC\w+>)?', text)


@unittest.skipUnless(os.name == "nt", "Windows only")
class TestSplitScreenGui(unittest.TestCase):
    def test_narrow_panel_and_nothing_saved(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        script, output = os.path.join(folder, "split.py"), os.path.join(folder, "sizes.json")
        with open(script, "w", encoding="utf-8") as f:
            f.write(SCRIPT % {"root": ROOT, "output": output})
        before = _saved_window()
        subprocess.run([os.path.join(FREECAD_BIN, "freecad.exe"), script], timeout=120, capture_output=True)
        with open(output) as f:
            sizes = json.load(f)
        # The Model/Tasks panel becomes narrow so the part shows up larger.
        self.assertTrue(sizes["panels"])
        self.assertLessEqual(max(sizes["panels"]), sizes["window"] // split_screen.PANEL_RATIO + 10)
        # All of this only this time: the user's FreeCAD keeps opening as before.
        self.assertEqual(_saved_window(), before)


if __name__ == "__main__":
    unittest.main()
