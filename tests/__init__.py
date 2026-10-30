"""Makes FreeCAD importable in the tests (run them with FreeCAD's python.exe)."""
import os
import sys

_BIN = os.environ.get("FREECAD_BIN", r"C:\Program Files\FreeCAD 1.1\bin")
for _p in (_BIN, os.path.join(os.path.dirname(_BIN), "lib")):
    if _p not in sys.path:
        sys.path.append(_p)

import FreeCAD  # noqa: E402,F401
import Fem  # noqa: E402,F401  (registers the paths of the femmesh/femtools modules)
