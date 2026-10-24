import math
import unittest

from otimizador.modelo import encontrar_modelo
from otimizador.planilha import aplicar_valores, ler_configuracao
from otimizador.topologia import AssinaturaFace, capturar_assinaturas, comparar_assinaturas
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



class TestTopologiaVizinha(unittest.TestCase):
    """Troca para uma face vizinha no mesmo plano e de tamanho parecido: normal igual,
    centro perto e área na mesma ordem passam nos limites — mas outra face corresponde melhor."""

    ANTES = {"ConstraintForce": [AssinaturaFace("Face13", 400.0, (30.0, -10.0, 220.0), (1.0, 0.0, 0.0))]}

    def test_detecta_troca_para_vizinha_parecida(self):
        original = AssinaturaFace("Face13", 400.0, (30.0, -10.0, 220.0), (1.0, 0.0, 0.0))
        vizinha = AssinaturaFace("Face14", 200.0, (30.0, -10.0, 235.0), (1.0, 0.0, 0.0), alternativas=[original])
        problemas = comparar_assinaturas(self.ANTES, {"ConstraintForce": [vizinha]}, 290.0)
        self.assertTrue(problemas)
        self.assertIn("Face13", " ".join(problemas))

    def test_face_que_so_se_moveu_continua_valida(self):
        longe = AssinaturaFace("Face10", 3580.0, (40.0, -10.0, 120.0), (1.0, 0.0, 0.0))
        movida = AssinaturaFace("Face13", 400.0, (40.0, -10.0, 220.0), (1.0, 0.0, 0.0), alternativas=[longe])
        self.assertEqual(comparar_assinaturas(self.ANTES, {"ConstraintForce": [movida]}, 290.0), [])


if __name__ == "__main__":
    unittest.main()
