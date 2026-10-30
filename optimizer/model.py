"""Discovery of the FEM analysis objects of a part and mass calculation."""
from dataclasses import dataclass, field

import FreeCAD as App

FORCE_TYPES = ("Fem::ConstraintForce", "Fem::ConstraintPressure")
FIXED_TYPES = ("Fem::ConstraintFixed",)


class ModelError(Exception):
    """Problem in how the analysis is set up, with a message for the user."""


@dataclass
class Model:
    doc: object
    analysis: object
    solver: object
    mesh: object
    material: object
    body: object
    fixtures: list = field(default_factory=list)
    forces: list = field(default_factory=list)

    @property
    def constraints(self):
        return self.fixtures + self.forces


def _single(objects, description, how_to_create):
    if not objects:
        raise ModelError("The analysis has no %s. %s" % (description, how_to_create))
    if len(objects) > 1:
        raise ModelError("The analysis has more than one %s (%s); keep only one."
                         % (description, ", ".join(o.Label for o in objects)))
    return objects[0]


def find_model(doc):
    analyses = [o for o in doc.Objects if o.isDerivedFrom("Fem::FemAnalysis")]
    if not analyses:
        raise ModelError("Could not find any FEM analysis. In the FEM workbench, create a "
                         "CalculiX analysis (Analysis) with material, fixed constraint, force and mesh.")
    if len(analyses) > 1:
        raise ModelError("The file has more than one FEM analysis (%s). Keep only one Analysis."
                         % ", ".join(a.Label for a in analyses))
    analysis = analyses[0]
    members = analysis.Group
    solver = _single([o for o in members if o.isDerivedFrom("Fem::FemSolverObject")],
                     "solver", "Add the CalculiX solver (SolverCcxTools).")
    mesh = _single([o for o in members if o.isDerivedFrom("Fem::FemMeshObject")
                    and getattr(o, "Shape", None) is not None],
                   "mesh", "Create a mesh with Gmsh (FEM mesh from shape by Gmsh).")
    material = _single([o for o in members if hasattr(o, "Material") and o.isDerivedFrom("App::MaterialObject")],
                       "material", "Add a solid material (Material for solid).")
    fixtures = [o for o in members if o.TypeId in FIXED_TYPES]
    forces = [o for o in members if o.TypeId in FORCE_TYPES]
    return Model(doc=doc, analysis=analysis, solver=solver, mesh=mesh, material=material,
                 body=mesh.Shape, fixtures=fixtures, forces=forces)


def density_kg_mm3(model):
    return App.Units.Quantity(model.material.Material["Density"]).getValueAs("kg/mm^3").Value


def mass_kg(model):
    return model.body.Shape.Volume * density_kg_mm3(model)


def constraint_faces(model):
    """Faces of each boundary condition, by object name. Faces that no longer
    exist are left out."""
    faces = {}
    for constraint in model.constraints:
        found = []
        for obj, subs in constraint.References:
            for sub in subs:
                try:
                    found.append(obj.Shape.getElement(sub))
                except Exception:
                    pass
        faces[constraint.Name] = found
    return faces


def objects_with_errors(doc):
    """Labels of the objects that failed to recompute (Invalid/Error state)."""
    return [o.Label for o in doc.Objects if "Invalid" in o.State or "Error" in o.State]


def element_size_mm(model):
    """Maximum element size of the mesh; if automatic (0), 1/40 of the part diagonal."""
    size = model.mesh.CharacteristicLengthMax.Value
    return size if size > 0 else model.body.Shape.BoundBox.DiagonalLength / 40
