import math
import unittest

from otimizador.tensao import medir_tensao


def _distancia_x(p):
    return p[0]


class TestTensao(unittest.TestCase):
    def test_ignora_pico_na_zona(self):
        coords = [(1, 0, 0), (50, 0, 0), (60, 0, 0)]
        m = medir_tensao(coords, [900, 300, 100], _distancia_x, 10, 5, 250)
        self.assertEqual(m.max_filtrado, 300)
        self.assertEqual(m.local_filtrado, (50, 0, 0))
        self.assertEqual(m.max_bruto, 900)
        self.assertEqual(m.local_bruto, (1, 0, 0))
        self.assertEqual(m.max_na_zona, 900)
        self.assertFalse(m.na_borda)

    def test_borda_da_zona(self):
        coords = [(12, 0, 0), (60, 0, 0)]
        self.assertTrue(medir_tensao(coords, [300, 100], _distancia_x, 10, 5, 250).na_borda)
        coords = [(40, 0, 0), (60, 0, 0)]
        self.assertFalse(medir_tensao(coords, [300, 100], _distancia_x, 10, 5, 250).na_borda)

    def test_sem_exclusao(self):
        coords = [(1, 0, 0), (50, 0, 0)]
        m = medir_tensao(coords, [900, 300], lambda p: math.inf, 10, 5, 250)
        self.assertEqual(m.max_filtrado, 900)
        self.assertEqual(m.max_bruto, 900)
        self.assertEqual(m.max_na_zona, 0)

    def test_distancia_calculada_so_no_topo(self):
        chamadas = []

        def dist(p):
            chamadas.append(p)
            return p[0]
        coords = [(i, 0, 0) for i in range(1000)]
        vm = [float(i) for i in range(1000)]
        medir_tensao(coords, vm, dist, 10, 5, 250)
        self.assertLessEqual(len(chamadas), 5)


if __name__ == "__main__":
    unittest.main()
