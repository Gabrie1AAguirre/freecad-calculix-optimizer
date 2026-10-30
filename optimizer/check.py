"""Checks how the part is prepared (--check command)."""
import re
from dataclasses import dataclass

from optimizer.model import ModelError, find_model, objects_with_errors
from optimizer.spreadsheet import ALIAS_STRESS_LIMIT, SHEET_NAME, SpreadsheetError, read_settings

EDGE_TYPES = ("PartDesign::Fillet", "PartDesign::Chamfer")


@dataclass
class Problem:
    level: str  # "error" or "warning"
    message: str


def _expressions(doc):
    for obj in doc.Objects:
        for prop, expression in getattr(obj, "ExpressionEngine", []):
            yield obj, prop, expression


def _uses_alias(expression, alias):
    """Expressions reference the spreadsheet as Parameters.alias or <<Parameters>>.alias."""
    return re.search(r"\.%s\b" % re.escape(alias), expression) is not None


def _check_recompute(doc):
    doc.recompute()
    broken = objects_with_errors(doc)
    if broken:
        return [Problem("error", "The document cannot recompute with the current values (%s). "
                                 "Open it in FreeCAD and fix the objects marked with errors."
                        % ", ".join(broken))]
    return []


def check(doc):
    problems = []
    try:
        model = find_model(doc)
        if not model.fixtures:
            problems.append(Problem("error", "The analysis has no fixed constraint. In the FEM workbench, use "
                                             "'Fixed boundary condition' and select the fixed face."))
        if not model.forces:
            problems.append(Problem("error", "The analysis has no force or pressure. In the FEM workbench, "
                                             "use 'Force load' and select the face where the force is applied."))
    except ModelError as exc:
        problems.append(Problem("error", str(exc)))

    try:
        settings = read_settings(doc)
    except SpreadsheetError as exc:
        problems.append(Problem("error", str(exc)))
        return problems + _check_recompute(doc)

    if not settings.parameters:
        problems.append(Problem("error", "No parameters in the %s spreadsheet. Put each value that may change "
                                         "in column B with an alias, the minimum in column C and the maximum in D."
                                % SHEET_NAME))
    if settings.stress_limit is None:
        problems.append(Problem("error", "The cell with alias '%s' (maximum allowed Von Mises, in MPa) is missing."
                                % ALIAS_STRESS_LIMIT))
    expressions = list(_expressions(doc))
    for p in settings.parameters:
        if p.minimum >= p.maximum:
            problems.append(Problem("error", "Parameter '%s' has a minimum (%g) greater than or equal to its "
                                             "maximum (%g)." % (p.alias, p.minimum, p.maximum)))
        elif not p.minimum <= p.value <= p.maximum:
            problems.append(Problem("error", "The current value of '%s' (%g) is outside the limits [%g, %g]."
                                    % (p.alias, p.value, p.minimum, p.maximum)))
        uses = [(obj, prop) for obj, prop, expr in expressions
                if obj.TypeId != "Spreadsheet::Sheet" and _uses_alias(expr, p.alias)]
        if not uses:
            problems.append(Problem("error", "Parameter '%s' is not used by any dimension. In the Sketcher, "
                                             "click the f(x) of the dimension and type %s.%s."
                                    % (p.alias, SHEET_NAME, p.alias)))
        for obj, prop in uses:
            if obj.TypeId in EDGE_TYPES:
                problems.append(Problem("warning", "Parameter '%s' controls the %s '%s'. PartDesign fillets and "
                                                   "chamfers depend on the edge name and may break; prefer the "
                                                   "Sketcher fillet." % (p.alias, obj.TypeId.split("::")[1],
                                                                         obj.Label)))
    return problems + _check_recompute(doc)
