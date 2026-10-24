import os
import tempfile
import unittest

from otimizador.fea import FalhaAvaliacao, rodar_fea
from otimizador.modelo import encontrar_modelo
from otimizador.tensao import distancia_faces
from otimizador.modelo import faces_cc
from tests.util import EXEMPLO_L, abrir_copia


class TestFea(unittest.TestCase):
    def test_roda_exemplo(self):
        m = encontrar_modelo(abrir_copia(EXEMPLO_L, self))
        r = rodar_fea(m, tempfile.mkdtemp())
        self.assertTrue(200 < max(r.vonMises) < 5000, max(r.vonMises))  # r=1 mm: ~1080 MPa
        resultados = [o for o in m.analise.Group if o.isDerivedFrom("Fem::FemResultObject")]
        self.assertEqual(len(resultados), 1)
        self.assertEqual(len(r.NodeNumbers), len(r.vonMises))

    def test_falha_vira_mensagem(self):
        doc = abrir_copia(EXEMPLO_L, self)
        m = encontrar_modelo(doc)
        doc.removeObject(m.material.Name)
        with self.assertRaises(FalhaAvaliacao) as ctx:
            rodar_fea(m, tempfile.mkdtemp())
        self.assertTrue(str(ctx.exception))

    def test_distancia_faces(self):
        m = encontrar_modelo(abrir_copia(EXEMPLO_L, self))
        dist = distancia_faces(faces_cc(m)["ConstraintFixed"])  # face z = 0
        self.assertAlmostEqual(dist((90.0, -10.0, 7.0)), 7.0, 6)


if __name__ == "__main__":
    unittest.main()
