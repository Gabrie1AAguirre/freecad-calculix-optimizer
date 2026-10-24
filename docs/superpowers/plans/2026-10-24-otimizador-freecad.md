# Otimizador de forma FreeCAD + CalculiX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A generic Python tool, launched from the VS Code terminal, that takes any FreeCAD part prepared with an FEM analysis and a `Parametros` spreadsheet and finds the lightest variant whose Von Mises stays under a limit, showing progress live in the FreeCAD window.

**Architecture:** A stdlib-only launcher (`otimizar.py`, system Python) finds FreeCAD, writes a job JSON, starts `freecad.exe` (live) or `freecadcmd.exe` (headless/checar), and streams the run's `log.txt` to the terminal. Inside FreeCAD, the package `otimizador/` reads the spreadsheet, applies values, recomputes, guards boundary-condition faces, meshes (Gmsh), solves (CalculiX via `femtools.ccxtools`), measures filtered Von Mises and mass, and drives scipy COBYLA. Outputs go to `resultados/<peca>_<data-hora>/`.

**Tech Stack:** FreeCAD 1.1.4 (bundled Python 3.11, numpy 1.26, scipy 1.16, matplotlib 3.10, Gmsh, CalculiX), stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-24-otimizador-freecad-design.md`

## Global Constraints

- Windows + FreeCAD 1.1; default install `C:\Program Files\FreeCAD 1.1\bin`, overridable by `--freecad <pasta>` and env `FREECAD_BIN`.
- No extra dependencies: launcher = stdlib only; package = stdlib + numpy/scipy/matplotlib bundled with FreeCAD. **No pytest** (not bundled) — tests use `unittest`.
- Test command (from repo root, PowerShell): `& "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests -t . -v`
- Run scripts in freecadcmd with `freecadcmd.exe -c "exec(open(r'<path>').read())"` — positional script path did not execute in tests.
- Never name a module after a stdlib module (`inspect.py` shadowed stdlib and broke FreeCAD during the spike).
- Code, messages, README in Portuguese. Spreadsheet name `Parametros`; reserved aliases: `tensao_limite` (MPa, required), `max_iteracoes` (default 30), `zona_exclusao_mm` (default 2 × mesh `CharacteristicLengthMax`; if that is 0, bbox diagonal / 20), `excluir_<NomeDoObjetoCC>` (0/1, default 1).
- Parameter rows: column B = value cell with alias, column C = min, column D = max (same row). Any alias in column B that is not reserved is a parameter.
- Exact status strings: `"OK ✓"`, `"OK ⚠ verificar"`, `"acima do limite"`, `"inválida"`.
- The input `.FCStd` is never modified; work on a copy inside the results folder.
- Objective: minimize mass s.t. filtered `VonMises_max ≤ tensao_limite`, params in [min, max].
- Launcher reconfigures stdout to UTF-8 (`errors="replace"`) so ✓/⚠ never crash the terminal.

## Review Focus

