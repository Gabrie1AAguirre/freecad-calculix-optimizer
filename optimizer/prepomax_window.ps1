<#
Drives a PrePoMax window that is already open (called by optimizer/prepomax.py).

  -Id <pid>                    puts the window on the right half of the screen, waits for
                               the result to load and turns to the isometric view
  -Id <pid> -Result <x.frd>    opens another result in the SAME window (File > Open) and turns

Clicks are Windows messages sent without waiting for an answer: a click that opens
a dialog blocks PrePoMax until the dialog closes, and waiting for it would hang
this script. Exit code 0 = done; non-zero = did not work (Python then reopens
PrePoMax the simple way).
#>
param([int]$Id, [string]$Result = "", [int]$Timeout = 120)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type -ReferencedAssemblies UIAutomationClient, UIAutomationTypes, WindowsBase @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Automation;
public static class PpmWindow {
    public static string ClickError = "";
    public static void InvokeWithoutWaiting(IntPtr window, string name) {
        var t = new Thread(() => {
            try {
                var b = AutomationElement.FromHandle(window).FindFirst(TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.NameProperty, name));
                ((InvokePattern)b.GetCurrentPattern(InvokePattern.Pattern)).Invoke();
            } catch (Exception e) { ClickError = e.GetType().Name + ": " + e.Message; }
        });
        t.IsBackground = true;
        t.Start();
    }

    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern int GetDlgCtrlID(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetParent(IntPtr h);
    [DllImport("user32.dll")] static extern bool ScreenToClient(IntPtr h, ref Point p);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, string l);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    public struct Point { public int X, Y; }

    static string ClassOf(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    static string TextOf(IntPtr h) { var s = new StringBuilder(256); GetWindowText(h, s, 256); return s.ToString(); }

    // Visible window of the process with this class and/or title (empty = any); Zero if none.
    public static IntPtr Window(int pid, string windowClass, string title) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p);
            if (p == pid && IsWindowVisible(h) && (string.IsNullOrEmpty(windowClass) || ClassOf(h) == windowClass)
                && (string.IsNullOrEmpty(title) || TextOf(h) == title)) { found = h; return false; }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    // For diagnostics: visible windows of the process and the texts of the dialogs.
    public static string Describe(int pid) {
        var r = new StringBuilder();
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p);
            if (p == pid && IsWindowVisible(h)) {
                r.Append("[" + ClassOf(h) + " '" + TextOf(h) + "'");
                if (ClassOf(h) == "#32770")
                    EnumChildWindows(h, (k, m) => { var t = TextOf(k); if (t.Length > 0) r.Append(" '" + t + "'"); return true; }, IntPtr.Zero);
                r.Append("] ");
            }
            return true;
        }, IntPtr.Zero);
        return r.ToString();
    }

    public static IntPtr Child(IntPtr parent, string classContains, string text) {
        IntPtr found = IntPtr.Zero;
        EnumChildWindows(parent, (h, l) => {
            if (ClassOf(h).Contains(classContains) && (string.IsNullOrEmpty(text) || TextOf(h) == text)) { found = h; return false; }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    public static void Click(IntPtr window, int xScreen, int yScreen) {
        var p = new Point { X = xScreen, Y = yScreen };
        ScreenToClient(window, ref p);
        var pos = new IntPtr((p.Y << 16) | (p.X & 0xFFFF));
        PostMessage(window, 0x0200 /*WM_MOUSEMOVE*/, IntPtr.Zero, pos);
        PostMessage(window, 0x0201 /*WM_LBUTTONDOWN*/, new IntPtr(1), pos);
        PostMessage(window, 0x0202 /*WM_LBUTTONUP*/, IntPtr.Zero, pos);
    }

    public static void ClickButton(IntPtr button) { PostMessage(button, 0x00F5 /*BM_CLICK*/, IntPtr.Zero, IntPtr.Zero); }

    // Split screen: right half of the main screen (FreeCAD takes the left one),
    // as in optimizer/split_screen.py: the visible part fills the half, without the invisible border.
    public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] static extern bool SystemParametersInfo(uint action, uint p, ref Rect r, uint f);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out Rect r);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int mode);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int hgt, uint f);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attribute, out Rect r, int size);
    public static bool RightHalf(IntPtr h) {
        if (IsZoomed(h) || IsIconic(h)) ShowWindow(h, 9 /*SW_RESTORE*/);
        var area = new Rect();
        SystemParametersInfo(0x0030 /*SPI_GETWORKAREA*/, 0, ref area, 0);
        Rect outer, inner;
        GetWindowRect(h, out outer);
        if (DwmGetWindowAttribute(h, 9 /*EXTENDED_FRAME_BOUNDS*/, out inner, Marshal.SizeOf(typeof(Rect))) != 0) inner = outer;
        int middle = (area.Left + area.Right) / 2;
        int x = middle - (inner.Left - outer.Left), y = area.Top - (inner.Top - outer.Top);
        int w = area.Right - middle + (inner.Left - outer.Left) + (outer.Right - inner.Right);
        int hgt = area.Bottom - area.Top + (inner.Top - outer.Top) + (outer.Bottom - inner.Bottom);
        return SetWindowPos(h, IntPtr.Zero, x, y, w, hgt, 0x0004 /*SWP_NOZORDER*/ | 0x0010 /*SWP_NOACTIVATE*/);
    }

    // "A recovery file from a previous PrePoMax session exists...": answers Cancel (do not recover).
    // Python has already kept a copy of the recovery file.
    public static bool DeclineRecovery(int pid) {
        IntPtr dlg = Window(pid, "#32770", "");
        if (dlg == IntPtr.Zero) return false;
        bool isRecovery = false;
        EnumChildWindows(dlg, (h, l) => { if (TextOf(h).Contains("recovery file")) { isRecovery = true; return false; } return true; }, IntPtr.Zero);
        if (isRecovery) PostMessage(dlg, 0x0111 /*WM_COMMAND*/, new IntPtr(2) /*IDCANCEL*/, IntPtr.Zero);
        return isRecovery;
    }

    // List (SysListView32) of another process: the messages need memory inside it.
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern IntPtr VirtualAllocEx(IntPtr p, IntPtr addr, UIntPtr n, uint type, uint prot);
    [DllImport("kernel32.dll")] static extern bool VirtualFreeEx(IntPtr p, IntPtr addr, UIntPtr n, uint type);
    [DllImport("kernel32.dll")] static extern bool WriteProcessMemory(IntPtr p, IntPtr addr, byte[] b, int n, out IntPtr done);
    [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr p, IntPtr addr, byte[] b, int n, out IntPtr done);
    [DllImport("user32.dll", EntryPoint = "SendMessageW")] static extern IntPtr Send(IntPtr h, uint m, IntPtr w, IntPtr l);
    const int ITEM_SIZE = 88, TEXT_SIZE = 512;  // 64-bit LVITEMW + text

    static byte[] Item(IntPtr remote, uint state) {
        var b = new byte[ITEM_SIZE];
        BitConverter.GetBytes(0x1u /*LVIF_TEXT*/).CopyTo(b, 0);
        BitConverter.GetBytes(state).CopyTo(b, 12);                      // state
        BitConverter.GetBytes(state).CopyTo(b, 16);                      // stateMask
        BitConverter.GetBytes((remote + ITEM_SIZE).ToInt64()).CopyTo(b, 24);  // pszText
        BitConverter.GetBytes(TEXT_SIZE / 2).CopyTo(b, 32);              // cchTextMax
        return b;
    }

    static T InMemory<T>(int pid, Func<IntPtr, IntPtr, T> use) {
        IntPtr proc = OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, false, pid);
        IntPtr remote = VirtualAllocEx(proc, IntPtr.Zero, new UIntPtr(ITEM_SIZE + TEXT_SIZE), 0x3000, 0x04);
        try { return use(proc, remote); }
        finally { VirtualFreeEx(proc, remote, UIntPtr.Zero, 0x8000); CloseHandle(proc); }
    }

    public static List<string> ListTexts(int pid, IntPtr list) {
        return InMemory(pid, (proc, remote) => {
            var texts = new List<string>();
            int n = Send(list, 0x1004 /*LVM_GETITEMCOUNT*/, IntPtr.Zero, IntPtr.Zero).ToInt32();
            IntPtr done;
            for (int i = 0; i < n; i++) {
                var b = Item(remote, 0);
                WriteProcessMemory(proc, remote, b, b.Length, out done);
                Send(list, 0x1073 /*LVM_GETITEMTEXTW*/, new IntPtr(i), remote);
                var t = new byte[TEXT_SIZE];
                ReadProcessMemory(proc, remote + ITEM_SIZE, t, t.Length, out done);
                var s = Encoding.Unicode.GetString(t);
                texts.Add(s.Substring(0, Math.Max(0, s.IndexOf('\0'))));
            }
            return texts;
        });
    }

    public static bool SelectInList(int pid, IntPtr list, int index) {
        return InMemory(pid, (proc, remote) => {
            var b = Item(remote, 0x3 /*LVIS_FOCUSED|LVIS_SELECTED*/);
            IntPtr done;
            WriteProcessMemory(proc, remote, b, b.Length, out done);
            return Send(list, 0x102B /*LVM_SETITEMSTATE*/, new IntPtr(index), remote) != IntPtr.Zero;
        });
    }

    // Windows "Open" dialog: file name field (id 1148) and OK.
    public static bool FillOpen(IntPtr dlg, string file) {
        IntPtr edit = IntPtr.Zero;
        EnumChildWindows(dlg, (h, l) => {
            if (ClassOf(h) == "Edit" && (GetDlgCtrlID(h) == 1148 || GetDlgCtrlID(GetParent(h)) == 1148)) { edit = h; return false; }
            return true;
        }, IntPtr.Zero);
        if (edit == IntPtr.Zero) return false;
        SendMessage(edit, 0x000C /*WM_SETTEXT*/, IntPtr.Zero, file);
        PostMessage(dlg, 0x0111 /*WM_COMMAND*/, new IntPtr(1) /*IDOK*/, IntPtr.Zero);
        return true;
    }
}
"@

