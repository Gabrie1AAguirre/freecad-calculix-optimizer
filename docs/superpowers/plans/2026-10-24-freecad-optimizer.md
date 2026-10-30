# FreeCAD + CalculiX shape optimizer — Implementation Plan

> Historical plan, already implemented. Translated to English on 2026-10-29 with the
> identifiers renamed to the current English names; the original commits are in Portuguese.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A generic Python tool, launched from the VS Code terminal, that takes any FreeCAD part prepared with an FEM analysis and a `Parameters` spreadsheet and finds the lightest variant whose Von Mises stays under a limit, showing progress live in the FreeCAD window.

**Architecture:** A stdlib-only launcher (`optimize.py`, system Python) finds FreeCAD, writes a job JSON, starts `freecad.exe` (live) or `freecadcmd.exe` (headless/check), and streams the run's `log.txt` to the terminal. Inside FreeCAD, the package `optimizer/` reads the spreadsheet, applies values, recomputes, guards boundary-condition faces, meshes (Gmsh), solves (CalculiX via `femtools.ccxtools`), measures filtered Von Mises and mass, and drives scipy COBYLA. Outputs go to `results/<part>_<date-time>/`.

**Tech Stack:** FreeCAD 1.1.4 (bundled Python 3.11, numpy 1.26, scipy 1.16, matplotlib 3.10, Gmsh, CalculiX), stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-24-freecad-optimizer-design.md`

## Global Constraints

- Windows + FreeCAD 1.1; default install `C:\Program Files\FreeCAD 1.1\bin`, overridable by `--freecad <folder>` and env `FREECAD_BIN`.
- No extra dependencies: launcher = stdlib only; package = stdlib + numpy/scipy/matplotlib bundled with FreeCAD. **No pytest** (not bundled) — tests use `unittest`.
- Test command (from repo root, PowerShell): `& "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests -t . -v`
- Run scripts in freecadcmd with `freecadcmd.exe -c "exec(open(r'<path>').read())"` — positional script path did not execute in tests.
- Never name a module after a stdlib module (`inspect.py` shadowed stdlib and broke FreeCAD during the spike).
- Spreadsheet name `Parameters`; reserved aliases: `stress_limit` (MPa, required), `max_iterations` (default 30, later changed to 20), `exclusion_zone_mm` (default 2 × mesh `CharacteristicLengthMax`; if that is 0, bbox diagonal / 20), `exclude_<ConstraintObjectName>` (0/1, default 1).
- Parameter rows: column B = value cell with alias, column C = min, column D = max (same row). Any alias in column B that is not reserved is a parameter.
- Exact status strings: `"OK ✓"`, `"OK ⚠ check"`, `"above limit"`, `"invalid"`.
- The input `.FCStd` is never modified; work on a copy inside the results folder.
- Objective: minimize mass s.t. filtered `VonMises_max ≤ stress_limit`, params in [min, max].
- Launcher reconfigures stdout to UTF-8 (`errors="replace"`) so ✓/⚠ never crash the terminal.

## Review Focus

