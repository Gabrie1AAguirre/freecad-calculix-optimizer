# Ponto de entrada executado dentro do FreeCAD (freecad.exe ou freecadcmd.exe).
# Lê o trabalho indicado pela variável de ambiente e chama otimizador.executar.
import json as _json
import os as _os
import sys as _sys

with open(_os.environ["OTIMIZADOR_TRABALHO"], encoding="utf-8") as _f:
    _repo = _json.load(_f)["repo"]
if _repo not in _sys.path:
    _sys.path.insert(0, _repo)

from otimizador import executar as _executar  # noqa: E402

_executar.iniciar(_os.environ["OTIMIZADOR_TRABALHO"])