$A = [System.Windows.Automation.AutomationElement]
$Desc = [System.Windows.Automation.TreeScope]::Descendants
$deadline = (Get-Date).AddSeconds($Timeout)

function Fail($reason) {
    if ([PpmWindow]::ClickError) { $reason += " (click: $([PpmWindow]::ClickError))" }
    try { $reason += " | windows: " + [PpmWindow]::Describe($Id) } catch { }
    [Console]::Error.WriteLine($reason)
    exit 1
}
function WaitFor([scriptblock]$condition, [int]$seconds = 0) {
    $end = if ($seconds) { (Get-Date).AddSeconds($seconds) } else { $deadline }
    while ((Get-Date) -lt $end) {
        if (-not (Get-Process -Id $Id -ErrorAction SilentlyContinue)) { Fail "PrePoMax closed" }
        try { $r = & $condition; if ($r) { return $r } } catch { }
        Start-Sleep -Milliseconds 300
    }
    return $null
}
function Await([scriptblock]$condition, [string]$what, [int]$seconds = 0) {
    $r = WaitFor $condition $seconds
    if (-not $r) { Fail "timed out waiting for $what" }
    return $r
}
function Element($root, $name) {
    $root.FindFirst($Desc, (New-Object System.Windows.Automation.PropertyCondition($A::NameProperty, $name)))
}
function InvokeElement($root, $name) {
    (Element $root $name).GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}
