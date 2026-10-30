"""Utilities shared by the tests."""
import hashlib
import os
import shutil
import tempfile

import FreeCAD as App

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L_EXAMPLE = os.path.join(ROOT, "examples", "L_part.FCStd")
ORIGINAL_L = os.path.join(ROOT, "tests", "data", "L_part_original.FCStd")  # part without spreadsheet, with old results
FREECAD_BIN = os.environ.get("FREECAD_BIN", r"C:\Program Files\FreeCAD 1.1\bin")
FREECAD_PYTHON = os.path.join(FREECAD_BIN, "python.exe")


def temporary_copy(path, testcase, folder_prefix="opt"):
    """Copies the file to a temporary folder deleted at the end of the test."""
    folder = tempfile.mkdtemp(prefix=folder_prefix)
    testcase.addCleanup(shutil.rmtree, folder, True)
    destination = os.path.join(folder, os.path.basename(path))
    shutil.copy(path, destination)
    return destination


def open_copy(path, testcase):
    doc = App.openDocument(temporary_copy(path, testcase))
    testcase.addCleanup(lambda: App.closeDocument(doc.Name) if doc.Name in App.listDocuments() else None)
    return doc


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def visible_part(pid):
    """(x, y, width, height) visible part of the largest window of the process."""
    import ctypes
    from ctypes import wintypes
    user32, found = ctypes.windll.user32, []

    def note(h, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(h):
            r = wintypes.RECT()
            ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(h), 9, ctypes.byref(r), ctypes.sizeof(r))
            found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(note), 0)
    return max(found, key=lambda r: r[2] * r[3], default=None)
