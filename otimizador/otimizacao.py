"""Laço de otimização: menor massa com Von Mises abaixo do limite (COBYLA)."""
import numpy as np
from scipy.optimize import minimize

from otimizador.avaliacao import OK, OK_VERIFICAR

INVALIDAS_SEGUIDAS_MAX = 3
PASSO_INICIAL = 0.25  # fração da faixa de cada parâmetro


class ErroLinhaDeBase(Exception):
    """A peça com os valores atuais não pôde ser avaliada."""


class _Parar(Exception):
    pass


def escolher_melhor(historico):
    """Mais leve entre as 'OK ✓'; senão mais leve entre as 'OK ⚠'; senão a de menor tensão."""
    for status in (OK, OK_VERIFICAR):
        candidatas = [it for it in historico if it.status == status]
        if candidatas:
            return min(candidatas, key=lambda it: it.massa_kg)
    validas = [it for it in historico if it.valida]
    return min(validas, key=lambda it: it.von_mises) if validas else None


def otimizar(avaliar, cfg, ao_iterar, deve_parar):
    params = cfg.parametros
    minimos = np.array([p.minimo for p in params])
    faixas = np.array([p.maximo - p.minimo for p in params])
    limite = cfg.tensao_limite
    historico, cache = [], {}
    estado = {"melhor": None, "invalidas": 0, "maior_massa": 0.0}

    def executar(x):
        x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
        chave = tuple(np.round(x, 6))
        if chave in cache:
            return cache[chave]
        if len(historico) >= cfg.max_iteracoes or (historico and deve_parar()):
            raise _Parar()
        valores = {p.alias: float(v) for p, v in zip(params, minimos + x * faixas)}
        it = avaliar(valores)
        historico.append(it)
        cache[chave] = it
        melhor = escolher_melhor(historico)
        eh_melhor = melhor is it
        estado["melhor"] = melhor
        ao_iterar(it, eh_melhor)
        if it.valida:
            estado["invalidas"] = 0
            estado["maior_massa"] = max(estado["maior_massa"], it.massa_kg)
        else:
            estado["invalidas"] += 1
            if len(historico) > 1 and estado["invalidas"] >= INVALIDAS_SEGUIDAS_MAX:
                raise _Parar()
        return it

    x0 = np.array([(p.valor - p.minimo) / (p.maximo - p.minimo) for p in params])
    base = executar(x0)
    if not base.valida:
        raise ErroLinhaDeBase(base.motivo)

    def objetivo(x):
        it = executar(x)
        return it.massa_kg if it.valida else estado["maior_massa"]

    def folga(x):
        it = executar(x)
        return (limite - it.von_mises) / limite if it.valida else -1.0

    # O COBYLA testa x0 ± passo; partindo do limite, esses pontos cairiam fora da
    # faixa, seriam recortados para a linha de base e o passo encolheria até sumir.
    inicio = np.clip(x0, PASSO_INICIAL, 1.0 - PASSO_INICIAL)
    try:
        minimize(objetivo, inicio, method="COBYLA", bounds=[(0.0, 1.0)] * len(params),
                 constraints=[{"type": "ineq", "fun": folga}],
                 options={"maxiter": 10 * cfg.max_iteracoes, "rhobeg": PASSO_INICIAL})
    except _Parar:
        pass
    return escolher_melhor(historico), historico
