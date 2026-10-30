# FreeCAD + CalculiX shape optimizer — Design

Date: 2026-10-24
Status: approved and implemented (translated to English on 2026-10-29, with the
identifiers renamed to the current English names; see "Later changes" at the end).

## 1. Intent and why

The user models parts in FreeCAD and wants a tool that **reduces their Von Mises
stress** automatically and iteratively, without depending on an LLM or on manual work at
every round. The tool must:

- work with **any part**, not just the example L part;
- be a plain Python project, publishable on **GitHub**, that anyone with FreeCAD installed can run;
- be launched from the **VS Code terminal** and show the optimization **in real time inside the FreeCAD window**.

The user is new to FreeCAD's FEM workbench (learned to set up the first analysis during
this conversation). The tool must teach the preparation and give clear messages, not
assume knowledge of FEM/CalculiX.

The original name of the idea was "FreeCAD + PrePoMax integration". It was decided
(recommendation accepted by the user) to **use only FreeCAD** (FEM workbench + Gmsh +
CalculiX, all bundled with FreeCAD 1.1). PrePoMax stays out of the flow; at most it is
mentioned in the README as an optional result viewer. Reason: only FreeCAD knows the
parametric dimensions and the boundary conditions tied to the geometry; PrePoMax would
receive a solid without parameters. *(Later changed: see "Later changes".)*

## 2. Goals, non-goals, anti-goals

**Goals**
- Parametric shape optimization: vary dimensions chosen by the user, within limits, to find **the lowest-mass part whose maximum Von Mises stays below a limit** defined by the user. (Goal approved by the user.)
- Everything specific to a part lives **inside the `.FCStd`**; the code is generic.
- See the part change and the Von Mises color map at each iteration in the FreeCAD GUI.
- `--headless` mode for quick/long runs.
- A check command that says what is missing in the file.
- Step-by-step tutorial using the L part as the example, and the L part already prepared in the repository.

**Non-goals**
- Topology optimization (freely removing material, BESO/SIMP style).
- Selecting "movable" faces by clicking — the user confirmed that pointing to dimensions by name is what they want.
- Support for PrePoMax, other solvers, nonlinear, dynamic, thermal or contact analyses. Only linear static, one solid body, one analysis.
- Linux/macOS support in v1 (not forbidden, just not tested). Target: Windows + FreeCAD 1.1.

**Anti-goals (failure even if it "works")**
- Lowering the stress simply by thickening everything to the maximum (hence the objective is minimum mass under a stress constraint).
- Reporting as an improvement a stress drop that is a numerical artifact (singularity at a sharp corner, at the edge of a fixed constraint or of a force application).
- Keeping on optimizing when the fixed constraint/force "jumped" to another face because of FreeCAD's topological naming problem, producing meaningless results without warning.
- Overwriting the user's original file.
- Raw CalculiX/Gmsh/FreeCAD errors thrown at the user without explanation.

## 3. Environment and constraints (verified on the user's machine)

