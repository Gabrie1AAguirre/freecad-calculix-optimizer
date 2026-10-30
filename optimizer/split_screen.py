"""Split screen: FreeCAD on the left half, PrePoMax on the right (Windows only,
standard library). PrePoMax is placed by prepomax_window.ps1, with the same math."""
import ctypes
import os

LEFT, RIGHT = "left", "right"
PANEL_RATIO = 4  # on the split screen, FreeCAD's Model/Tasks panel takes 1/4 of the window


def half(area, side, border=(0, 0, 0, 0)):
    """(x, y, width, height) for the window to fill one half of the work area
    (left, top, right, bottom). `border` is the invisible window margin (left, top,
    right, bottom) that Windows 10/11 draws outside the visible part."""
    left, top, right, bottom = area
    middle = (left + right) // 2
    x0, x1 = (left, middle) if side == LEFT else (middle, right)
    return (x0 - border[0], top - border[1], x1 - x0 + border[0] + border[2], bottom - top + border[1] + border[3])


def work_area():
    """Main screen minus the taskbar: (left, top, right, bottom)."""
    from ctypes import wintypes
    r = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return (r.left, r.top, r.right, r.bottom)


def place(window, side):
    """Puts the window (HWND) on one half of the main screen. False if it did not work."""
    if os.name != "nt" or not window:
        return False
    from ctypes import wintypes
    user32, h = ctypes.windll.user32, wintypes.HWND(window)
    if not user32.IsWindow(h):
        return False
    if user32.IsZoomed(h) or user32.IsIconic(h):
        user32.ShowWindow(h, 9)  # SW_RESTORE: when maximized, it would ignore the size
    outer, inner = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(outer))
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(inner), ctypes.sizeof(inner)):  # EXTENDED_FRAME_BOUNDS
        inner = outer
    border = (inner.left - outer.left, inner.top - outer.top, outer.right - inner.right, outer.bottom - inner.bottom)
    x, y, width, height = half(work_area(), side, border)
    SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
    return bool(user32.SetWindowPos(h, None, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE))
