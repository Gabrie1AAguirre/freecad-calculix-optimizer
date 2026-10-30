import ctypes
import os
import unittest
from ctypes import wintypes

from optimizer import split_screen


class TestHalf(unittest.TestCase):
    AREA = (0, 0, 1920, 1032)  # full screen minus the taskbar

    def test_left(self):
        self.assertEqual(split_screen.half(self.AREA, split_screen.LEFT), (0, 0, 960, 1032))

    def test_right(self):
        self.assertEqual(split_screen.half(self.AREA, split_screen.RIGHT), (960, 0, 960, 1032))

    def test_shifted_area(self):
        # Taskbar on the left or a monitor that does not start at 0.
        self.assertEqual(split_screen.half((100, 50, 1101, 850), split_screen.RIGHT), (600, 50, 501, 800))

    def test_invisible_border(self):
        # On Windows 10/11 the window has an invisible border of about 7 px outside what is seen:
        # the rectangle grows so that the visible part fills exactly the half.
        self.assertEqual(split_screen.half(self.AREA, split_screen.LEFT, border=(7, 0, 7, 7)), (-7, 0, 974, 1039))


@unittest.skipUnless(os.name == "nt", "Windows only")
class TestPlace(unittest.TestCase):
    def setUp(self):
        user32 = ctypes.windll.user32
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        WS_OVERLAPPEDWINDOW, WS_VISIBLE = 0x00CF0000, 0x10000000
        self.window = user32.CreateWindowExW(0, "STATIC", "split screen test", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                             200, 200, 400, 300, None, None, None, None)
        self.assertTrue(self.window)
        self.addCleanup(user32.DestroyWindow, self.window)

    def _visible(self):
        r = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(self.window), 9, ctypes.byref(r), ctypes.sizeof(r))
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    def test_visible_part_fills_the_half(self):
        for side in (split_screen.LEFT, split_screen.RIGHT):
            self.assertTrue(split_screen.place(self.window, side))
            self.assertEqual(self._visible(), split_screen.half(split_screen.work_area(), side))

    def test_maximized_window(self):
        ctypes.windll.user32.ShowWindow(wintypes.HWND(self.window), 3)  # SW_MAXIMIZE
        self.assertTrue(split_screen.place(self.window, split_screen.RIGHT))
        self.assertFalse(ctypes.windll.user32.IsZoomed(wintypes.HWND(self.window)))
        self.assertEqual(self._visible(), split_screen.half(split_screen.work_area(), split_screen.RIGHT))

    def test_missing_window(self):
        self.assertFalse(split_screen.place(0, split_screen.LEFT))


if __name__ == "__main__":
    unittest.main()
