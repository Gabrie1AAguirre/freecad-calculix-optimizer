"""Shape optimizer for FreeCAD + CalculiX.

Usage:
    python optimize.py my_part.FCStd             # FreeCAD shows the part, PrePoMax the stresses
    python optimize.py my_part.FCStd --headless  # without opening a window
    python optimize.py my_part.FCStd --check     # only checks how the part is prepared

Runs with the system Python (standard library only): finds FreeCAD,
starts the optimization inside it and shows the progress here in the terminal.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from optimizer import prepomax  # noqa: E402
from optimizer.job import END_MARK, ENVIRONMENT_VARIABLE, LOG_NAME, STOP_NAME, Job, save  # noqa: E402

DEFAULT_FREECAD = r"C:\Program Files\FreeCAD 1.1\bin"
START = os.path.join(ROOT, "optimizer", "_start.py")
INTERVAL_S = 0.3


def read_end_code(lines):
    for line in reversed(lines):
        if line.startswith(END_MARK):
            return int(line[len(END_MARK):].strip())
    return None


def _freecad_folder(args):
    folder = args.freecad or os.environ.get("FREECAD_BIN") or DEFAULT_FREECAD
    if os.path.isdir(os.path.join(folder, "bin")):
        folder = os.path.join(folder, "bin")
    missing = [exe for exe in ("freecad.exe", "freecadcmd.exe") if not os.path.isfile(os.path.join(folder, exe))]
    return folder, missing


def _choose_prepomax(folder, no_prepomax, gui):
    """(PrePoMax.exe or None, warning or None). PrePoMax only opens with the interface."""
    if no_prepomax or not gui:
        return None, None
    exe = prepomax.find(folder)
    if exe is None:
        return None, ("Could not find PrePoMax%s: the stress colors will be shown in the FreeCAD window. To see "
                      "them in PrePoMax, give its folder with --prepomax \"C:\\...\\PrePoMax v2.6.0\"."
                      % (" in %s" % folder if folder else ""))
    return exe, None


def _command(freecad_folder, gui):
    if gui:
        return [os.path.join(freecad_folder, "freecad.exe"), START]
    return [os.path.join(freecad_folder, "freecadcmd.exe"), "-c",
            "exec(open(r'%s', encoding='utf-8').read())" % START]


def _process_options():
    """On Windows Ctrl+C goes to every process on the console. In a group of its
    own, FreeCAD (and CalculiX) are not interrupted halfway: the launcher gets the
    Ctrl+C and requests the stop through the 'stop' file."""
    return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}


def _follow(process, log_path, stop_path):
    """Prints the new log lines until FreeCAD finishes. Ctrl+C requests a stop."""
    read, lines = 0, []
    while True:
        try:
            finished = process.poll() is not None
            if os.path.exists(log_path):
                with open(log_path, encoding="utf-8") as f:
                    lines = f.read().splitlines()
                for line in lines[read:]:
                    if not line.startswith(END_MARK):
                        print(line, flush=True)
                read = len(lines)
            # With the interface FreeCAD stays open showing the result:
            # the terminal returns as soon as the log marks the end.
            if finished or read_end_code(lines) is not None:
                return lines
            time.sleep(INTERVAL_S)
        except KeyboardInterrupt:
            if not os.path.exists(stop_path):
                open(stop_path, "w").close()
                print("\nStop requested: finishing the current iteration and saving the best result...", flush=True)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Optimizes the shape of a FreeCAD part to reduce the Von Mises stress.")
    parser.add_argument("part", help="prepared .FCStd file (FEM analysis + Parameters spreadsheet)")
    parser.add_argument("--headless", action="store_true", help="runs without opening the FreeCAD window")
    parser.add_argument("--check", action="store_true", help="only checks whether the part is ready")
    parser.add_argument("--freecad", help="FreeCAD folder (the one with freecad.exe), if not the default one")
    parser.add_argument("--results", help="folder where the results are saved")
    parser.add_argument("--prepomax", help="PrePoMax folder (the one with PrePoMax.exe), if not found automatically")
    parser.add_argument("--no-prepomax", action="store_true",
                        help="does not open PrePoMax: the stress colors are shown in the FreeCAD window")
    parser.add_argument("--close-when-done", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    part = os.path.abspath(args.part)
    if not os.path.isfile(part):
        print("Could not find the file %s." % part)
        return 1
    freecad_folder, missing = _freecad_folder(args)
    if missing:
        print("Could not find FreeCAD in %s (missing %s). Give its folder with --freecad \"C:\\...\\FreeCAD 1.1\\bin\"."
              % (freecad_folder, ", ".join(missing)))
        return 1

    if args.check:
        folder = args.results or tempfile.mkdtemp(prefix="check_")
    else:
        name = os.path.splitext(os.path.basename(part))[0]
        folder = args.results or os.path.join(ROOT, "results",
                                              "%s_%s" % (name, datetime.now().strftime("%Y%m%d-%H%M%S")))
    os.makedirs(folder, exist_ok=True)
    log_path = os.path.join(folder, LOG_NAME)
    if os.path.exists(log_path):
        os.remove(log_path)

    gui = not (args.headless or args.check)
    prepomax_exe, warning = _choose_prepomax(args.prepomax, args.no_prepomax, gui)
    if warning:
        print(warning)
    job = Job(mode="check" if args.check else "optimize", input=part, folder=folder, gui=gui,
              close_when_done=args.close_when_done, repo=ROOT, prepomax=prepomax_exe)
    job_path = os.path.join(folder, "job.json")
    save(job, job_path)

    env = dict(os.environ, **{ENVIRONMENT_VARIABLE: job_path})
    with open(os.path.join(folder, "freecad_output.txt"), "w", encoding="utf-8", errors="replace") as output:
        process = subprocess.Popen(_command(freecad_folder, gui), env=env, stdout=output, stderr=subprocess.STDOUT,
                                   **_process_options())
        lines = _follow(process, log_path, os.path.join(folder, STOP_NAME))

    code = read_end_code(lines)
    if code is None:
        print("FreeCAD was closed before the end. The best result so far (if any) is in %s." % folder)
        print("Details of the FreeCAD output: %s" % os.path.join(folder, "freecad_output.txt"))
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
