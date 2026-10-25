"""Visualização ao vivo na janela do FreeCAD (só usado com interface)."""
import FreeCADGui as Gui


def atualizar():
    Gui.updateGui()


def manter_janela_salva():
    """O FreeCAD grava o tamanho da janela ao fechar: devolve o que estava gravado,
    para a tela dividida valer só desta vez. Chamar logo ao abrir, antes de o
    FreeCAD regravar esses valores."""
    import FreeCAD as App
    from PySide import QtCore
    grupo = App.ParamGet("User parameter:BaseApp/Preferences/MainWindow")
    geometria = grupo.GetString("Geometry") if "Geometry" in grupo.GetStrings() else None
    maximizada = grupo.GetBool("Maximized") if "Maximized" in grupo.GetBools() else None

    def restaurar():
        if geometria is None:
            grupo.RemString("Geometry")
        else:
            grupo.SetString("Geometry", geometria)
        if maximizada is None:
            grupo.RemBool("Maximized")
        else:
            grupo.SetBool("Maximized", maximizada)
    QtCore.QCoreApplication.instance().aboutToQuit.connect(restaurar)


def metade_esquerda():
    """Tela dividida com o PrePoMax: o FreeCAD fica com a metade esquerda."""
    from otimizador import janelas
    janela = Gui.getMainWindow()
    janela.showNormal()
    atualizar()
    janelas.posicionar(int(janela.winId()), janelas.ESQUERDA)
    atualizar()


def mostrar(doc, resultado, enquadrar=False):
    """Esconde o resto e pinta a malha do resultado com o Von Mises."""
    if resultado is None:
        atualizar()
        return
    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None)
        if vo is not None and obj is not resultado.Mesh:
            vo.Visibility = False
    vo = resultado.Mesh.ViewObject
    vo.Visibility = True
    vo.setNodeColorByScalars(list(resultado.NodeNumbers), list(resultado.vonMises))
    if enquadrar:
        vista = Gui.getDocument(doc.Name).activeView()
        vista.viewIsometric()
        vista.fitAll()
    atualizar()


def mostrar_peca(doc, corpo, enquadrar=False):
    """Esconde o resto e mostra só a peça (as tensões ficam no PrePoMax)."""
    visiveis = {o.Name for o in (corpo, getattr(corpo, "Tip", None)) if o is not None}
    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None)
        if vo is not None:
            vo.Visibility = obj.Name in visiveis
    if enquadrar:
        vista = Gui.getDocument(doc.Name).activeView()
        vista.viewIsometric()
        vista.fitAll()
    atualizar()


def salvar_imagem(doc, caminho_png):
    Gui.getDocument(doc.Name).activeView().saveImage(caminho_png, 1200, 800, "White")


def fechar():
    """Fecha o FreeCAD sem perguntar nem gravar nada (os resultados já foram salvos)."""
    import FreeCAD as App
    for nome in list(App.listDocuments()):
        App.closeDocument(nome)
    Gui.getMainWindow().close()
