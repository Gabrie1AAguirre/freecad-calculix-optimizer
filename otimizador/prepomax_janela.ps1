<#
Comanda uma janela do PrePoMax já aberta (chamado por otimizador/prepomax.py).

  -Id <pid>                    põe a janela na metade direita da tela, espera o resultado
                               carregar e gira para a vista isométrica
  -Id <pid> -Arquivo <x.frd>   abre outro resultado na MESMA janela (File > Open) e gira

Os cliques são mensagens do Windows enviadas sem esperar resposta: um clique que
abre um diálogo prende o PrePoMax até o diálogo fechar, e esperar por ele travaria
este script. Código de saída 0 = feito; diferente de 0 = não deu (o Python então
reabre o PrePoMax do jeito simples).
#>
param([int]$Id, [string]$Arquivo = "", [int]$Espera = 120)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type -ReferencedAssemblies UIAutomationClient, UIAutomationTypes, WindowsBase @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Automation;
public static class PpmJanela {
    public static string ErroClique = "";
    public static void InvocarSemEsperar(IntPtr janela, string nome) {
        var t = new Thread(() => {
            try {
                var b = AutomationElement.FromHandle(janela).FindFirst(TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.NameProperty, nome));
                ((InvokePattern)b.GetCurrentPattern(InvokePattern.Pattern)).Invoke();
            } catch (Exception e) { ErroClique = e.GetType().Name + ": " + e.Message; }
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
    [DllImport("user32.dll")] static extern bool ScreenToClient(IntPtr h, ref Ponto p);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, string l);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    public struct Ponto { public int X, Y; }

    static string Classe(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    static string Texto(IntPtr h) { var s = new StringBuilder(256); GetWindowText(h, s, 256); return s.ToString(); }

    // Janela visível do processo com essa classe e/ou título (vazio = qualquer); Zero se não houver.
    public static IntPtr Janela(int pid, string classe, string titulo) {
        IntPtr achada = IntPtr.Zero;
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p);
            if (p == pid && IsWindowVisible(h) && (string.IsNullOrEmpty(classe) || Classe(h) == classe)
                && (string.IsNullOrEmpty(titulo) || Texto(h) == titulo)) { achada = h; return false; }
            return true;
        }, IntPtr.Zero);
        return achada;
    }

    // Para diagnóstico: janelas visíveis do processo e os textos dos diálogos.
    public static string Descrever(int pid) {
        var r = new StringBuilder();
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p);
            if (p == pid && IsWindowVisible(h)) {
                r.Append("[" + Classe(h) + " '" + Texto(h) + "'");
                if (Classe(h) == "#32770")
                    EnumChildWindows(h, (k, m) => { var t = Texto(k); if (t.Length > 0) r.Append(" '" + t + "'"); return true; }, IntPtr.Zero);
                r.Append("] ");
            }
            return true;
        }, IntPtr.Zero);
        return r.ToString();
    }

    public static IntPtr Filho(IntPtr pai, string classeContem, string texto) {
        IntPtr achado = IntPtr.Zero;
        EnumChildWindows(pai, (h, l) => {
            if (Classe(h).Contains(classeContem) && (string.IsNullOrEmpty(texto) || Texto(h) == texto)) { achado = h; return false; }
            return true;
        }, IntPtr.Zero);
        return achado;
    }

    public static void Clicar(IntPtr janela, int xTela, int yTela) {
        var p = new Ponto { X = xTela, Y = yTela };
        ScreenToClient(janela, ref p);
        var pos = new IntPtr((p.Y << 16) | (p.X & 0xFFFF));
        PostMessage(janela, 0x0200 /*WM_MOUSEMOVE*/, IntPtr.Zero, pos);
        PostMessage(janela, 0x0201 /*WM_LBUTTONDOWN*/, new IntPtr(1), pos);
        PostMessage(janela, 0x0202 /*WM_LBUTTONUP*/, IntPtr.Zero, pos);
    }

    public static void ClicarBotao(IntPtr botao) { PostMessage(botao, 0x00F5 /*BM_CLICK*/, IntPtr.Zero, IntPtr.Zero); }

    // Tela dividida: metade direita da tela principal (o FreeCAD fica com a esquerda),
    // como otimizador/janelas.py: a parte visível ocupa a metade, sem a borda invisível.
    public struct Ret { public int Esq, Topo, Dir, Base; }
    [DllImport("user32.dll")] static extern bool SystemParametersInfo(uint acao, uint p, ref Ret r, uint f);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out Ret r);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int modo);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr depois, int x, int y, int l, int a, uint f);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int atributo, out Ret r, int tamanho);
    public static bool MetadeDireita(IntPtr h) {
        if (IsZoomed(h) || IsIconic(h)) ShowWindow(h, 9 /*SW_RESTORE*/);
        var area = new Ret();
        SystemParametersInfo(0x0030 /*SPI_GETWORKAREA*/, 0, ref area, 0);
        Ret fora, dentro;
        GetWindowRect(h, out fora);
        if (DwmGetWindowAttribute(h, 9 /*EXTENDED_FRAME_BOUNDS*/, out dentro, Marshal.SizeOf(typeof(Ret))) != 0) dentro = fora;
        int meio = (area.Esq + area.Dir) / 2;
        int x = meio - (dentro.Esq - fora.Esq), y = area.Topo - (dentro.Topo - fora.Topo);
        int l = area.Dir - meio + (dentro.Esq - fora.Esq) + (fora.Dir - dentro.Dir);
        int a = area.Base - area.Topo + (dentro.Topo - fora.Topo) + (fora.Base - dentro.Base);
        return SetWindowPos(h, IntPtr.Zero, x, y, l, a, 0x0004 /*SWP_NOZORDER*/ | 0x0010 /*SWP_NOACTIVATE*/);
    }

    // "A recovery file from a previous PrePoMax session exists...": responde Cancel (não recuperar).
    // O Python já guardou uma cópia do arquivo de recuperação.
    public static bool RecusarRecuperacao(int pid) {
        IntPtr dlg = Janela(pid, "#32770", "");
        if (dlg == IntPtr.Zero) return false;
        bool ehRecuperacao = false;
        EnumChildWindows(dlg, (h, l) => { if (Texto(h).Contains("recovery file")) { ehRecuperacao = true; return false; } return true; }, IntPtr.Zero);
        if (ehRecuperacao) PostMessage(dlg, 0x0111 /*WM_COMMAND*/, new IntPtr(2) /*IDCANCEL*/, IntPtr.Zero);
        return ehRecuperacao;
    }

    // Lista (SysListView32) de outro processo: as mensagens precisam de memória dentro dele.
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint acesso, bool herda, int pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern IntPtr VirtualAllocEx(IntPtr p, IntPtr end, UIntPtr n, uint tipo, uint prot);
    [DllImport("kernel32.dll")] static extern bool VirtualFreeEx(IntPtr p, IntPtr end, UIntPtr n, uint tipo);
    [DllImport("kernel32.dll")] static extern bool WriteProcessMemory(IntPtr p, IntPtr end, byte[] b, int n, out IntPtr feito);
    [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr p, IntPtr end, byte[] b, int n, out IntPtr feito);
    [DllImport("user32.dll", EntryPoint = "SendMessageW")] static extern IntPtr Enviar(IntPtr h, uint m, IntPtr w, IntPtr l);
    const int TAM_ITEM = 88, TAM_TEXTO = 512;  // LVITEMW em 64 bits + texto

    static byte[] Item(IntPtr remoto, uint estado) {
        var b = new byte[TAM_ITEM];
        BitConverter.GetBytes(0x1u /*LVIF_TEXT*/).CopyTo(b, 0);
        BitConverter.GetBytes(estado).CopyTo(b, 12);                    // state
        BitConverter.GetBytes(estado).CopyTo(b, 16);                    // stateMask
        BitConverter.GetBytes((remoto + TAM_ITEM).ToInt64()).CopyTo(b, 24);  // pszText
        BitConverter.GetBytes(TAM_TEXTO / 2).CopyTo(b, 32);             // cchTextMax
        return b;
    }

    static T NaMemoria<T>(int pid, Func<IntPtr, IntPtr, T> uso) {
        IntPtr proc = OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, false, pid);
        IntPtr remoto = VirtualAllocEx(proc, IntPtr.Zero, new UIntPtr(TAM_ITEM + TAM_TEXTO), 0x3000, 0x04);
        try { return uso(proc, remoto); }
        finally { VirtualFreeEx(proc, remoto, UIntPtr.Zero, 0x8000); CloseHandle(proc); }
    }

    public static List<string> TextosLista(int pid, IntPtr lista) {
        return NaMemoria(pid, (proc, remoto) => {
            var textos = new List<string>();
            int n = Enviar(lista, 0x1004 /*LVM_GETITEMCOUNT*/, IntPtr.Zero, IntPtr.Zero).ToInt32();
            IntPtr feito;
            for (int i = 0; i < n; i++) {
                var b = Item(remoto, 0);
                WriteProcessMemory(proc, remoto, b, b.Length, out feito);
                Enviar(lista, 0x1073 /*LVM_GETITEMTEXTW*/, new IntPtr(i), remoto);
                var t = new byte[TAM_TEXTO];
                ReadProcessMemory(proc, remoto + TAM_ITEM, t, t.Length, out feito);
                var s = Encoding.Unicode.GetString(t);
                textos.Add(s.Substring(0, Math.Max(0, s.IndexOf('\0'))));
            }
            return textos;
        });
    }

    public static bool SelecionarLista(int pid, IntPtr lista, int indice) {
        return NaMemoria(pid, (proc, remoto) => {
            var b = Item(remoto, 0x3 /*LVIS_FOCUSED|LVIS_SELECTED*/);
            IntPtr feito;
            WriteProcessMemory(proc, remoto, b, b.Length, out feito);
            return Enviar(lista, 0x102B /*LVM_SETITEMSTATE*/, new IntPtr(indice), remoto) != IntPtr.Zero;
        });
    }

    // Diálogo "Abrir" do Windows: campo do nome do arquivo (id 1148) e OK.
    public static bool PreencherAbrir(IntPtr dlg, string arquivo) {
        IntPtr edit = IntPtr.Zero;
        EnumChildWindows(dlg, (h, l) => {
            if (Classe(h) == "Edit" && (GetDlgCtrlID(h) == 1148 || GetDlgCtrlID(GetParent(h)) == 1148)) { edit = h; return false; }
            return true;
        }, IntPtr.Zero);
        if (edit == IntPtr.Zero) return false;
        SendMessage(edit, 0x000C /*WM_SETTEXT*/, IntPtr.Zero, arquivo);
        PostMessage(dlg, 0x0111 /*WM_COMMAND*/, new IntPtr(1) /*IDOK*/, IntPtr.Zero);
        return true;
    }
}
"@

