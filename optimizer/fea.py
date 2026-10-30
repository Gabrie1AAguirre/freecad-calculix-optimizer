"""Generates the mesh (Gmsh) and runs CalculiX for the part's analysis."""
import contextlib
import os
import subprocess


class EvaluationFailed(Exception):
    """The evaluation could not be completed; the message explains why."""


@contextlib.contextmanager
def _no_console_window():
    """FreeCAD starts CalculiX without hiding its window: on Windows a cmd window
    would open at every iteration. While active, every process started has no window."""
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    original = subprocess.Popen

    def popen(*args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | flag
        return original(*args, **kwargs)

    subprocess.Popen = popen
    try:
        yield
    finally:
        subprocess.Popen = original


def frd_file(work_folder):
    """The .frd (CalculiX result) of the last analysis run in this folder."""
    files = [os.path.join(work_folder, n) for n in os.listdir(work_folder) if n.lower().endswith(".frd")]
    return max(files, key=os.path.getmtime)


def run_fea(model, work_folder):
    """Remeshes, solves and returns the new result object (Fem::FemResultObject)."""
    with _no_console_window():
        return _run_fea(model, work_folder)


def _run_fea(model, work_folder):
    from femmesh.gmshtools import GmshTools
    from femtools import ccxtools

    os.makedirs(work_folder, exist_ok=True)
    try:
        error = GmshTools(model.mesh).create_mesh()
    except Exception as exc:
        raise EvaluationFailed("Gmsh could not generate the mesh: %s" % exc)
    if error:
        raise EvaluationFailed("Gmsh could not generate the mesh: %s" % error)
    if model.mesh.FemMesh.NodeCount == 0:
        raise EvaluationFailed("Gmsh generated an empty mesh.")

    try:
        fea = ccxtools.FemToolsCcx(model.analysis, model.solver)
        fea.purge_results()
        fea.update_objects()
        fea.setup_working_dir(work_folder)
        fea.setup_ccx()
        message = fea.check_prerequisites()
    except Exception as exc:
        raise EvaluationFailed("The analysis is incomplete: %s" % exc)
    if message:
        raise EvaluationFailed("The analysis is incomplete: %s" % message.strip())

    try:
        fea.write_inp_file()
        fea.ccx_run()
        fea.load_results()
    except Exception as exc:
        raise EvaluationFailed("CalculiX failed: %s" % exc)

    results = [o for o in model.analysis.Group if o.isDerivedFrom("Fem::FemResultObject")]
    if not results or not results[-1].vonMises:
        raise EvaluationFailed("CalculiX finished without results (see the .dat file in %s)." % work_folder)
    return results[-1]
