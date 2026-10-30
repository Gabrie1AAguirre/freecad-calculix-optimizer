"""Showing the results in PrePoMax: part colored by Von Mises with the stress
color bar. Standard library only (the launcher imports it too)."""
import glob
import os
import re
import shutil
import subprocess
import time

EXE_NAME = "PrePoMax.exe"
ENVIRONMENT_VARIABLE = "PREPOMAX_BIN"
DEFAULT_LOCATIONS = [
    os.path.join(os.path.expanduser("~"), "Documents", "PrePoMax*"),
    os.path.join(os.path.expanduser("~"), "Documents", "*", "PrePoMax*"),
    os.path.join(os.path.expanduser("~"), "Desktop", "PrePoMax*"),
    os.path.join(os.path.expanduser("~"), "Downloads", "PrePoMax*"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PrePoMax*"),
    r"C:\PrePoMax*",
]
# mm, tonne, s: stresses in MPa and lengths in mm, as in FreeCAD.
UNITS = "MM_TON_S_C"


def _exe_in(folder):
    exe = os.path.join(folder, EXE_NAME)
    return exe if os.path.isfile(exe) else None


def _version(path):
    return [int(n) for n in re.findall(r"\d+", os.path.basename(os.path.dirname(path)))]


def find(folder=None, environment=os.environ, locations=None):
    """Path to PrePoMax.exe: given folder, PREPOMAX_BIN variable or the newest
    version in the usual locations. None if not found."""
    if folder:
        return _exe_in(folder)
    if environment.get(ENVIRONMENT_VARIABLE):
        return _exe_in(environment[ENVIRONMENT_VARIABLE])
    found = [exe for pattern in (DEFAULT_LOCATIONS if locations is None else locations)
             for exe in glob.glob(os.path.join(pattern, EXE_NAME))]
    return max(found, key=_version) if found else None


def stress_first(source, destination):
    """Copies the CalculiX .frd putting the stress block before the others:
    PrePoMax opens showing the first block, so it opens on the Von Mises."""
    with open(source, encoding="latin-1") as f:
        lines = f.read().splitlines(keepends=True)
    header, blocks, end, current = [], [], [], None
    for line in lines:
        text = line.strip()
        if text.startswith("1PSTEP"):
            current = [line]
            blocks.append(current)
        elif text == "9999":
            end.append(line)
            current = None
        elif current is not None:
            current.append(line)
            if text == "-3":
                current = None
        else:
            header.append(line)
    if not any(_block_name(b) == "STRESS" for b in blocks):
        shutil.copyfile(source, destination)
        return
    blocks.sort(key=lambda b: _block_name(b) != "STRESS")
    with open(destination, "w", encoding="latin-1", newline="") as f:
        f.write("".join(header + [line for b in blocks for line in b] + end))


def _block_name(block):
    for line in block:
        parts = line.split()
        if parts and parts[0] == "-4" and len(parts) > 1:
            return parts[1]
    return None


def recovery_file(exe):
    """Where PrePoMax keeps the session to recover it if killed. If the file
    exists, the next start asks whether to recover it and does not load the .frd."""
    return os.path.join(os.path.dirname(exe), "history.pmh")


def _process_alive(pid):
    import ctypes
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


def close_like_x(pid, wait_s=15):
    """Closes PrePoMax as if by the X button, answering "No" to "Save file before closing?":
    this way it leaves no recovery file. False if it did not close."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    WM_CLOSE, WM_COMMAND, IDNO = 0x0010, 0x0111, 7
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def windows():
        found = []

        def note(h, _):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(h):
                window_class = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(h, window_class, 64)
                found.append((h, window_class.value == "#32770"))
            return True
        user32.EnumWindows(callback(note), 0)
        return found

    for h, dialog in windows():
        if not dialog:
            user32.PostMessageW(h, WM_CLOSE, 0, 0)
    end = time.time() + wait_s
    while time.time() < end:
        if not _process_alive(pid):
            return True
        for h, dialog in windows():
            if dialog:
                user32.PostMessageW(h, WM_COMMAND, IDNO, 0)
        time.sleep(0.2)
    return False


def _start(command, errors=None, folder=None):
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors or subprocess.DEVNULL, cwd=folder,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _delete(path):
    try:
        os.remove(path)
    except OSError:
        pass


class Viewer:
    """One PrePoMax window with the latest result.

    The first time it opens PrePoMax; after that, the prepomax_window.ps1 script opens
    each new result in the SAME window (File > Open) and turns to the isometric view.
    Each swap takes a few seconds: if a result arrives while the window is still busy,
    only the newest one waits. If the script fails, it closes the window and opens
    another one next time. It only closes windows it opened itself."""

    def __init__(self, command, folder, drive_window=True):
        self.command = list(command)
        self.folder = folder  # copies of the .frd files (deleted when no longer needed)
        self.drive_window = drive_window
        os.makedirs(folder, exist_ok=True)
        self.log = os.path.join(os.path.dirname(os.path.abspath(folder)), WINDOW_LOG_NAME)
        self.process = None    # PrePoMax
        self.driver = None     # the script driving the window, while it runs
        self.loading = None
        self.shown = None
        self.pending = None
        self.counter = 0
        self.last_drive_ok = None

    def show(self, calculix_frd):
        """Shows a CalculiX result (copied: the next analysis overwrites the file)."""
        self.counter += 1
        copy = os.path.join(self.folder, "result_%03d.frd" % self.counter)
        stress_first(calculix_frd, copy)
        self._enqueue(copy)

    def show_file(self, frd, wait=True):
        """Shows a ready .frd (never deleted), by default waiting for it to load."""
        self._enqueue(frd)
        if wait:
            self.wait()
            if self.drive_window and self.last_drive_ok is False:
                # Last resort: open it the simple way (without the isometric view).
                self.close()
                self.process = self._open_prepomax(frd)

    def wait(self):
        """Waits for the window to finish loading everything in the queue."""
        while self.driver is not None or self.pending is not None:
            if self.driver is not None:
                self.driver.wait()
            self._update()

    def close(self):
        if self.driver is not None and self.driver.poll() is None:
            self.driver.kill()
            self.driver.wait()
        if self.process is not None and self.process.poll() is None:
            if not close_like_x(self.process.pid):
                self.process.kill()
                self.process.wait()
        self.driver = self.process = None

    def _open_prepomax(self, frd):
        recovery = recovery_file(self.command[0])
        if os.path.exists(recovery):
            # The script answers "no" to the recovery question; the file is kept here.
            copy = os.path.join(os.path.dirname(self.log),
                                "prepomax_recovery_%s.pmh" % time.strftime("%Y%m%d-%H%M%S"))
            shutil.copyfile(recovery, copy)
            with open(self.log, "a", encoding="utf-8") as log:
                log.write("PrePoMax recovery file kept at %s\n" % copy)
        # In its own folder, as when opened from the shortcut.
        return _start(self.command + ["-f", frd, "-u", UNITS], folder=os.path.dirname(self.command[0]))

    def _owned(self, path):
        return path is not None and os.path.dirname(os.path.abspath(path)) == os.path.abspath(self.folder)

    def _discard(self, path):
        if self._owned(path):
            _delete(path)

    def _enqueue(self, frd):
        self._discard(self.pending)
        self.pending = frd
        self._update()

    def _update(self):
        if self.driver is not None:
            if self.driver.poll() is None:
                return  # window busy: the pending one goes next time
            self.last_drive_ok = self.driver.returncode == 0
            with open(self.log, "a", encoding="utf-8") as log:
                log.write("  -> %s\n" % ("ok" if self.last_drive_ok else "failed (%d)" % self.driver.returncode))
            self.driver = None
            self._displayed(self.loading, self.last_drive_ok)
        if self.pending is None:
            return
        frd, self.pending = self.pending, None
        is_open = self.process is not None and self.process.poll() is None
        if not self.drive_window:
            self.close()
            self.process = self._open_prepomax(frd)
            self._displayed(frd, True)
            return
        if not is_open:
            self.process = self._open_prepomax(frd)
        with open(self.log, "a", encoding="utf-8") as log:
            log.write("%s %s\n" % ("switch to" if is_open else "open", frd))
            log.flush()
            self.driver = _start(_window_command(self.process.pid, frd if is_open else None), errors=log)
        self.loading = frd

    def _displayed(self, frd, ok):
        if ok:
            if self.shown != frd:
                self._discard(self.shown)
            self.shown = frd
        else:
            # Window state unknown (dialog open?): next time it opens another one.
            self.close()
            self._discard(frd)
            self._discard(self.shown)
            self.shown = None
        self.loading = None


WINDOW_LOG_NAME = "prepomax_window.log"  # what the script driving the window said (diagnostics)
WINDOW_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prepomax_window.ps1")


def _window_command(pid, frd=None):
    command = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", WINDOW_SCRIPT, "-Id", str(pid)]
    return command + (["-Result", frd] if frd else [])