$A = [System.Windows.Automation.AutomationElement]
$Desc = [System.Windows.Automation.TreeScope]::Descendants
$limite = (Get-Date).AddSeconds($Espera)

function Falhar($motivo) {
    if ([PpmJanela]::ErroClique) { $motivo += " (clique: $([PpmJanela]::ErroClique))" }
    try { $motivo += " | janelas: " + [PpmJanela]::Descrever($Id) } catch { }
    [Console]::Error.WriteLine($motivo)
    exit 1
}
function Esperar([scriptblock]$condicao, [int]$segundos = 0) {
    $fim = if ($segundos) { (Get-Date).AddSeconds($segundos) } else { $limite }
    while ((Get-Date) -lt $fim) {
        if (-not (Get-Process -Id $Id -ErrorAction SilentlyContinue)) { Falhar "o PrePoMax fechou" }
        try { $r = & $condicao; if ($r) { return $r } } catch { }
        Start-Sleep -Milliseconds 300
    }
    return $null
}
function Aguardar([scriptblock]$condicao, [string]$oque, [int]$segundos = 0) {
    $r = Esperar $condicao $segundos
    if (-not $r) { Falhar "tempo esgotado esperando $oque" }
    return $r
}
function Elemento($raiz, $nome) {
    $raiz.FindFirst($Desc, (New-Object System.Windows.Automation.PropertyCondition($A::NameProperty, $nome)))
}
function Invocar($raiz, $nome) {
    (Elemento $raiz $nome).GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}
