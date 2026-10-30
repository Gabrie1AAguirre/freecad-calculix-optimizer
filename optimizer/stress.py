"""Maximum Von Mises stress ignoring the zones around the boundary conditions."""
import math
from dataclasses import dataclass


@dataclass
class StressMeasure:
    filtered_max: float
    filtered_location: tuple
    raw_max: float
    raw_location: tuple
    max_in_zone: float
    at_edge: bool


def measure_stress(coords, vm, distance, zone_mm, element_size, limit):
    """Walks the nodes from highest to lowest stress and stops at the first one
    outside the exclusion zone: the (expensive) distance is only computed at the top.
    `limit` is accepted to keep the plan's signature; the status decision is up
    to the caller."""
    order = sorted(range(len(vm)), key=lambda i: vm[i], reverse=True)
    if not order:
        raise ValueError("result without nodes")
    max_in_zone = 0.0
    for i in order:
        d = distance(coords[i])
        if d < zone_mm:
            max_in_zone = max(max_in_zone, vm[i])
            continue
        return StressMeasure(vm[i], tuple(coords[i]), vm[order[0]], tuple(coords[order[0]]),
                             max_in_zone, d < zone_mm + element_size)
    return StressMeasure(0.0, None, vm[order[0]], tuple(coords[order[0]]), max_in_zone, True)


def face_distance(faces):
    """Function point → smallest distance to the given faces (inf if there are none)."""
    if not faces:
        return lambda p: math.inf
    import FreeCAD as App
    import Part
    compound = Part.Compound(faces)

    def distance(p):
        return compound.distToShape(Part.Vertex(App.Vector(*p)))[0]
    return distance
