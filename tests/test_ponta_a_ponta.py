"""Testes lentos: rodam o otimizar.py de verdade (FreeCAD + Gmsh + CalculiX)."""
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import FreeCAD as App

from otimizador import prepomax
from tests.util import EXEMPLO_L, ORIGINAL_L, RAIZ, sha256

LANCADOR = os.path.join(RAIZ, "otimizar.py")
PARAMETROS = {"raio_canto": (1, 20), "espessura_vertical": (20, 45), "espessura_horizontal": (20, 45)}


def _numero(texto):
    return float(texto.replace(",", ".")) if texto else None


def _processos_prepomax(pasta):
    """(pid, linha de comando) dos PrePoMax abertos com um arquivo dessa pasta."""
    script = ("Get-CimInstance Win32_Process -Filter \"Name='PrePoMax.exe'\" | "
              "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }")
    saida = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                           encoding="utf-8", errors="replace").stdout
    linhas = [l.split("|", 1) for l in saida.splitlines() if "|" in l]
    return [(int(pid), cmd) for pid, cmd in linhas if os.path.normcase(pasta) in os.path.normcase(cmd)]


def _fechar_prepomax(pasta):
    # Pelo X: fechado à força, o PrePoMax deixaria um arquivo de recuperação.
    for pid, _ in _processos_prepomax(pasta):
        if not prepomax.fechar_pelo_x(pid):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


class TestPontaAPonta(unittest.TestCase):
    def setUp(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        self.pasta = os.path.join(base, "pasta com espaço ç")
        os.makedirs(self.pasta)
        self.resultados = os.path.join(self.pasta, "res")

    def _peca(self, max_iteracoes):
        destino = os.path.join(self.pasta, "L_part.FCStd")
        shutil.copy(EXEMPLO_L, destino)
        doc = App.openDocument(destino)
        sheet = doc.getObject("Parametros")
        sheet.set(sheet.getCellFromAlias("max_iteracoes"), str(max_iteracoes))
        doc.recompute()
        doc.save()
        App.closeDocument(doc.Name)
        return destino

    def _rodar(self, *args, timeout=900):
        proc = subprocess.run([sys.executable, LANCADOR] + list(args), capture_output=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        return proc.returncode, proc.stdout + proc.stderr

    def _sem_backups(self):
        backups = [os.path.join(r, n) for r, _, ns in os.walk(self.resultados) for n in ns if n.endswith(".FCBak")]
        self.assertEqual(backups, [])

    def _historico(self):
        with open(os.path.join(self.resultados, "historico.csv"), encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f, delimiter=";"))

    def test_sem_interface(self):
        peca = self._peca(6)
        antes = sha256(peca)
        codigo, saida = self._rodar(peca, "--sem-interface", "--resultados", self.resultados)
        self.assertIn(codigo, (0, 2), saida)
        for nome in ("L_part_otimizada.FCStd", "L_part_otimizada.frd", "historico.csv", "grafico.png", "log.txt"):
            self.assertTrue(os.path.exists(os.path.join(self.resultados, nome)), nome)
        with open(os.path.join(self.resultados, "L_part_otimizada.frd"), encoding="latin-1") as f:
            blocos = [l.split()[1] for l in f if l.strip().startswith("-4")]
        self.assertEqual(blocos[0], "STRESS")  # o PrePoMax abre direto no Von Mises
        linhas = self._historico()
        self.assertEqual(len(linhas), 6)
        validas = [l for l in linhas if l["von_mises_mpa"]]
        base = _numero(linhas[0]["von_mises_mpa"])
        self.assertLess(min(_numero(l["von_mises_mpa"]) for l in validas), base)
        for linha in linhas:
            for alias, (minimo, maximo) in PARAMETROS.items():
                self.assertTrue(minimo - 1e-6 <= _numero(linha[alias]) <= maximo + 1e-6, linha)
        self.assertEqual(sha256(peca), antes)
        self._sem_backups()
        self.assertIn("Linha de base", saida)
        self.assertIn("VonMises_max", saida)

    def test_checar_ok(self):
        codigo, saida = self._rodar(self._peca(30), "--checar")
        self.assertEqual(codigo, 0, saida)
        self.assertIn("pronta", saida)

    def test_checar_erro(self):
        codigo, saida = self._rodar(ORIGINAL_L, "--checar")
        self.assertEqual(codigo, 1, saida)
        self.assertIn("Parametros", saida)

    def test_parar(self):
        peca = self._peca(30)
        os.makedirs(self.resultados)
        open(os.path.join(self.resultados, "parar"), "w").close()
        codigo, saida = self._rodar(peca, "--sem-interface", "--resultados", self.resultados)
        self.assertIn(codigo, (0, 2), saida)
        self.assertEqual(len(self._historico()), 1)
        self.assertTrue(os.path.exists(os.path.join(self.resultados, "L_part_otimizada.FCStd")))
        self.assertIn("Parada pedida pelo usuário", saida)

    def test_gui_fumaca(self):
        peca = self._peca(2)
        codigo, saida = self._rodar(peca, "--resultados", self.resultados, "--fechar-ao-terminar", "--sem-prepomax")
        self.assertIn(codigo, (0, 2), saida)
        self.assertEqual(len(self._historico()), 2)
        self.assertTrue(os.path.exists(os.path.join(self.resultados, "vista.png")))
        self._sem_backups()

    @unittest.skipUnless(prepomax.encontrar(), "PrePoMax não instalado")
    def test_gui_com_prepomax(self):
        peca = self._peca(2)
        self.addCleanup(_fechar_prepomax, self.resultados)
        codigo, saida = self._rodar(peca, "--resultados", self.resultados, "--fechar-ao-terminar")
        self.assertIn(codigo, (0, 2), saida)
        self.assertNotIn("Não encontrei o PrePoMax", saida)
        # Uma única janela, atualizada a cada iteração, fica aberta no fim com a melhor;
        # as cópias das iterações foram apagadas.
        self.assertEqual(len(_processos_prepomax(self.resultados)), 1)
        self.assertEqual(os.listdir(os.path.join(self.resultados, "trabalho", "prepomax")), [])
        self.assertTrue(os.path.exists(os.path.join(self.resultados, "L_part_otimizada.frd")))
        self.assertIn("aberto no PrePoMax", saida)
        with open(os.path.join(self.resultados, "trabalho", "prepomax_janela.log"), encoding="utf-8") as f:
            log_janela = f.read()
        self.assertNotIn("falhou", log_janela)  # todas as trocas na mesma janela deram certo
        _fechar_prepomax(self.resultados)
        self.assertFalse(os.path.exists(prepomax.arquivo_recuperacao(prepomax.encontrar())))


if __name__ == "__main__":
    unittest.main()