function Status($raiz) {
    $barra = Elemento $raiz "statusStrip1"
    $textos = $barra.FindAll($Desc, [System.Windows.Automation.Condition]::TrueCondition)
    ($textos | ForEach-Object { $_.Current.Name }) -join "|"
}

# Janelas em que o PrePoMax pergunta o sistema de unidades ao abrir um arquivo pelo
# menu: "Results Properties" e, a partir da segunda vez, antes dela "Model Properties".
$JANELAS_UNIDADES = "Model Properties", "Results Properties"

function JanelaUnidades() {
    foreach ($titulo in $JANELAS_UNIDADES) {
        $h = [PpmJanela]::Janela($Id, $null, $titulo)
        if ($h -ne [IntPtr]::Zero) { return @{ Handle = $h; Titulo = $titulo } }
    }
    return $null
}

# Escolhe mm, ton, s (tensões em MPa), clica OK e espera a janela fechar.
function ResponderUnidades($janela) {
    $props = $janela.Handle
    $lista = Aguardar { $h = [PpmJanela]::Filho($props, "SysListView32", ""); if ($h -ne [IntPtr]::Zero) { $h } } "a lista de unidades" 10
    $opcoes = Aguardar { $t = [PpmJanela]::TextosLista($Id, $lista); if ($t.Count) { ,$t } } "as opções de unidade" 10
    $indice = -1
    for ($i = 0; $i -lt $opcoes.Count; $i++) { if ($opcoes[$i] -match "^\s*mm\s*,\s*ton") { $indice = $i } }
    if ($indice -lt 0) { Falhar "não achei mm, ton, s entre as unidades: $($opcoes -join ' / ')" }
    [PpmJanela]::SelecionarLista($Id, $lista, $indice) | Out-Null
    Start-Sleep -Milliseconds 200
    $ok = [PpmJanela]::Filho($props, "BUTTON", "OK")
    if ($ok -eq [IntPtr]::Zero) { Falhar "não achei o OK da janela de unidades" }
    [PpmJanela]::ClicarBotao($ok)
    Aguardar { [PpmJanela]::Janela($Id, $null, $janela.Titulo) -ne $props } "fechar a janela de unidades" 10 | Out-Null
}