1. Spreadsheet values typed with a decimal comma (`12,5`) or with units (`20 mm`) → read as 12.5 / 20.0 mm, not crash. Test in Task 1.
2. Paths with spaces and accents (the user's folder is `vscode scripts`) → whole pipeline works. Test in Task 9 (temp dir named `folder with space ç`).
3. Input file already containing old FEM results (the user's `L_part.FCStd` does) → stale results never read as the new iteration's. Test in Task 6.
4. Document with two `Fem::FemAnalysis` objects, or none → `--check` says which. Test in Task 5.
5. FreeCAD not found at default path → clear message naming `--freecad`, exit code 1. Test in Task 9.

## File Structure

```
optimize.py                      launcher (system Python, stdlib only)
optimizer/__init__.py
optimizer/job.py                 job JSON (shared by launcher & FreeCAD side; stdlib only)
optimizer/spreadsheet.py         read Parameters, apply values
optimizer/model.py               discover analysis objects, mass
optimizer/face_tracking.py       BC face signatures + comparison
optimizer/fea.py                 mesh + CalculiX run
optimizer/stress.py              filtered stress measure (pure)
optimizer/check.py               --check problems
optimizer/evaluation.py          one evaluation → Iteration
optimizer/optimization.py        COBYLA loop, best selection (pure)
optimizer/outputs.py             CSV, terminal line, plot, summary
optimizer/gui.py                 live view (FreeCADGui only)
optimizer/run.py                 entry point inside FreeCAD
optimizer/_start.py              bootstrap passed to freecad.exe / freecadcmd
tools/prepare_L_example.py       builds examples/L_part.FCStd from L_part.FCStd
examples/L_part.FCStd
tests/__init__.py                adds FreeCAD bin/lib to sys.path, imports FreeCAD, Fem
tests/test_*.py
README.md, LICENSE (MIT), .gitignore (results/, *.FCBak, __pycache__/)
```

Shared types (defined in the task that first needs them, listed here for consistency):

```python
@dataclass class Parameter: alias: str; value: float; minimum: float; maximum: float; cell: str
@dataclass class Settings: parameters: list[Parameter]; stress_limit: float | None;
    max_iterations: int; exclusion_zone_mm: float | None; exclude: dict[str, bool]
@dataclass class Model: doc; analysis; solver; mesh; material; body; fixtures: list; forces: list
@dataclass class StressMeasure: filtered_max: float; filtered_location: tuple; raw_max: float;
    raw_location: tuple; max_in_zone: float; at_edge: bool
@dataclass class Iteration: number: int; values: dict[str, float]; von_mises: float | None;
    von_mises_raw: float | None; location: tuple | None; mass_kg: float | None; status: str; reason: str
```

---

### Task 1: Scaffold + spreadsheet reading/writing

**Files:**
- Create: `.gitignore`, `LICENSE`, `optimizer/__init__.py`, `optimizer/spreadsheet.py`, `tests/__init__.py`, `tests/test_spreadsheet.py`

**Interfaces:**
- Produces: `Parameter`, `Settings` (above); `read_settings(doc) -> Settings` (raises `SpreadsheetError(message)` if no sheet named/labelled `Parameters`); `apply_values(doc, settings: Settings, values: dict[str, float]) -> None` (sets cells, no recompute); `numeric_value(text_or_quantity) -> float`.

- [ ] **Step 1:** `git init` in repo root; create `.gitignore`, `LICENSE` (MIT, 2026, author = repo owner), `tests/__init__.py` (append `FREECAD_BIN` or default bin and sibling `lib` to `sys.path`, `import FreeCAD, Fem`).
- [ ] **Step 2: Write failing tests** in `tests/test_spreadsheet.py`, each building a fresh `App.newDocument()` with a `Spreadsheet::Sheet` named `Parameters`:

```python
def test_reads_parameters_and_settings(self):
    # B2 alias corner_radius=1, C2=1, D2=20; B3 alias thickness=30, C3 20, D3 45; B5 alias stress_limit=250
    settings = read_settings(doc)
    self.assertEqual([p.alias for p in settings.parameters], ["corner_radius", "thickness"])
    self.assertEqual((settings.parameters[0].minimum, settings.parameters[0].maximum), (1.0, 20.0))
    self.assertEqual(settings.stress_limit, 250.0); self.assertEqual(settings.max_iterations, 30)
    self.assertIsNone(settings.exclusion_zone_mm); self.assertEqual(settings.exclude, {})
def test_exclude_per_constraint(self):  # alias exclude_ConstraintFixed = 0 → settings.exclude == {"ConstraintFixed": False}, not a parameter
def test_comma_and_units(self):  # C2 "12,5", D2 "20 mm" → minimum 12.5, maximum 20.0
def test_no_sheet(self):  # no sheet → SpreadsheetError with "Parameters" in message
def test_apply_values(self):  # apply_values(..., {"corner_radius": 7.5}); doc.recompute(); sheet.get("corner_radius") == 7.5
```

- [ ] **Step 3:** Run tests → FAIL (module missing).
- [ ] **Step 4:** Implement `optimizer/spreadsheet.py`. Enumerate cells with `sheet.getUsedCells()` + `sheet.getAlias(cell)`; min/max from columns C/D of the alias's row via `sheet.getContents`. `numeric_value` accepts float, `App.Units.Quantity` (use `.Value`), and strings (strip unit, comma→dot). Write values as plain `"%.6g"` strings.
- [ ] **Step 5:** Run tests → PASS.
- [ ] **Step 6:** Commit `feat: read the Parameters spreadsheet`.

### Task 2: Example part `examples/L_part.FCStd`

**Files:**
- Create: `tools/prepare_L_example.py`, `examples/L_part.FCStd` (generated), `tests/test_L_example.py`

**Interfaces:**
- Consumes: root `L_part.FCStd` (user's file: `Sketch` L profile, `Pad` 20 mm, `Analysis` with `ConstraintFixed` Face2, `ConstraintForce` Face12 5000 N −X, Steel-C10, Gmsh 5 mm 2nd order). Read-only.
- Produces: `examples/L_part.FCStd` with sheet `Parameters`: `corner_radius` 1 [1, 20], `vertical_thickness` 30 [20, 45], `horizontal_thickness` 30 [20, 45], `stress_limit` 250, `max_iterations` 30. Old result objects removed.

- [ ] **Step 1: Write failing tests:**

```python
def test_example_spreadsheet(self):  # read_settings → 3 params with bounds above, stress_limit 250
def test_radius_at_inner_corner(self):  # Sketch has an arc (Part.ArcOfCircle) with radius 1 near (30,30) in sketch coords
def test_outer_size_fixed(self):
    # set vertical_thickness=40, horizontal_thickness=25, corner_radius=10; recompute
    bb = doc.getObject("Body").Shape.BoundBox
    self.assertAlmostEqual(bb.XLength, 180, 3); self.assertAlmostEqual(bb.ZLength, 230, 3)
    self.assertTrue(doc.getObject("Body").Shape.isValid())
def test_no_old_results(self):  # no Fem::FemResultObject in Analysis.Group
def test_original_untouched(self):  # sha256 of root L_part.FCStd unchanged by running the script
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `tools/prepare_L_example.py` (runnable with FreeCAD python, `--input`, `--output`). Inner corner = intersection of sketch lines (30,230)-(30,30) and (30,30)-(180,30): use `Sketch.fillet(g1, g2, p1, p2, 1.0)`, then set the new arc's Radius constraint expression to `Parameters.corner_radius`. Find the leg-thickness constraints by type+value (DistanceX 30 → `vertical_thickness`, DistanceY 30 → `horizontal_thickness`; verify by changing and checking geometry, don't trust indices). Keep outer size: DistanceX 150 → `180 - Parameters.vertical_thickness`, DistanceY 200 → `230 - Parameters.horizontal_thickness`. Remove result objects (`Fem::FemResultObject`, `Fem::FemPostPipeline`, result meshes, `ccx_dat_file`). Generate the file and commit it.
- [ ] **Step 4:** Run → PASS (opening in the GUI is checked in Task 9).
- [ ] **Step 5:** Commit `feat: prepared L example part`.

### Task 3: Model discovery, mass, BC face signatures

**Files:**
- Create: `optimizer/model.py`, `optimizer/face_tracking.py`, `tests/test_model.py`, `tests/test_face_tracking.py`

**Interfaces:**
- Produces: `Model` (above); `find_model(doc) -> Model` (raises `ModelError(message)`; `body = mesh.Shape`); `mass_kg(model) -> float` (volume mm³ × `Density` converted with `App.Units.Quantity(...).getValueAs("kg/mm^3")`); `constraint_faces(model) -> dict[str, list[Part.Face]]` keyed by constraint Name; `capture_signatures(model) -> dict[str, list[FaceSignature]]`; `compare_signatures(before, after, diagonal_mm: float) -> list[str]` (problem messages, empty = ok).
- `FaceSignature(subelement: str, area: float, center: tuple, normal: tuple)`.

- [ ] **Step 1: Failing tests** on a temp copy of `examples/L_part.FCStd`:

```python
def test_finds_objects(self): m = find_model(doc); self.assertEqual([f.Name for f in m.fixtures], ["ConstraintFixed"]); forces == ["ConstraintForce"]
def test_mass(self): self.assertAlmostEqual(mass_kg(m), volume_mm3 * density, places=4)  # ~1.8 kg for steel
def test_stable_signature(self):  # change vertical_thickness 30→40, recompute → compare_signatures == []
def test_signature_detects_swap(self):  # point ConstraintForce at another face (e.g. Face2) → non-empty list naming "ConstraintForce"
def test_missing_face(self):  # reference "Face99" → non-empty list, no exception
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Faces from `obj.Shape.getElement(sub)`. Match rule (my defaults): normal dot ≥ 0.99, centroid shift ≤ 0.25 × bbox diagonal, area ratio in [0.2, 5].
- [ ] **Step 4:** Run → PASS. **Step 5:** Commit `feat: model discovery and face protection`.

### Task 4: FEA run + filtered stress

**Files:**
- Create: `optimizer/fea.py`, `optimizer/stress.py`, `tests/test_stress.py`, `tests/test_fea.py`

**Interfaces:**
- Produces: `run_fea(model, work_folder: str) -> object` (the new `Fem::FemResultObject`; raises `EvaluationFailed(reason)`); `measure_stress(coords: list[tuple], vm: list[float], distance: Callable[[tuple], float], zone_mm: float, element_size: float, limit: float) -> StressMeasure`; `face_distance(faces: list[Part.Face]) -> Callable[[tuple], float]`.

- [ ] **Step 1: Failing pure tests** (`test_stress.py`, synthetic nodes, `distance = lambda p: p[0]` meaning "distance to the BC face is x"):

```python
def test_ignores_peak_in_zone(self):  # nodes x=1 vm 900, x=50 vm 300; zone 10 → filtered_max 300, raw_max 900, max_in_zone 900
def test_zone_edge(self):  # filtered max at x=12, zone 10, element 5 → at_edge True; at x=40 → False
def test_no_exclusion(self):  # distance = lambda p: inf → filtered_max == raw_max, max_in_zone == 0
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `measure_stress`: walk nodes in descending vm, compute distance lazily, stop at first node outside zone (do **not** compute distance for all ~20k nodes; `distToShape` is slow). `at_edge = dist < zone + element_size`. `max_in_zone` = largest vm seen inside zone during the walk (0 if none).
- [ ] **Step 4: Failing integration test** (`test_fea.py`, copy of example): `r = run_fea(m, tmp)` → `200 < max(r.vonMises) < 1000`, exactly one `Fem::FemResultObject` in `m.analysis.Group`, `len(r.NodeNumbers) == len(r.vonMises)`.
- [ ] **Step 5:** Implement `run_fea` (verified in spike):
  `GmshTools(mesh).create_mesh()` (non-None return = error) → remove previous result objects from the analysis → `fea = ccxtools.FemToolsCcx(analysis, solver)`; `fea.purge_results(); fea.update_objects(); fea.setup_working_dir(folder); fea.setup_ccx()`; `msg = fea.check_prerequisites()` (non-empty = failure); `fea.write_inp_file(); fea.ccx_run(); fea.load_results()`. Wrap every failure in `EvaluationFailed` with a reason (e.g. "Gmsh could not generate the mesh: ...").
- [ ] **Step 6:** Run all → PASS. **Step 7:** Commit `feat: FEA run and filtered stress measure`.

### Task 5: `--check`

**Files:**
- Create: `optimizer/check.py`, `tests/test_check.py`

**Interfaces:**
- Consumes: `read_settings`, `find_model`.
- Produces: `Problem(level: Literal["error","warning"], message: str)`; `check(doc) -> list[Problem]`.

- [ ] **Step 1: Failing tests**, each mutating a copy of the example:

```python
def test_example_ok(self): self.assertEqual([p for p in check(doc) if p.level == "error"], [])
def test_no_force(self):   # remove ConstraintForce → error mentioning "force"
def test_two_analyses(self):  # add second Fem::FemAnalysis → error mentioning "Analysis" names
def test_inverted_limits(self):  # C2=20, D2=1 → error naming "corner_radius"
def test_value_outside_limits(self):  # B2=50 → error naming "corner_radius"
def test_unused_parameter(self):  # add alias "ghost" B9 with C9/D9 → error "not used"
def test_no_stress_limit(self):  # clear alias → error "stress_limit"
def test_partdesign_fillet(self):  # add PartDesign::Fillet whose Radius expression uses Parameters.corner_radius → warning
def test_recompute_fails(self):  # set vertical_thickness so the sketch is impossible (e.g. 0) → error
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement; "used" = alias appears (word boundary) in any `obj.ExpressionEngine` expression. Every message says how to fix (one sentence). **Step 4:** PASS. **Step 5:** Commit `feat: part check (--check)`.

### Task 6: One evaluation

**Files:**
- Create: `optimizer/evaluation.py`, `tests/test_evaluation.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4.
- Produces: `Iteration` (above); `class Evaluator: __init__(self, doc, settings, model, work_folder: str)`; `evaluate(self, values: dict[str, float]) -> Iteration` (increments `number`); attributes `base_signatures`, `zone_mm`, `element_size`.

- [ ] **Step 1: Failing tests** (copy of example; slow, ~15 s each):

```python
def test_baseline(self):  # evaluate(current values) → status in ("above limit","OK ✓","OK ⚠ check"), von_mises > 0, mass_kg > 0, number == 1
def test_old_result_not_reused(self):  # Review Focus 3: copy of ROOT L_part.FCStd (has old results, vm≈509) plus a Parameters sheet → after evaluate with thickness 40, von_mises != 508.84 and only one result object
def test_impossible_value_is_invalid(self):  # corner_radius 100 → status "invalid", reason non-empty, no exception
def test_default_zone(self):  # zone_mm == 10.0 (2 × 5 mm)
def test_ok_check(self):  # with stress_limit low enough that a peak inside the zone exceeds it but filtered max does not → "OK ⚠ check" (build case by setting stress_limit between filtered_max and max_in_zone from a first run)
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `evaluate`: `apply_values` → `doc.recompute()` (any object in error state or invalid body shape → "invalid") → `compare_signatures` (problems → "invalid", reason joins them) → `run_fea` (`EvaluationFailed` → "invalid") → `measure_stress` with faces of BCs whose `settings.exclude.get(name, True)` → status: `filtered_max > limit` → "above limit"; else `max_in_zone > limit or at_edge` → "OK ⚠ check"; else "OK ✓". `reason` for ⚠ names the location.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: evaluation of one iteration`.

### Task 7: Optimization loop (pure)

**Files:**
- Create: `optimizer/optimization.py`, `tests/test_optimization.py`

**Interfaces:**
- Consumes: `Iteration`, `Settings`.
- Produces: `optimize(evaluate: Callable[[dict], Iteration], settings: Settings, on_iteration: Callable[[Iteration, bool], None], should_stop: Callable[[], bool]) -> tuple[Iteration | None, list[Iteration]]` (best, history; `on_iteration(it, is_best)`); `class BaselineError(Exception)`; `choose_best(history) -> Iteration | None`.

- [ ] **Step 1: Failing tests** with a fake evaluator (no FreeCAD): mass = `a + b`, stress = `1000 / (a*b)`, bounds [1, 20], limit 10:

```python
def test_finds_light_feasible(self):  # best.status == "OK ✓", best.von_mises <= 10, best.mass_kg < 40 (start at a=b=20 mass 40)
def test_respects_limits(self):  # every evaluate call receives values within [1, 20]
def test_max_iterations(self):  # settings.max_iterations=5 → len(history) <= 5 (baseline counts)
def test_stop_requested(self):  # should_stop returns True after 3 calls → stops, best returned
def test_none_feasible(self):  # limit 0.1 → best is min von_mises, status "above limit"
def test_prefers_clean_ok(self):  # choose_best([OK⚠ mass 1, OK✓ mass 2]) → the OK✓
def test_invalid_does_not_break(self):  # fake returns "invalid" for a>18 → loop completes
def test_baseline_already_feasible(self):  # limit 1e6 → finishes, best.status "OK ✓", best.mass_kg <= baseline.mass_kg
def test_invalid_baseline(self):  # baseline "invalid" → raises BaselineError(reason) before any other evaluation
def test_three_invalid_in_a_row(self):  # 3 consecutive "invalid" after baseline → stops; history ends with them; returns best so far
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement: first call = baseline (current values). Normalize params to [0,1]; `scipy.optimize.minimize(method="COBYLA", bounds=[(0,1)]*n, constraints=[{"type":"ineq","fun": g}], options={"maxiter": settings.max_iterations - 1, "rhobeg": 0.25})`, objective = mass, `g = (limit - vm)/limit`. Cache evaluations by rounded x (objective and constraint share one FEA). Invalid point: objective = largest mass seen, `g = -1`. Clip x to [0,1] before denormalizing. Stop via internal exception when `should_stop()` or evaluation count reaches `max_iterations`. Baseline invalid → `BaselineError` (run turns it into code 1 with the reason, e.g. swapped faces). 3 consecutive invalid → stop, log explains. Best: min mass among "OK ✓"; else among "OK ⚠ check"; else min von_mises among valid.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: COBYLA optimization loop`.

### Task 8: Outputs

**Files:**
- Create: `optimizer/outputs.py`, `tests/test_outputs.py`

**Interfaces:**
- Produces: `class History: __init__(self, csv_path, aliases: list[str]); add(self, it: Iteration) -> None` (flushes each row); `terminal_line(it, aliases, is_best: bool) -> str`; `terminal_header(aliases) -> str`; `make_chart(history: list[Iteration], limit: float, png_path) -> None`; `summary(base: Iteration, best: Iteration | None, limit: float) -> str`.

- [ ] **Step 1: Failing tests:** CSV header = `iteration,<aliases...>,von_mises_mpa,von_mises_raw_mpa,max_location,mass_kg,status,reason` (UTF-8 with BOM so Excel shows ✓); `terminal_line` contains `"509 MPa"`, `"1.79 kg"`, `"above limit"`, and `"✓ best so far"` when `is_best`; `make_chart` creates a non-empty PNG (matplotlib `Agg`); `summary` says whether the limit was "reached" or "did not reach" it and the % mass change vs. baseline.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: history, chart and summary`.

### Task 9: Orchestration, live GUI, launcher

**Files:**
- Create: `optimizer/job.py`, `optimizer/run.py`, `optimizer/gui.py`, `optimizer/_start.py`, `optimize.py`, `tests/test_end_to_end.py`, `tests/test_launcher.py`

**Interfaces:**
- `job.py` (stdlib): `Job(mode: "optimize"|"check", input: str, folder: str, gui: bool, close_when_done: bool, repo: str)`; `save(job, path)`, `load(path) -> Job`. Env var `OPTIMIZER_JOB` = job path.
- Log protocol: FreeCAD side appends human lines to `<folder>/log.txt`, last line `### END code=<n>`. Codes: 0 = limit reached / check without errors; 2 = finished without reaching the limit; 1 = fatal error / check with errors. Stop request = file `<folder>/stop`.
- `run.start()`: reads job; copies input to `<folder>/work/<part>.FCStd`, opens it; check (errors → code 1); prints baseline; runs `optimize`; on each new best: save a copy to `<folder>/<part>_optimized.FCStd`; writes `history.csv`, `chart.png`, `summary`; in GUI mode calls `gui.show(doc, result)` after each evaluation and opens the best file at the end; closes the main window only if `close_when_done`.
- `gui.show(doc, result_obj)`: hide other objects, show result mesh, `ViewObject.setNodeColorByScalars(list(r.NodeNumbers), list(r.vonMises))`, `Gui.updateGui()` (verified in spike). Also `App.Console.PrintMessage` each terminal line (Report View).
- `optimize.py`: `python optimize.py <part.FCStd> [--headless] [--check] [--freecad FOLDER] [--results FOLDER]` (+ hidden `--close-when-done` for tests). Results default `results/<part>_<YYYYMMDD-HHMMSS>/` next to the repo; `--check` uses a temp dir. Starts `freecad.exe _start.py` (GUI) or `freecadcmd.exe -c "exec(open(r'..._start.py').read())"`, tails `log.txt` to stdout until process exit, returns the `### END` code (missing → message "FreeCAD was closed before the end; the best result so far is in ..." and code 1). Ctrl+C → creates `stop` file and keeps tailing.

- [ ] **Step 1: Failing launcher tests** (`test_launcher.py`, stdlib only, no FreeCAD launch): `--freecad C:\does\not\exist` → exit 1, output contains `"--freecad"`; missing input file → exit 1 with a clear message; END parsing returns 0/2/1.
- [ ] **Step 2: Failing end-to-end tests** (`test_end_to_end.py`, run `optimize.py` via subprocess with system/FreeCAD python, input = copy of example inside temp dir `folder with space ç`, sheet `max_iterations` set to 6):

```python
def test_headless(self):  # exit code in (0, 2); <folder>/L_part_optimized.FCStd, history.csv (7 lines incl. header), chart.png exist
    # best row von_mises < baseline row von_mises; every param in its bounds; input file sha256 unchanged
def test_check_ok(self):  # --check on example → exit 0, output contains "ready"
def test_check_error(self):  # --check on root L_part.FCStd (no sheet) → exit 1, output contains "Parameters"
def test_stop(self):  # create <folder>/stop before start via --results → finishes after baseline with code in (0,2), best file exists
def test_gui_smoke(self):  # GUI mode + --close-when-done, max_iterations 2 → exit code in (0,2), log has 2 iteration lines
```

- [ ] **Step 3:** Run → FAIL. **Step 4:** Implement. **Step 5:** Run all tests → PASS.
- [ ] **Step 6: Manual check** — run `python optimize.py examples\L_part.FCStd`: FreeCAD opens, part recolors each iteration, terminal shows the table, final summary printed, best part open at the end. Report what you saw (screenshot via `saveImage` into the results folder is fine).
- [ ] **Step 7:** Commit `feat: full run, live mode and launcher`.

### Task 10: README + tutorial

**Files:**
- Create: `README.md`, `docs/images/*.png` (screenshots captured with `Gui.activeDocument().activeView().saveImage` from the example where possible)

- [ ] **Step 1:** Write `README.md`: what it is; requirements (Windows, FreeCAD 1.1); running the example (`python optimize.py examples\L_part.FCStd`, `--headless`, `--check`); outputs; **step-by-step tutorial** for a new part: create Analysis/material/fixed constraint/force/mesh/solver in the FEM workbench; create the `Parameters` spreadsheet (B/C/D layout, aliases, `stress_limit`, `max_iterations`, `exclusion_zone_mm`, `exclude_<Name>`); link dimensions with f(x) (`Parameters.corner_radius`); corner radius via the Sketcher fillet (not the PartDesign Fillet) and why; why a sharp corner has no "true" stress; what the exclusion zones and the "OK ⚠ check" status are; how to open results in PrePoMax optionally; how to run the tests. Where a screenshot can't be generated, insert `> 📷 TODO: screenshot of <what>`.
- [ ] **Step 2: Verify:** every command in the README runs as written on this machine; every alias mentioned matches Task 1 constants.
- [ ] **Step 3:** Commit `docs: README and tutorial`.