1. Spreadsheet values typed Brazilian-style (`12,5`) or with units (`20 mm`) → read as 12.5 / 20.0 mm, not crash. Test in Task 1.
2. Paths with spaces and accents (the user's folder is `vscode scripts`) → whole pipeline works. Test in Task 9 (temp dir named `pasta com espaço ç`).
3. Input file already containing old FEM results (the user's `L_part.FCStd` does) → stale results never read as the new iteration's. Test in Task 6.
4. Document with two `Fem::FemAnalysis` objects, or none → `--checar` says which, in Portuguese. Test in Task 5.
5. FreeCAD not found at default path → clear message naming `--freecad`, exit code 1. Test in Task 9.

## File Structure

```
otimizar.py                      launcher (system Python, stdlib only)
otimizador/__init__.py
otimizador/trabalho.py           job JSON (shared by launcher & FreeCAD side; stdlib only)
otimizador/planilha.py           read Parametros, apply values
otimizador/modelo.py             discover analysis objects, mass
otimizador/topologia.py          BC face signatures + comparison
otimizador/fea.py                mesh + CalculiX run
otimizador/tensao.py             filtered stress measure (pure)
otimizador/checagem.py           --checar problems
otimizador/avaliacao.py          one evaluation → Iteracao
otimizador/otimizacao.py         COBYLA loop, best selection (pure)
otimizador/saidas.py             CSV, terminal line, plot, summary
otimizador/gui.py                live view (FreeCADGui only)
otimizador/executar.py           entry point inside FreeCAD
otimizador/_iniciar.py           bootstrap passed to freecad.exe / freecadcmd
ferramentas/preparar_exemplo_L.py builds exemplos/L_part.FCStd from L_part.FCStd
exemplos/L_part.FCStd
tests/__init__.py                adds FreeCAD bin/lib to sys.path, imports FreeCAD, Fem
tests/test_*.py
README.md, LICENSE (MIT), .gitignore (resultados/, *.FCBak, __pycache__/)
```

Shared types (defined in the task that first needs them, listed here for consistency):

```python
@dataclass class Parametro: alias: str; valor: float; minimo: float; maximo: float; celula: str
@dataclass class Configuracao: parametros: list[Parametro]; tensao_limite: float | None;
    max_iteracoes: int; zona_exclusao_mm: float | None; excluir: dict[str, bool]
@dataclass class Modelo: doc; analise; solver; malha; material; corpo; fixacoes: list; forcas: list
@dataclass class MedidaTensao: max_filtrado: float; local_filtrado: tuple; max_bruto: float;
    local_bruto: tuple; max_na_zona: float; na_borda: bool
@dataclass class Iteracao: numero: int; valores: dict[str, float]; von_mises: float | None;
    von_mises_bruto: float | None; local: tuple | None; massa_kg: float | None; status: str; motivo: str
```

---

### Task 1: Scaffold + spreadsheet reading/writing

**Files:**
- Create: `.gitignore`, `LICENSE`, `otimizador/__init__.py`, `otimizador/planilha.py`, `tests/__init__.py`, `tests/test_planilha.py`

**Interfaces:**
- Produces: `Parametro`, `Configuracao` (above); `ler_configuracao(doc) -> Configuracao` (raises `ErroPlanilha(mensagem_pt)` if no sheet named/labelled `Parametros`); `aplicar_valores(doc, cfg: Configuracao, valores: dict[str, float]) -> None` (sets cells, no recompute); `valor_numerico(texto_ou_quantidade) -> float`.

- [ ] **Step 1:** `git init` in repo root; create `.gitignore`, `LICENSE` (MIT, 2026, author = repo owner), `tests/__init__.py` (append `FREECAD_BIN` or default bin and sibling `lib` to `sys.path`, `import FreeCAD, Fem`).
- [ ] **Step 2: Write failing tests** in `tests/test_planilha.py`, each building a fresh `App.newDocument()` with a `Spreadsheet::Sheet` named `Parametros`:

```python
def test_le_parametros_e_config(self):
    # B2 alias raio_canto=1, C2=1, D2=20; B3 alias espessura=30, C3 20, D3 45; B5 alias tensao_limite=250
    cfg = ler_configuracao(doc)
    self.assertEqual([p.alias for p in cfg.parametros], ["raio_canto", "espessura"])
    self.assertEqual((cfg.parametros[0].minimo, cfg.parametros[0].maximo), (1.0, 20.0))
    self.assertEqual(cfg.tensao_limite, 250.0); self.assertEqual(cfg.max_iteracoes, 30)
    self.assertIsNone(cfg.zona_exclusao_mm); self.assertEqual(cfg.excluir, {})
def test_excluir_por_cc(self):  # alias excluir_ConstraintFixed = 0 → cfg.excluir == {"ConstraintFixed": False}, not a parameter
def test_virgula_e_unidades(self):  # C2 "12,5", D2 "20 mm" → minimo 12.5, maximo 20.0
def test_sem_planilha(self):  # no sheet → ErroPlanilha with "Parametros" in message
def test_aplicar_valores(self):  # aplicar_valores(..., {"raio_canto": 7.5}); doc.recompute(); sheet.get("raio_canto") == 7.5
```

- [ ] **Step 3:** Run tests → FAIL (module missing).
- [ ] **Step 4:** Implement `otimizador/planilha.py`. Enumerate cells with `sheet.getUsedCells()` + `sheet.getAlias(cell)`; min/max from columns C/D of the alias's row via `sheet.getContents`. `valor_numerico` accepts float, `App.Units.Quantity` (use `.Value`), and strings (strip unit, comma→dot). Write values as plain `"%.6g"` strings.
- [ ] **Step 5:** Run tests → PASS.
- [ ] **Step 6:** Commit `feat: leitura da planilha Parametros`.

### Task 2: Example part `exemplos/L_part.FCStd`

**Files:**
- Create: `ferramentas/preparar_exemplo_L.py`, `exemplos/L_part.FCStd` (generated), `tests/test_exemplo_L.py`

**Interfaces:**
- Consumes: root `L_part.FCStd` (user's file: `Sketch` L profile, `Pad` 20 mm, `Analysis` with `ConstraintFixed` Face2, `ConstraintForce` Face12 5000 N −X, Steel-C10, Gmsh 5 mm 2nd order). Read-only.
- Produces: `exemplos/L_part.FCStd` with sheet `Parametros`: `raio_canto` 1 [1, 20], `espessura_vertical` 30 [20, 45], `espessura_horizontal` 30 [20, 45], `tensao_limite` 250, `max_iteracoes` 30. Old result objects removed.

- [ ] **Step 1: Write failing tests:**

```python
def test_planilha_do_exemplo(self):  # ler_configuracao → 3 params with bounds above, tensao_limite 250
def test_raio_no_canto_interno(self):  # Sketch has an arc (Part.ArcOfCircle) with radius 1 near (30,30) in sketch coords
def test_tamanho_externo_fixo(self):
    # set espessura_vertical=40, espessura_horizontal=25, raio_canto=10; recompute
    bb = doc.getObject("Body").Shape.BoundBox
    self.assertAlmostEqual(bb.XLength, 180, 3); self.assertAlmostEqual(bb.ZLength, 230, 3)
    self.assertTrue(doc.getObject("Body").Shape.isValid())
def test_sem_resultados_antigos(self):  # no Fem::FemResultObject in Analysis.Group
def test_original_intocado(self):  # sha256 of root L_part.FCStd unchanged by running the script
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `ferramentas/preparar_exemplo_L.py` (runnable with FreeCAD python, `--entrada`, `--saida`). Inner corner = intersection of sketch lines (30,230)-(30,30) and (30,30)-(180,30): use `Sketch.fillet(g1, g2, p1, p2, 1.0)`, then set the new arc's Radius constraint expression to `Parametros.raio_canto`. Find the leg-thickness constraints by type+value (DistanceX 30 → `espessura_vertical`, DistanceY 30 → `espessura_horizontal`; verify by changing and checking geometry, don't trust indices). Keep outer size: DistanceX 150 → `180 - Parametros.espessura_vertical`, DistanceY 200 → `230 - Parametros.espessura_horizontal`. Remove result objects (`Fem::FemResultObject`, `Fem::FemPostPipeline`, result meshes, `ccx_dat_file`). Generate the file and commit it.
- [ ] **Step 4:** Run → PASS (opening in the GUI is checked in Task 9).
- [ ] **Step 5:** Commit `feat: peça em L de exemplo preparada`.

### Task 3: Model discovery, mass, BC face signatures

**Files:**
- Create: `otimizador/modelo.py`, `otimizador/topologia.py`, `tests/test_modelo.py`, `tests/test_topologia.py`

**Interfaces:**
- Produces: `Modelo` (above); `encontrar_modelo(doc) -> Modelo` (raises `ErroModelo(mensagem_pt)`; `corpo = malha.Shape`); `massa_kg(modelo) -> float` (volume mm³ × `Density` converted with `App.Units.Quantity(...).getValueAs("kg/mm^3")`); `faces_cc(modelo) -> dict[str, list[Part.Face]]` keyed by constraint Name; `capturar_assinaturas(modelo) -> dict[str, list[AssinaturaFace]]`; `comparar_assinaturas(antes, depois, diagonal_mm: float) -> list[str]` (problem messages, empty = ok).
- `AssinaturaFace(subelemento: str, area: float, centro: tuple, normal: tuple)`.

- [ ] **Step 1: Failing tests** on a temp copy of `exemplos/L_part.FCStd`:

```python
def test_encontra_objetos(self): m = encontrar_modelo(doc); self.assertEqual([f.Name for f in m.fixacoes], ["ConstraintFixed"]); forcas == ["ConstraintForce"]
def test_massa(self): self.assertAlmostEqual(massa_kg(m), volume_mm3 * densidade, places=4)  # ~1.8 kg for steel
def test_assinatura_estavel(self):  # change espessura_vertical 30→40, recompute → comparar_assinaturas == []
def test_assinatura_detecta_troca(self):  # point ConstraintForce at another face (e.g. Face2) → non-empty list naming "ConstraintForce"
def test_face_inexistente(self):  # reference "Face99" → non-empty list, no exception
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Faces from `obj.Shape.getElement(sub)`. Match rule (my defaults): normal dot ≥ 0.99, centroid shift ≤ 0.25 × bbox diagonal, area ratio in [0.2, 5].
- [ ] **Step 4:** Run → PASS. **Step 5:** Commit `feat: descoberta do modelo e proteção de faces`.

### Task 4: FEA run + filtered stress

**Files:**
- Create: `otimizador/fea.py`, `otimizador/tensao.py`, `tests/test_tensao.py`, `tests/test_fea.py`

**Interfaces:**
- Produces: `rodar_fea(modelo, pasta_trabalho: str) -> object` (the new `Fem::FemResultObject`; raises `FalhaAvaliacao(motivo_pt)`); `medir_tensao(coords: list[tuple], vm: list[float], distancia: Callable[[tuple], float], zona_mm: float, tamanho_elemento: float, limite: float) -> MedidaTensao`; `distancia_faces(faces: list[Part.Face]) -> Callable[[tuple], float]`.

- [ ] **Step 1: Failing pure tests** (`test_tensao.py`, synthetic nodes, `distancia = lambda p: p[0]` meaning "distance to the BC face is x"):

```python
def test_ignora_pico_na_zona(self):  # nodes x=1 vm 900, x=50 vm 300; zona 10 → max_filtrado 300, max_bruto 900, max_na_zona 900
def test_borda_da_zona(self):  # filtered max at x=12, zona 10, elemento 5 → na_borda True; at x=40 → False
def test_sem_exclusao(self):  # distancia = lambda p: inf → max_filtrado == max_bruto, max_na_zona == 0
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `medir_tensao`: walk nodes in descending vm, compute distance lazily, stop at first node outside zone (do **not** compute distance for all ~20k nodes; `distToShape` is slow). `na_borda = dist < zona + tamanho_elemento`. `max_na_zona` = largest vm seen inside zone during the walk (0 if none).
- [ ] **Step 4: Failing integration test** (`test_fea.py`, copy of example): `r = rodar_fea(m, tmp)` → `200 < max(r.vonMises) < 1000`, exactly one `Fem::FemResultObject` in `m.analise.Group`, `len(r.NodeNumbers) == len(r.vonMises)`.
- [ ] **Step 5:** Implement `rodar_fea` (verified in spike):
  `GmshTools(malha).create_mesh()` (non-None return = error) → remove previous result objects from the analysis → `fea = ccxtools.FemToolsCcx(analise, solver)`; `fea.purge_results(); fea.update_objects(); fea.setup_working_dir(pasta); fea.setup_ccx()`; `msg = fea.check_prerequisites()` (non-empty = failure); `fea.write_inp_file(); fea.ccx_run(); fea.load_results()`. Wrap every failure in `FalhaAvaliacao` with a Portuguese reason (e.g. "Gmsh não conseguiu gerar a malha: ...").
- [ ] **Step 6:** Run all → PASS. **Step 7:** Commit `feat: análise FEA e medida de tensão filtrada`.

### Task 5: `--checar`

**Files:**
- Create: `otimizador/checagem.py`, `tests/test_checagem.py`

**Interfaces:**
- Consumes: `ler_configuracao`, `encontrar_modelo`.
- Produces: `Problema(nivel: Literal["erro","aviso"], mensagem: str)`; `checar(doc) -> list[Problema]`.

- [ ] **Step 1: Failing tests**, each mutating a copy of the example:

```python
def test_exemplo_ok(self): self.assertEqual([p for p in checar(doc) if p.nivel == "erro"], [])
def test_sem_forca(self):   # remove ConstraintForce → erro mentioning "força"
def test_duas_analises(self):  # add second Fem::FemAnalysis → erro mentioning "Analysis" names
def test_limites_invertidos(self):  # C2=20, D2=1 → erro naming "raio_canto"
def test_valor_fora_dos_limites(self):  # B2=50 → erro naming "raio_canto"
def test_parametro_sem_uso(self):  # add alias "fantasma" B9 with C9/D9 → erro "não é usado"
def test_sem_tensao_limite(self):  # clear alias → erro "tensao_limite"
def test_fillet_partdesign(self):  # add PartDesign::Fillet whose Radius expression uses Parametros.raio_canto → aviso
def test_recompute_falha(self):  # set espessura_vertical so sketch is impossible (e.g. 0) → erro
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement; "used" = alias appears (word boundary) in any `obj.ExpressionEngine` expression. Every message says how to fix (one sentence). **Step 4:** PASS. **Step 5:** Commit `feat: verificação da peça (--checar)`.

### Task 6: One evaluation

**Files:**
- Create: `otimizador/avaliacao.py`, `tests/test_avaliacao.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4.
- Produces: `Iteracao` (above); `class Avaliador: __init__(self, doc, cfg, modelo, pasta_trabalho: str)`; `avaliar(self, valores: dict[str, float]) -> Iteracao` (increments `numero`); attributes `assinaturas_base`, `zona_mm`, `tamanho_elemento`.

- [ ] **Step 1: Failing tests** (copy of example; slow, ~15 s each):

```python
def test_linha_de_base(self):  # avaliar(current values) → status in ("acima do limite","OK ✓","OK ⚠ verificar"), von_mises > 0, massa_kg > 0, numero == 1
def test_resultado_antigo_nao_reaproveitado(self):  # Review Focus 3: copy of ROOT L_part.FCStd (has old results, vm≈509) plus a Parametros sheet → after avaliar with espessura 40, von_mises != 508.84 and only one result object
def test_valor_impossivel_invalida(self):  # raio_canto 100 → status "inválida", motivo non-empty, no exception
def test_zona_padrao(self):  # zona_mm == 10.0 (2 × 5 mm)
def test_ok_verificar(self):  # with tensao_limite low enough that a peak inside the zone exceeds it but filtered max does not → "OK ⚠ verificar" (build case by setting tensao_limite between max_filtrado and max_na_zona from a first run)
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `avaliar`: `aplicar_valores` → `doc.recompute()` (any object in error state or invalid body shape → "inválida") → `comparar_assinaturas` (problems → "inválida", motivo joins them) → `rodar_fea` (`FalhaAvaliacao` → "inválida") → `medir_tensao` with faces of BCs whose `cfg.excluir.get(name, True)` → status: `max_filtrado > limite` → "acima do limite"; else `max_na_zona > limite or na_borda` → "OK ⚠ verificar"; else "OK ✓". `motivo` for ⚠ names the location.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: avaliação de uma iteração`.

### Task 7: Optimization loop (pure)

**Files:**
- Create: `otimizador/otimizacao.py`, `tests/test_otimizacao.py`

**Interfaces:**
- Consumes: `Iteracao`, `Configuracao`.
- Produces: `otimizar(avaliar: Callable[[dict], Iteracao], cfg: Configuracao, ao_iterar: Callable[[Iteracao, bool], None], deve_parar: Callable[[], bool]) -> tuple[Iteracao | None, list[Iteracao]]` (best, history; `ao_iterar(it, eh_melhor)`); `class ErroLinhaDeBase(Exception)`; `escolher_melhor(historico) -> Iteracao | None`.

- [ ] **Step 1: Failing tests** with a fake evaluator (no FreeCAD): mass = `a + b`, stress = `1000 / (a*b)`, bounds [1, 20], limite 10:

```python
def test_encontra_viavel_leve(self):  # best.status == "OK ✓", best.von_mises <= 10, best.massa_kg < 40 (start at a=b=20 mass 40)
def test_respeita_limites(self):  # every avaliar call receives values within [1, 20]
def test_max_iteracoes(self):  # cfg.max_iteracoes=5 → len(history) <= 5 (baseline counts)
def test_parada_pedida(self):  # deve_parar returns True after 3 calls → stops, best returned
def test_nenhum_viavel(self):  # limite 0.1 → best is min von_mises, status "acima do limite"
def test_prefere_ok_limpo(self):  # escolher_melhor([OK⚠ massa 1, OK✓ massa 2]) → the OK✓
def test_inválida_nao_quebra(self):  # fake returns "inválida" for a>18 → loop completes
def test_linha_de_base_ja_viavel(self):  # limite 1e6 → finishes, best.status "OK ✓", best.massa_kg <= baseline.massa_kg
def test_linha_de_base_invalida(self):  # baseline "inválida" → raises ErroLinhaDeBase(motivo) before any other evaluation
def test_tres_invalidas_seguidas(self):  # 3 consecutive "inválida" after baseline → stops; history ends with them; returns best so far
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement: first call = baseline (current values). Normalize params to [0,1]; `scipy.optimize.minimize(method="COBYLA", bounds=[(0,1)]*n, constraints=[{"type":"ineq","fun": g}], options={"maxiter": cfg.max_iteracoes - 1, "rhobeg": 0.25})`, objective = mass, `g = (limite - vm)/limite`. Cache evaluations by rounded x (objective and constraint share one FEA). Invalid point: objective = largest mass seen, `g = -1`. Clip x to [0,1] before denormalizing. Stop via internal exception when `deve_parar()` or evaluation count reaches `max_iteracoes`. Baseline invalid → `ErroLinhaDeBase` (executar turns it into code 1 with the reason, e.g. faces trocadas). 3 consecutive invalid → stop, log explains. Best: min mass among "OK ✓"; else among "OK ⚠ verificar"; else min von_mises among valid.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: laço de otimização COBYLA`.

### Task 8: Outputs

**Files:**
- Create: `otimizador/saidas.py`, `tests/test_saidas.py`

**Interfaces:**
- Produces: `class Historico: __init__(self, caminho_csv, aliases: list[str]); adicionar(self, it: Iteracao) -> None` (flushes each row); `linha_terminal(it, aliases, eh_melhor: bool) -> str`; `cabecalho_terminal(aliases) -> str`; `gerar_grafico(historico: list[Iteracao], limite: float, caminho_png) -> None`; `resumo(base: Iteracao, melhor: Iteracao | None, limite: float) -> str`.

- [ ] **Step 1: Failing tests:** CSV header = `iteracao,<aliases...>,von_mises_mpa,von_mises_bruto_mpa,local_max,massa_kg,status,motivo` (UTF-8 with BOM so Excel shows ✓); `linha_terminal` contains `"509 MPa"`, `"1.79 kg"`, `"acima do limite"`, and `"✓ melhor até agora"` when `eh_melhor`; `gerar_grafico` creates a non-empty PNG (matplotlib `Agg`); `resumo` mentions "atingiu" vs "não atingiu" the limit and the % mass change vs. baseline.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: histórico, gráfico e resumo`.

### Task 9: Orchestration, live GUI, launcher

**Files:**
- Create: `otimizador/trabalho.py`, `otimizador/executar.py`, `otimizador/gui.py`, `otimizador/_iniciar.py`, `otimizar.py`, `tests/test_ponta_a_ponta.py`, `tests/test_lancador.py`

**Interfaces:**
- `trabalho.py` (stdlib): `Trabalho(modo: "otimizar"|"checar", entrada: str, pasta: str, gui: bool, fechar_ao_terminar: bool, repo: str)`; `salvar(t, caminho)`, `carregar(caminho) -> Trabalho`. Env var `OTIMIZADOR_TRABALHO` = job path.
- Log protocol: FreeCAD side appends human lines to `<pasta>/log.txt`, last line `### FIM codigo=<n>`. Codes: 0 = limit reached / checar without errors; 2 = finished without reaching the limit; 1 = fatal error / checar with errors. Stop request = file `<pasta>/parar`.
- `executar.main()`: reads job; copies input to `<pasta>/trabalho/<peca>.FCStd`, opens it; checar (errors → code 1) ; prints baseline; runs `otimizar`; on each new best: `doc.save()` then copy to `<pasta>/<peca>_otimizada.FCStd`; writes `historico.csv`, `grafico.png`, `resumo`; in GUI mode calls `gui.mostrar(doc, resultado)` after each evaluation and opens the best file at the end; closes the main window only if `fechar_ao_terminar`.
- `gui.mostrar(doc, resultado_obj)`: hide other objects, show result mesh, `ViewObject.setNodeColorByScalars(list(r.NodeNumbers), list(r.vonMises))`, `Gui.updateGui()` (verified in spike). Also `App.Console.PrintMessage` each terminal line (Report View).
- `otimizar.py`: `python otimizar.py <peca.FCStd> [--sem-interface] [--checar] [--freecad PASTA] [--resultados PASTA]` (+ hidden `--fechar-ao-terminar` for tests). Results default `resultados/<peca>_<AAAAMMDD-HHMMSS>/` next to the repo; `--checar` uses a temp dir. Starts `freecad.exe _iniciar.py` (GUI) or `freecadcmd.exe -c "exec(open(r'..._iniciar.py').read())"`, tails `log.txt` to stdout until process exit, returns the `### FIM` code (missing → message "O FreeCAD foi fechado antes do fim; o melhor resultado até agora está em ..." and code 1). Ctrl+C → creates `parar` file and keeps tailing.

- [ ] **Step 1: Failing launcher tests** (`test_lancador.py`, stdlib only, no FreeCAD launch): `--freecad C:\nao\existe` → exit 1, output contains `"--freecad"`; missing input file → exit 1 with Portuguese message; FIM parsing returns 0/2/1.
- [ ] **Step 2: Failing end-to-end tests** (`test_ponta_a_ponta.py`, run `otimizar.py` via subprocess with system/FreeCAD python, input = copy of example inside temp dir `pasta com espaço ç`, sheet `max_iteracoes` set to 6):

```python
def test_sem_interface(self):  # exit code in (0, 2); <pasta>/L_part_otimizada.FCStd, historico.csv (7 lines incl. header), grafico.png exist
    # best row von_mises < baseline row von_mises; every param in its bounds; input file sha256 unchanged
def test_checar_ok(self):  # --checar on example → exit 0, output contains "pronta"
def test_checar_erro(self):  # --checar on root L_part.FCStd (no sheet) → exit 1, output contains "Parametros"
def test_parar(self):  # create <pasta>/parar before start via --resultados → finishes after baseline with code in (0,2), best file exists
def test_gui_fumaca(self):  # GUI mode + --fechar-ao-terminar, max_iteracoes 2 → exit code in (0,2), log has 2 iteration lines
```

- [ ] **Step 3:** Run → FAIL. **Step 4:** Implement. **Step 5:** Run all tests → PASS.
- [ ] **Step 6: Manual check** — run `python otimizar.py exemplos\L_part.FCStd`: FreeCAD opens, part recolors each iteration, terminal shows the table, final summary printed, best part open at the end. Report what you saw (screenshot via `saveImage` into the results folder is fine).
- [ ] **Step 7:** Commit `feat: execução completa, modo ao vivo e lançador`.

### Task 10: README + tutorial

**Files:**
- Create: `README.md`, `docs/imagens/*.png` (screenshots captured with `Gui.activeDocument().activeView().saveImage` from the example where possible)

- [ ] **Step 1:** Write `README.md` (Portuguese): o que é; requisitos (Windows, FreeCAD 1.1); rodar o exemplo (`python otimizar.py exemplos\L_part.FCStd`, `--sem-interface`, `--checar`); saídas; **tutorial passo a passo** para uma peça nova: criar Analysis/material/fixação/força/malha/solver na bancada FEM; criar planilha `Parametros` (layout B/C/D, aliases, `tensao_limite`, `max_iteracoes`, `zona_exclusao_mm`, `excluir_<Nome>`); ligar cotas com f(x) (`Parametros.raio_canto`); raio de canto via fillet do Sketcher (não PartDesign Fillet) e por quê; por que canto vivo não tem tensão "verdadeira"; o que são as zonas de exclusão e o status "OK ⚠ verificar"; como abrir resultados no PrePoMax opcionalmente; como rodar os testes. Where a screenshot can't be generated, insert `> 📷 TODO: print de <o quê>`.
- [ ] **Step 2: Verify:** every command in the README runs as written on this machine; every alias mentioned matches Task 1 constants.
- [ ] **Step 3:** Commit `docs: README e tutorial`.
