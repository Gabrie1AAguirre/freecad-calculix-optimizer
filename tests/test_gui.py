"""Testes da janela do FreeCAD (abre o freecad.exe de verdade, que fecha sozinho)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import FreeCAD as App

from otimizador import janelas
from tests.util import FREECAD_BIN, RAIZ

# Roda dentro do FreeCAD: divide a tela como numa otimização com o PrePoMax e anota o resultado.
SCRIPT = """import json, sys
sys.path.insert(0, %(raiz)r)
import FreeCADGui as Gui
from PySide import QtWidgets
from otimizador import gui
gui.manter_janela_salva()
gui.metade_esquerda()
janela = Gui.getMainWindow()
paineis = [d.width() for d in janela.findChildren(QtWidgets.QDockWidget) if d.isVisible() and not d.isFloating()]
with open(%(saida)r, "w") as f:
    json.dump({"janela": janela.width(), "paineis": paineis}, f)
gui.fechar()
"""


def _janela_salva():
    """O que o FreeCAD grava da janela ao fechar (user.cfg): tamanho, maximizada e painéis."""
    with open(os.path.join(App.getUserConfigDir(), "user.cfg"), encoding="utf-8") as f:
        texto = f.read()
    return re.findall(r'<FC\w+ Name="(?:Geometry|Maximized|MainWindowState)"[^>]*>(?:[^<]*</FC\w+>)?', texto)


@unittest.skipUnless(os.name == "nt", "só Windows")
class TestTelaDividida(unittest.TestCase):
    def test_painel_estreito_e_nada_gravado(self):
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        script, saida = os.path.join(pasta, "dividir.py"), os.path.join(pasta, "medidas.json")
        with open(script, "w", encoding="utf-8") as f:
            f.write(SCRIPT % {"raiz": RAIZ, "saida": saida})
        antes = _janela_salva()
        subprocess.run([os.path.join(FREECAD_BIN, "freecad.exe"), script], timeout=120, capture_output=True)
        with open(saida) as f:
            medidas = json.load(f)
        # O painel Model/Tasks fica estreito para a peça aparecer maior.
        self.assertTrue(medidas["paineis"])
        self.assertLessEqual(max(medidas["paineis"]), medidas["janela"] // janelas.PROPORCAO_PAINEL + 10)
        # Tudo isso só desta vez: o FreeCAD do usuário continua abrindo como antes.
        self.assertEqual(_janela_salva(), antes)


if __name__ == "__main__":
    unittest.main()
