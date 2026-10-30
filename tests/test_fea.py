import os
import subprocess
import tempfile
import unittest

from optimizer.fea import EvaluationFailed, run_fea
from optimizer.model import constraint_faces, find_model
from optimizer.stress import face_distance
from tests.util import L_EXAMPLE, open_copy


class TestFea(unittest.TestCase):
    def test_runs_example(self):
        m = find_model(open_copy(L_EXAMPLE, self))
        r = run_fea(m, tempfile.mkdtemp())
        self.assertTrue(200 < max(r.vonMises) < 5000, max(r.vonMises))  # r=1 mm: ~1080 MPa
        results = [o for o in m.analysis.Group if o.isDerivedFrom("Fem::FemResultObject")]
        self.assertEqual(len(results), 1)
        self.assertEqual(len(r.NodeNumbers), len(r.vonMises))

    def test_creates_work_folder(self):
        m = find_model(open_copy(L_EXAMPLE, self))
        folder = os.path.join(tempfile.mkdtemp(), "new", "ccx")
        run_fea(m, folder)
        self.assertTrue(any(n.endswith(".inp") for n in os.listdir(folder)))

    def test_no_console_window(self):
        # FreeCAD starts CalculiX without hiding the window: on Windows a cmd shows up at every iteration.
        calls = []
        original = subprocess.Popen

        def record(*args, **kwargs):
            calls.append(kwargs)
            return original(*args, **kwargs)

        subprocess.Popen = record
        self.addCleanup(setattr, subprocess, "Popen", original)
        m = find_model(open_copy(L_EXAMPLE, self))
        run_fea(m, tempfile.mkdtemp())
        self.assertTrue(calls)
        for kwargs in calls:
            self.assertTrue(kwargs.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW, kwargs)

    def test_failure_becomes_message(self):
        doc = open_copy(L_EXAMPLE, self)
        m = find_model(doc)
        doc.removeObject(m.material.Name)
        with self.assertRaises(EvaluationFailed) as ctx:
            run_fea(m, tempfile.mkdtemp())
        self.assertTrue(str(ctx.exception))

    def test_face_distance(self):
        m = find_model(open_copy(L_EXAMPLE, self))
        dist = face_distance(constraint_faces(m)["ConstraintFixed"])  # face z = 0
        self.assertAlmostEqual(dist((90.0, -10.0, 7.0)), 7.0, 6)


if __name__ == "__main__":
    unittest.main()
