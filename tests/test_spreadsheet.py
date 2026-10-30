import unittest

import FreeCAD as App

from optimizer.spreadsheet import SpreadsheetError, apply_values, read_settings


def _doc_with_sheet(cells):
    """cells: list of (cell, content, alias_or_None)."""
    doc = App.newDocument("spreadsheet_test")
    sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
    for cell, content, alias in cells:
        sheet.set(cell, content)
        if alias:
            sheet.setAlias(cell, alias)
    doc.recompute()
    return doc


BASE = [
    ("A2", "Corner radius", None), ("B2", "1", "corner_radius"), ("C2", "1", None), ("D2", "20", None),
    ("A3", "Thickness", None), ("B3", "30", "thickness"), ("C3", "20", None), ("D3", "45", None),
    ("A5", "Limit", None), ("B5", "250", "stress_limit"),
]


class TestSpreadsheet(unittest.TestCase):
    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def test_reads_parameters_and_settings(self):
        settings = read_settings(_doc_with_sheet(BASE))
        self.assertEqual([p.alias for p in settings.parameters], ["corner_radius", "thickness"])
        self.assertEqual((settings.parameters[0].minimum, settings.parameters[0].maximum), (1.0, 20.0))
        self.assertEqual(settings.parameters[1].value, 30.0)
        self.assertEqual(settings.parameters[0].cell, "B2")
        self.assertEqual(settings.stress_limit, 250.0)
        self.assertEqual(settings.max_iterations, 20)
        self.assertIsNone(settings.exclusion_zone_mm)
        self.assertEqual(settings.exclude, {})

    def test_exclude_per_constraint(self):
        settings = read_settings(_doc_with_sheet(BASE + [("B7", "0", "exclude_ConstraintFixed")]))
        self.assertEqual(settings.exclude, {"ConstraintFixed": False})
        self.assertNotIn("exclude_ConstraintFixed", [p.alias for p in settings.parameters])

    def test_optional_settings(self):
        settings = read_settings(_doc_with_sheet(
            BASE + [("B8", "12", "max_iterations"), ("B9", "7.5", "exclusion_zone_mm")]))
        self.assertEqual(settings.max_iterations, 12)
        self.assertEqual(settings.exclusion_zone_mm, 7.5)
        self.assertEqual(len(settings.parameters), 2)

    def test_comma_and_units(self):
        cells = [c for c in BASE if c[0] not in ("C2", "D2")] + [("C2", "'12,5", None), ("D2", "20 mm", None)]
        settings = read_settings(_doc_with_sheet(cells))
        self.assertEqual((settings.parameters[0].minimum, settings.parameters[0].maximum), (12.5, 20.0))

    def test_limit_with_unit(self):
        cells = [c for c in BASE if c[0] != "B5"] + [("B5", "250 MPa", "stress_limit")]
        self.assertEqual(read_settings(_doc_with_sheet(cells)).stress_limit, 250.0)
        cells = [c for c in BASE if c[0] != "B5"] + [("B5", "0.25 GPa", "stress_limit")]
        self.assertAlmostEqual(read_settings(_doc_with_sheet(cells)).stress_limit, 250.0)

    def test_text_with_another_length_unit(self):
        cells = [c for c in BASE if c[0] != "D2"] + [("D2", "'2 cm", None)]
        self.assertEqual(read_settings(_doc_with_sheet(cells)).parameters[0].maximum, 20.0)

    def test_no_sheet(self):
        doc = App.newDocument("empty")
        with self.assertRaises(SpreadsheetError) as ctx:
            read_settings(doc)
        self.assertIn("Parameters", str(ctx.exception))

    def test_apply_values(self):
        doc = _doc_with_sheet(BASE)
        settings = read_settings(doc)
        apply_values(doc, settings, {"corner_radius": 7.5})
        doc.recompute()
        self.assertEqual(float(doc.getObject("Parameters").get("corner_radius")), 7.5)


if __name__ == "__main__":
    unittest.main()
