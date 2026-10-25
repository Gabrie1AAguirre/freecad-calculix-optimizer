"""Utilidades compartilhadas pelos testes."""
import hashlib
import os
import shutil
import tempfile

import FreeCAD as App

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEMPLO_L = os.path.join(RAIZ, "exemplos", "L_part.FCStd")
ORIGINAL_L = os.path.join(RAIZ, "tests", "dados", "L_part_original.FCStd")  # peça sem planilha, com resultados antigos
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


def parte_visivel(pid):
    """(x, y, largura, altura) visível da maior janela do processo."""
    import ctypes
    from ctypes import wintypes
    user32, achadas = ctypes.windll.user32, []

    def anotar(h, _):
        dono = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(dono))
        if dono.value == pid and user32.IsWindowVisible(h):
            r = wintypes.RECT()
            ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(h), 9, ctypes.byref(r), ctypes.sizeof(r))
            achadas.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(anotar), 0)
    return max(achadas, key=lambda r: r[2] * r[3], default=None)
