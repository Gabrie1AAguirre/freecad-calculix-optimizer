import unittest

import FreeCAD as App

from otimizador.modelo import ErroModelo, encontrar_modelo, faces_cc, massa_kg
from tests.util import EXEMPLO_L, abrir_copia


class TestModelo(unittest.TestCase):
    def test_encontra_objetos(self):
        m = encontrar_modelo(abrir_copia(EXEMPLO_L, self))
        self.assertEqual([f.Name for f in m.fixacoes], ["ConstraintFixed"])
        self.assertEqual([f.Name for f in m.forcas], ["ConstraintForce"])
        self.assertEqual(m.analise.Name, "Analysis")
        self.assertEqual(m.malha.Name, "FEMMeshGmsh")
        self.assertEqual(m.solver.Name, "SolverCcxTools")
        self.assertEqual(m.material.Name, "MaterialSolid")
        self.assertEqual(m.corpo.Name, "Body")

    def test_massa(self):
        m = encontrar_modelo(abrir_copia(EXEMPLO_L, self))
        densidade = App.Units.Quantity(m.material.Material["Density"]).getValueAs("kg/mm^3").Value
        self.assertAlmostEqual(massa_kg(m), m.corpo.Shape.Volume * densidade, places=6)
        self.assertTrue(1.0 < massa_kg(m) < 3.0)

    def test_faces_cc(self):
        faces = faces_cc(encontrar_modelo(abrir_copia(EXEMPLO_L, self)))
        self.assertEqual(sorted(faces), ["ConstraintFixed", "ConstraintForce"])
        self.assertAlmostEqual(faces["ConstraintForce"][0].Area, 400.0, 3)

    def test_sem_analise(self):
        doc = App.newDocument("sem_analise")
        self.addCleanup(App.closeDocument, doc.Name)
        with self.assertRaises(ErroModelo) as ctx:
            encontrar_modelo(doc)
        self.assertIn("análise", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
