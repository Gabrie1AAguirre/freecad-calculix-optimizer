"""Descrição de uma execução, passada do lançador para o FreeCAD em JSON.
Só usa a biblioteca padrão (é importado pelo lançador também)."""
import json
from dataclasses import asdict, dataclass

VARIAVEL_AMBIENTE = "OTIMIZADOR_TRABALHO"
NOME_LOG = "log.txt"
NOME_PARAR = "parar"
MARCA_FIM = "### FIM codigo="


@dataclass
class Trabalho:
    modo: str  # "otimizar" ou "checar"
    entrada: str
    pasta: str
    gui: bool
    fechar_ao_terminar: bool
    repo: str


def salvar(trabalho, caminho):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(asdict(trabalho), f, ensure_ascii=False, indent=2)


def carregar(caminho):
    with open(caminho, encoding="utf-8") as f:
        return Trabalho(**json.load(f))
