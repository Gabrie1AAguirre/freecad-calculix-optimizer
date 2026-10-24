"""Uma avaliação: aplica valores, recalcula, confere faces, roda a FEA e mede."""
from dataclasses import dataclass, field

from otimizador.fea import FalhaAvaliacao, rodar_fea
from otimizador.modelo import faces_cc, massa_kg, objetos_com_erro, tamanho_elemento_mm
from otimizador.planilha import aplicar_valores
from otimizador.tensao import distancia_faces, medir_tensao
from otimizador.topologia import capturar_assinaturas, comparar_assinaturas

OK = "OK ✓"
OK_VERIFICAR = "OK ⚠ verificar"
ACIMA = "acima do limite"
INVALIDA = "inválida"


@dataclass
class Iteracao:
    numero: int
    valores: dict
    von_mises: float = None
    von_mises_bruto: float = None
    local: tuple = None
    massa_kg: float = None
    status: str = INVALIDA
    motivo: str = ""

    @property
    def valida(self):
        return self.status != INVALIDA


def _ponto(p):
    return "(%.1f, %.1f, %.1f)" % tuple(p)


class Avaliador:
    def __init__(self, doc, cfg, modelo, pasta_trabalho):
        self.doc = doc
        self.cfg = cfg
        self.modelo = modelo
        self.pasta_trabalho = pasta_trabalho
        self.diagonal = modelo.corpo.Shape.BoundBox.DiagonalLength
        self.tamanho_elemento = tamanho_elemento_mm(modelo)
        self.zona_mm = cfg.zona_exclusao_mm if cfg.zona_exclusao_mm is not None else 2 * self.tamanho_elemento
        self.assinaturas_base = capturar_assinaturas(modelo)
        self.numero = 0
        self.ultimo_resultado = None

    def avaliar(self, valores):
        self.numero += 1
        it = Iteracao(numero=self.numero, valores=dict(valores))
        self.ultimo_resultado = None
        try:
            self._avaliar(it)
        except FalhaAvaliacao as exc:
            it.status, it.motivo = INVALIDA, str(exc)
        return it

    def _avaliar(self, it):
        aplicar_valores(self.doc, self.cfg, it.valores)
        self.doc.recompute()
        quebrados = objetos_com_erro(self.doc)
        if quebrados or not self.modelo.corpo.Shape.isValid():
            raise FalhaAvaliacao("A geometria não fecha com esses valores (%s)."
                                 % (", ".join(quebrados) or "sólido inválido"))
        problemas = comparar_assinaturas(self.assinaturas_base, capturar_assinaturas(self.modelo), self.diagonal)
        if problemas:
            raise FalhaAvaliacao(" ".join(problemas))
        it.massa_kg = massa_kg(self.modelo)

        resultado = rodar_fea(self.modelo, self.pasta_trabalho)
        self.ultimo_resultado = resultado
        malha = resultado.Mesh.FemMesh
        coords = [tuple(malha.getNodeById(n)) for n in resultado.NodeNumbers]
        faces = [f for nome, lista in faces_cc(self.modelo).items()
                 if self.cfg.excluir.get(nome, True) for f in lista]
        limite = self.cfg.tensao_limite
        m = medir_tensao(coords, list(resultado.vonMises), distancia_faces(faces),
                         self.zona_mm, self.tamanho_elemento, limite)
        it.von_mises, it.von_mises_bruto, it.local = m.max_filtrado, m.max_bruto, m.local_filtrado

        if m.max_filtrado > limite:
            it.status = ACIMA
        elif m.max_na_zona > limite:
            it.status = OK_VERIFICAR
            it.motivo = ("Pico de %.0f MPa dentro da zona de exclusão em %s; confira se é real."
                         % (m.max_na_zona, _ponto(m.local_bruto)))
        elif m.na_borda:
            it.status = OK_VERIFICAR
            it.motivo = ("O máximo fica na borda da zona de exclusão em %s; a tensão pode continuar "
                         "subindo para dentro dela." % _ponto(m.local_filtrado))
        else:
            it.status = OK