function Status($root) {
    $bar = Element $root "statusStrip1"
    $texts = $bar.FindAll($Desc, [System.Windows.Automation.Condition]::TrueCondition)
    ($texts | ForEach-Object { $_.Current.Name }) -join "|"
}

# Windows in which PrePoMax asks for the unit system when a file is opened from the
# menu: "Results Properties" and, from the second time on, "Model Properties" before it.
$UNIT_WINDOWS = "Model Properties", "Results Properties"

function UnitsWindow() {
    foreach ($title in $UNIT_WINDOWS) {
        $h = [PpmWindow]::Window($Id, $null, $title)
        if ($h -ne [IntPtr]::Zero) { return @{ Handle = $h; Title = $title } }
    }
    return $null
}

# Picks mm, ton, s (stresses in MPa), clicks OK and waits for the window to close.
function AnswerUnits($window) {
    $props = $window.Handle
    $list = Await { $h = [PpmWindow]::Child($props, "SysListView32", ""); if ($h -ne [IntPtr]::Zero) { $h } } "the unit list" 10
    $options = Await { $t = [PpmWindow]::ListTexts($Id, $list); if ($t.Count) { ,$t } } "the unit options" 10
    $index = -1
    for ($i = 0; $i -lt $options.Count; $i++) { if ($options[$i] -match "^\s*mm\s*,\s*ton") { $index = $i } }
    if ($index -lt 0) { Fail "could not find mm, ton, s among the units: $($options -join ' / ')" }
    [PpmWindow]::SelectInList($Id, $list, $index) | Out-Null
    Start-Sleep -Milliseconds 200
    $ok = [PpmWindow]::Child($props, "BUTTON", "OK")
    if ($ok -eq [IntPtr]::Zero) { Fail "could not find the OK button of the units window" }
    [PpmWindow]::ClickButton($ok)
    Await { [PpmWindow]::Window($Id, $null, $window.Title) -ne $props } "the units window to close" 10 | Out-Null
}

$main = Await { $h = (Get-Process -Id $Id).MainWindowHandle; if ($h -ne 0) { $h } } "the PrePoMax window"
$root = $A::FromHandle($main)
# Newly opened window: goes to the right half of the screen (and again before fitting,
# in case PrePoMax restored its own size while loading).
if (-not $Result) { [PpmWindow]::RightHalf($main) | Out-Null }

if ($Result) {
    # File > Open through the toolbar button. The click only returns when the dialog closes,
    # so it runs on a separate thread.
    Await { Element $root "Open file" } "the Open file button" | Out-Null
    [PpmWindow]::InvokeWithoutWaiting($main, "Open file")
    $dlg = Await { $h = [PpmWindow]::Window($Id, "#32770", $null); if ($h -ne [IntPtr]::Zero) { $h } } "the Open dialog" 15
    Start-Sleep -Milliseconds 300
    if (-not [PpmWindow]::FillOpen($dlg, $Result)) { Fail "could not find the file name field" }
    AnswerUnits (Await { UnitsWindow } "the units window" 30)
}

# Loaded: status bar at "Ready", already with units in mm, and no pending question.
Await {
    if (-not $Result) { [PpmWindow]::DeclineRecovery($Id) | Out-Null }
    $question = UnitsWindow
    if ($question) { AnswerUnits $question; return $false }
    $s = Status $root; $s -match "Ready" -and $s -match "Unit system: mm"
} "the result to load" | Out-Null
if (-not $Result) { [PpmWindow]::RightHalf($main) | Out-Null }
Start-Sleep -Milliseconds 500
InvokeElement $root "Isometric view"
InvokeElement $root "Zoom to fit"
exit 0
