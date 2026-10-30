# Entry point run inside FreeCAD (freecad.exe or freecadcmd.exe).
# Reads the job named by the environment variable and calls optimizer.run.
import json as _json
import os as _os
import sys as _sys

with open(_os.environ["OPTIMIZER_JOB"], encoding="utf-8") as _f:
    _repo = _json.load(_f)["repo"]
if _repo not in _sys.path:
    _sys.path.insert(0, _repo)

from optimizer import run as _run  # noqa: E402

_run.start(_os.environ["OPTIMIZER_JOB"])