- Windows 11, FreeCAD **1.1.4** at `C:\Program Files\FreeCAD 1.1\` with `bin\freecad.exe`, `bin\freecadcmd.exe`, `bin\python.exe` (Python 3.11.14), `bin\ccx.exe`, `bin\gmsh.exe`.
- FreeCAD's Python already has **numpy 1.26, scipy 1.16, matplotlib 3.10**. No extra dependency must be installed.
- The user also has the system Python 3.11.9 (VS Code's `python`). It **cannot** import the FreeCAD module directly.
- To run scripts in `freecadcmd` use `freecadcmd.exe -c "exec(open(r'<path>').read())"` — passing the script path as a positional argument did **not** run the script in the tests done in this conversation.
- The project was not yet a git repository; it will become a GitHub repository.

## 4. Example part (state of `L_part.FCStd` at the time)

Inspected through freecadcmd:
- `Body` with `Sketch` (L profile on the XZ plane: horizontal leg 180×30, vertical leg 30×230) → `Pad` 20 mm; `Sketch001` + `Pad001` (10 mm, reversed) only to split a 20×20 face at the inner top of the vertical leg (total volume unchanged: 228 000 mm³).
- `Analysis` with `ConstraintFixed` (Face2, base of the horizontal leg), `ConstraintForce` (Face12, 5000 N in the −X direction), `MaterialSolid` (Steel-C10: E 210 GPa, ν 0.3, yield 380 MPa, ultimate 650 MPa), `FEMMeshGmsh` (max. size 5 mm, 2nd order), `SolverCcxTools` (linear static), existing results.
- Current result: max. Von Mises ≈ 509 MPa at the sharp inner corner (30, −10, 31.9); max. displacement 1.66 mm. Nominal bending stress estimated by hand ≈ 317 MPa.
- The inner corner is sharp: the peak is singular and depends on the mesh. The part does **not** have a spreadsheet nor a corner radius yet.

## 5. How a part is prepared (convention — decided with the user)

The user prepares each part once, in the FreeCAD GUI:

1. A normal **FEM analysis** in the FEM workbench: material, one or more `ConstraintFixed`, one or more `ConstraintForce` (and optionally pressure), Gmsh mesh, CalculiX solver. The tool discovers all of this on its own from the document's `Fem::FemAnalysis` object.
2. **A spreadsheet called `Parameters`** (Label or Name) containing **only what may change**. Everything that is not in the spreadsheet is fixed. (Point raised and decided by the user.)
   - One row per parameter: column A = free description, column B = value with an **alias** (the name the code uses, e.g. `corner_radius`), column C = minimum, column D = maximum.
   - Sketch dimensions / feature properties are linked by expression (`Parameters.corner_radius`) using the f(x) button.
3. **Objective settings**, also in the `Parameters` spreadsheet, in cells with a reserved alias. Required minimum: `stress_limit` (MPa). Optional with a default: `max_iterations`. The builder may add other optional ones if needed (e.g. exclusion zone, see §7), always with a sensible default.
4. **Corner radius through the Sketcher** (sketch fillet with a radius constraint), not through the PartDesign Fillet on an edge, so as not to depend on an edge name. This becomes a recommendation in the tutorial and a warning in `--check` when there is a `PartDesign::Fillet` linked to a parameter.

The exact layout of the settings cells (separate rows below the parameters, or another area) is up to the builder, as long as it is documented in the tutorial and the code tells parameters from settings without ambiguity (e.g. reserved aliases).

## 6. User experience

```
python optimize.py examples/L_part.FCStd            # opens FreeCAD and optimizes live
python optimize.py examples/L_part.FCStd --headless
python optimize.py examples/L_part.FCStd --check    # only checks the preparation
```

- `optimize.py` runs with the **system Python, standard library only**: finds FreeCAD (default `C:\Program Files\FreeCAD 1.1\bin`, overridable by `--freecad <folder>` and an environment variable), and launches `freecad.exe` (live mode) or `freecadcmd.exe` (headless/check) with the internal script. The optimization logic lives in a package that runs inside FreeCAD's Python.
- **Before the loop**, it runs one analysis with the current values and shows the maximum Von Mises, where it is and the mass — the "baseline".
- **At each iteration**, in live mode: geometry recomputed on screen, part painted with Von Mises (same color scale as the FEM workbench), a line in the Report View and in the VS Code terminal:

```
iter  corner_radius  vertical_thickness  VonMises_max  mass     status
  1        1.0             30.0             509 MPa   1.79 kg  above limit
  3       14.0             35.0             247 MPa   1.95 kg  OK ✓ best so far