$principal = Aguardar { $h = (Get-Process -Id $Id).MainWindowHandle; if ($h -ne 0) { $h } } "a janela do PrePoMax"
$raiz = $A::FromHandle($principal)
# Janela recém-aberta: vai para a metade direita da tela (e de novo antes de enquadrar,
# caso o PrePoMax tenha restaurado o tamanho dele enquanto carregava).
if (-not $Arquivo) { [PpmJanela]::MetadeDireita($principal) | Out-Null }

if ($Arquivo) {
    # File > Open pelo botão da barra. O clique só volta quando o diálogo fecha,
    # então roda numa thread à parte.
    Aguardar { Elemento $raiz "Open file" } "o botão Open file" | Out-Null
    [PpmJanela]::InvocarSemEsperar($principal, "Open file")
    $dlg = Aguardar { $h = [PpmJanela]::Janela($Id, "#32770", $null); if ($h -ne [IntPtr]::Zero) { $h } } "o diálogo Abrir" 15
    Start-Sleep -Milliseconds 300
    if (-not [PpmJanela]::PreencherAbrir($dlg, $Arquivo)) { Falhar "não achei o campo do nome do arquivo" }
    ResponderUnidades (Aguardar { JanelaUnidades } "a janela de unidades" 30)
}

# Carregado: barra de status em "Ready", já com as unidades em mm, e sem pergunta pendente.
Aguardar {
    if (-not $Arquivo) { [PpmJanela]::RecusarRecuperacao($Id) | Out-Null }
    $pergunta = JanelaUnidades
    if ($pergunta) { ResponderUnidades $pergunta; return $false }
    $s = Status $raiz; $s -match "Ready" -and $s -match "Unit system: mm"
} "o resultado carregar" | Out-Null
if (-not $Arquivo) { [PpmJanela]::MetadeDireita($principal) | Out-Null }
Start-Sleep -Milliseconds 500
Invocar $raiz "Isometric view"
Invocar $raiz "Zoom to fit"
exit 0
