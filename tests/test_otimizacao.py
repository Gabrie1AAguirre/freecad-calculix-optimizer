import unittest

from otimizador.avaliacao import ACIMA, INVALIDA, OK, OK_VERIFICAR, Iteracao
from otimizador.otimizacao import ErroLinhaDeBase, escolher_melhor, otimizar
from otimizador.planilha import Configuracao, Parametro


def _cfg(limite=10.0, max_iteracoes=30):
    return Configuracao(parametros=[Parametro("a", 20.0, 1.0, 20.0, "B2"), Parametro("b", 20.0, 1.0, 20.0, "B3")],
                        tensao_limite=limite, max_iteracoes=max_iteracoes)


class Falso:
    """Peça de mentira: massa = a + b, tensão = 1000 / (a * b)."""

    def __init__(self, limite, invalida_se=None):
        self.limite, self.invalida_se, self.chamadas = limite, invalida_se, []

    def __call__(self, valores):
        self.chamadas.append(dict(valores))
        n = len(self.chamadas)
        if self.invalida_se and self.invalida_se(valores):
            return Iteracao(n, dict(valores), status=INVALIDA, motivo="geometria impossível")
        vm = 1000.0 / (valores["a"] * valores["b"])
        return Iteracao(n, dict(valores), von_mises=vm, von_mises_bruto=vm, massa_kg=valores["a"] + valores["b"],
                        status=OK if vm <= self.limite else ACIMA)


def _nada(*_):
    pass


def _nunca():
    return False


class TestOtimizacao(unittest.TestCase):
    def test_encontra_viavel_leve(self):
        melhor, hist = otimizar(Falso(10.0), _cfg(), _nada, _nunca)
        self.assertEqual(melhor.status, OK)
        self.assertLessEqual(melhor.von_mises, 10.0)
        self.assertLess(melhor.massa_kg, 30.0)  # começa em 40; ótimo é 20

    def test_respeita_limites(self):
        falso = Falso(10.0)
        otimizar(falso, _cfg(), _nada, _nunca)
        for v in falso.chamadas:
            self.assertTrue(1.0 <= v["a"] <= 20.0 and 1.0 <= v["b"] <= 20.0, v)

    def test_linha_de_base_primeiro(self):
        falso = Falso(10.0)
        otimizar(falso, _cfg(), _nada, _nunca)
        self.assertEqual(falso.chamadas[0], {"a": 20.0, "b": 20.0})

    def test_passos_nao_minusculos_partindo_do_limite(self):
        # Valores iniciais no limite (como raio_canto = mínimo): os primeiros passos
        # precisam ser grandes o bastante para sair do ruído da malha.
        falso = Falso(10.0)
        otimizar(falso, _cfg(max_iteracoes=4), _nada, _nunca)
        for v in falso.chamadas[1:]:
            mudanca = max(abs(v["a"] - 20.0), abs(v["b"] - 20.0)) / 19.0
            self.assertGreaterEqual(mudanca, 0.1, v)

    def test_max_iteracoes(self):
        _, hist = otimizar(Falso(10.0), _cfg(max_iteracoes=5), _nada, _nunca)
        self.assertLessEqual(len(hist), 5)

    def test_parada_pedida(self):
        chamadas = []

        def parar():
            chamadas.append(1)
            return len(chamadas) >= 3
        melhor, hist = otimizar(Falso(10.0), _cfg(), _nada, parar)
        self.assertLessEqual(len(hist), 4)
        self.assertIsNotNone(melhor)

    def test_ao_iterar_avisa_melhor(self):
        avisos = []
        otimizar(Falso(10.0), _cfg(max_iteracoes=6), lambda it, melhor: avisos.append((it.numero, melhor)), _nunca)
        self.assertEqual(avisos[0], (1, True))
        self.assertEqual(len(avisos), 6)

    def test_nenhum_viavel(self):
        melhor, hist = otimizar(Falso(0.1), _cfg(limite=0.1, max_iteracoes=15), _nada, _nunca)
        self.assertEqual(melhor.status, ACIMA)
        self.assertEqual(melhor.von_mises, min(it.von_mises for it in hist))

    def test_prefere_ok_limpo(self):
        verificar = Iteracao(1, {}, von_mises=5, massa_kg=1.0, status=OK_VERIFICAR)
        limpo = Iteracao(2, {}, von_mises=5, massa_kg=2.0, status=OK)
        self.assertIs(escolher_melhor([verificar, limpo]), limpo)
        self.assertIs(escolher_melhor([verificar]), verificar)

    def test_invalida_nao_quebra(self):
        melhor, hist = otimizar(Falso(10.0, invalida_se=lambda v: v["a"] < 12), _cfg(), _nada, _nunca)
        self.assertIsNotNone(melhor)
        self.assertNotEqual(melhor.status, INVALIDA)

    def test_linha_de_base_ja_viavel(self):
        melhor, hist = otimizar(Falso(1e6), _cfg(limite=1e6), _nada, _nunca)
        self.assertEqual(melhor.status, OK)
        self.assertLessEqual(melhor.massa_kg, hist[0].massa_kg)

    def test_linha_de_base_invalida(self):
        falso = Falso(10.0, invalida_se=lambda v: True)
        with self.assertRaises(ErroLinhaDeBase) as ctx:
            otimizar(falso, _cfg(), _nada, _nunca)
        self.assertIn("geometria impossível", str(ctx.exception))
        self.assertEqual(len(falso.chamadas), 1)

    def test_tres_invalidas_seguidas(self):
        falso = Falso(10.0, invalida_se=lambda v: len(falso.chamadas) > 1)
        melhor, hist = otimizar(falso, _cfg(), _nada, _nunca)
        self.assertEqual(len(hist), 4)
        self.assertEqual([it.status for it in hist[1:]], [INVALIDA] * 3)
        self.assertIs(melhor, hist[0])


if __name__ == "__main__":
    unittest.main()
