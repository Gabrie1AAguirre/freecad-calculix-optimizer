import tempfile
import unittest

from otimizador.avaliacao import Avaliador
from otimizador.modelo import encontrar_modelo
from otimizador.planilha import ler_configuracao
from tests.util import EXEMPLO_L, ORIGINAL_L, abrir_copia


def _avaliador(doc, **cfg_extra):
    cfg = ler_configuracao(doc)
    for chave, valor in cfg_extra.items():
        setattr(cfg, chave, valor)
    return Avaliador(doc, cfg, encontrar_modelo(doc), tempfile.mkdtemp())


def _valores_atuais(av):
    return {p.alias: p.valor for p in av.cfg.parametros}


class TestAvaliacao(unittest.TestCase):
    def test_linha_de_base(self):
        av = _avaliador(abrir_copia(EXEMPLO_L, self))
        it = av.avaliar(_valores_atuais(av))
        self.assertEqual(it.numero, 1)
        self.assertEqual(it.status, "acima do limite")  # r = 1 mm: ~1080 MPa > 250
        self.assertGreater(it.von_mises, 250)
        self.assertGreater(it.massa_kg, 0)
        self.assertEqual(it.valores, _valores_atuais(av))
        self.assertIsNotNone(av.ultimo_resultado)

    def test_resultado_antigo_nao_reaproveitado(self):
        doc = abrir_copia(ORIGINAL_L, self)  # tem resultados antigos (~509 MPa)
        sheet = doc.addObject("Spreadsheet::Sheet", "Parametros")
        for celula, conteudo in (("B2", "30"), ("C2", "20"), ("D2", "45"), ("B4", "250")):
            sheet.set(celula, conteudo)
        sheet.setAlias("B2", "espessura_vertical")
        sheet.setAlias("B4", "tensao_limite")
        sk = doc.getObject("Sketch")
        indice = [i for i, c in enumerate(sk.Constraints) if c.Type == "DistanceX" and abs(c.Value - 30) < 1e-9][0]
        sk.setExpression("Constraints[%d]" % indice, "Parametros.espessura_vertical")
        doc.recompute()
        av = _avaliador(doc)
        it = av.avaliar({"espessura_vertical": 40.0})
        self.assertNotEqual(it.status, "inválida", it.motivo)
        self.assertNotAlmostEqual(it.von_mises_bruto, 508.842, 2)
        resultados = [o for o in av.modelo.analise.Group if o.isDerivedFrom("Fem::FemResultObject")]
        self.assertEqual(len(resultados), 1)

    def test_valor_impossivel_invalida(self):
        av = _avaliador(abrir_copia(EXEMPLO_L, self))
        it = av.avaliar(dict(_valores_atuais(av), raio_canto=500.0))  # não cabe nas pernas (150/200 mm)
        self.assertEqual(it.status, "inválida")
        self.assertTrue(it.motivo)
        self.assertIsNone(it.von_mises)

    def test_zona_padrao(self):
        av = _avaliador(abrir_copia(EXEMPLO_L, self))
        self.assertEqual(av.zona_mm, 10.0)
        self.assertEqual(av.tamanho_elemento, 5.0)

    def test_ok_verificar(self):
        # Zona de 60 mm em volta da fixação (z = 0) engloba o canto (z ≈ 30).
        doc = abrir_copia(EXEMPLO_L, self)
        av = _avaliador(doc, zona_exclusao_mm=60.0, tensao_limite=1e9)
        primeira = av.avaliar(_valores_atuais(av))
        self.assertIn(primeira.status, ("OK ✓", "OK ⚠ verificar"))  # 60 mm: máximo cai na borda da zona
        self.assertGreater(primeira.von_mises_bruto, primeira.von_mises)
        meio = (primeira.von_mises + primeira.von_mises_bruto) / 2
        av.cfg.tensao_limite = meio
        it = av.avaliar(_valores_atuais(av))
        self.assertEqual(it.status, "OK ⚠ verificar")
        self.assertIn("Pico", it.motivo)


if __name__ == "__main__":
    unittest.main()
