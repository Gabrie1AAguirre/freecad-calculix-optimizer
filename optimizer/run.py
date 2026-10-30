"""Run inside FreeCAD: check or full optimization of a part."""
import os
import shutil
import traceback

import FreeCAD as App

from optimizer import prepomax
from optimizer.check import check
from optimizer.evaluation import OK, OK_CHECK, Evaluator
from optimizer.fea import frd_file
from optimizer.job import END_MARK, LOG_NAME, STOP_NAME, load
from optimizer.model import find_model
from optimizer.optimization import BaselineError, optimize, stop_message
from optimizer.outputs import History, make_chart, summary, terminal_header, terminal_line
from optimizer.spreadsheet import read_settings

GUI_DELAY_MS = 500


class Log:
    """Writes each line to log.txt (read live by the launcher) and, with the
    interface, also to FreeCAD's Report view."""

    def __init__(self, path, gui):
        self.path, self.gui = path, gui

    def write(self, text=""):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        if self.gui:
            App.Console.PrintMessage(text + "\n")

    def end(self, code):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("%s%d\n" % (END_MARK, code))


def start(job_path):
    job = load(job_path)
    if job.gui:
        if job.prepomax:
            from optimizer import gui
            gui.keep_saved_window()  # the split screen is not saved in FreeCAD
        # Let the window open before starting, so the part shows up live.
        from PySide import QtCore
        QtCore.QTimer.singleShot(GUI_DELAY_MS, lambda: run(job))
    else:
        run(job)


def run(job):
    os.makedirs(job.folder, exist_ok=True)
    log = Log(os.path.join(job.folder, LOG_NAME), job.gui)
    try:
        code = (check_part if job.mode == "check" else optimize_part)(job, log)
    except Exception:
        log.write(traceback.format_exc())
        log.write("Unexpected error. The details above help to report the problem.")
        code = 1
    log.end(code)
    if job.gui and job.close_when_done:
        from optimizer import gui
        gui.close()


def _open_copy(job):
    """Opens a copy of the part: the user's file is never written."""
    folder = os.path.join(job.folder, "work")
    os.makedirs(folder, exist_ok=True)
    copy = os.path.join(folder, os.path.basename(job.input))
    shutil.copy(job.input, copy)
    return App.openDocument(copy)


def _report_problems(doc, log):
    problems = check(doc)
    for p in problems:
        log.write("%s: %s" % ("ERROR" if p.level == "error" else "WARNING", p.message))
    return any(p.level == "error" for p in problems)


def check_part(job, log):
    doc = _open_copy(job)
    if _report_problems(doc, log):
        log.write("The part is not ready yet. Fix the errors above and run --check again.")
        return 1
    log.write("✓ The part is ready to optimize.")
    return 0


def optimize_part(job, log):
    from optimizer import gui
    name = os.path.splitext(os.path.basename(job.input))[0]
    doc = _open_copy(job)
    if _report_problems(doc, log):
        log.write("The part is not ready yet. Fix the errors above (see --check) and run again.")
        return 1

    settings = read_settings(doc)
    ev = Evaluator(doc, settings, find_model(doc), os.path.join(job.folder, "work", "ccx"))
    aliases = [p.alias for p in settings.parameters]
    history_csv = History(os.path.join(job.folder, "history.csv"), aliases)
    destination = os.path.join(job.folder, "%s_optimized.FCStd" % name)
    destination_frd = os.path.join(job.folder, "%s_optimized.frd" % name)
    stop_path = os.path.join(job.folder, STOP_NAME)
    viewer = None
    if job.gui and job.prepomax:
        viewer = prepomax.Viewer([job.prepomax], os.path.join(job.folder, "work", "prepomax"))
        gui.left_half()  # PrePoMax takes the right one

    log.write("Optimizing %s: lowest mass with Von Mises ≤ %.0f MPa, up to %d iterations."
              % (os.path.basename(job.input), settings.stress_limit, settings.max_iterations))
    for p in settings.parameters:
        log.write("  %s: %g (range %g to %g)" % (p.alias, p.value, p.minimum, p.maximum))
    log.write("  zone ignored around fixed constraints/forces: %.1f mm" % ev.zone_mm)
    log.write("")
    log.write(terminal_header(aliases))
    if job.gui:
        gui.refresh()

    def on_iteration(it, is_best):
        history_csv.add(it)
        log.write(terminal_line(it, aliases, is_best))
        if is_best and it.valid:
            # saveCopy does not rename the document; deleting first avoids the .FCBak backup.
            if os.path.exists(destination):
                os.remove(destination)
            doc.saveCopy(destination)
            prepomax.stress_first(frd_file(ev.work_folder), destination_frd)
        if viewer:
            if ev.last_result is not None:
                viewer.show(frd_file(ev.work_folder))
            gui.show_part(doc, ev.model.body, fit=it.number == 1)
        elif job.gui:
            gui.show(doc, ev.last_result, fit=it.number == 1)

    try:
        best, history, reason = optimize(ev.evaluate, settings, on_iteration, lambda: os.path.exists(stop_path))
    except BaselineError as exc:
        log.write("The part with its current values could not be analyzed: %s" % exc)
        return 1

    log.write("")
    log.write(stop_message(reason, settings))
    make_chart(history, settings.stress_limit, os.path.join(job.folder, "chart.png"))
    log.write(summary(history[0], best, settings.stress_limit))
    log.write("Results in: %s" % job.folder)

    if job.gui:
        App.closeDocument(doc.Name)
        final = App.openDocument(destination)
        results = [o for o in final.Objects if o.isDerivedFrom("Fem::FemResultObject")]
        gui.show(final, results[-1] if results else None, fit=True)
        gui.save_image(final, os.path.join(job.folder, "view.png"))
        if viewer:
            gui.show_part(final, find_model(final).body, fit=True)
    if viewer:
        if os.path.exists(destination_frd):
            viewer.show_file(destination_frd)
            log.write("Result of the best iteration opened in PrePoMax (STRESS → MISES, in MPa).")
        else:
            viewer.close()
    return 0 if best.status in (OK, OK_CHECK) else 2
