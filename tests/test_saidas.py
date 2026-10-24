import csv
import os
import shutil
import tempfile
import unittest

from otimizador.avaliacao import ACIMA, INVALIDA, OK, OK_VERIFICAR, Iteracao
from otimizador.saidas import Historico, cabecalho_terminal, gerar_grafico, linha_terminal, resumo

ALIASES = ["raio_canto", "espessura_vertical"]
BASE = Iteracao(1, {"raio_canto": 1.0, "espessura_vertical": 30.0}, von_mises=509.2, von_mises_bruto=509.2,
                local=(30.0, -10.0, 31.9), massa_kg=1.79, status=ACIMA)
BOA = Iteracao(3, {"raio_canto": 14.0, "espessura_vertical": 35.0}, von_mises=247.0, von_mises_bruto=300.0,
               local=(40.0, -10.0, 45.0), massa_kg=1.95, status=OK)
RUIM = Iteracao(4, {"raio_canto": 20.0, "espessura_vertical": 45.0}, status=INVALIDA, motivo="malha falhou")


class TestSaidas(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.pasta, True)

    def test_csv(self):
        caminho = os.path.join(self.pasta, "historico.csv")
        h = Historico(caminho, ALIASES)
        h.adicionar(BASE)
        with open(caminho, encoding="utf-8-sig") as f:  # já gravado a cada linha
            self.assertEqual(len(f.read().strip().splitlines()), 2)
        h.adicionar(RUIM)
        with open(caminho, "rb") as f:
            self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(linhas[0], ["iteracao", "raio_canto", "espessura_vertical", "von_mises_mpa",
                                     "von_mises_bruto_mpa", "local_max", "massa_kg", "status", "motivo"])
        self.assertEqual(linhas[1][:4], ["1", "1", "30", "509,2"])
        self.assertEqual(linhas[1][7], "acima do limite")
        self.assertEqual(linhas[2][3], "")
        self.assertEqual(linhas[2][8], "malha falhou")

    def test_linha_terminal(self):
        linha = linha_terminal(BASE, ALIASES, eh_melhor=False)
        self.assertIn("509 MPa", linha)
        self.assertIn("1.79 kg", linha)
        self.assertIn("acima do limite", linha)
        self.assertIn("OK ✓ melhor até agora", linha_terminal(BOA, ALIASES, eh_melhor=True))
        self.assertIn("malha falhou", linha_terminal(RUIM, ALIASES, eh_melhor=False))

    def test_cabecalho_alinhado(self):
        cab = cabecalho_terminal(ALIASES)
        linha = linha_terminal(BASE, ALIASES, eh_melhor=False)
        self.assertEqual(cab.index("VonMises_max"), linha.index("509 MPa") - (len("VonMises_max") - len("509 MPa")))

    def test_grafico(self):
        caminho = os.path.join(self.pasta, "grafico.png")
        gerar_grafico([BASE, BOA, RUIM], 250.0, caminho)
        self.assertGreater(os.path.getsize(caminho), 1000)

    def test_resumo(self):
        texto = resumo(BASE, BOA, 250.0)
        self.assertIn("atingiu", texto)
        self.assertNotIn("não atingiu", texto)
        self.assertIn("+8.9%", texto)  # massa 1.79 → 1.95
        nao = resumo(BASE, BASE, 250.0)
        self.assertIn("não atingiu", nao)
        verificar = Iteracao(5, BOA.valores, von_mises=240, massa_kg=1.9, status=OK_VERIFICAR, motivo="pico")
        self.assertIn("verificar", resumo(BASE, verificar, 250.0))


if __name__ == "__main__":
    unittest.main()
