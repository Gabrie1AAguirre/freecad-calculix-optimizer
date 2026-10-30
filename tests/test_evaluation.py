import tempfile
import unittest

from optimizer.evaluation import Evaluator
from optimizer.model import find_model
from optimizer.spreadsheet import read_settings
from tests.util import L_EXAMPLE, ORIGINAL_L, open_copy


def _evaluator(doc, **extra_settings):
    settings = read_settings(doc)
    for key, value in extra_settings.items():
        setattr(settings, key, value)
    return Evaluator(doc, settings, find_model(doc), tempfile.mkdtemp())


def _current_values(ev):
    return {p.alias: p.value for p in ev.settings.parameters}


class TestEvaluation(unittest.TestCase):
    def test_baseline(self):
        ev = _evaluator(open_copy(L_EXAMPLE, self))
        it = ev.evaluate(_current_values(ev))
        self.assertEqual(it.number, 1)
        self.assertEqual(it.status, "above limit")  # r = 1 mm: ~1080 MPa > 250
        self.assertGreater(it.von_mises, 250)
        self.assertGreater(it.mass_kg, 0)
        self.assertEqual(it.values, _current_values(ev))
        self.assertIsNotNone(ev.last_result)

    def test_old_result_not_reused(self):
        doc = open_copy(ORIGINAL_L, self)  # has old results (~509 MPa)
        sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
        for cell, content in (("B2", "30"), ("C2", "20"), ("D2", "45"), ("B4", "250")):
            sheet.set(cell, content)
        sheet.setAlias("B2", "vertical_thickness")
        sheet.setAlias("B4", "stress_limit")
        sk = doc.getObject("Sketch")
        index = [i for i, c in enumerate(sk.Constraints) if c.Type == "DistanceX" and abs(c.Value - 30) < 1e-9][0]
        sk.setExpression("Constraints[%d]" % index, "Parameters.vertical_thickness")
        doc.recompute()
        ev = _evaluator(doc)
        it = ev.evaluate({"vertical_thickness": 40.0})
        self.assertNotEqual(it.status, "invalid", it.reason)
        self.assertNotAlmostEqual(it.von_mises_raw, 508.842, 2)
        results = [o for o in ev.model.analysis.Group if o.isDerivedFrom("Fem::FemResultObject")]
        self.assertEqual(len(results), 1)

    def test_impossible_value_is_invalid(self):
        ev = _evaluator(open_copy(L_EXAMPLE, self))
        it = ev.evaluate(dict(_current_values(ev), corner_radius=500.0))  # does not fit in the legs (150/200 mm)
        self.assertEqual(it.status, "invalid")
        self.assertTrue(it.reason)
        self.assertIsNone(it.von_mises)

    def test_default_zone(self):
        ev = _evaluator(open_copy(L_EXAMPLE, self))
        self.assertEqual(ev.zone_mm, 10.0)
        self.assertEqual(ev.element_size, 5.0)

    def test_ok_check(self):
        # A 60 mm zone around the fixed constraint (z = 0) contains the corner (z ≈ 30).
        doc = open_copy(L_EXAMPLE, self)
        ev = _evaluator(doc, exclusion_zone_mm=60.0, stress_limit=1e9)
        first = ev.evaluate(_current_values(ev))
        self.assertIn(first.status, ("OK ✓", "OK ⚠ check"))  # 60 mm: the maximum falls at the zone edge
        self.assertGreater(first.von_mises_raw, first.von_mises)
        middle = (first.von_mises + first.von_mises_raw) / 2
        ev.settings.stress_limit = middle
        it = ev.evaluate(_current_values(ev))
        self.assertEqual(it.status, "OK ⚠ check")
        self.assertIn("Peak", it.reason)


if __name__ == "__main__":
    unittest.main()