```

- The VS Code terminal must receive these lines in real time also in live mode (the FreeCAD GUI is another process; the builder chooses how: stdout, a log file followed by the launcher, etc.).
- It is acceptable for the window to look frozen while CalculiX solves; avoiding it is desirable.
- **At the end**: best version open in FreeCAD (live mode), summary in the terminal (best point, whether the limit was reached, mass vs. original, stress vs. original).
- If no combination within the limits reaches `stress_limit`: warn clearly and deliver the closest feasible best (lowest stress), do not fail silently.

## 7. Optimization behavior (builder decisions already taken by me — marked)

- **Formulation**: minimize mass (volume × material density) subject to `VonMises_max ≤ stress_limit`, with each parameter within [min, max]. *(my decision)*
- **Algorithm**: derivative-free, constrained, few evaluations (each evaluation = recompute + mesh + solve, seconds to ~1 min). Suggestion: scipy's COBYLA starting from the current values, or equivalent. The builder makes the final choice. The FEA evaluation is noisy (the mesh changes), the algorithm must tolerate that. *(my decision: scipy available, nothing to install)*
- **Stress measure**: maximum nodal Von Mises, **excluding nodes close to the boundary-condition faces** (fixed constraints and forces), because the edges of fixed constraints/load application are artificial singularities that would dominate the maximum once the corner is rounded. Exclusion distance with a sensible default (e.g. ~2× element size) and configurable in the spreadsheet. The raw maximum (without exclusion) is also recorded in the CSV for transparency. *(my decision)*
- **The exclusion must never silently hide a real peak.** Risk: in a real part the critical point may be right next to a fixed face (root of a bolted support), or in the example the thin leg may bring the corner into the zone; the optimizer would then thin the part and say "OK ✓" about something above the limit. Rules *(my decision, presented to the user for veto)*:
  - Default: exclude a zone around forces/pressures **and** fixed constraints.
  - Every iteration compares the maximum **inside** the excluded zones with `stress_limit`. If the raw maximum inside the zone exceeds the limit, the iteration gets the status **"OK ⚠ check"** (not "OK ✓"), with the location of the peak; the final summary and the CSV highlight it, and the best point is chosen preferring clean "OK ✓" iterations.
  - Also flag when the filtered maximum is at the edge of the zone (a sign that the gradient continues into it).
  - The user can turn off the exclusion per boundary condition (e.g. an alias/option per fixed constraint or force in the spreadsheet; format up to the builder) and change the distance.
  - The tutorial explains in simple language why these zones exist and when to turn them off.
- **Mesh**: uses the user's own mesh settings (`FEMMeshGmsh`) in every iteration; the tool does not refine the mesh on its own in v1. The tutorial explains that a sharp corner has no "true" stress. *(my decision)*
- **Protection against topological naming**: after each recompute, check that each boundary condition still points to an existing face "similar" to the original (e.g. normal and centroid position/area within tolerance). If not, the iteration is marked invalid with a clear message; if it happens at the baseline or repeatedly, stop and explain. *(my decision)*
- **Evaluation failures** (recompute error, impossible sketch, Gmsh or CalculiX fail): iteration marked invalid in the CSV with the reason, treated by the optimizer as a bad point; the run continues. *(my decision)*
- **Stopping**: algorithm convergence or `max_iterations` (default 20). Ctrl+C in the terminal (or closing FreeCAD) ends saving the best so far. *(my decision)*
- **The original file is never modified**; it works on a copy.

## 8. Outputs

Per run, in a `results/<part_name>_<date-time>/` folder:
- `<part>_optimized.FCStd` — best feasible point (or best found, if none feasible), with FEM results inside;
- `history.csv` — one row per iteration: parameter values, Von Mises (filtered and raw), location of the maximum, mass, status/reason;
- `chart.png` — stress and mass per iteration, limit line (matplotlib);
- `log.txt` — full output.
*(folder structure: my decision)*

## 9. Check (`--check`)

Messages, one per problem, saying how to fix it. Minimum:
- there is no `Analysis`, material, fixed constraint, force, mesh or solver;
- there is no `Parameters` spreadsheet, or it has no parameter;
- parameter without minimum/maximum, minimum ≥ maximum, current value outside the limits;
- parameter not used by any expression in the document (forgotten link);
- `stress_limit` is missing;
- parameter linked to `PartDesign::Fillet`/`Chamfer` (warning, not error);
- the document does not recompute without errors with the current values.

## 10. Repository and documentation

- Structure and module names: up to the builder. *(Originally code, messages and README in Portuguese; translated to English on 2026-10-29.)*
- `examples/L_part.FCStd`: the **prepared** L part (`Parameters` spreadsheet, corner radius through a sketch fillet linked to `corner_radius`, leg thicknesses linked to parameters, `stress_limit` e.g. 250 MPa ≈ 380/1.5). The preparation may be done by script, but the result must open and work normally in the FreeCAD GUI. The user's original `L_part.FCStd` at the root must be preserved.
- `README.md`: what it is, requirements (Windows, FreeCAD 1.1), how to run the example, and a **step-by-step tutorial** for preparing a new part (FEM analysis, spreadsheet, aliases, f(x), sketch fillet, `--check`). Screenshots are desirable; if they cannot be generated automatically, leave clear markers for the user to complete.
- MIT license. *(my decision)*
- Tests: at least one end-to-end test that runs the example headless with few iterations and checks that the final stress is lower than the initial one and that the result respects the limits; more unit tests where it makes sense.

## 11. Left to the builder

- Internal architecture, module names, how the GUI process reports progress to the terminal.
- Exact optimization algorithm and tolerances.
- How to paint Von Mises in the GUI (FEM post-processing pipeline or color per node on the mesh).
- Exact layout of the spreadsheet settings area.
- How to avoid freezing the GUI during the solve.

## Later changes

- **2026-10-25 — PrePoMax as the stress viewer.** Contrary to §1 and §2, PrePoMax became
  the live viewer of the stresses: a single PrePoMax window, on the right half of the
  screen, is driven by `optimizer/prepomax_window.ps1` (UI Automation: File → Open,
  mm/ton/s units, isometric view) to show each iteration's `.frd`, while FreeCAD shows the
  part changing shape on the left half. It remains optional (`--no-prepomax` paints the
  colors in FreeCAD). PrePoMax is still only a viewer: the dimensions and boundary
  conditions stay in FreeCAD.
- **2026-10-29 — Everything in English.** Code, messages, CLI options, spreadsheet name
  and aliases, README and these documents were translated to English for the
  international community, with no change in behavior. `history.csv` now uses a comma
  separator and a dot decimal.
