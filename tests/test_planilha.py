import unittest

import FreeCAD as App

from otimizador.planilha import ErroPlanilha, aplicar_valores, ler_configuracao


def _doc_com_planilha(celulas):
    """celulas: lista de (celula, conteudo, alias_ou_None)."""
    doc = App.newDocument("teste_planilha")
    sheet = doc.addObject("Spreadsheet::Sheet", "Parametros")
    for celula, conteudo, alias in celulas:
        sheet.set(celula, conteudo)
        if alias:
            sheet.setAlias(celula, alias)
    doc.recompute()
    return doc


BASE = [
    ("A2", "Raio do canto", None), ("B2", "1", "raio_canto"), ("C2", "1", None), ("D2", "20", None),
    ("A3", "Espessura", None), ("B3", "30", "espessura"), ("C3", "20", None), ("D3", "45", None),
    ("A5", "Limite", None), ("B5", "250", "tensao_limite"),
]


class TestPlanilha(unittest.TestCase):
    def tearDown(self):
        for nome in list(App.listDocuments()):
            App.closeDocument(nome)

    def test_le_parametros_e_config(self):
        cfg = ler_configuracao(_doc_com_planilha(BASE))
        self.assertEqual([p.alias for p in cfg.parametros], ["raio_canto", "espessura"])
        self.assertEqual((cfg.parametros[0].minimo, cfg.parametros[0].maximo), (1.0, 20.0))
        self.assertEqual(cfg.parametros[1].valor, 30.0)
        self.assertEqual(cfg.parametros[0].celula, "B2")
        self.assertEqual(cfg.tensao_limite, 250.0)
        self.assertEqual(cfg.max_iteracoes, 20)
        self.assertIsNone(cfg.zona_exclusao_mm)
        self.assertEqual(cfg.excluir, {})

    def test_excluir_por_cc(self):
        cfg = ler_configuracao(_doc_com_planilha(BASE + [("B7", "0", "excluir_ConstraintFixed")]))
        self.assertEqual(cfg.excluir, {"ConstraintFixed": False})
        self.assertNotIn("excluir_ConstraintFixed", [p.alias for p in cfg.parametros])

    def test_config_opcionais(self):
        cfg = ler_configuracao(_doc_com_planilha(
            BASE + [("B8", "12", "max_iteracoes"), ("B9", "7.5", "zona_exclusao_mm")]))
        self.assertEqual(cfg.max_iteracoes, 12)
        self.assertEqual(cfg.zona_exclusao_mm, 7.5)
        self.assertEqual(len(cfg.parametros), 2)

    def test_virgula_e_unidades(self):
        celulas = [c for c in BASE if c[0] not in ("C2", "D2")] + [("C2", "'12,5", None), ("D2", "20 mm", None)]
        cfg = ler_configuracao(_doc_com_planilha(celulas))
        self.assertEqual((cfg.parametros[0].minimo, cfg.parametros[0].maximo), (12.5, 20.0))

    def test_sem_planilha(self):
        doc = App.newDocument("vazio")
        with self.assertRaises(ErroPlanilha) as ctx:
            ler_configuracao(doc)
        self.assertIn("Parametros", str(ctx.exception))

    def test_aplicar_valores(self):
        doc = _doc_com_planilha(BASE)
        cfg = ler_configuracao(doc)
        aplicar_valores(doc, cfg, {"raio_canto": 7.5})
        doc.recompute()
        self.assertEqual(float(doc.getObject("Parametros").get("raio_canto")), 7.5)


if __name__ == "__main__":
    unittest.main()
