"""Von Mises máximo ignorando as zonas em volta das condições de contorno."""
import math
from dataclasses import dataclass


@dataclass
class MedidaTensao:
    max_filtrado: float
    local_filtrado: tuple
    max_bruto: float
    local_bruto: tuple
    max_na_zona: float
    na_borda: bool


def medir_tensao(coords, vm, distancia, zona_mm, tamanho_elemento, limite):
    """Percorre os nós da maior para a menor tensão e para no primeiro fora
    da zona de exclusão: a distância (cara de calcular) só é avaliada no topo.
    `limite` é aceito para manter a assinatura do plano; a decisão de status
    fica com quem chama."""
    ordem = sorted(range(len(vm)), key=lambda i: vm[i], reverse=True)
    if not ordem:
        raise ValueError("resultado sem nós")
    max_na_zona = 0.0
    for i in ordem:
        d = distancia(coords[i])
        if d < zona_mm:
            max_na_zona = max(max_na_zona, vm[i])
            continue
        return MedidaTensao(vm[i], tuple(coords[i]), vm[ordem[0]], tuple(coords[ordem[0]]),
                            max_na_zona, d < zona_mm + tamanho_elemento)
    return MedidaTensao(0.0, None, vm[ordem[0]], tuple(coords[ordem[0]]), max_na_zona, True)


def distancia_faces(faces):
    """Função ponto → menor distância até as faces dadas (inf se não houver)."""
    if not faces:
        return lambda p: math.inf
    import FreeCAD as App
    import Part
    composto = Part.Compound(faces)

    def distancia(p):
        return composto.distToShape(Part.Vertex(App.Vector(*p)))[0]
    return distancia
