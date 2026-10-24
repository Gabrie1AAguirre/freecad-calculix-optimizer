import os
import subprocess
import sys
import tempfile
import time
import unittest

import otimizar
from tests.util import EXEMPLO_L, RAIZ

LANCADOR = os.path.join(RAIZ, "otimizar.py")


def rodar(*args):
    env = dict(os.environ, PYTHONIOENCODING="")
    proc = subprocess.run([sys.executable, LANCADOR] + list(args), capture_output=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


class TestLancador(unittest.TestCase):
    def test_freecad_inexistente(self):
        codigo, saida = rodar(EXEMPLO_L, "--freecad", r"C:\nao\existe")
        self.assertEqual(codigo, 1)
        self.assertIn("--freecad", saida)
        self.assertIn("Não encontrei o FreeCAD", saida)

    def test_peca_inexistente(self):
        codigo, saida = rodar(os.path.join(tempfile.gettempdir(), "nao_existe.FCStd"))
        self.assertEqual(codigo, 1)
        self.assertIn("Não encontrei o arquivo", saida)

    def test_codigo_fim(self):
        self.assertEqual(otimizar.ler_codigo_fim(["a", "### FIM codigo=0"]), 0)
        self.assertEqual(otimizar.ler_codigo_fim(["### FIM codigo=2\n"]), 2)
        self.assertEqual(otimizar.ler_codigo_fim(["### FIM codigo=1"]), 1)
        self.assertIsNone(otimizar.ler_codigo_fim(["sem fim"]))

    def test_volta_ao_terminal_sem_esperar_fechar_freecad(self):
        # Com a janela aberta o FreeCAD continua rodando; o lançador deve voltar
        # assim que o log marcar o fim.
        pasta = tempfile.mkdtemp()
        log = os.path.join(pasta, "log.txt")
        with open(log, "w", encoding="utf-8") as f:
            f.write("linha\n### FIM codigo=0\n")
        processo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(processo.kill)
        inicio = time.time()
        linhas = otimizar._acompanhar(processo, log, os.path.join(pasta, "parar"))
        self.assertLess(time.time() - inicio, 5)
        self.assertEqual(otimizar.ler_codigo_fim(linhas), 0)


if __name__ == "__main__":
    unittest.main()
