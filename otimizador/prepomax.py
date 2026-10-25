"""Visualização dos resultados no PrePoMax: peça colorida pelo Von Mises com a
barra de tensão. Só usa a biblioteca padrão (é importado pelo lançador também)."""
import glob
import os
import re
import shutil
import subprocess
import time

NOME_EXE = "PrePoMax.exe"
VARIAVEL_AMBIENTE = "PREPOMAX_BIN"
LOCAIS_PADRAO = [
    os.path.join(os.path.expanduser("~"), "Documents", "PrePoMax*"),
    os.path.join(os.path.expanduser("~"), "Documents", "*", "PrePoMax*"),
    os.path.join(os.path.expanduser("~"), "Desktop", "PrePoMax*"),
    os.path.join(os.path.expanduser("~"), "Downloads", "PrePoMax*"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PrePoMax*"),
    r"C:\PrePoMax*",
]
# mm, tonelada, s: tensões em MPa e comprimentos em mm, como no FreeCAD.
UNIDADES = "MM_TON_S_C"


def _exe_em(pasta):
    exe = os.path.join(pasta, NOME_EXE)
    return exe if os.path.isfile(exe) else None


def _versao(caminho):
    return [int(n) for n in re.findall(r"\d+", os.path.basename(os.path.dirname(caminho)))]


def encontrar(pasta=None, ambiente=os.environ, locais=None):
    """Caminho do PrePoMax.exe: pasta informada, variável PREPOMAX_BIN ou a versão
    mais nova nos locais comuns. None se não encontrar."""
    if pasta:
        return _exe_em(pasta)
    if ambiente.get(VARIAVEL_AMBIENTE):
        return _exe_em(ambiente[VARIAVEL_AMBIENTE])
    achados = [exe for padrao in (LOCAIS_PADRAO if locais is None else locais)
               for exe in glob.glob(os.path.join(padrao, NOME_EXE))]
    return max(achados, key=_versao) if achados else None


def tensao_primeiro(origem, destino):
    """Copia o .frd do CalculiX pondo o bloco de tensões antes dos outros: o
    PrePoMax abre mostrando o primeiro bloco, então já abre no Von Mises."""
    with open(origem, encoding="latin-1") as f:
        linhas = f.read().splitlines(keepends=True)
    cabecalho, blocos, fim, atual = [], [], [], None
    for linha in linhas:
        texto = linha.strip()
        if texto.startswith("1PSTEP"):
            atual = [linha]
            blocos.append(atual)
        elif texto == "9999":
            fim.append(linha)
            atual = None
        elif atual is not None:
            atual.append(linha)
            if texto == "-3":
                atual = None
        else:
            cabecalho.append(linha)
    if not any(_nome_bloco(b) == "STRESS" for b in blocos):
        shutil.copyfile(origem, destino)
        return
    blocos.sort(key=lambda b: _nome_bloco(b) != "STRESS")
    with open(destino, "w", encoding="latin-1", newline="") as f:
        f.write("".join(cabecalho + [linha for b in blocos for linha in b] + fim))


def _nome_bloco(bloco):
    for linha in bloco:
        partes = linha.split()
        if partes and partes[0] == "-4" and len(partes) > 1:
            return partes[1]
    return None


def arquivo_recuperacao(exe):
    """Onde o PrePoMax guarda a sessão para recuperar se for fechado à força. Se o
    arquivo existe, a próxima abertura pergunta se quer recuperar e não carrega o .frd."""
    return os.path.join(os.path.dirname(exe), "history.pmh")


def _processo_vivo(pid):
    import ctypes
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        codigo = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


def fechar_pelo_x(pid, espera_s=15):
    """Fecha o PrePoMax como pelo X, respondendo "No" a "Save file before closing?":
    assim ele não deixa arquivo de recuperação. False se não fechou."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    WM_CLOSE, WM_COMMAND, IDNO = 0x0010, 0x0111, 7
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def janelas():
        achadas = []

        def anotar(h, _):
            dono = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(dono))
            if dono.value == pid and user32.IsWindowVisible(h):
                classe = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(h, classe, 64)
                achadas.append((h, classe.value == "#32770"))
            return True
        user32.EnumWindows(callback(anotar), 0)
        return achadas

    for h, dialogo in janelas():
        if not dialogo:
            user32.PostMessageW(h, WM_CLOSE, 0, 0)
    fim = time.time() + espera_s
    while time.time() < fim:
        if not _processo_vivo(pid):
            return True
        for h, dialogo in janelas():
            if dialogo:
                user32.PostMessageW(h, WM_COMMAND, IDNO, 0)
        time.sleep(0.2)
    return False


def _iniciar(comando, erros=None, pasta=None):
    return subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=erros or subprocess.DEVNULL, cwd=pasta,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _apagar(caminho):
    try:
        os.remove(caminho)
    except OSError:
        pass


class Visualizador:
    """Uma janela do PrePoMax com o último resultado.

    A primeira vez abre o PrePoMax; depois o script prepomax_janela.ps1 abre cada
    novo resultado na MESMA janela (File > Open) e gira para a vista isométrica.
    Cada troca leva alguns segundos: se chegar um resultado com a janela ainda
    ocupada, fica só o mais novo esperando. Se o script falhar, fecha a janela e
    abre outra na próxima vez. Só fecha janelas que ele mesmo abriu."""

    def __init__(self, comando, pasta, comandar_janela=True):
        self.comando = list(comando)
        self.pasta = pasta  # cópias dos .frd (apagadas quando não são mais necessárias)
        self.comandar_janela = comandar_janela
        os.makedirs(pasta, exist_ok=True)
        self.log = os.path.join(os.path.dirname(os.path.abspath(pasta)), NOME_LOG_JANELA)
        self.processo = None   # o PrePoMax
        self.ajuste = None     # o script comandando a janela, enquanto roda
        self.carregando = None
        self.mostrado = None
        self.pendente = None
        self.contador = 0
        self.ultimo_ajuste_ok = None

    def mostrar(self, frd_calculix):
        """Mostra um resultado do CalculiX (copiado: a próxima análise sobrescreve o arquivo)."""
        self.contador += 1
        copia = os.path.join(self.pasta, "resultado_%03d.frd" % self.contador)
        tensao_primeiro(frd_calculix, copia)
        self._enfileirar(copia)

    def mostrar_arquivo(self, frd, esperar=True):
        """Mostra um .frd já pronto (que nunca é apagado), por padrão esperando carregar."""
        self._enfileirar(frd)
        if esperar:
            self.esperar()
            if self.comandar_janela and self.ultimo_ajuste_ok is False:
                # Último recurso: abre do jeito simples (sem a vista isométrica).
                self.fechar()
                self.processo = self._abrir_prepomax(frd)

    def esperar(self):
        """Espera a janela terminar de carregar tudo o que estava na fila."""
        while self.ajuste is not None or self.pendente is not None:
            if self.ajuste is not None:
                self.ajuste.wait()
            self._atualizar()

    def fechar(self):
        if self.ajuste is not None and self.ajuste.poll() is None:
            self.ajuste.kill()
            self.ajuste.wait()
        if self.processo is not None and self.processo.poll() is None:
            if not fechar_pelo_x(self.processo.pid):
                self.processo.kill()
                self.processo.wait()
        self.ajuste = self.processo = None

    def _abrir_prepomax(self, frd):
        recuperacao = arquivo_recuperacao(self.comando[0])
        if os.path.exists(recuperacao):
            # O script responde "não" à pergunta de recuperação; o arquivo fica guardado aqui.
            copia = os.path.join(os.path.dirname(self.log),
                                 "prepomax_recuperacao_%s.pmh" % time.strftime("%Y%m%d-%H%M%S"))
            shutil.copyfile(recuperacao, copia)
            with open(self.log, "a", encoding="utf-8") as log:
                log.write("arquivo de recuperação do PrePoMax guardado em %s\n" % copia)
        # Na pasta dele, como quando aberto pelo atalho.
        return _iniciar(self.comando + ["-f", frd, "-u", UNIDADES], pasta=os.path.dirname(self.comando[0]))

    def _proprio(self, caminho):
        return caminho is not None and os.path.dirname(os.path.abspath(caminho)) == os.path.abspath(self.pasta)

    def _descartar(self, caminho):
        if self._proprio(caminho):
            _apagar(caminho)

    def _enfileirar(self, frd):
        self._descartar(self.pendente)
        self.pendente = frd
        self._atualizar()

    def _atualizar(self):
        if self.ajuste is not None:
            if self.ajuste.poll() is None:
                return  # janela ocupada: o pendente vai na próxima vez
            self.ultimo_ajuste_ok = self.ajuste.returncode == 0
            with open(self.log, "a", encoding="utf-8") as log:
                log.write("  -> %s\n" % ("ok" if self.ultimo_ajuste_ok else "falhou (%d)" % self.ajuste.returncode))
            self.ajuste = None
            self._exibido(self.carregando, self.ultimo_ajuste_ok)
        if self.pendente is None:
            return
        frd, self.pendente = self.pendente, None
        aberto = self.processo is not None and self.processo.poll() is None
        if not self.comandar_janela:
            self.fechar()
            self.processo = self._abrir_prepomax(frd)
            self._exibido(frd, True)
            return
        if not aberto:
            self.processo = self._abrir_prepomax(frd)
        with open(self.log, "a", encoding="utf-8") as log:
            log.write("%s %s\n" % ("trocar para" if aberto else "abrir", frd))
            log.flush()
            self.ajuste = _iniciar(_comando_janela(self.processo.pid, frd if aberto else None), erros=log)
        self.carregando = frd

    def _exibido(self, frd, ok):
        if ok:
            if self.mostrado != frd:
                self._descartar(self.mostrado)
            self.mostrado = frd
        else:
            # Estado da janela desconhecido (diálogo aberto?): na próxima vez abre outra.
            self.fechar()
            self._descartar(frd)
            self._descartar(self.mostrado)
            self.mostrado = None
        self.carregando = None


NOME_LOG_JANELA = "prepomax_janela.log"  # o que o script que comanda a janela disse (diagnóstico)
SCRIPT_JANELA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prepomax_janela.ps1")


def _comando_janela(pid, frd=None):
    comando = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", SCRIPT_JANELA, "-Id", str(pid)]
    return comando + (["-Arquivo", frd] if frd else [])
