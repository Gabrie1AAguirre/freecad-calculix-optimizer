"""Saídas da otimização: histórico CSV, linhas do terminal, gráfico e resumo."""
import csv

from otimizador.avaliacao import OK, OK_VERIFICAR

COLUNAS_FIXAS = ["von_mises_mpa", "von_mises_bruto_mpa", "local_max", "massa_kg", "status", "motivo"]
LARGURA_VM = 12
LARGURA_MASSA = 9


def _numero_csv(valor):
    """Número no formato do Excel em português (vírgula decimal); vazio se None."""
    return "" if valor is None else ("%.6g" % valor).replace(".", ",")


class Historico:
    """CSV com uma linha por iteração (separador ';', vírgula decimal, UTF-8 com BOM
    para o Excel em português abrir direto). Cada linha é gravada na hora."""

    def __init__(self, caminho_csv, aliases):
        self.caminho = caminho_csv
        self.aliases = list(aliases)
        with open(self.caminho, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f, delimiter=";").writerow(["iteracao"] + self.aliases + COLUNAS_FIXAS)

    def adicionar(self, it):
        local = "" if it.local is None else "%.1f %.1f %.1f" % tuple(it.local)
        linha = ([str(it.numero)] + [_numero_csv(it.valores.get(a)) for a in self.aliases]
                 + [_numero_csv(it.von_mises), _numero_csv(it.von_mises_bruto), local,
                    _numero_csv(it.massa_kg), it.status, it.motivo])
        with open(self.caminho, "a", encoding="utf-8", newline="") as f:
            csv.writer(f, delimiter=";").writerow(linha)


def _largura(alias):
    return max(len(alias), 8)


def cabecalho_terminal(aliases):
    partes = ["iter"] + [a.rjust(_largura(a)) for a in aliases]
    partes += ["VonMises_max".rjust(LARGURA_VM), "massa".rjust(LARGURA_MASSA), "  status"]
    return "  ".join(partes)


def linha_terminal(it, aliases, eh_melhor):
    partes = ["%4d" % it.numero] + [("%.1f" % it.valores[a]).rjust(_largura(a)) for a in aliases]
    vm = "" if it.von_mises is None else "%.0f MPa" % it.von_mises
    massa = "" if it.massa_kg is None else "%.2f kg" % it.massa_kg
    partes += [vm.rjust(LARGURA_VM), massa.rjust(LARGURA_MASSA)]
    status = "  " + it.status
    if eh_melhor:
        status += " melhor até agora" if it.status in (OK, OK_VERIFICAR) else " (menor tensão até agora)"
    if it.motivo:
        status += " — " + it.motivo
    return "  ".join(partes + [status])


def gerar_grafico(historico, limite, caminho_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    validas = [it for it in historico if it.valida]
    fig, (eixo_vm, eixo_massa) = plt.subplots(2, 1, sharex=True, figsize=(8, 6))
    cores = {OK: "tab:green", OK_VERIFICAR: "tab:orange"}
    eixo_vm.plot([it.numero for it in validas], [it.von_mises for it in validas], color="0.6", zorder=1)
    eixo_vm.scatter([it.numero for it in validas], [it.von_mises for it in validas],
                    c=[cores.get(it.status, "tab:red") for it in validas], zorder=2)
    eixo_vm.axhline(limite, color="tab:red", linestyle="--", label="limite %.0f MPa" % limite)
    eixo_vm.set_ylabel("Von Mises máx. (MPa)")
    eixo_vm.legend()
    eixo_massa.plot([it.numero for it in validas], [it.massa_kg for it in validas], marker="o")
    eixo_massa.set_ylabel("Massa (kg)")
    eixo_massa.set_xlabel("Iteração")
    fig.tight_layout()
    fig.savefig(caminho_png, dpi=100)
    plt.close(fig)


def resumo(base, melhor, limite):
    if melhor is None:
        return "Nenhuma iteração válida: não há resultado para entregar."
    variacao = 100.0 * (melhor.massa_kg - base.massa_kg) / base.massa_kg
    linhas = [
        "Linha de base: %.0f MPa, %.2f kg" % (base.von_mises, base.massa_kg),
        "Melhor: iteração %d — %.0f MPa, %.2f kg (%+.1f%% de massa)"
        % (melhor.numero, melhor.von_mises, melhor.massa_kg, variacao),
        "Valores: " + ", ".join("%s = %.2f" % kv for kv in melhor.valores.items()),
    ]
    if melhor.status == OK:
        linhas.append("✓ A otimização atingiu o limite de %.0f MPa." % limite)
    elif melhor.status == OK_VERIFICAR:
        linhas.append("⚠ A otimização atingiu o limite de %.0f MPa, mas é preciso verificar: %s"
                      % (limite, melhor.motivo))
    else:
        linhas.append("✗ A otimização não atingiu o limite de %.0f MPa dentro das faixas dos parâmetros; "
                      "esta é a combinação com menor tensão. Amplie as faixas ou revise o projeto." % limite)
    return "\n".join(linhas)
