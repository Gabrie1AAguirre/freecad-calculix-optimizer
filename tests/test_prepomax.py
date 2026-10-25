import os
import shutil
import sys
import tempfile
import time
import unittest

from otimizador import prepomax

FRD = """    1C
    2C                             2                                     1
 -1         1 0.00000E+00 0.00000E+00 0.00000E+00
 -3
    1PSTEP                         1           1           1
 -4  DISP        4    1
 -1         1 1.00000E-03 0.00000E+00 0.00000E+00
 -3
    1PSTEP                         2           1           1
 -4  STRESS      6    1
 -1         1 2.50000E+02 0.00000E+00 0.00000E+00
 -3
 9999
"""

# Conteúdo qualquer no lugar do arquivo de recuperação (history.pmh) do PrePoMax.
HISTORICO_FALSO = b"historico de teste do otimizador"

# Programa falso no lugar do PrePoMax: grava os argumentos e fica aberto.
FALSO = """import os, sys, time
open(sys.argv[1], "w").write("\\n".join(sys.argv[2:] + [os.getcwd()]))
time.sleep(120)
"""


def _blocos(texto):
    return [l.split()[1] for l in texto.splitlines() if l.strip().startswith("-4")]


class TestFrd(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.origem = os.path.join(self.pasta, "a.frd")

    def test_tensao_vem_primeiro(self):
        # O PrePoMax abre mostrando o primeiro bloco do .frd: assim abre direto no Von Mises.
        with open(self.origem, "w") as f:
            f.write(FRD)
        destino = os.path.join(self.pasta, "b.frd")
        prepomax.tensao_primeiro(self.origem, destino)
        with open(destino) as f:
            texto = f.read()
        self.assertEqual(_blocos(texto), ["STRESS", "DISP"])
        self.assertEqual(sorted(texto.splitlines()), sorted(FRD.splitlines()))
        self.assertTrue(texto.startswith("    1C\n"))
        self.assertEqual(texto.splitlines()[-1].strip(), "9999")

    def test_sem_tensao_copia_igual(self):
        sem_tensao = FRD.replace("STRESS", "TOSTRAIN")
        with open(self.origem, "w") as f:
            f.write(sem_tensao)
        destino = os.path.join(self.pasta, "b.frd")
        prepomax.tensao_primeiro(self.origem, destino)
        with open(destino) as f:
            self.assertEqual(f.read(), sem_tensao)


class TestEncontrar(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, True)

    def _instalar(self, nome):
        pasta = os.path.join(self.base, nome)
        os.makedirs(pasta)
        open(os.path.join(pasta, "PrePoMax.exe"), "w").close()
        return pasta

    def test_pasta_informada(self):
        pasta = self._instalar("qualquer")
        self.assertEqual(prepomax.encontrar(pasta, ambiente={}, locais=[]), os.path.join(pasta, "PrePoMax.exe"))

    def test_pasta_informada_sem_exe(self):
        self.assertIsNone(prepomax.encontrar(self.base, ambiente={}, locais=[]))

    def test_variavel_de_ambiente(self):
        pasta = self._instalar("env")
        self.assertEqual(prepomax.encontrar(None, ambiente={"PREPOMAX_BIN": pasta}, locais=[]),
                         os.path.join(pasta, "PrePoMax.exe"))

    def test_procura_versao_mais_nova(self):
        self._instalar("PrePoMax v2.5.10")
        self._instalar("PrePoMax v2.6.0")
        self._instalar("PrePoMax v2.10.1")
        achado = prepomax.encontrar(None, ambiente={}, locais=[os.path.join(self.base, "PrePoMax*")])
        self.assertEqual(achado, os.path.join(self.base, "PrePoMax v2.10.1", "PrePoMax.exe"))

    def test_nao_encontrado(self):
        self.assertIsNone(prepomax.encontrar(None, ambiente={}, locais=[os.path.join(self.base, "PrePoMax*")]))


class _Base(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.copias = os.path.join(self.pasta, "copias")
        self.frd = os.path.join(self.pasta, "ccx.frd")
        with open(self.frd, "w") as f:
            f.write(FRD)


class TestVisualizadorSemJanela(_Base):
    """Com um programa falso no lugar do PrePoMax (sem janela para comandar)."""

    def setUp(self):
        super().setUp()
        self.falso = os.path.join(self.pasta, "falso.py")
        with open(self.falso, "w") as f:
            f.write(FALSO)
        self.registro = os.path.join(self.pasta, "registro.txt")
        self.vis = prepomax.Visualizador([sys.executable, self.falso, self.registro], self.copias, comandar_janela=False)
        self.addCleanup(self.vis.fechar)

    def _argumentos(self):
        for _ in range(100):
            if os.path.exists(self.registro) and os.path.getsize(self.registro):
                with open(self.registro) as f:
                    return f.read().splitlines()
            time.sleep(0.1)
        self.fail("o programa não foi iniciado")

    def test_abre_copia_com_tensao_primeiro(self):
        self.vis.mostrar(self.frd)
        args = self._argumentos()
        self.assertEqual(args[0], "-f")
        self.assertEqual(os.path.dirname(args[1]), self.copias)  # cópia: o CalculiX sobrescreve o original
        self.assertEqual(args[2:4], ["-u", "MM_TON_S_C"])
        # Aberto pelo FreeCAD, com a pasta de trabalho dele, o PrePoMax não carrega o .frd.
        self.assertEqual(os.path.normcase(args[4]), os.path.normcase(os.path.dirname(sys.executable)))
        with open(args[1]) as f:
            self.assertEqual(_blocos(f.read()), ["STRESS", "DISP"])

    def test_sem_comandar_a_janela_reabre(self):
        self.vis.mostrar(self.frd)
        primeiro = self.vis.processo
        self.vis.mostrar(self.frd)
        self.assertIsNotNone(primeiro.wait(timeout=10))  # a janela anterior foi fechada
        self.assertIsNone(self.vis.processo.poll())
        self.assertEqual(len(os.listdir(self.copias)), 1)  # a cópia anterior foi apagada

    def test_arquivo_final_nao_e_apagado(self):
        final = os.path.join(self.pasta, "final.frd")
        shutil.copy(self.frd, final)
        self.vis.mostrar(self.frd)
        self.vis.mostrar_arquivo(final)
        self.assertTrue(os.path.exists(final))
        self.assertEqual(os.listdir(self.copias), [])


@unittest.skipUnless(prepomax.encontrar(), "PrePoMax não instalado")
class TestVisualizadorPrePoMax(_Base):
    def setUp(self):
        super().setUp()
        self.recuperacao = prepomax.arquivo_recuperacao(prepomax.encontrar())
        if os.path.exists(self.recuperacao):
            self.skipTest("há um arquivo de recuperação do PrePoMax de uma sessão sua; não mexo nele")
        self.addCleanup(lambda: os.path.exists(self.recuperacao) and os.remove(self.recuperacao))
        from otimizador.fea import arquivo_frd, rodar_fea
        from otimizador.modelo import encontrar_modelo
        from tests.util import EXEMPLO_L, abrir_copia
        ccx = os.path.join(self.pasta, "ccx")
        rodar_fea(encontrar_modelo(abrir_copia(EXEMPLO_L, self)), ccx)
        self.frd = arquivo_frd(ccx)

    def test_atualiza_a_mesma_janela(self):
        vis = prepomax.Visualizador([prepomax.encontrar()], self.copias)
        self.addCleanup(vis.fechar)
        vis.mostrar(self.frd)
        vis.esperar()
        self.assertTrue(vis.ultimo_ajuste_ok, "não girou para a vista isométrica")
        pid = vis.processo.pid

        vis.mostrar(self.frd)
        vis.esperar()
        self.assertTrue(vis.ultimo_ajuste_ok, "não abriu o novo resultado na janela")
        self.assertEqual(vis.processo.pid, pid)       # mesma janela
        self.assertIsNone(vis.processo.poll())
        self.assertEqual(len(os.listdir(self.copias)), 1)

        # Fechado à força, o PrePoMax deixa um arquivo de recuperação e pergunta por ele
        # na próxima abertura (e não carrega o .frd): tem que fechar como pelo X.
        self.assertTrue(prepomax.fechar_pelo_x(vis.processo.pid))
        self.assertFalse(os.path.exists(self.recuperacao))

    def test_pergunta_de_recuperacao_nao_trava(self):
        # Um arquivo de recuperação de outra sessão: guardado e a pergunta respondida "não".
        with open(self.recuperacao, "wb") as f:
            f.write(HISTORICO_FALSO)
        vis = prepomax.Visualizador([prepomax.encontrar()], self.copias)
        self.addCleanup(vis.fechar)
        vis.mostrar(self.frd)
        vis.esperar()
        self.assertTrue(vis.ultimo_ajuste_ok)
        guardados = [n for n in os.listdir(self.pasta) if n.startswith("prepomax_recuperacao")]
        self.assertEqual(len(guardados), 1)
        with open(os.path.join(self.pasta, guardados[0]), "rb") as f:
            self.assertEqual(f.read(), HISTORICO_FALSO)


if __name__ == "__main__":
    unittest.main()
