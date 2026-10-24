import unittest

from otimizador.checagem import checar
from tests.util import EXEMPLO_L, abrir_copia


def _erros(doc):
    return [p.mensagem for p in checar(doc) if p.nivel == "erro"]


class TestChecagem(unittest.TestCase):
    def setUp(self):
        self.doc = abrir_copia(EXEMPLO_L, self)
        self.sheet = self.doc.getObject("Parametros")

    def test_exemplo_ok(self):
        self.assertEqual(_erros(self.doc), [])

    def test_sem_forca(self):
        self.doc.removeObject("ConstraintForce")
        self.assertIn("força", " ".join(_erros(self.doc)).lower())

    def test_sem_fixacao(self):
        self.doc.removeObject("ConstraintFixed")
        self.assertIn("fixação", " ".join(_erros(self.doc)).lower())

    def test_duas_analises(self):
        import ObjectsFem
        ObjectsFem.makeAnalysis(self.doc, "Analysis2")
        self.assertIn("Analysis2", " ".join(_erros(self.doc)))

    def test_limites_invertidos(self):
        self.sheet.set("C2", "20")
        self.sheet.set("D2", "1")
        self.doc.recompute()
        self.assertIn("raio_canto", " ".join(_erros(self.doc)))

    def test_valor_fora_dos_limites(self):
        self.sheet.set("B2", "50")
        self.doc.recompute()
        self.assertIn("raio_canto", " ".join(_erros(self.doc)))

    def test_parametro_sem_uso(self):
        self.sheet.set("B9", "5")
        self.sheet.setAlias("B9", "fantasma")
        self.sheet.set("C9", "1")
        self.sheet.set("D9", "9")
        self.doc.recompute()
        erros = " ".join(_erros(self.doc))
        self.assertIn("fantasma", erros)
        self.assertIn("não é usado", erros)

    def test_sem_tensao_limite(self):
        celula = self.sheet.getCellFromAlias("tensao_limite")
        self.sheet.setAlias(celula, "")
        self.doc.recompute()
        self.assertIn("tensao_limite", " ".join(_erros(self.doc)))

    def test_sem_parametros(self):
        for alias in ("raio_canto", "espessura_vertical", "espessura_horizontal"):
            self.sheet.setAlias(self.sheet.getCellFromAlias(alias), "")
        self.doc.recompute()
        self.assertIn("nenhum parâmetro", " ".join(_erros(self.doc)).lower())

    def test_fillet_partdesign(self):
        corpo = self.doc.getObject("Body")
        fillet = corpo.newObject("PartDesign::Fillet", "Fillet")
        fillet.setExpression("Radius", "Parametros.raio_canto")
        avisos = [p.mensagem for p in checar(self.doc) if p.nivel == "aviso"]
        self.assertIn("Fillet", " ".join(avisos))

    def test_recompute_falha(self):
        self.sheet.set("B3", "0")
        self.doc.recompute()
        self.assertIn("recalcular", " ".join(_erros(self.doc)).lower())


if __name__ == "__main__":
    unittest.main()
