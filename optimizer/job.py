"""Description of a run, passed from the launcher to FreeCAD as JSON.
Standard library only (the launcher imports it too)."""
import json
from dataclasses import asdict, dataclass

ENVIRONMENT_VARIABLE = "OPTIMIZER_JOB"
LOG_NAME = "log.txt"
STOP_NAME = "stop"
END_MARK = "### END code="


@dataclass
class Job:
    mode: str  # "optimize" or "check"
    input: str
    folder: str
    gui: bool
    close_when_done: bool
    repo: str
    prepomax: str = None  # PrePoMax.exe to show the results; None paints the colors in FreeCAD


def save(job, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(job), f, ensure_ascii=False, indent=2)


def load(path):
    with open(path, encoding="utf-8") as f:
        return Job(**json.load(f))
