"""Protection against the topological naming problem: checks that fixed
constraints and forces stay on the same faces after the geometry changes."""
from dataclasses import dataclass, field

MIN_NORMAL_DOT = 0.99
MAX_SHIFT_FRACTION = 0.25
MIN_AREA_RATIO, MAX_AREA_RATIO = 0.2, 5.0
# Another "similar" face to the original: same orientation and area of the same order.
SIMILAR_MIN_RATIO, SIMILAR_MAX_RATIO = 0.5, 2.0


@dataclass
class FaceSignature:
    subelement: str
    area: float = None
    center: tuple = None
    normal: tuple = None
    # Other faces of the same object (only filled in after the recompute).
    alternatives: list = field(default_factory=list)

    @property
    def exists(self):
        return self.area is not None


def _signature(obj, sub):
    try:
        face = obj.Shape.getElement(sub)
        u0, u1, v0, v1 = face.ParameterRange
        n = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        c = face.CenterOfMass
        return FaceSignature(sub, face.Area, (c.x, c.y, c.z), (n.x, n.y, n.z))
    except Exception:
        return FaceSignature(sub)


def _with_alternatives(obj, sub):
    signature = _signature(obj, sub)
    total = len(getattr(obj.Shape, "Faces", []))
    signature.alternatives = [_signature(obj, "Face%d" % i) for i in range(1, total + 1)
                              if "Face%d" % i != sub]
    return signature


def capture_signatures(model):
    return {c.Name: [_with_alternatives(obj, sub) for obj, subs in c.References for sub in subs]
            for c in model.constraints}


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _better_alternative(original, current):
    """A face of the object that matches the original better than the referenced one."""
    current_distance = _distance(original.center, current.center)
    for alt in current.alternatives:
        if (alt.exists and _dot(original.normal, alt.normal) >= MIN_NORMAL_DOT
                and SIMILAR_MIN_RATIO <= alt.area / original.area <= SIMILAR_MAX_RATIO
                and _distance(original.center, alt.center) < current_distance - 1e-6):
            return alt
    return None


def compare_signatures(before, after, diagonal_mm):
    problems = []
    for name, list_before in before.items():
        list_after = after.get(name, [])
        if len(list_after) != len(list_before):
            problems.append("%s: the number of faces changed (%d → %d)." % (name, len(list_before), len(list_after)))
            continue
        for b, a in zip(list_before, list_after):
            if not a.exists:
                problems.append("%s: face %s no longer exists." % (name, a.subelement))
                continue
            if not b.exists:
                continue
            ratio = a.area / b.area if b.area else float("inf")
            if (_dot(b.normal, a.normal) < MIN_NORMAL_DOT
                    or _distance(b.center, a.center) > MAX_SHIFT_FRACTION * diagonal_mm
                    or not MIN_AREA_RATIO <= ratio <= MAX_AREA_RATIO):
                problems.append(
                    "%s: face %s moved or changed orientation (likely a face swap caused by "
                    "FreeCAD's topological naming problem)." % (name, a.subelement))
                continue
            better = _better_alternative(b, a)
            if better is not None:
                problems.append(
                    "%s: points to %s, but %s matches the original face (%s) better; likely a face "
                    "swap caused by FreeCAD's topological naming problem."
                    % (name, a.subelement, better.subelement, b.subelement))
    return problems
