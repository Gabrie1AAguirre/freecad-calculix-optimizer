import math
import unittest

from otimizador.modelo import encontrar_modelo
from otimizador.planilha import aplicar_valores, ler_configuracao
from otimizador.topologia import capturar_assinaturas, comparar_assinaturas
from tests.util import EXEMPLO_L, abrir_copia


def _diagonal(m):
    return m.corpo.Shape.BoundBox.DiagonalLength


class TestTopologia(unittest.TestCase):
    def setUp(self):
        self.doc = abrir_copia(EXEMPLO_L, self)
        self.m = encontrar_modelo(self.doc)
        self.antes = capturar_assinaturas(self.m)

    def test_assinatura_estavel(self):
        aplicar_valores(self.doc, ler_configuracao(self.doc), {"espessura_vertical": 40, "raio_canto": 12})
        self.doc.recompute()
        self.assertEqual(comparar_assinaturas(self.antes, capturar_assinaturas(self.m), _diagonal(self.m)), [])

    def test_assinatura_detecta_troca(self):
        forca = self.doc.getObject("ConstraintForce")
        obj, _ = forca.References[0]
        forca.References = [(obj, "Face2")]
        self.doc.recompute()
        problemas = comparar_assinaturas(self.antes, capturar_assinaturas(self.m), _diagonal(self.m))
        self.assertTrue(problemas)
        self.assertIn("ConstraintForce", " ".join(problemas))

    def test_face_inexistente(self):
        forca = self.doc.getObject("ConstraintForce")
        obj, _ = forca.References[0]
        forca.References = [(obj, "Face99")]
        problemas = comparar_assinaturas(self.antes, capturar_assinaturas(self.m), _diagonal(self.m))
        self.assertTrue(problemas)
        self.assertIn("Face99", " ".join(problemas))


if __name__ == "__main__":
    unittest.main()
