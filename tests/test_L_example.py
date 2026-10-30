import os
import subprocess
import tempfile
import unittest

import Part

from optimizer.spreadsheet import apply_values, read_settings
from tests.util import FREECAD_PYTHON, L_EXAMPLE, ORIGINAL_L, ROOT, open_copy, sha256


class TestLExample(unittest.TestCase):
    def test_example_spreadsheet(self):
        settings = read_settings(open_copy(L_EXAMPLE, self))
        limits = {p.alias: (p.value, p.minimum, p.maximum) for p in settings.parameters}
        self.assertEqual(limits, {
            "corner_radius": (1.0, 1.0, 20.0),
            "vertical_thickness": (30.0, 20.0, 45.0),
            "horizontal_thickness": (30.0, 20.0, 45.0),
        })
        self.assertEqual(settings.stress_limit, 250.0)
        self.assertEqual(settings.max_iterations, 20)

    def test_radius_at_inner_corner(self):
        doc = open_copy(L_EXAMPLE, self)
        arcs = [g for g in doc.getObject("Sketch").Geometry if isinstance(g, Part.ArcOfCircle)]
        self.assertEqual(len(arcs), 1)
        self.assertAlmostEqual(arcs[0].Radius, 1.0, 6)
        self.assertAlmostEqual(arcs[0].Center.x, 31.0, 6)
        self.assertAlmostEqual(arcs[0].Center.y, 31.0, 6)

    def test_outer_size_fixed(self):
        doc = open_copy(L_EXAMPLE, self)
        settings = read_settings(doc)
        apply_values(doc, settings, {"vertical_thickness": 40, "horizontal_thickness": 25, "corner_radius": 10})
        doc.recompute()
        body = doc.getObject("Body").Shape
        self.assertTrue(body.isValid())
        self.assertAlmostEqual(body.BoundBox.XLength, 180, 3)
        self.assertAlmostEqual(body.BoundBox.ZLength, 230, 3)
        arc = [g for g in doc.getObject("Sketch").Geometry if isinstance(g, Part.ArcOfCircle)][0]
        self.assertAlmostEqual(arc.Radius, 10.0, 6)
        self.assertAlmostEqual(arc.Center.x, 50.0, 6)  # 40 + 10
        self.assertAlmostEqual(arc.Center.y, 35.0, 6)  # 25 + 10

    def test_no_old_results(self):
        doc = open_copy(L_EXAMPLE, self)
        types = [o.TypeId for o in doc.getObject("Analysis").Group]
        self.assertNotIn("Fem::FemResultObjectPython", types)
        self.assertNotIn("Fem::FemPostPipeline", types)

    def test_original_untouched(self):
        before = sha256(ORIGINAL_L)
        output = os.path.join(tempfile.mkdtemp(), "L.FCStd")
        script = os.path.join(ROOT, "tools", "prepare_L_example.py")
        proc = subprocess.run([FREECAD_PYTHON, script, "--input", ORIGINAL_L, "--output", output],
                              capture_output=True, text=True, errors="replace")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(os.path.exists(output))
        self.assertEqual(sha256(ORIGINAL_L), before)


if __name__ == "__main__":
    unittest.main()
