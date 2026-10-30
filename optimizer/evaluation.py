"""One evaluation: applies values, recomputes, checks faces, runs the FEA and measures."""
from dataclasses import dataclass, field

from optimizer.fea import EvaluationFailed, run_fea
from optimizer.model import constraint_faces, element_size_mm, mass_kg, objects_with_errors
from optimizer.spreadsheet import apply_values
from optimizer.stress import face_distance, measure_stress
from optimizer.face_tracking import capture_signatures, compare_signatures

OK = "OK ✓"
OK_CHECK = "OK ⚠ check"
ABOVE = "above limit"
INVALID = "invalid"


@dataclass
class Iteration:
    number: int
    values: dict
    von_mises: float = None
    von_mises_raw: float = None
    location: tuple = None
    mass_kg: float = None
    status: str = INVALID
    reason: str = ""

    @property
    def valid(self):
        return self.status != INVALID


def _point(p):
    return "(%.1f, %.1f, %.1f)" % tuple(p)


class Evaluator:
    def __init__(self, doc, settings, model, work_folder):
        self.doc = doc
        self.settings = settings
        self.model = model
        self.work_folder = work_folder
        self.diagonal = model.body.Shape.BoundBox.DiagonalLength
        self.element_size = element_size_mm(model)
        self.zone_mm = (settings.exclusion_zone_mm if settings.exclusion_zone_mm is not None
                        else 2 * self.element_size)
        self.base_signatures = capture_signatures(model)
        self.number = 0
        self.last_result = None

    def evaluate(self, values):
        self.number += 1
        it = Iteration(number=self.number, values=dict(values))
        self.last_result = None
        try:
            self._evaluate(it)
        except EvaluationFailed as exc:
            it.status, it.reason = INVALID, str(exc)
        return it

    def _evaluate(self, it):
        apply_values(self.doc, self.settings, it.values)
        self.doc.recompute()
        broken = objects_with_errors(self.doc)
        if broken or not self.model.body.Shape.isValid():
            raise EvaluationFailed("The geometry does not close with these values (%s)."
                                   % (", ".join(broken) or "invalid solid"))
        problems = compare_signatures(self.base_signatures, capture_signatures(self.model), self.diagonal)
        if problems:
            raise EvaluationFailed(" ".join(problems))
        it.mass_kg = mass_kg(self.model)

        result = run_fea(self.model, self.work_folder)
        self.last_result = result
        mesh = result.Mesh.FemMesh
        coords = [tuple(mesh.getNodeById(n)) for n in result.NodeNumbers]
        faces = [f for name, found in constraint_faces(self.model).items()
                 if self.settings.exclude.get(name, True) for f in found]
        limit = self.settings.stress_limit
        m = measure_stress(coords, list(result.vonMises), face_distance(faces),
                           self.zone_mm, self.element_size, limit)
        it.von_mises, it.von_mises_raw, it.location = m.filtered_max, m.raw_max, m.filtered_location

        if m.filtered_max > limit:
            it.status = ABOVE
        elif m.max_in_zone > limit:
            it.status = OK_CHECK
            it.reason = ("Peak of %.0f MPa inside the exclusion zone at %s; check whether it is real."
                         % (m.max_in_zone, _point(m.raw_location)))
        elif m.at_edge:
            it.status = OK_CHECK
            it.reason = ("The maximum lies at the edge of the exclusion zone at %s; the stress may keep "
                         "rising inside it." % _point(m.filtered_location))
        else:
            it.status = OK
