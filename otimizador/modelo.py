"""Descoberta dos objetos da análise FEM de uma peça e cálculo da massa."""
from dataclasses import dataclass, field

import FreeCAD as App

TIPOS_FORCA = ("Fem::ConstraintForce", "Fem::ConstraintPressure")
TIPOS_FIXACAO = ("Fem::ConstraintFixed",)


class ErroModelo(Exception):
    """Problema na montagem da análise, com mensagem em português."""


@dataclass
class Modelo:
    doc: object
    analise: object
    solver: object
    malha: object
    material: object
    corpo: object
    fixacoes: list = field(default_factory=list)
    forcas: list = field(default_factory=list)

    @property
    def condicoes(self):
        return self.fixacoes + self.forcas


def _unico(objetos, descricao, como_criar):
    if not objetos:
        raise ErroModelo("A análise não tem %s. %s" % (descricao, como_criar))
    if len(objetos) > 1:
        raise ErroModelo("A análise tem mais de um(a) %s (%s); deixe só um."
                         % (descricao, ", ".join(o.Label for o in objetos)))
    return objetos[0]


def encontrar_modelo(doc):
    analises = [o for o in doc.Objects if o.isDerivedFrom("Fem::FemAnalysis")]
    if not analises:
        raise ErroModelo("Não encontrei nenhuma análise FEM. Na bancada FEM, crie uma "
                         "análise CalculiX (Analysis) com material, fixação, força e malha.")
    if len(analises) > 1:
        raise ErroModelo("O arquivo tem mais de uma análise FEM (%s). Deixe só uma Analysis."
                         % ", ".join(a.Label for a in analises))
    analise = analises[0]
    membros = analise.Group
    solver = _unico([o for o in membros if o.isDerivedFrom("Fem::FemSolverObject")],
                    "solver", "Adicione o solver CalculiX (SolverCcxTools).")
    malha = _unico([o for o in membros if o.isDerivedFrom("Fem::FemMeshObject")
                    and getattr(o, "Shape", None) is not None],
                   "malha", "Crie uma malha com o Gmsh (FEM mesh from shape by Gmsh).")
    material = _unico([o for o in membros if hasattr(o, "Material") and o.isDerivedFrom("App::MaterialObject")],
                      "material", "Adicione um material sólido (Material for solid).")
    fixacoes = [o for o in membros if o.TypeId in TIPOS_FIXACAO]
    forcas = [o for o in membros if o.TypeId in TIPOS_FORCA]
    return Modelo(doc=doc, analise=analise, solver=solver, malha=malha, material=material,
                  corpo=malha.Shape, fixacoes=fixacoes, forcas=forcas)


def densidade_kg_mm3(modelo):
    return App.Units.Quantity(modelo.material.Material["Density"]).getValueAs("kg/mm^3").Value


def massa_kg(modelo):
    return modelo.corpo.Shape.Volume * densidade_kg_mm3(modelo)


def faces_cc(modelo):
    """Faces de cada condição de contorno, por nome do objeto. Faces que não
    existem mais são omitidas."""
    faces = {}
    for cc in modelo.condicoes:
        lista = []
        for obj, subs in cc.References:
            for sub in subs:
                try:
                    lista.append(obj.Shape.getElement(sub))
                except Exception:
                    pass
        faces[cc.Name] = lista
    return faces
