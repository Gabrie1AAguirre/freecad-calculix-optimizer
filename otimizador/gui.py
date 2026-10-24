"""Visualização ao vivo na janela do FreeCAD (só usado com interface)."""
import FreeCADGui as Gui


def atualizar():
    Gui.updateGui()


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


def salvar_imagem(doc, caminho_png):
    Gui.getDocument(doc.Name).activeView().saveImage(caminho_png, 1200, 800, "White")


def fechar():
    """Fecha o FreeCAD sem perguntar nem gravar nada (os resultados já foram salvos)."""
    import FreeCAD as App
    for nome in list(App.listDocuments()):
        App.closeDocument(nome)
    Gui.getMainWindow().close()
