"""Verificação da preparação da peça (comando --checar)."""
import re
from dataclasses import dataclass

from otimizador.modelo import ErroModelo, encontrar_modelo, objetos_com_erro
from otimizador.planilha import ALIAS_TENSAO_LIMITE, NOME_PLANILHA, ErroPlanilha, ler_configuracao

TIPOS_ARESTA = ("PartDesign::Fillet", "PartDesign::Chamfer")


@dataclass
class Problema:
    nivel: str  # "erro" ou "aviso"
    mensagem: str


def _expressoes(doc):
    for obj in doc.Objects:
        for propriedade, expressao in getattr(obj, "ExpressionEngine", []):
            yield obj, propriedade, expressao


def _usa_alias(expressao, alias):
    """Expressões referenciam a planilha como Parametros.alias ou <<Parametros>>.alias."""
    return re.search(r"\.%s\b" % re.escape(alias), expressao) is not None


def _checar_recompute(doc):
    doc.recompute()
    quebrados = objetos_com_erro(doc)
    if quebrados:
        return [Problema("erro", "O documento não consegue recalcular com os valores atuais (%s). "
                                 "Abra no FreeCAD e corrija os objetos marcados com erro."
                         % ", ".join(quebrados))]
    return []


def checar(doc):
    problemas = []
    try:
        modelo = encontrar_modelo(doc)
        if not modelo.fixacoes:
            problemas.append(Problema("erro", "A análise não tem nenhuma fixação. Na bancada FEM, use "
                                              "'Fixed boundary condition' e selecione a face presa."))
        if not modelo.forcas:
            problemas.append(Problema("erro", "A análise não tem nenhuma força nem pressão. Na bancada FEM, "
                                              "use 'Force load' e selecione a face onde a força entra."))
    except ErroModelo as exc:
        problemas.append(Problema("erro", str(exc)))

    try:
        cfg = ler_configuracao(doc)
    except ErroPlanilha as exc:
        problemas.append(Problema("erro", str(exc)))
        return problemas + _checar_recompute(doc)

    if not cfg.parametros:
        problemas.append(Problema("erro", "Nenhum parâmetro na planilha %s. Coloque cada valor que pode mudar "
                                          "na coluna B com um alias, mínimo na coluna C e máximo na D."
                                  % NOME_PLANILHA))
    if cfg.tensao_limite is None:
        problemas.append(Problema("erro", "Falta a célula com alias '%s' (Von Mises máximo permitido, em MPa)."
                                  % ALIAS_TENSAO_LIMITE))
    expressoes = list(_expressoes(doc))
    for p in cfg.parametros:
        if p.minimo >= p.maximo:
            problemas.append(Problema("erro", "O parâmetro '%s' tem mínimo (%g) maior ou igual ao máximo (%g)."
                                      % (p.alias, p.minimo, p.maximo)))
        elif not p.minimo <= p.valor <= p.maximo:
            problemas.append(Problema("erro", "O valor atual de '%s' (%g) está fora dos limites [%g, %g]."
                                      % (p.alias, p.valor, p.minimo, p.maximo)))
        usos = [(obj, prop) for obj, prop, expr in expressoes
                if obj.TypeId != "Spreadsheet::Sheet" and _usa_alias(expr, p.alias)]
        if not usos:
            problemas.append(Problema("erro", "O parâmetro '%s' não é usado por nenhuma cota. No Sketcher, "
                                              "clique no f(x) da cota e digite %s.%s."
                                      % (p.alias, NOME_PLANILHA, p.alias)))
        for obj, prop in usos:
            if obj.TypeId in TIPOS_ARESTA:
                problemas.append(Problema("aviso", "O parâmetro '%s' controla o %s '%s'. Arredondamentos do "
                                                   "PartDesign dependem do nome da aresta e podem quebrar; prefira "
                                                   "o fillet do Sketcher." % (p.alias, obj.TypeId.split("::")[1],
                                                                             obj.Label)))
    return problemas + _checar_recompute(doc)
