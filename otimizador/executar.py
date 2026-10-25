"""Execução dentro do FreeCAD: verificação ou otimização completa de uma peça."""
import os
import shutil
import traceback

import FreeCAD as App

from otimizador import prepomax
from otimizador.avaliacao import OK, OK_VERIFICAR, Avaliador
from otimizador.checagem import checar
from otimizador.fea import arquivo_frd
from otimizador.modelo import encontrar_modelo
from otimizador.otimizacao import ErroLinhaDeBase, mensagem_parada, otimizar
from otimizador.planilha import ler_configuracao
from otimizador.saidas import Historico, cabecalho_terminal, gerar_grafico, linha_terminal, resumo
from otimizador.trabalho import MARCA_FIM, NOME_LOG, NOME_PARAR, carregar

ESPERA_GUI_MS = 500


class Log:
    """Grava cada linha no log.txt (lido ao vivo pelo lançador) e, com
    interface, também no painel Relatório do FreeCAD."""

    def __init__(self, caminho, gui):
        self.caminho, self.gui = caminho, gui

    def escrever(self, texto=""):
        with open(self.caminho, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
        if self.gui:
            App.Console.PrintMessage(texto + "\n")

    def fim(self, codigo):
        with open(self.caminho, "a", encoding="utf-8") as f:
            f.write("%s%d\n" % (MARCA_FIM, codigo))


def iniciar(caminho_trabalho):
    trabalho = carregar(caminho_trabalho)
    if trabalho.gui:
        if trabalho.prepomax:
            from otimizador import gui
            gui.manter_janela_salva()  # a tela dividida não fica gravada no FreeCAD
        # Deixa a janela abrir antes de começar, para a peça aparecer ao vivo.
        from PySide import QtCore
        QtCore.QTimer.singleShot(ESPERA_GUI_MS, lambda: executar(trabalho))
    else:
        executar(trabalho)


def executar(trabalho):
    os.makedirs(trabalho.pasta, exist_ok=True)
    log = Log(os.path.join(trabalho.pasta, NOME_LOG), trabalho.gui)
    try:
        codigo = (checar_peca if trabalho.modo == "checar" else otimizar_peca)(trabalho, log)
    except Exception:
        log.escrever(traceback.format_exc())
        log.escrever("Erro inesperado. Os detalhes acima ajudam a reportar o problema.")
        codigo = 1
    log.fim(codigo)
    if trabalho.gui and trabalho.fechar_ao_terminar:
        from otimizador import gui
        gui.fechar()


def _abrir_copia(trabalho):
    """Abre uma cópia da peça: o arquivo do usuário nunca é gravado."""
    pasta = os.path.join(trabalho.pasta, "trabalho")
    os.makedirs(pasta, exist_ok=True)
    copia = os.path.join(pasta, os.path.basename(trabalho.entrada))
    shutil.copy(trabalho.entrada, copia)
    return App.openDocument(copia)


def _relatar_problemas(doc, log):
    problemas = checar(doc)
    for p in problemas:
        log.escrever("%s: %s" % ("ERRO" if p.nivel == "erro" else "AVISO", p.mensagem))
    return any(p.nivel == "erro" for p in problemas)


def checar_peca(trabalho, log):
    doc = _abrir_copia(trabalho)
    if _relatar_problemas(doc, log):
        log.escrever("A peça ainda não está pronta. Corrija os erros acima e rode --checar de novo.")
        return 1
    log.escrever("✓ A peça está pronta para otimizar.")
    return 0


def otimizar_peca(trabalho, log):
    from otimizador import gui
    nome = os.path.splitext(os.path.basename(trabalho.entrada))[0]
    doc = _abrir_copia(trabalho)
    if _relatar_problemas(doc, log):
        log.escrever("A peça ainda não está pronta. Corrija os erros acima (veja --checar) e rode de novo.")
        return 1

    cfg = ler_configuracao(doc)
    av = Avaliador(doc, cfg, encontrar_modelo(doc), os.path.join(trabalho.pasta, "trabalho", "ccx"))
    aliases = [p.alias for p in cfg.parametros]
    historico_csv = Historico(os.path.join(trabalho.pasta, "historico.csv"), aliases)
    destino = os.path.join(trabalho.pasta, "%s_otimizada.FCStd" % nome)
    destino_frd = os.path.join(trabalho.pasta, "%s_otimizada.frd" % nome)
    caminho_parar = os.path.join(trabalho.pasta, NOME_PARAR)
    vis = None
    if trabalho.gui and trabalho.prepomax:
        vis = prepomax.Visualizador([trabalho.prepomax], os.path.join(trabalho.pasta, "trabalho", "prepomax"))
        gui.metade_esquerda()  # o PrePoMax fica com a direita

    log.escrever("Otimizando %s: menor massa com Von Mises ≤ %.0f MPa, até %d iterações."
                 % (os.path.basename(trabalho.entrada), cfg.tensao_limite, cfg.max_iteracoes))
    for p in cfg.parametros:
        log.escrever("  %s: %g (faixa %g a %g)" % (p.alias, p.valor, p.minimo, p.maximo))
    log.escrever("  zona ignorada em volta de fixações/forças: %.1f mm" % av.zona_mm)
    log.escrever("")
    log.escrever(cabecalho_terminal(aliases))
    if trabalho.gui:
        gui.atualizar()

    def ao_iterar(it, eh_melhor):
        historico_csv.adicionar(it)
        log.escrever(linha_terminal(it, aliases, eh_melhor))
        if eh_melhor and it.valida:
            # saveCopy não renomeia o documento; apagar antes evita o backup .FCBak.
            if os.path.exists(destino):
                os.remove(destino)
            doc.saveCopy(destino)
            prepomax.tensao_primeiro(arquivo_frd(av.pasta_trabalho), destino_frd)
        if vis:
            if av.ultimo_resultado is not None:
                vis.mostrar(arquivo_frd(av.pasta_trabalho))
            gui.mostrar_peca(doc, av.modelo.corpo, enquadrar=it.numero == 1)
        elif trabalho.gui:
            gui.mostrar(doc, av.ultimo_resultado, enquadrar=it.numero == 1)

    try:
        melhor, historico, motivo = otimizar(av.avaliar, cfg, ao_iterar, lambda: os.path.exists(caminho_parar))
    except ErroLinhaDeBase as exc:
        log.escrever("A peça com os valores atuais não pôde ser analisada: %s" % exc)
        return 1

    log.escrever("")
    log.escrever(mensagem_parada(motivo, cfg))
    gerar_grafico(historico, cfg.tensao_limite, os.path.join(trabalho.pasta, "grafico.png"))
    log.escrever(resumo(historico[0], melhor, cfg.tensao_limite))
    log.escrever("Resultados em: %s" % trabalho.pasta)

    if trabalho.gui:
        App.closeDocument(doc.Name)
        final = App.openDocument(destino)
        resultados = [o for o in final.Objects if o.isDerivedFrom("Fem::FemResultObject")]
        gui.mostrar(final, resultados[-1] if resultados else None, enquadrar=True)
        gui.salvar_imagem(final, os.path.join(trabalho.pasta, "vista.png"))
        if vis:
            gui.mostrar_peca(final, encontrar_modelo(final).corpo, enquadrar=True)
    if vis:
        if os.path.exists(destino_frd):
            vis.mostrar_arquivo(destino_frd)
            log.escrever("Resultado da melhor iteração aberto no PrePoMax (STRESS → MISES, em MPa).")
        else:
            vis.fechar()
    return 0 if melhor.status in (OK, OK_VERIFICAR) else 2
