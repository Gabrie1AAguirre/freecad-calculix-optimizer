import unittest

import FreeCAD as App

from optimizer.model import ModelError, constraint_faces, find_model, mass_kg
from tests.util import L_EXAMPLE, open_copy


class TestModel(unittest.TestCase):
    def test_finds_objects(self):
        m = find_model(open_copy(L_EXAMPLE, self))
        self.assertEqual([f.Name for f in m.fixtures], ["ConstraintFixed"])
        self.assertEqual([f.Name for f in m.forces], ["ConstraintForce"])
        self.assertEqual(m.analysis.Name, "Analysis")
        self.assertEqual(m.mesh.Name, "FEMMeshGmsh")
        self.assertEqual(m.solver.Name, "SolverCcxTools")
        self.assertEqual(m.material.Name, "MaterialSolid")
        self.assertEqual(m.body.Name, "Body")

    def test_mass(self):
        m = find_model(open_copy(L_EXAMPLE, self))
        density = App.Units.Quantity(m.material.Material["Density"]).getValueAs("kg/mm^3").Value
        self.assertAlmostEqual(mass_kg(m), m.body.Shape.Volume * density, places=6)
        self.assertTrue(1.0 < mass_kg(m) < 3.0)

    def test_constraint_faces(self):
        faces = constraint_faces(find_model(open_copy(L_EXAMPLE, self)))
        self.assertEqual(sorted(faces), ["ConstraintFixed", "ConstraintForce"])
        self.assertAlmostEqual(faces["ConstraintForce"][0].Area, 400.0, 3)

    def test_no_analysis(self):
        doc = App.newDocument("no_analysis")
        self.addCleanup(App.closeDocument, doc.Name)
        with self.assertRaises(ModelError) as ctx:
            find_model(doc)
        self.assertIn("analysis", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
