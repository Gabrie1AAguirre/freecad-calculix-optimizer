"""Reading and writing the `Parameters` spreadsheet of a part."""
import re
from dataclasses import dataclass, field

import FreeCAD as App

SHEET_NAME = "Parameters"
ALIAS_STRESS_LIMIT = "stress_limit"
ALIAS_MAX_ITERATIONS = "max_iterations"
ALIAS_EXCLUSION_ZONE = "exclusion_zone_mm"
EXCLUDE_PREFIX = "exclude_"
RESERVED_ALIASES = (ALIAS_STRESS_LIMIT, ALIAS_MAX_ITERATIONS, ALIAS_EXCLUSION_ZONE)
DEFAULT_MAX_ITERATIONS = 20


class SpreadsheetError(Exception):
    """Problem in the spreadsheet, with a message for the user."""


@dataclass
class Parameter:
    alias: str
    value: float
    minimum: float
    maximum: float
    cell: str


@dataclass
class Settings:
    parameters: list
    stress_limit: float = None
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    exclusion_zone_mm: float = None
    exclude: dict = field(default_factory=dict)


def _from_quantity(q):
    """FreeCAD Quantity → float in mm (length) or MPa (stress).
    The .Value of a stress is in kPa (internal unit), hence the conversion."""
    if q.Unit == App.Units.Unit("MPa"):
        return float(q.getValueAs("MPa"))
    return float(q.Value)


def numeric_value(value):
    """Converts a number, Quantity or text ('12,5', '20 mm', '250 MPa') to float (mm/MPa)."""
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "Value"):
        return _from_quantity(value)
    text = str(value).strip().lstrip("'=").replace(",", ".")
    try:
        return _from_quantity(App.Units.Quantity(text))
    except Exception:
        pass
    match = re.match(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", text)
    if not match:
        raise ValueError("not a number: %r" % value)
    return float(match.group(0))


def find_sheet(doc):
    for obj in doc.Objects:
        if obj.TypeId == "Spreadsheet::Sheet" and SHEET_NAME in (obj.Name, obj.Label):
            return obj
    return None


def _split_cell(cell):
    match = re.match(r"^([A-Z]+)(\d+)$", cell)
    return match.group(1), match.group(2)


def _numeric_content(sheet, cell, alias, description):
    content = sheet.getContents(cell)
    if not str(content).strip():
        raise SpreadsheetError(
            "Parameter '%s' has no %s in cell %s. Fill in this value in the %s spreadsheet."
            % (alias, description, cell, SHEET_NAME))
    try:
        return numeric_value(sheet.get(cell))
    except Exception:
        try:
            return numeric_value(content)
        except ValueError:
            raise SpreadsheetError(
                "The %s of parameter '%s' (cell %s) is not a number: %r."
                % (description, alias, cell, content))


def read_settings(doc):
    sheet = find_sheet(doc)
    if sheet is None:
        raise SpreadsheetError(
            "Could not find the '%s' spreadsheet. Create a spreadsheet (Spreadsheet workbench) with this name "
            "listing the parameters that may change." % SHEET_NAME)
    settings = Settings(parameters=[])
    for cell in sorted(sheet.getUsedCells(), key=lambda c: (int(_split_cell(c)[1]), c)):
        alias = sheet.getAlias(cell)
        if not alias:
            continue
        if alias == ALIAS_STRESS_LIMIT:
            settings.stress_limit = _numeric_content(sheet, cell, alias, "value")
        elif alias == ALIAS_MAX_ITERATIONS:
            settings.max_iterations = int(_numeric_content(sheet, cell, alias, "value"))
        elif alias == ALIAS_EXCLUSION_ZONE:
            settings.exclusion_zone_mm = _numeric_content(sheet, cell, alias, "value")
        elif alias.startswith(EXCLUDE_PREFIX):
            constraint_name = alias[len(EXCLUDE_PREFIX):]
            settings.exclude[constraint_name] = bool(_numeric_content(sheet, cell, alias, "value"))
        else:
            column, row = _split_cell(cell)
            if column != "B":
                continue
            settings.parameters.append(Parameter(
                alias=alias,
                value=_numeric_content(sheet, cell, alias, "value"),
                minimum=_numeric_content(sheet, "C" + row, alias, "minimum (column C)"),
                maximum=_numeric_content(sheet, "D" + row, alias, "maximum (column D)"),
                cell=cell,
            ))
    return settings


def apply_values(doc, settings, values):
    """Writes the values into the parameter cells (does not recompute the document)."""
    sheet = find_sheet(doc)
    cells = {p.alias: p.cell for p in settings.parameters}
    for alias, value in values.items():
        sheet.set(cells[alias], "%.6g" % value)
