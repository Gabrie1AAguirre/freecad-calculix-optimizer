"""Gera a malha (Gmsh) e roda o CalculiX para a análise da peça."""
import contextlib
import os
import subprocess


class FalhaAvaliacao(Exception):
    """A avaliação não pôde ser concluída; a mensagem explica o motivo em português."""


@contextlib.contextmanager
def _sem_janela_de_console():
    """O FreeCAD inicia o CalculiX sem esconder a janela: no Windows abriria um cmd
    a cada iteração. Enquanto ativo, todo processo iniciado fica sem janela."""
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    original = subprocess.Popen

    def popen(*args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | flag
        return original(*args, **kwargs)

    subprocess.Popen = popen
    try:
        yield
    finally:
        subprocess.Popen = original


def arquivo_frd(pasta_trabalho):
    """O .frd (resultado do CalculiX) da última análise rodada nessa pasta."""
    arquivos = [os.path.join(pasta_trabalho, n) for n in os.listdir(pasta_trabalho) if n.lower().endswith(".frd")]
    return max(arquivos, key=os.path.getmtime)


def rodar_fea(modelo, pasta_trabalho):
    """Remalha, resolve e devolve o novo objeto de resultado (Fem::FemResultObject)."""
    with _sem_janela_de_console():
        return _rodar_fea(modelo, pasta_trabalho)


def _rodar_fea(modelo, pasta_trabalho):
    from femmesh.gmshtools import GmshTools
    from femtools import ccxtools

    os.makedirs(pasta_trabalho, exist_ok=True)
    try:
        erro = GmshTools(modelo.malha).create_mesh()
    except Exception as exc:
        raise FalhaAvaliacao("O Gmsh não conseguiu gerar a malha: %s" % exc)
    if erro:
        raise FalhaAvaliacao("O Gmsh não conseguiu gerar a malha: %s" % erro)
    if modelo.malha.FemMesh.NodeCount == 0:
        raise FalhaAvaliacao("O Gmsh gerou uma malha vazia.")

    try:
        fea = ccxtools.FemToolsCcx(modelo.analise, modelo.solver)
        fea.purge_results()
        fea.update_objects()
        fea.setup_working_dir(pasta_trabalho)
        fea.setup_ccx()
        mensagem = fea.check_prerequisites()
    except Exception as exc:
        raise FalhaAvaliacao("A análise não está completa: %s" % exc)
    if mensagem:
        raise FalhaAvaliacao("A análise não está completa: %s" % mensagem.strip())

    try:
        fea.write_inp_file()
        fea.ccx_run()
        fea.load_results()
    except Exception as exc:
        raise FalhaAvaliacao("O CalculiX falhou: %s" % exc)

    resultados = [o for o in modelo.analise.Group if o.isDerivedFrom("Fem::FemResultObject")]
    if not resultados or not resultados[-1].vonMises:
        raise FalhaAvaliacao("O CalculiX terminou sem resultados (veja o arquivo .dat em %s)." % pasta_trabalho)
    return resultados[-1]
