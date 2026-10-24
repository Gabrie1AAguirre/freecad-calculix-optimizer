"""Proteção contra o problema de nomes topológicos: confere se fixações e
forças continuam nas mesmas faces depois que a geometria muda."""
from dataclasses import dataclass, field

NORMAL_MIN_PRODUTO = 0.99
DESLOCAMENTO_MAX_FRACAO = 0.25
AREA_RAZAO_MIN, AREA_RAZAO_MAX = 0.2, 5.0
# Outra face "parecida" com a original: mesma orientação e área na mesma ordem.
PARECIDA_RAZAO_MIN, PARECIDA_RAZAO_MAX = 0.5, 2.0


@dataclass
class AssinaturaFace:
    subelemento: str
    area: float = None
    centro: tuple = None
    normal: tuple = None
    # Demais faces do mesmo objeto (só preenchido depois do recálculo).
    alternativas: list = field(default_factory=list)

    @property
    def existe(self):
        return self.area is not None


def _assinatura(obj, sub):
    try:
        face = obj.Shape.getElement(sub)
        u0, u1, v0, v1 = face.ParameterRange
        n = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        c = face.CenterOfMass
        return AssinaturaFace(sub, face.Area, (c.x, c.y, c.z), (n.x, n.y, n.z))
    except Exception:
        return AssinaturaFace(sub)


def _com_alternativas(obj, sub):
    assinatura = _assinatura(obj, sub)
    total = len(getattr(obj.Shape, "Faces", []))
    assinatura.alternativas = [_assinatura(obj, "Face%d" % i) for i in range(1, total + 1)
                               if "Face%d" % i != sub]
    return assinatura


def capturar_assinaturas(modelo):
    return {cc.Name: [_com_alternativas(obj, sub) for obj, subs in cc.References for sub in subs]
            for cc in modelo.condicoes}


def _produto(a, b):
    return sum(x * y for x, y in zip(a, b))


def _distancia(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _melhor_alternativa(original, atual):
    """Uma face do objeto que corresponde à original melhor que a referenciada."""
    distancia_atual = _distancia(original.centro, atual.centro)
    for alt in atual.alternativas:
        if (alt.existe and _produto(original.normal, alt.normal) >= NORMAL_MIN_PRODUTO
                and PARECIDA_RAZAO_MIN <= alt.area / original.area <= PARECIDA_RAZAO_MAX
                and _distancia(original.centro, alt.centro) < distancia_atual - 1e-6):
            return alt
    return None


def comparar_assinaturas(antes, depois, diagonal_mm):
    problemas = []
    for nome, lista_antes in antes.items():
        lista_depois = depois.get(nome, [])
        if len(lista_depois) != len(lista_antes):
            problemas.append("%s: o número de faces mudou (%d → %d)." % (nome, len(lista_antes), len(lista_depois)))
            continue
        for a, d in zip(lista_antes, lista_depois):
            if not d.existe:
                problemas.append("%s: a face %s não existe mais." % (nome, d.subelemento))
                continue
            if not a.existe:
                continue
            razao = d.area / a.area if a.area else float("inf")
            if (_produto(a.normal, d.normal) < NORMAL_MIN_PRODUTO
                    or _distancia(a.centro, d.centro) > DESLOCAMENTO_MAX_FRACAO * diagonal_mm
                    or not AREA_RAZAO_MIN <= razao <= AREA_RAZAO_MAX):
                problemas.append(
                    "%s: a face %s mudou de lugar/orientação (provável troca de face pelo "
                    "problema de nomes topológicos do FreeCAD)." % (nome, d.subelemento))
                continue
            melhor = _melhor_alternativa(a, d)
            if melhor is not None:
                problemas.append(
                    "%s: aponta para %s, mas %s corresponde melhor à face original (%s); provável troca "
                    "de face pelo problema de nomes topológicos do FreeCAD."
                    % (nome, d.subelemento, melhor.subelemento, a.subelemento))
    return problemas
