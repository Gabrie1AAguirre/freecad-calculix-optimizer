import unittest

from optimizer.check import check
from tests.util import L_EXAMPLE, open_copy


def _errors(doc):
    return [p.message for p in check(doc) if p.level == "error"]


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.doc = open_copy(L_EXAMPLE, self)
        self.sheet = self.doc.getObject("Parameters")

    def test_example_ok(self):
        self.assertEqual(_errors(self.doc), [])

    def test_no_force(self):
        self.doc.removeObject("ConstraintForce")
        self.assertIn("force", " ".join(_errors(self.doc)).lower())

    def test_no_fixed_constraint(self):
        self.doc.removeObject("ConstraintFixed")
        self.assertIn("fixed constraint", " ".join(_errors(self.doc)).lower())

    def test_two_analyses(self):
        import ObjectsFem
        ObjectsFem.makeAnalysis(self.doc, "Analysis2")
        self.assertIn("Analysis2", " ".join(_errors(self.doc)))

    def test_inverted_limits(self):
        self.sheet.set("C2", "20")
        self.sheet.set("D2", "1")
        self.doc.recompute()
        self.assertIn("corner_radius", " ".join(_errors(self.doc)))

    def test_value_outside_limits(self):
        self.sheet.set("B2", "50")
        self.doc.recompute()
        self.assertIn("corner_radius", " ".join(_errors(self.doc)))

    def test_unused_parameter(self):
        self.sheet.set("B9", "5")
        self.sheet.setAlias("B9", "ghost")
        self.sheet.set("C9", "1")
        self.sheet.set("D9", "9")
        self.doc.recompute()
        errors = " ".join(_errors(self.doc))
        self.assertIn("ghost", errors)
        self.assertIn("not used", errors)

    def test_no_stress_limit(self):
        cell = self.sheet.getCellFromAlias("stress_limit")
        self.sheet.setAlias(cell, "")
        self.doc.recompute()
        self.assertIn("stress_limit", " ".join(_errors(self.doc)))

    def test_no_parameters(self):
        for alias in ("corner_radius", "vertical_thickness", "horizontal_thickness"):
            self.sheet.setAlias(self.sheet.getCellFromAlias(alias), "")
        self.doc.recompute()
        self.assertIn("no parameters", " ".join(_errors(self.doc)).lower())

    def test_partdesign_fillet(self):
        body = self.doc.getObject("Body")
        fillet = body.newObject("PartDesign::Fillet", "Fillet")
        fillet.setExpression("Radius", "Parameters.corner_radius")
        warnings = [p.message for p in check(self.doc) if p.level == "warning"]
        self.assertIn("Fillet", " ".join(warnings))

    def test_recompute_fails(self):
        self.sheet.set("B3", "0")
        self.doc.recompute()
        self.assertIn("recompute", " ".join(_errors(self.doc)).lower())


if __name__ == "__main__":
    unittest.main()
