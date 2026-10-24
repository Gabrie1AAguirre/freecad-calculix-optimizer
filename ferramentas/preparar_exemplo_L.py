"""Gera exemplos/L_part.FCStd a partir do L_part.FCStd do usuário.

Adiciona a planilha Parametros, um raio no canto interno (fillet de sketch)
e liga as espessuras das pernas à planilha, mantendo o tamanho externo
180 x 230 mm. O arquivo de entrada só é lido.

Uso (com o Python do FreeCAD):
    python.exe ferramentas/preparar_exemplo_L.py --entrada L_part.FCStd --saida exemplos/L_part.FCStd
"""
import argparse
import os
import shutil
import sys
import tempfile

_BIN = os.environ.get("FREECAD_BIN", r"C:\Program Files\FreeCAD 1.1\bin")
sys.path += [_BIN, os.path.join(os.path.dirname(_BIN), "lib")]

import FreeCAD as App  # noqa: E402
import Sketcher  # noqa: E402

LARGURA_EXTERNA = 180.0
ALTURA_EXTERNA = 230.0
CANTO_INTERNO = (30.0, 30.0)

PARAMETROS = [
    # descrição, alias, valor, mínimo, máximo
    ("Raio do canto interno (mm)", "raio_canto", 1, 1, 20),
    ("Espessura da perna vertical (mm)", "espessura_vertical", 30, 20, 45),
    ("Espessura da perna horizontal (mm)", "espessura_horizontal", 30, 20, 45),
]
CONFIGURACOES = [
    ("Von Mises máximo permitido (MPa)", "tensao_limite", 250),
    ("Máximo de iterações", "max_iteracoes", 30),
]

TIPOS_RESULTADO = ("Fem::FemResultObjectPython", "Fem::FemPostPipeline",
                   "Fem::FemMeshObjectPython", "App::TextDocument")


def _perto(a, b, tol=1e-6):
    return abs(a - b) < tol


def _linha_no_canto(sketch, vertical):
    """Índice da linha vertical/horizontal que toca o canto interno."""
    cx, cy = CANTO_INTERNO
    for i, g in enumerate(sketch.Geometry):
        if g.TypeId != "Part::GeomLineSegment":
            continue
        pontos = (g.StartPoint, g.EndPoint)
        toca = any(_perto(p.x, cx) and _perto(p.y, cy) for p in pontos)
        eh_vertical = _perto(g.StartPoint.x, g.EndPoint.x)
        if toca and eh_vertical == vertical:
            return i
    raise RuntimeError("não achei a linha do canto interno no Sketch")


def _linha_externa(sketch, vertical):
    """Índice da linha externa inteira (borda em x=0 ou y=0)."""
    for i, g in enumerate(sketch.Geometry):
        if g.TypeId != "Part::GeomLineSegment":
            continue
        if vertical and _perto(g.StartPoint.x, 0) and _perto(g.EndPoint.x, 0):
            return i
        if not vertical and _perto(g.StartPoint.y, 0) and _perto(g.EndPoint.y, 0):
            return i
    raise RuntimeError("não achei a borda externa no Sketch")


def _restricao(sketch, tipo, valor):
    achadas = [i for i, c in enumerate(sketch.Constraints)
               if c.Type == tipo and _perto(c.Value, valor)]
    if len(achadas) != 1:
        raise RuntimeError("esperava uma restrição %s = %s, achei %d" % (tipo, valor, len(achadas)))
    return achadas[0]


def _criar_planilha(doc):
    sheet = doc.addObject("Spreadsheet::Sheet", "Parametros")
    for celula, texto in (("A1", "Parâmetro"), ("B1", "Valor"), ("C1", "Mínimo"), ("D1", "Máximo")):
        sheet.set(celula, texto)
    linha = 2
    for descricao, alias, valor, minimo, maximo in PARAMETROS:
        sheet.set("A%d" % linha, descricao)
        sheet.set("B%d" % linha, str(valor))
        sheet.setAlias("B%d" % linha, alias)
        sheet.set("C%d" % linha, str(minimo))
        sheet.set("D%d" % linha, str(maximo))
        linha += 1
    linha += 1
    sheet.set("A%d" % linha, "Configurações")
    for descricao, alias, valor in CONFIGURACOES:
        linha += 1
        sheet.set("A%d" % linha, descricao)
        sheet.set("B%d" % linha, str(valor))
        sheet.setAlias("B%d" % linha, alias)
    return sheet


def _remover_resultados(doc):
    analise = doc.getObject("Analysis")
    for obj in list(analise.Group):
        if obj.TypeId in TIPOS_RESULTADO:
            doc.removeObject(obj.Name)


def preparar(entrada, saida):
    # Trabalha numa cópia temporária para nunca gravar sobre a entrada.
    pasta = tempfile.mkdtemp()
    copia = os.path.join(pasta, "L_part.FCStd")
    shutil.copy(entrada, copia)
    doc = App.openDocument(copia)
    try:
        _remover_resultados(doc)
        _criar_planilha(doc)
        doc.recompute()

        sk = doc.getObject("Sketch")
        cx, cy = CANTO_INTERNO
        g_vert = _linha_no_canto(sk, vertical=True)
        g_horiz = _linha_no_canto(sk, vertical=False)
        # O fillet apaga as cotas que usavam o canto (150 e 200); o tamanho
        # externo é então fixado diretamente pelas bordas externas.
        sk.fillet(g_vert, g_horiz, App.Vector(cx, cy + 10, 0), App.Vector(cx + 10, cy, 0), 1.0, True, False)
        arco = len(sk.Geometry) - 1
        sk.addConstraint(Sketcher.Constraint("DistanceX", _linha_externa(sk, vertical=False), 1,
                                             _linha_externa(sk, vertical=False), 2, LARGURA_EXTERNA))
        sk.addConstraint(Sketcher.Constraint("DistanceY", _linha_externa(sk, vertical=True), 1,
                                             _linha_externa(sk, vertical=True), 2, ALTURA_EXTERNA))
        raio = sk.addConstraint(Sketcher.Constraint("Radius", arco, 1.0))

        sk.setExpression("Constraints[%d]" % raio, "Parametros.raio_canto")
        sk.setExpression("Constraints[%d]" % _restricao(sk, "DistanceX", 30.0), "Parametros.espessura_vertical")
        sk.setExpression("Constraints[%d]" % _restricao(sk, "DistanceY", 30.0), "Parametros.espessura_horizontal")
        doc.recompute()
        if not doc.getObject("Body").Shape.isValid():
            raise RuntimeError("o corpo ficou inválido depois do fillet")
        doc.saveAs(os.path.abspath(saida))
    finally:
        App.closeDocument(doc.Name)
        shutil.rmtree(pasta, True)


def main():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", default=os.path.join(raiz, "L_part.FCStd"))
    parser.add_argument("--saida", default=os.path.join(raiz, "exemplos", "L_part.FCStd"))
    args = parser.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
    preparar(args.entrada, args.saida)
    print("Exemplo gerado em", args.saida)


if __name__ == "__main__":
    main()
