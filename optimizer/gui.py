"""Live view in the FreeCAD window (only used with the interface)."""
import FreeCADGui as Gui


def refresh():
    Gui.updateGui()


def keep_saved_window():
    """FreeCAD saves the window size when it closes: puts back what was saved,
    so the split screen applies only this time. Call it right after opening, before
    FreeCAD saves these values again."""
    import FreeCAD as App
    from PySide import QtCore
    group = App.ParamGet("User parameter:BaseApp/Preferences/MainWindow")
    texts = {n: group.GetString(n) for n in ("Geometry", "MainWindowState") if n in group.GetStrings()}
    maximized = group.GetBool("Maximized") if "Maximized" in group.GetBools() else None

    def restore():
        for name in ("Geometry", "MainWindowState"):  # window and panel sizes
            if name in texts:
                group.SetString(name, texts[name])
            else:
                group.RemString(name)
        if maximized is None:
            group.RemBool("Maximized")
        else:
            group.SetBool("Maximized", maximized)
    QtCore.QCoreApplication.instance().aboutToQuit.connect(restore)


def left_half():
    """Split screen with PrePoMax: FreeCAD takes the left half, with a narrow
    Model/Tasks panel to leave room for the part."""
    from PySide import QtCore, QtWidgets
    from optimizer import split_screen
    window = Gui.getMainWindow()
    window.showNormal()
    refresh()
    split_screen.place(int(window.winId()), split_screen.LEFT)
    refresh()
    panels = [d for d in window.findChildren(QtWidgets.QDockWidget) if d.isVisible() and not d.isFloating()
              and window.dockWidgetArea(d) in (QtCore.Qt.LeftDockWidgetArea, QtCore.Qt.RightDockWidgetArea)]
    if panels:
        width = window.width() // split_screen.PANEL_RATIO
        window.resizeDocks(panels, [width] * len(panels), QtCore.Qt.Horizontal)
        refresh()


def show(doc, result, fit=False):
    """Hides everything else and paints the result mesh with the Von Mises stress."""
    if result is None:
        refresh()
        return
    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None)
        if vo is not None and obj is not result.Mesh:
            vo.Visibility = False
    vo = result.Mesh.ViewObject
    vo.Visibility = True
    vo.setNodeColorByScalars(list(result.NodeNumbers), list(result.vonMises))
    if fit:
        view = Gui.getDocument(doc.Name).activeView()
        view.viewIsometric()
        view.fitAll()
    refresh()


def show_part(doc, body, fit=False):
    """Hides everything else and shows only the part (the stresses are in PrePoMax)."""
    visible = {o.Name for o in (body, getattr(body, "Tip", None)) if o is not None}
    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None)
        if vo is not None:
            vo.Visibility = obj.Name in visible
    if fit:
        view = Gui.getDocument(doc.Name).activeView()
        view.viewIsometric()
        view.fitAll()
    refresh()


def save_image(doc, png_path):
    Gui.getDocument(doc.Name).activeView().saveImage(png_path, 1200, 800, "White")


def close():
    """Closes FreeCAD without asking or saving anything (the results are already saved)."""
    import FreeCAD as App
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    Gui.getMainWindow().close()
