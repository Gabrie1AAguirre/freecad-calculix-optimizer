"""Utilidades compartilhadas pelos testes."""
import hashlib
import os
import shutil
import tempfile

import FreeCAD as App

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEMPLO_L = os.path.join(RAIZ, "exemplos", "L_part.FCStd")
ORIGINAL_L = os.path.join(RAIZ, "L_part.FCStd")
FREECAD_BIN = os.environ.get("FREECAD_BIN", r"C:\Program Files\FreeCAD 1.1\bin")
FREECAD_PYTHON = os.path.join(FREECAD_BIN, "python.exe")


def copia_temporaria(caminho, testcase, nome_pasta="otim"):
    """Copia o arquivo para uma pasta temporária apagada ao fim do teste."""
    pasta = tempfile.mkdtemp(prefix=nome_pasta)
    testcase.addCleanup(shutil.rmtree, pasta, True)
    destino = os.path.join(pasta, os.path.basename(caminho))
    shutil.copy(caminho, destino)
    return destino


def abrir_copia(caminho, testcase):
    doc = App.openDocument(copia_temporaria(caminho, testcase))
    testcase.addCleanup(lambda: App.closeDocument(doc.Name) if doc.Name in App.listDocuments() else None)
    return doc


def sha256(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
