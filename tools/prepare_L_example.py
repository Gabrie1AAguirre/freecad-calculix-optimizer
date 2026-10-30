"""Generates examples/L_part.FCStd from the original L part (tests/data/L_part_original.FCStd).

Adds the Parameters spreadsheet, a radius at the inner corner (sketch fillet)
and links the leg thicknesses to the spreadsheet, keeping the outer size at
180 x 230 mm. The input file is only read.

Usage (with FreeCAD's Python):
    python.exe tools/prepare_L_example.py --input tests/data/L_part_original.FCStd --output examples/L_part.FCStd
"""
import argparse
import os
import shutil
import sys
import tempfile

_BIN = os.environ.get("FREECAD_BIN", r"C:\Program Files\FreeCAD 1.1\bin")
sys.path += [_BIN, os.path.join(os.path.dirname(_BIN), "lib")]

import FreeCAD as App  # noqa: E402
import Sketcher  # noqa: E402

OUTER_WIDTH = 180.0
OUTER_HEIGHT = 230.0
INNER_CORNER = (30.0, 30.0)

PARAMETERS = [
    # description, alias, value, minimum, maximum
    ("Inner corner radius (mm)", "corner_radius", 1, 1, 20),
    ("Vertical leg thickness (mm)", "vertical_thickness", 30, 20, 45),
    ("Horizontal leg thickness (mm)", "horizontal_thickness", 30, 20, 45),
]
SETTINGS = [
    ("Maximum allowed Von Mises (MPa)", "stress_limit", 250),
    ("Maximum iterations", "max_iterations", 20),
]

RESULT_TYPES = ("Fem::FemResultObjectPython", "Fem::FemPostPipeline",
                "Fem::FemMeshObjectPython", "App::TextDocument")


def _close(a, b, tol=1e-6):
    return abs(a - b) < tol


def _corner_line(sketch, vertical):
    """Index of the vertical/horizontal line touching the inner corner."""
    cx, cy = INNER_CORNER
    for i, g in enumerate(sketch.Geometry):
        if g.TypeId != "Part::GeomLineSegment":
            continue
        points = (g.StartPoint, g.EndPoint)
        touches = any(_close(p.x, cx) and _close(p.y, cy) for p in points)
        is_vertical = _close(g.StartPoint.x, g.EndPoint.x)
        if touches and is_vertical == vertical:
            return i
    raise RuntimeError("could not find the inner corner line in the Sketch")


def _outer_line(sketch, vertical):
    """Index of the full outer line (edge at x=0 or y=0)."""
    for i, g in enumerate(sketch.Geometry):
        if g.TypeId != "Part::GeomLineSegment":
            continue
        if vertical and _close(g.StartPoint.x, 0) and _close(g.EndPoint.x, 0):
            return i
        if not vertical and _close(g.StartPoint.y, 0) and _close(g.EndPoint.y, 0):
            return i
    raise RuntimeError("could not find the outer edge in the Sketch")


def _constraint(sketch, kind, value):
    found = [i for i, c in enumerate(sketch.Constraints)
             if c.Type == kind and _close(c.Value, value)]
    if len(found) != 1:
        raise RuntimeError("expected one %s = %s constraint, found %d" % (kind, value, len(found)))
    return found[0]


def _create_sheet(doc):
    sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
    for cell, text in (("A1", "Parameter"), ("B1", "Value"), ("C1", "Minimum"), ("D1", "Maximum")):
        sheet.set(cell, text)
    row = 2
    for description, alias, value, minimum, maximum in PARAMETERS:
        sheet.set("A%d" % row, description)
        sheet.set("B%d" % row, str(value))
        sheet.setAlias("B%d" % row, alias)
        sheet.set("C%d" % row, str(minimum))
        sheet.set("D%d" % row, str(maximum))
        row += 1
    row += 1
    sheet.set("A%d" % row, "Settings")
    for description, alias, value in SETTINGS:
        row += 1
        sheet.set("A%d" % row, description)
        sheet.set("B%d" % row, str(value))
        sheet.setAlias("B%d" % row, alias)
    sheet.setColumnWidth("A", 260)  # room for the descriptions
    return sheet


def _remove_results(doc):
    analysis = doc.getObject("Analysis")
    for obj in list(analysis.Group):
        if obj.TypeId in RESULT_TYPES:
            doc.removeObject(obj.Name)


def prepare(input_path, output_path):
    # Works on a temporary copy so the input is never written.
    folder = tempfile.mkdtemp()
    copy = os.path.join(folder, "L_part.FCStd")
    shutil.copy(input_path, copy)
    doc = App.openDocument(copy)
    try:
        _remove_results(doc)
        doc.getObject("Body").Label = "Body"  # the original part was labeled in Portuguese
        _create_sheet(doc)
        doc.recompute()

        sk = doc.getObject("Sketch")
        cx, cy = INNER_CORNER
        g_vert = _corner_line(sk, vertical=True)
        g_horiz = _corner_line(sk, vertical=False)
        # The fillet deletes the dimensions that used the corner (150 and 200); the
        # outer size is then fixed directly by the outer edges.
        sk.fillet(g_vert, g_horiz, App.Vector(cx, cy + 10, 0), App.Vector(cx + 10, cy, 0), 1.0, True, False)
        arc = len(sk.Geometry) - 1
        sk.addConstraint(Sketcher.Constraint("DistanceX", _outer_line(sk, vertical=False), 1,
                                             _outer_line(sk, vertical=False), 2, OUTER_WIDTH))
        sk.addConstraint(Sketcher.Constraint("DistanceY", _outer_line(sk, vertical=True), 1,
                                             _outer_line(sk, vertical=True), 2, OUTER_HEIGHT))
        radius = sk.addConstraint(Sketcher.Constraint("Radius", arc, 1.0))

        sk.setExpression("Constraints[%d]" % radius, "Parameters.corner_radius")
        sk.setExpression("Constraints[%d]" % _constraint(sk, "DistanceX", 30.0), "Parameters.vertical_thickness")
        sk.setExpression("Constraints[%d]" % _constraint(sk, "DistanceY", 30.0), "Parameters.horizontal_thickness")
        doc.recompute()
        if not doc.getObject("Body").Shape.isValid():
            raise RuntimeError("the body became invalid after the fillet")
        doc.saveAs(os.path.abspath(output_path))
    finally:
        App.closeDocument(doc.Name)
        shutil.rmtree(folder, True)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=os.path.join(root, "tests", "data", "L_part_original.FCStd"))
    parser.add_argument("--output", default=os.path.join(root, "examples", "L_part.FCStd"))
    args = parser.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    prepare(args.input, args.output)
    print("Example generated at", args.output)


if __name__ == "__main__":
    main()
