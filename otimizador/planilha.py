"""Leitura e escrita da planilha `Parametros` de uma peça."""
import re
from dataclasses import dataclass, field

import FreeCAD as App

NOME_PLANILHA = "Parametros"
ALIAS_TENSAO_LIMITE = "tensao_limite"
ALIAS_MAX_ITERACOES = "max_iteracoes"
ALIAS_ZONA_EXCLUSAO = "zona_exclusao_mm"
PREFIXO_EXCLUIR = "excluir_"
ALIASES_RESERVADOS = (ALIAS_TENSAO_LIMITE, ALIAS_MAX_ITERACOES, ALIAS_ZONA_EXCLUSAO)
MAX_ITERACOES_PADRAO = 30


class ErroPlanilha(Exception):
    """Problema na planilha, com mensagem em português para o usuário."""


@dataclass
class Parametro:
    alias: str
    valor: float
    minimo: float
    maximo: float
    celula: str


@dataclass
class Configuracao:
    parametros: list
    tensao_limite: float = None
    max_iteracoes: int = MAX_ITERACOES_PADRAO
    zona_exclusao_mm: float = None
    excluir: dict = field(default_factory=dict)


def valor_numerico(valor):
    """Converte número, Quantity ou texto ('12,5', '20 mm') em float (mm/MPa)."""
    if isinstance(valor, (int, float)):
        return float(valor)
    if hasattr(valor, "Value"):
        return float(valor.Value)
    texto = str(valor).strip().lstrip("'=").replace(",", ".")
    achado = re.match(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", texto)
    if not achado:
        raise ValueError("não é um número: %r" % valor)
    return float(achado.group(0))


def encontrar_planilha(doc):
    for obj in doc.Objects:
        if obj.TypeId == "Spreadsheet::Sheet" and NOME_PLANILHA in (obj.Name, obj.Label):
            return obj
    return None


def _separar_celula(celula):
    achado = re.match(r"^([A-Z]+)(\d+)$", celula)
    return achado.group(1), achado.group(2)


def _conteudo_numerico(sheet, celula, alias, descricao):
    conteudo = sheet.getContents(celula)
    if not str(conteudo).strip():
        raise ErroPlanilha(
            "O parâmetro '%s' não tem %s na célula %s. Preencha esse valor na planilha %s."
            % (alias, descricao, celula, NOME_PLANILHA))
    try:
        return valor_numerico(sheet.get(celula))
    except Exception:
        try:
            return valor_numerico(conteudo)
        except ValueError:
            raise ErroPlanilha(
                "O %s do parâmetro '%s' (célula %s) não é um número: %r."
                % (descricao, alias, celula, conteudo))


def ler_configuracao(doc):
    sheet = encontrar_planilha(doc)
    if sheet is None:
        raise ErroPlanilha(
            "Não encontrei a planilha '%s'. Crie uma planilha (bancada Spreadsheet) com esse nome "
            "listando os parâmetros que podem mudar." % NOME_PLANILHA)
    cfg = Configuracao(parametros=[])
    for celula in sorted(sheet.getUsedCells(), key=lambda c: (int(_separar_celula(c)[1]), c)):
        alias = sheet.getAlias(celula)
        if not alias:
            continue
        if alias == ALIAS_TENSAO_LIMITE:
            cfg.tensao_limite = _conteudo_numerico(sheet, celula, alias, "valor")
        elif alias == ALIAS_MAX_ITERACOES:
            cfg.max_iteracoes = int(_conteudo_numerico(sheet, celula, alias, "valor"))
        elif alias == ALIAS_ZONA_EXCLUSAO:
            cfg.zona_exclusao_mm = _conteudo_numerico(sheet, celula, alias, "valor")
        elif alias.startswith(PREFIXO_EXCLUIR):
            nome_cc = alias[len(PREFIXO_EXCLUIR):]
            cfg.excluir[nome_cc] = bool(_conteudo_numerico(sheet, celula, alias, "valor"))
        else:
            coluna, linha = _separar_celula(celula)
            if coluna != "B":
                continue
            cfg.parametros.append(Parametro(
                alias=alias,
                valor=_conteudo_numerico(sheet, celula, alias, "valor"),
                minimo=_conteudo_numerico(sheet, "C" + linha, alias, "mínimo (coluna C)"),
                maximo=_conteudo_numerico(sheet, "D" + linha, alias, "máximo (coluna D)"),
                celula=celula,
            ))
    return cfg


def aplicar_valores(doc, cfg, valores):
    """Escreve os valores nas células dos parâmetros (não recalcula o documento)."""
    sheet = encontrar_planilha(doc)
    celulas = {p.alias: p.celula for p in cfg.parametros}
    for alias, valor in valores.items():
        sheet.set(celulas[alias], "%.6g" % valor)
