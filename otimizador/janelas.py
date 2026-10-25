"""Tela dividida: FreeCAD na metade esquerda, PrePoMax na direita (só Windows,
biblioteca padrão). O PrePoMax é posicionado pelo prepomax_janela.ps1, com a
mesma conta."""
import ctypes
import os

ESQUERDA, DIREITA = "esquerda", "direita"


def metade(area, lado, borda=(0, 0, 0, 0)):
    """(x, y, largura, altura) para a janela ocupar uma metade da área de trabalho
    (esq, topo, dir, base). `borda` é a margem invisível da janela (esq, topo, dir,
    base) que o Windows 10/11 desenha fora da parte visível."""
    esq, topo, dir_, base = area
    meio = (esq + dir_) // 2
    x0, x1 = (esq, meio) if lado == ESQUERDA else (meio, dir_)
    return (x0 - borda[0], topo - borda[1], x1 - x0 + borda[0] + borda[2], base - topo + borda[1] + borda[3])


def area_de_trabalho():
    """Tela principal menos a barra de tarefas: (esq, topo, dir, base)."""
    from ctypes import wintypes
    r = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return (r.left, r.top, r.right, r.bottom)


def posicionar(janela, lado):
    """Põe a janela (HWND) numa metade da tela principal. False se não deu."""
    if os.name != "nt" or not janela:
        return False
    from ctypes import wintypes
    user32, h = ctypes.windll.user32, wintypes.HWND(janela)
    if not user32.IsWindow(h):
        return False
    if user32.IsZoomed(h) or user32.IsIconic(h):
        user32.ShowWindow(h, 9)  # SW_RESTORE: maximizada, ela ignoraria o tamanho
    fora, dentro = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(fora))
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(dentro), ctypes.sizeof(dentro)):  # EXTENDED_FRAME_BOUNDS
        dentro = fora
    borda = (dentro.left - fora.left, dentro.top - fora.top, fora.right - dentro.right, fora.bottom - dentro.bottom)
    x, y, largura, altura = metade(area_de_trabalho(), lado, borda)
    SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
    return bool(user32.SetWindowPos(h, None, x, y, largura, altura, SWP_NOZORDER | SWP_NOACTIVATE))
