import ctypes
import os
import unittest
from ctypes import wintypes

from otimizador import janelas


class TestMetade(unittest.TestCase):
    AREA = (0, 0, 1920, 1032)  # tela cheia menos a barra de tarefas

    def test_esquerda(self):
        self.assertEqual(janelas.metade(self.AREA, janelas.ESQUERDA), (0, 0, 960, 1032))

    def test_direita(self):
        self.assertEqual(janelas.metade(self.AREA, janelas.DIREITA), (960, 0, 960, 1032))

    def test_area_deslocada(self):
        # Barra de tarefas à esquerda ou monitor que não começa em 0.
        self.assertEqual(janelas.metade((100, 50, 1101, 850), janelas.DIREITA), (600, 50, 501, 800))

    def test_borda_invisivel(self):
        # No Windows 10/11 a janela tem uma borda invisível de uns 7 px fora do que se vê:
        # o retângulo cresce para que a parte visível ocupe exatamente a metade.
        self.assertEqual(janelas.metade(self.AREA, janelas.ESQUERDA, borda=(7, 0, 7, 7)), (-7, 0, 974, 1039))


@unittest.skipUnless(os.name == "nt", "só Windows")
class TestPosicionar(unittest.TestCase):
    def setUp(self):
        user32 = ctypes.windll.user32
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        WS_OVERLAPPEDWINDOW, WS_VISIBLE = 0x00CF0000, 0x10000000
        self.janela = user32.CreateWindowExW(0, "STATIC", "teste janelas", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                             200, 200, 400, 300, None, None, None, None)
        self.assertTrue(self.janela)
        self.addCleanup(user32.DestroyWindow, self.janela)

    def _visivel(self):
        r = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(self.janela), 9, ctypes.byref(r), ctypes.sizeof(r))
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    def test_parte_visivel_ocupa_a_metade(self):
        for lado in (janelas.ESQUERDA, janelas.DIREITA):
            self.assertTrue(janelas.posicionar(self.janela, lado))
            self.assertEqual(self._visivel(), janelas.metade(janelas.area_de_trabalho(), lado))

    def test_janela_maximizada(self):
        ctypes.windll.user32.ShowWindow(wintypes.HWND(self.janela), 3)  # SW_MAXIMIZE
        self.assertTrue(janelas.posicionar(self.janela, janelas.DIREITA))
        self.assertFalse(ctypes.windll.user32.IsZoomed(wintypes.HWND(self.janela)))
        self.assertEqual(self._visivel(), janelas.metade(janelas.area_de_trabalho(), janelas.DIREITA))

    def test_janela_inexistente(self):
        self.assertFalse(janelas.posicionar(0, janelas.ESQUERDA))


if __name__ == "__main__":
    unittest.main()
