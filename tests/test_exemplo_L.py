import os
import subprocess
import tempfile
import unittest

import Part

from otimizador.planilha import aplicar_valores, ler_configuracao
from tests.util import EXEMPLO_L, FREECAD_PYTHON, ORIGINAL_L, RAIZ, abrir_copia, sha256


class TestExemploL(unittest.TestCase):
    def test_planilha_do_exemplo(self):
        cfg = ler_configuracao(abrir_copia(EXEMPLO_L, self))
        limites = {p.alias: (p.valor, p.minimo, p.maximo) for p in cfg.parametros}
        self.assertEqual(limites, {
            "raio_canto": (1.0, 1.0, 20.0),
            "espessura_vertical": (30.0, 20.0, 45.0),
            "espessura_horizontal": (30.0, 20.0, 45.0),
        })
        self.assertEqual(cfg.tensao_limite, 250.0)
        self.assertEqual(cfg.max_iteracoes, 30)

    def test_raio_no_canto_interno(self):
        doc = abrir_copia(EXEMPLO_L, self)
        arcos = [g for g in doc.getObject("Sketch").Geometry if isinstance(g, Part.ArcOfCircle)]
        self.assertEqual(len(arcos), 1)
        self.assertAlmostEqual(arcos[0].Radius, 1.0, 6)
        self.assertAlmostEqual(arcos[0].Center.x, 31.0, 6)
        self.assertAlmostEqual(arcos[0].Center.y, 31.0, 6)

    def test_tamanho_externo_fixo(self):
        doc = abrir_copia(EXEMPLO_L, self)
        cfg = ler_configuracao(doc)
        aplicar_valores(doc, cfg, {"espessura_vertical": 40, "espessura_horizontal": 25, "raio_canto": 10})
        doc.recompute()
        corpo = doc.getObject("Body").Shape
        self.assertTrue(corpo.isValid())
        self.assertAlmostEqual(corpo.BoundBox.XLength, 180, 3)
        self.assertAlmostEqual(corpo.BoundBox.ZLength, 230, 3)
        arco = [g for g in doc.getObject("Sketch").Geometry if isinstance(g, Part.ArcOfCircle)][0]
        self.assertAlmostEqual(arco.Radius, 10.0, 6)
        self.assertAlmostEqual(arco.Center.x, 50.0, 6)  # 40 + 10
        self.assertAlmostEqual(arco.Center.y, 35.0, 6)  # 25 + 10

    def test_sem_resultados_antigos(self):
        doc = abrir_copia(EXEMPLO_L, self)
        tipos = [o.TypeId for o in doc.getObject("Analysis").Group]
        self.assertNotIn("Fem::FemResultObjectPython", tipos)
        self.assertNotIn("Fem::FemPostPipeline", tipos)

    def test_original_intocado(self):
        antes = sha256(ORIGINAL_L)
        saida = os.path.join(tempfile.mkdtemp(), "L.FCStd")
        script = os.path.join(RAIZ, "ferramentas", "preparar_exemplo_L.py")
        proc = subprocess.run([FREECAD_PYTHON, script, "--entrada", ORIGINAL_L, "--saida", saida],
                              capture_output=True, text=True, errors="replace")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(os.path.exists(saida))
        self.assertEqual(sha256(ORIGINAL_L), antes)


if __name__ == "__main__":
    unittest.main()
