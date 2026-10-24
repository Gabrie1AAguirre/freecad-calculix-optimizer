"""Proteção contra o problema de nomes topológicos: confere se fixações e
forças continuam nas mesmas faces depois que a geometria muda."""
from dataclasses import dataclass

NORMAL_MIN_PRODUTO = 0.99
DESLOCAMENTO_MAX_FRACAO = 0.25
AREA_RAZAO_MIN, AREA_RAZAO_MAX = 0.2, 5.0


@dataclass
class AssinaturaFace:
    subelemento: str
    area: float = None
    centro: tuple = None
    normal: tuple = None

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


def capturar_assinaturas(modelo):
    return {cc.Name: [_assinatura(obj, sub) for obj, subs in cc.References for sub in subs]
            for cc in modelo.condicoes}


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
            produto = sum(x * y for x, y in zip(a.normal, d.normal))
            deslocamento = sum((x - y) ** 2 for x, y in zip(a.centro, d.centro)) ** 0.5
            razao = d.area / a.area if a.area else float("inf")
            if (produto < NORMAL_MIN_PRODUTO or deslocamento > DESLOCAMENTO_MAX_FRACAO * diagonal_mm
                    or not AREA_RAZAO_MIN <= razao <= AREA_RAZAO_MAX):
                problemas.append(
                    "%s: a face %s mudou de lugar/orientação (provável troca de face pelo "
                    "problema de nomes topológicos do FreeCAD)." % (nome, d.subelemento))
    return problemas
