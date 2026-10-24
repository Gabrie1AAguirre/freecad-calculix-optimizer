"""Otimizador de forma FreeCAD + CalculiX.

Uso:
    python otimizar.py minha_peca.FCStd                 # abre o FreeCAD e otimiza ao vivo
    python otimizar.py minha_peca.FCStd --sem-interface # sem abrir janela
    python otimizar.py minha_peca.FCStd --checar        # só verifica a preparação

Roda com o Python do sistema (só biblioteca padrão): encontra o FreeCAD,
inicia a otimização dentro dele e mostra o progresso aqui no terminal.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

from otimizador.trabalho import (MARCA_FIM, NOME_LOG, NOME_PARAR, VARIAVEL_AMBIENTE,  # noqa: E402
                                 Trabalho, salvar)

FREECAD_PADRAO = r"C:\Program Files\FreeCAD 1.1\bin"
INICIAR = os.path.join(RAIZ, "otimizador", "_iniciar.py")
INTERVALO_S = 0.3


def ler_codigo_fim(linhas):
    for linha in reversed(linhas):
        if linha.startswith(MARCA_FIM):
            return int(linha[len(MARCA_FIM):].strip())
    return None


def _pasta_freecad(args):
    pasta = args.freecad or os.environ.get("FREECAD_BIN") or FREECAD_PADRAO
    if os.path.isdir(os.path.join(pasta, "bin")):
        pasta = os.path.join(pasta, "bin")
    faltando = [exe for exe in ("freecad.exe", "freecadcmd.exe") if not os.path.isfile(os.path.join(pasta, exe))]
    return pasta, faltando


def _comando(pasta_freecad, gui):
    if gui:
        return [os.path.join(pasta_freecad, "freecad.exe"), INICIAR]
    return [os.path.join(pasta_freecad, "freecadcmd.exe"), "-c",
            "exec(open(r'%s', encoding='utf-8').read())" % INICIAR]


def _acompanhar(processo, caminho_log, caminho_parar):
    """Mostra as linhas novas do log até o FreeCAD terminar. Ctrl+C pede parada."""
    lidas, linhas = 0, []
    while True:
        try:
            terminou = processo.poll() is not None
            if os.path.exists(caminho_log):
                with open(caminho_log, encoding="utf-8") as f:
                    linhas = f.read().splitlines()
                for linha in linhas[lidas:]:
                    if not linha.startswith(MARCA_FIM):
                        print(linha, flush=True)
                lidas = len(linhas)
            if terminou:
                return linhas
            time.sleep(INTERVALO_S)
        except KeyboardInterrupt:
            if not os.path.exists(caminho_parar):
                open(caminho_parar, "w").close()
                print("\nParada pedida: termino a iteração atual e salvo o melhor resultado...", flush=True)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Otimiza a forma de uma peça do FreeCAD para reduzir o Von Mises.")
    parser.add_argument("peca", help="arquivo .FCStd preparado (análise FEM + planilha Parametros)")
    parser.add_argument("--sem-interface", action="store_true", help="roda sem abrir a janela do FreeCAD")
    parser.add_argument("--checar", action="store_true", help="só verifica se a peça está pronta")
    parser.add_argument("--freecad", help="pasta do FreeCAD (a que tem freecad.exe), se não for a padrão")
    parser.add_argument("--resultados", help="pasta onde salvar os resultados")
    parser.add_argument("--fechar-ao-terminar", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    peca = os.path.abspath(args.peca)
    if not os.path.isfile(peca):
        print("Não encontrei o arquivo %s." % peca)
        return 1
    pasta_freecad, faltando = _pasta_freecad(args)
    if faltando:
        print("Não encontrei o FreeCAD em %s (faltam %s). Informe a pasta com --freecad \"C:\\...\\FreeCAD 1.1\\bin\"."
              % (pasta_freecad, ", ".join(faltando)))
        return 1

    if args.checar:
        pasta = args.resultados or tempfile.mkdtemp(prefix="checar_")
    else:
        nome = os.path.splitext(os.path.basename(peca))[0]
        pasta = args.resultados or os.path.join(RAIZ, "resultados",
                                                "%s_%s" % (nome, datetime.now().strftime("%Y%m%d-%H%M%S")))
    os.makedirs(pasta, exist_ok=True)
    caminho_log = os.path.join(pasta, NOME_LOG)
    if os.path.exists(caminho_log):
        os.remove(caminho_log)

    gui = not (args.sem_interface or args.checar)
    trabalho = Trabalho(modo="checar" if args.checar else "otimizar", entrada=peca, pasta=pasta, gui=gui,
                        fechar_ao_terminar=args.fechar_ao_terminar, repo=RAIZ)
    caminho_trabalho = os.path.join(pasta, "trabalho.json")
    salvar(trabalho, caminho_trabalho)

    env = dict(os.environ, **{VARIAVEL_AMBIENTE: caminho_trabalho})
    with open(os.path.join(pasta, "freecad_saida.txt"), "w", encoding="utf-8", errors="replace") as saida:
        processo = subprocess.Popen(_comando(pasta_freecad, gui), env=env, stdout=saida, stderr=subprocess.STDOUT)
        linhas = _acompanhar(processo, caminho_log, os.path.join(pasta, NOME_PARAR))

    codigo = ler_codigo_fim(linhas)
    if codigo is None:
        print("O FreeCAD foi fechado antes do fim. O melhor resultado até agora (se houver) está em %s." % pasta)
        print("Detalhes da saída do FreeCAD: %s" % os.path.join(pasta, "freecad_saida.txt"))
        return 1
    return codigo


if __name__ == "__main__":
    sys.exit(main())
