# CLAUDE.md — vasp_auto

## Project summary

`vasp_auto` is a Python CLI that automates preparing, running, and parsing VASP
DFT calculations. It eliminates manual file management: given a POSCAR it builds
INCAR, KPOINTS, POTCAR, launches VASP through `mpirun`, and writes an Excel
summary. It supports SCF, structure optimisation (treated as SCF with NSW>0),
NEB/TSS, ASE structure import, and an automatic NELM+KPOINTS convergence scan.

The long-term goal is a **MedeA-style GUI layer** on top of this engine — a
workflow builder where users pick a calculation type, adjust parameters through
forms, chain tasks (convergence → optimisation → SCF → DOS), and view results,
without writing a single INCAR line by hand. All planned GUI work must stay
fully backward-compatible with the existing CLI.

---

## Repository layout

```
src/vasp_auto/          Python package (the engine, the only source of truth)
  cli.py                argparse entry point, orchestrates everything
  calc_types.py         CalcType enum + descriptions + per-type chain inputs
  config_loader.py      config.yaml search, normalisation, per-case merging
  incar.py              INCAR editing helpers: set_incar_value, spin/MAGMOM
  job_manager.py        input-file preparation, INCAR templates, dry-run preview
  kpoints.py            KPOINTS generation (gamma/MP mesh, density, line-mode)
  structure.py          pure-Python POSCAR tools (supercell, vacancy,
                        substitution, interstitial, cell<->parameters,
                        set_cell, wrap, coordination/bond analysis,
                        combine_structures for deposition/heterostructures,
                        make_prototype crystal library, match_supercells
                        commensurate-cell search, add_adsorbate)
  runner.py             mpirun invocation + SLURM/PBS submit scripts
  workflow.py           OUTCAR parsing (incl. magmoms), error detection +
                        auto-retry fixes, run-one-case helpers
  chain.py              chained workflows (relax → scf → dos); a leading
                        `converge` step runs convergence.py and carries the
                        chosen ENCUT/SIGMA/NELM/KPOINTS into the later steps
  convergence.py        automatic ENCUT + SIGMA + NELM + KPOINTS scan
  excel_writer.py       pandas → styled Excel summary + energy bar chart
  report.py             per-job Markdown calculation report (--report)
  trajectory.py         XDATCAR/NEB frames → cartesian animation data
  potcar_finder.py      POTCAR library lookup, variant map, concatenation
  target_utils.py       case-type detection, project vs single mode
  ase_tools.py          ASE import, bulk/slab/molecule/space-group-crystal/
                        nanotube builders, NEB interpolation
  ml_tools.py           MLIP pre-relax/screening: Meta OMat24/UMA via fairchem
                        (optional dep), "emt" demo backend; --ml-relax
  parser.py             vasprun.xml parsing incl. PDOS (+aggregate_pdos),
                        bands (parse_bands, read_kpoints_labels) and the
                        dielectric function (OUTCAR/OSZICAR in workflow.py)
  analysis.py           catalysis post-processing: adsorption energy, vibrational
                        thermochemistry (ZPE/TS/Gibbs), d-band center, work
                        function, optical absorption (reads finished job dirs)
  chgcar.py             CHGCAR/LOCPOT/AECCAR volumetrics: diff, sum, planar
                        average, Bader helper (Henkelman binary + ACF.dat)
  qe_tools.py           Quantum ESPRESSO (pw.x) engine: POSCAR->pw.in builder
                        (namelists+cards, ENCUT->ecutwfc Ry), UPF pseudopotential
                        lookup (pseudo_dir/pseudo_map), create_qe_job/
                        preview_qe_job; selected by engine=qe/--engine qe

src/vasp_auto_ui/       web UI package (`vasp-auto-ui`, stdlib http.server only)
  server.py             JSON API wrapping engine functions; runs jobs via the CLI
  static/index.html     single-page front end: Build / Calculate / Workflow /
                        Results tabs + canvas 3D structure viewer; the Build
                        tab uses a searchable "Build function" catalog
                        (BUILD_FUNCTIONS + showBuildFn) that reveals one
                        builder form at a time instead of stacking them all

config.yaml             vasp_executable, jobs_root, potcar_root, neb_images,
                        potcar_map, scheduler, job_template, scheduler_options, workflow
pyproject.toml          pip install -e . gives the `vasp-auto` console command
                        (symlinked into ~/.local/bin → callable from anywhere)
tests/                  pytest unit tests (run: venv/bin/python -m pytest)
selfcheck/              end-to-end feature check with fake mpirun/vasp_std/sbatch
                        (run: selfcheck/run_selfcheck.sh — 47 checks, no VASP needed)
docs/MANUAL.md          user-facing operation manual (commands + file structure)
docs/TUTORIAL_CATALYSIS.md  photo/electrocatalysis walkthrough (adsorption,
                        CHE free energies, DOS/d-band, Bader, work function…)
docs/TUTORIAL_HETEROSTRUCTURE.md  combining mismatched unit cells (TiO2(111)
                        slab on graphene: prototypes, match-cells, combine)
inputs/                 user-supplied calculation input directories
jobs/                   generated job directories + Excel summaries
TSS/                    NEB example inputs and jobs
POTCAR/                 per-element POTCAR library (POTCAR/<El>/POTCAR)
example/                INCAR templates (scf, dos, optimize, charge_density)
docs/                   user-facing prose: MANUAL, TUTORIAL_*, PORTABILITY
                        (manuals / tutorials)
src/docs/               developer / code-structure docs: this CLAUDE.md,
                        VASP_AUTO_CAPABILITIES, FILE_STRUCTURE,
                        VASP_AUTO_COMMAND_AND_STRUCTURE
_archive/               historical outputs, not source
```

### Documentation layout (where .md files live)

- **`src/docs/`** — anything describing the *code structure* of the engine:
  this `CLAUDE.md` and the capability/command/file-structure references.
  Edit these when the architecture changes.
- **`docs/`** — anything a *user* reads: `MANUAL.md`, the `TUTORIAL_*` series,
  and `PORTABILITY.md`. Edit these when behaviour or usage changes.

---

## Known problems (as of 2026-06-13)

> Items 1–14 were addressed in the 2026-06-11 build-out (two passes). A
> third pass on 2026-06-12 (v0.4.0) added the friendly UI redesign, spin
> presets (`--spin`/`--magmom`/`magmom_map:`), HSE06 templates, magnetic
> moments parsing, `--auto-retry` with known INCAR fixes, a SIGMA scan +
> `--reuse-wavecar`, `--interstitial`, the Excel energy chart, and CI. A
> same-day addendum implemented the user's plan.txt: `--report` (Markdown
> report per job, `report.py`), relax/NEB animation (`trajectory.py` +
> viewer), DOS/energy graphs with PNG export (`parser.parse_dos`), a UI NEB
> case builder, and `docs/PORTABILITY.md` (+`VASP_AUTO_MPI` override). A
> fourth pass (v0.5.0, same day) fixed three bugs — negative-scale POSCARs
> (target-volume convention) mishandled outside kpoints.py; `;`-compound
> INCAR lines getting conflicting duplicate tags from `set_incar_value`;
> `--retry-failed` wiping CONTCAR/WAVECAR/CHGCAR (pass-2 memo item 13) —
> and added `ml_tools.py`: MLIP pre-relaxation with Meta's OMat24/UMA
> models (`--ml-relax`, fairchem optional dep, `emt` demo backend, UI card,
> `/api/mlrelax`). A fifth pass (v0.6.0, 2026-06-12, per `building
> structure.txt` + `periodic_structure_builder_reimplementation.md`)
> rebuilt the Builder UI as a full interactive editor: engine gained
> cell_from_parameters/cell_parameters/set_cell/wrap_to_cell/delete_atoms/
> build_struct/coordination (Jmol r1+r2+0.45 Å convention, periodic
> images)/combine_structures (stack/insert, e.g. Au on graphite) +
> `--combine*` CLI flags; the UI got cursor atom control (click-select,
> drag-move, arrow-key nudge, delete, undo/redo), bonds/labels/axes
> overlays, a coordination panel, a,b,c,α,β,γ cell editing, a hideable
> live-editable POSCAR side panel, and an explicit 💾 Save button —
> builders now load into the editor via `to_editor`/`/api/combine`/POST
> `/api/structure` and write nothing until saved. A sixth pass (v0.7.0,
> same day) built the catalysis toolchain + `docs/TUTORIAL_CATALYSIS.md`:
> new modules `analysis.py` (adsorption-energy assembly, IBRION=5
> frequency parsing + ZPE/U_vib/T·S Gibbs corrections for CHE diagrams,
> d-band center/width from PDOS, LOCPOT work function, LOPTICS absorption
> spectra) and `chgcar.py` (pure-Python volumetric IO, charge-density
> difference, AECCAR sum, Bader via the Henkelman binary, config
> `bader_executable:`); `parser.parse_pdos`/`parse_dielectric`; calc types
> `freq`/`optics`/`workfunction` + templates; CLI `--delete SEL` and the
> read-only analysis commands `--adsorption-energy` (+`--molecule-scale`),
> `--thermo` (+`--temperature`), `--work-function`, `--d-band`
> (+`--d-band-emax`), `--chg-diff`, `--bader`, `--optics-parse`. A seventh
> pass (2026-06-13, small hours) added the prototype crystal library
> (`--build-prototype`: graphene/graphite/rutile/anatase-TiO2/hBN),
> `match_supercells` (`--match-cells` + `--match-max`/`--match-strain`/
> `--match-gamma-tol`), `add_adsorbate`, `parser.aggregate_pdos`/
> `parse_bands`/`read_kpoints_labels`, and UI endpoints+cards for
> PDOS/bands/volumetrics/chg-diff/cell-match. An eighth pass (v0.8.0, same
> day) consolidated pass 7: full test coverage (236 tests), the remaining
> analysis UI (GET /api/thermo|dband|workfunction|optics, POST
> /api/adsorption|bader; 🧪 Analysis + 🧗 Adsorption cards, CSV export
> everywhere), `docs/TUTORIAL_HETEROSTRUCTURE.md` (TiO2(111) on graphene,
> mismatched-cell strategies), picker last-folder memory, selfcheck checks
> 22–25 (41 total). A ninth pass (2026-06-14, per `building ui.md`) added the
> Build-tab "Build function" catalog (a searchable, category-grouped launcher
> that shows one builder form at a time instead of stacking all of them) and
> two new ASE builders: a space-group crystal builder
> (`build_crystal_case`, `--ase-build-crystal`/`--ase-spacegroup`/`--ase-basis`
> + cell params, `/api/build` action "crystal") and a single-wall nanotube
> builder (`build_nanotube_case`, `--ase-build-nanotube`/`--ase-nt-n|m|length|
> bond`, action "nanotube"); both load into the editor like the other
> builders. Tests: `tests/test_ase_builders.py`; selfcheck checks 26–27. A
> tenth pass (2026-06-14) made convergence a first-class **workflow step**:
> chain.py gained a `converge` step (`--workflow "converge,relax,scf,dos"` or
> a workflow.yaml step with encut/sigma/nelm/kpoints/energy_tol/reuse_wavecar)
> that runs `converge_scf_case` and carries the chosen ENCUT/SIGMA/NELM/KPOINTS
 into the later steps; `api_run` accepts a `workflow_yaml` it writes to the
> case; the Workflow tab got a Converge→…→DOS preset + a convergence-settings
> panel (the Calculate tab already had a standalone scan). Tests: 251 total;
> selfcheck check 28 (47 total). Remaining backlog at that point: symmetry
> k-paths, queue polling, dataclass rows, solvation. An eleventh pass (v0.9.0, 2026-06-14) fixed and added:
> **NEB retry** (`should_retry_failed` now excludes both first and last endpoint
> dirs; `_build_neb_row` uses `_neb_image_energy` that falls back OUTCAR→OSZICAR
> →vasprun.xml for endpoint energies); **phonon description** corrected to DFPT
> (IBRION=8); **`--ml-energy TARGET`** single-point MLIP screen (read-only,
> `ml_tools.ml_energy`, `/api/mlenergy`); **`--poll JOBID`** scheduler status
> query (`runner.poll_job_status`, SLURM/PBS, graceful unknown when binary
> absent); **`--kpath auto`** pure-Python lattice-type heuristic
> (`kpoints.guess_lattice_type`/`auto_kpath`, no spglib); **`--solvation`**
> implicit solvent via VASPsol (`LSOL`/`EB_K`, `--solvation-eps`).
> Tests: 281 total; selfcheck: 47 (unchanged). A twelfth pass (2026-06-16)
> added an **open-source DFT engine: Quantum ESPRESSO (pw.x)** so users without
> a VASP licence can run the same cases: new `qe_tools.py` (POSCAR->pw.in
> generation, UPF pseudopotential lookup via `pseudo_dir`/`pseudo_map`,
> `create_qe_job`/`preview_qe_job`), `parser.parse_pw_output`/
> `parse_pw_final_structure`, `runner.run_qe`. The engine is chosen with
> `engine: vasp|qe` in config.yaml (default vasp), `--engine qe`, a per-case
> override, or the UI's engine dropdown; threaded through
> `create_job_from_case`/`preview_job_from_case`/`run_one_case`/`build_row` with
> a `.engine` marker file in each job dir (like `.remote.json`). QE scope:
> scf/relax/vcrelax/dos/bands (NEB/phonon/convergence/chaining/solvation stay
> VASP-only, guarded with clear errors). Tests: `tests/test_qe.py` (21);
> selfcheck checks 29-30 (fake `pw.x` + UPF stubs, 55 total). Docs: MANUAL.md
> "Open-source engine" section, `example/pw_scf.in`, config.yaml QE block.
> A thirteenth pass (2026-06-18) **rebuilt the Results tab and
> connected the Workflow tab to remote machines**. Results: one unified table
> across **All machines / Local / one remote** (`r-machine` gained an "All
> machines" option that aggregates local `/api/results` + each remote's
> `/api/remote/jobs` in the browser via `Promise.allSettled`, tolerant of a down
> machine); always sorted by date (the sort dropdown and the "Energy per case"
> chart were removed); name-search + from/to date-range + per-page filters with
> pager (`applyResultFilters`/`renderResults`/`gotoResPage`); clearer fonts;
> clicking a job name opens its file list and clicking a **file name** now shows
> the file inline (`jdView`) with a download button — local and remote — backed
> by new endpoint **`/api/filetext`** (POST; `runner.read_remote_text` over SSH,
> capped at 200 KB, constrained to the machine's `remote_root`; POTCAR/binaries
> are download-only and never printed). The catalysis cards (🧪 Property
> analysis, adsorption, Δρ) are now hidden until invoked, with the 🧪 card's
> purpose spelled out. **Workflow tab** got a "run on machine" selector +
> cores field (`w-remote`/`w-cpus`, `refreshWorkflowRemoteSelect`); `runWorkflow`
> now passes `remote`, so a chain offloads to the chosen machine instead of
> silently running locally. Two engine fixes make offloaded chains actually run:
> `_run_detached_offload` ships `workflow.yaml` in the bundle, and
> `submit_job_detached` ships the `example/INCAR_*` templates to
> `<remote_root>/.vasp_auto/example` and exports `VASP_AUTO_ROOT` in `run.sh` so
> the remote engine can build INCARs for **every** calc type (relax/dos/bands/…),
> not just built-in scf/neb. Verified live on **apl2** (oneAPI, ssh_detached):
> the UI shipped a `relax,scf` workflow, the remote built the optimize INCAR from
> the shipped template, ran both steps with `mpirun -np 8 vasp_std`
> (scf TOTEN −1.997 eV), `/api/remote/status`→completed, fetch pulled the step
> dirs back. Tests: 397 total (+6: filetext local/remote/POTCAR-block,
> read_remote_text, offload workflow.yaml + template shipping); selfcheck 55/0.

### 1 — Calculation types are severely limited — FIXED 2026-06-11

`--calc-type` (scf | relax | dos | bands | charge | neb | md | phonon |
hse06 | freq | optics | workfunction) selects the matching
`example/INCAR_<type>` template;
`calc_types.CalcType` is the canonical enum (with `CALC_TYPE_INFO`
descriptions) for both the CLI and the GUI. A user-supplied case INCAR still
takes precedence (with a printed note). Spin-polarised runs: `--spin`
(+`--magmom`/`magmom_map:`) via `incar.py`; hybrid functional: `hse06`.

---

### 2 — Default INCAR is too minimal and hard-coded — FIXED 2026-06-11

`job_manager.load_incar_template(calc_type)` now reads
`example/INCAR_<type>` (searching `$VASP_AUTO_ROOT/example` first, then the
repo `example/`) and falls back to the built-in default strings only when no
template file exists. `INCAR_TEMPLATE_FILES` maps calc types to filenames;
adding a type means adding a template file plus a map entry.

---

### 3 — KPOINTS generation is primitive — FIXED 2026-06-11

`kpoints.py` + CLI flags: `--kpoints-mode gamma|mp|line|spacing`, `--kmesh`,
`--kspacing` (mesh derived from the reciprocal lattice, VASP KSPACING
convention), `--kpath` (presets cubic/fcc/bcc/hex or explicit
`"G 0 0 0; X 0.5 0 0.5"`) with `--kpath-divisions`. Symmetry-detected k-paths
(seekpath/pymatgen) and hybrid-functional reduced meshes remain open.

---

### 4 — Convergence scan covers only NELM and KPOINTS — FIXED 2026-06-11

`--converge-encut 400,450,500,550` scans ENCUT first (the selected value is
then held fixed for the SIGMA/NELM/KPOINTS stages). `--converge-sigma
0.2,0.1,0.05` picks the largest smearing whose entropy T*S per atom is below
`--sigma-tol` (default 1 meV). Energy stages use `_select_converged_trial`:
the first converged trial whose |E_N − E_{N−1}| ≤ tol, not the lowest
energy. `--reuse-wavecar` seeds trials with the previous WAVECAR/CHGCAR.

---

### 5 — No VASP error detection or recovery hints — FIXED 2026-06-11

`workflow.scan_vasp_errors()` scans `run.log`/`OUTCAR` for known signatures
(ZBRENT, EDDDAV, RHOSYG, Sub-Space-Matrix, ZPOTRF, PRICEL, SGRCON, TOO FEW
BANDS, "SICK JOB"); `report_vasp_errors()` prints a diagnostic with an INCAR
fix hint after every run (`run_one_case` and convergence trials) and the
summary lands in the Excel `errors` column. Extend by appending to
`VASP_ERROR_SIGNATURES` in `workflow.py`. `--auto-retry N` applies the safe
fixes in `VASP_ERROR_FIXES` and re-runs (local scheduler only); codes without
a safe generic fix are reported but never auto-fixed.

---

### 6 — Serial case execution within a project — FIXED 2026-06-11

`--parallel N` runs up to N cases concurrently via
`concurrent.futures.ThreadPoolExecutor` (each case is its own `mpirun`
subprocess in its own job directory). Terminal output from concurrent cases
may interleave.

---

### 7 — No workflow chaining (the MedeA gap) — FIXED 2026-06-11

`chain.py` runs ordered steps in per-step subdirectories of the job dir,
feeding outputs forward (CONTCAR → POSCAR; CHGCAR for dos/bands) via
`calc_types.CHAIN_INPUTS` defaults or an explicit `copy:` map. Three ways to
specify: `--workflow "relax,scf,dos"`, a `workflow.yaml` in the case
directory (steps with optional `incar:`, `kpoints:`, `kpath:` overrides), or
a `workflow:` key in config.yaml. CLI flag > case file > config. A special
`converge` step (e.g. `--workflow "converge,relax,scf,dos"`) runs an SCF
convergence scan first and carries the chosen ENCUT/SIGMA/NELM/KPOINTS into
the later steps (scan ranges via the step's `encut`/`sigma`/`nelm`/`kpoints`
keys; a later step's own `incar:`/`kpoints:` still win).

---

### 8 — POTCAR selection ignores pseudopotential variants — FIXED 2026-06-11

`config.yaml` now supports:

```yaml
potcar_map:
  Fe: Fe_pv
  O: O_s
```

`potcar_finder.map_potcar_dirs()` consults this map before falling back to
the bare element symbol; it is wired from `cli.py` through
`create_job_from_case(potcar_map=…)`. Switching whole GGA/LDA libraries still
goes through `potcar_root`.

---

### 9 — Output parsing is too narrow — MOSTLY FIXED 2026-06-11

`parser.parse_vasprun()` reads `vasprun.xml` (stdlib ElementTree) into a
structured dict: energy, Fermi level, band gap (VBM/CBM from eigenvalue
occupations), max force, pressure, ionic steps. `workflow.build_row` merges
these into the Excel summary automatically when vasprun.xml exists. NEB rows
include forward/backward barriers and the per-image profile; spin runs add
total magnetisation and per-atom moments (OUTCAR).

---

### 10 — No job scheduler integration — FIXED 2026-06-11

`scheduler: local | slurm | pbs` in config.yaml (or `--scheduler`), with
optional `job_template:` (a format string with {job_name}, {cpus}, {exe},
{job_dir}, {extra}) and `scheduler_options:` (list of extra script lines).
Non-local runs write `submit.sh` and call `sbatch`/`qsub`; the row records
the queue job id with status "submitted". Use `--parse-only` later to harvest
results — there is no queue polling yet.

**Remote submission** (`--remote`, 2026-06-15): with a `remote:` block (or a
`remotes:` map of named machines) in config.yaml — host, remote_root,
vasp_executable; optional user/port/ssh_key/ssh_options/scheduler/
scheduler_options — the CLI prepares the full input set locally, copies the
whole job dir (INCAR/KPOINTS/POSCAR/POTCAR/submit.sh) to the remote machine via
rsync (scp fallback), and submits to its queue over SSH — so the local host can
be powered off afterwards. `--remote` uses `remote:`; `--remote NAME` uses
`remotes[NAME]`; `--remote-config FILE` loads one machine from a JSON/YAML file
(the UI uses this). `runner.submit_job_remote()` does the work;
`write_submit_script(run_dir=…)` bakes the remote run directory into the script,
and a `.remote.json` marker is written into the local job dir tagging the
machine/job_id/remote_dir. `build_row` reads that marker so results are tagged
with the machine and show status "remote" until fetched.
`runner.check_remote_connection/poll_remote_job/fetch_remote_results` back the
UI buttons (test SSH, poll the queue, pull results back — heavy binaries skipped
unless asked). **UI Remote tab** (`vasp_auto_ui`): manages machines in
`remotes.json` (`/api/remotes`, `/api/remote/{save,delete,test,status,fetch}`),
the Calculate tab has a "run on machine" selector, and the Results table gets a
machine column + per-row 🛰 status / ⬇ fetch buttons. Files stay on the remote;
fetch pulls a copy back so the local viewers work.

**Direct-SSH run mode (`run_mode: ssh`, 2026-06-17):** the original `--remote`
path only did fire-and-forget *scheduler* submission (`sbatch`/`qsub`), and the
convergence-scan and chained-workflow branches in `cli._process_case` ignored
`remote` entirely — so picking a remote machine while running a convergence scan
(the common case) silently ran **locally**. Fixed: each remote now has a
`run_mode` (resolved by `runner.remote_run_mode`; `run_mode: ssh|direct`, or
`scheduler: ssh|none|local`, ⇒ direct SSH; else the scheduler name).
`runner.run_vasp_remote()` is a synchronous drop-in for `run_vasp` — rsync inputs
to `<remote_root>/<subdir>`, run `mpirun` over SSH (sourcing the machine's
optional `env_setup`, e.g. `source /opt/intel/oneapi/setvars.sh`, so MKL/MPI are
on the path in a non-interactive shell; `ulimit -s unlimited`), then rsync the
results back and write a `.remote.json` marker (machine/remote_dir/mode=ssh) so
the row shows `status: done` + the machine. `_remote_vasp_exe` treats a
`vasp_executable` that is a directory as `<dir>/vasp_std`. `remote` is now
resolved once at the top of `_process_case` and threaded into the plain run
(`run_one_case`), the convergence scan (`converge_scf_case` →
`_scan_stage`/`_run_trial`, `remote_subdir` keeps trials from different cases
from colliding), and chained workflows (`run_workflow_case`, each step over SSH;
scheduler-mode chains are rejected with a clear error). Scheduler submission is
unchanged. UI: the Remote-tab form gained **run mode** + **env setup** fields
(`REMOTE_FIELDS` += `run_mode`, `env_setup`); the Test-connection check probes
`mpirun` for ssh machines (instead of `sbatch`). Verified live on a real
workstation (apl2, 64-core, oneAPI): plain SCF, ENCUT/SIGMA convergence, and the
UI HTTP path all run on the remote with results stored in `remote_root` and the
machine shown on the Results page. Tests: `tests/test_runner.py` (run-mode/exe/
run_vasp_remote) + `tests/test_workflow.py` (run_one_case dispatch); 368 total.

**Offload / detached run mode (`run_mode: ssh_detached`, 2026-06-18):** lets the
local host be powered off — the whole engine (incl. the iterative convergence/
workflow loops) runs on the remote. One-time `setup_remote_engine(remote)` builds
a wheel (`build_engine_wheel`), ships it, and pip-installs vasp_auto into
`<remote_root>/.vasp_auto/venv` (venv `--without-pip` + get-pip bootstrap, since
distro `python3-venv` may be absent; PyYAML+pandas+openpyxl pulled from PyPI —
needs remote internet). CLI `--remote-setup` / UI `/api/remote/setup` +
"⚙ Set up offload engine" button. `submit_job_detached()` ships an inputs bundle
(POSCAR + a locally pre-built POTCAR via `build_potcar`, so no POTCAR library on
the remote) + a generated `config.yaml` (`jobs_root: <remote_root>/results`),
writes a `run.sh`, launches it under `setsid` (records PID in
`<remote_root>/.vasp_auto/runs/<case>/{pid,rc,run.log}`), and returns at once with
a `.remote.json` marker (mode=ssh_detached, pid, control_dir). `cli._process_case`
routes detached runs to `_run_detached_offload` (early, before the workflow/
converge/run branches) and forwards the calc flags via `_forward_calc_flags(args)`
— the remote CLI re-branches, so convergence/workflow "just work" remotely.
`poll_detached_job()` checks the PID/rc files; `api_remote_status` routes
ssh_detached markers to it (else the scheduler poller); fetch reuses
`fetch_remote_results`. UI Remote form run-mode dropdown gained the
"offload (detached)" option. NEB/TSS offload not supported yet (needs a single
POSCAR). Verified live end-to-end on apl2 (oneAPI) and engine installed on tlclab
(system OpenMPI, no env_setup): `--remote-setup`, detached ENCUT convergence via
CLI and via the UI `/api/run`→status→fetch, laptop-off-safe (SSH returns while the
job runs under setsid). Tests: `tests/test_runner.py` (engine paths/submit/poll) +
`tests/test_cli_offload.py` (flag forwarding); 376 total, selfcheck 55/0.

> **Results now read the jobs/results folder (2026-06-15):** the Results tab
> had been driven by the *inputs* folder and guessed where each case's output
> went, so jobs run under a different name were hidden and buttons could land on
> a missing dir. `api_results` now detects when the target is the jobs folder
> (or any folder holding finished job dirs) and builds rows straight from the
> real output directories via `_scan_result_jobs`/`_job_dir_case_info`
> (handles flat `<jobs_root>/<case>`, nested `<jobs_root>/<project>/<case>`,
> a single job dir, NEB image dirs, and convergence subdirs). The Results tab
> has its own "results folder" picker (`r-root`) defaulting to `jobs_root`, so
> every row — and every per-row button (report/DOS/PDOS/bands/volume/trajectory/
> analysis/remote status+fetch) — points at the folder VASP actually wrote to.
> Pointing it at an inputs project still works (linked view via
> `_result_case_infos`, which mirrors the single-case layout with a fallback to
> the nested project layout).

> **Results: remote machine browser + per-file downloads (2026-06-18):** the
> Results tab gained a **machine selector** (`#r-machine`: Local + every saved
> remote). Picking a remote lists the jobs that physically live on it — a live
> SSH listing of a chosen **jobs directory** (`#r-rdir`, defaults to the
> machine's `remote_root`), newest first. New runner helpers do the SSH work
> with one round-trip each: `list_remote_jobs(remote, root)` (POSIX-sh walk of
> `root` one + two levels deep, emitting `<mtime>\t<o><v><z>\t<path>`; status
> done/running/prepared), `list_remote_dir(remote, path)` (immediate entries
> with size/mtime, dirs-first), and `fetch_remote_file(remote, rpath, local)`
> (single-file scp). Server: `api_remote_jobs`/`api_remote_files`/`api_job_files`
> (POST) + GET `/download_local` (any file in a local job dir) and
> `/download_remote?machine&path` (scp to a temp file, then stream; constrained
> to the machine's `remote_root`). Front end: clicking a job's **name** opens a
> full-screen detail modal (`#jobdetailmodal`, `showJobDetail`/`loadJobFiles`)
> listing every file with a ⬇ link and ↘ folder navigation (convergence trials,
> NEB images); works for both local and remote jobs. The remote view reuses the
> sort-by-date control and hides the local-only analysis cards/chart. Tests:
> `tests/test_runner.py` (list/fetch parsing, +5) + `tests/test_ui_server.py`
> (endpoints + downloads, +8); 391 total, selfcheck 55/0.

> **NEB/TSS energy stage graph (2026-06-15):** `workflow.neb_energy_profile()`
> returns the reaction-coordinate ("minimum energy path") data — per-image
> energies, energy relative to the initial image, a normalised reaction
> coordinate (cumulative configuration-space distance between images, else even
> spacing), forward/backward barriers, ΔE, and the TS image. Exposed at
> GET `/api/neb`. In the Results table, `tss` rows get a 📉 button (instead of
> DOS/PDOS/bands/volume) and the graph auto-previews for the first finished TSS
> job: a smooth Catmull-Rom curve through the images with the TS highlighted, the
> Eₐ annotation and a CSV/PNG export (`showNeb`/`drawNebProfile`/`exportNebCsv`,
> `nebcard`).

---

### 11 — Structure builder is limited to ASE bulk — FIXED 2026-06-11

ASE-backed: `--ase-build-slab` (element or structure file, with
`--ase-miller/--ase-layers/--ase-vacuum/--ase-repeat`) and
`--ase-build-molecule NAME --ase-box`. Pure-Python (`structure.py`, no ASE
needed): `--supercell 2x2x2`, `--vacancy INDEX`, `--substitute INDEX=El`,
`--interstitial "El@x,y,z"` — these compose with the builders and write a
derived case directory. `--build-only` (alias `--ase-only`) stops after
building.

---

### 12 — No per-project or per-case configuration — FIXED 2026-06-11

`config_loader.merge_local_config()` overlays a `config.yaml` found in the
target project directory and again in each case directory (global → project →
case precedence). Relative paths in a local file resolve against that file's
own directory; `jobs_root` keeps following the launch cwd.

---

### 13 — Excel output is static and unformatted — FIXED 2026-06-11

`excel_writer.py` now styles the sheet with `openpyxl`: bold filled header,
green/red colour-coding of the `converged` column, auto-fitted column widths
(capped at 60 chars), and an energy-per-case bar chart when two or more rows
have energies. `COLUMN_ORDER` lists only columns the row builders emit.

---

### 14 — No tests — FIXED 2026-06-11

`tests/` now holds 251 pytest unit tests covering every engine module, the
pass-3 features (`test_pass3_features.py`: spin, magmoms, auto-retry, SIGMA
selection, interstitial, HSE06), the pass-7 features
(`test_pass7_features.py`: prototypes, match_supercells, add_adsorbate,
aggregate_pdos, parse_bands, k-point labels), the ASE space-group/nanotube
builders (`test_ase_builders.py`), and the UI server API incl.
all analysis endpoints (`test_ui_server.py`). `conftest.py`
provides temporary case-directory and fake-POTCAR-library fixtures. Run with
`venv/bin/python -m pytest` from the repo root (`pytest.ini` sets testpaths).
CI: `.github/workflows/ci.yml` runs pytest + the selfcheck on every push.

---

## Architecture notes for GUI integration

The GUI layer exists since 2026-06-11: `vasp_auto_ui` (same repo, separate
package) — a localhost web app started with `vasp-auto-ui` (default port
8800, binds 127.0.0.1 only). It imports the engine for structure
building/parsing/previews and launches runs through `python -m
vasp_auto.cli` subprocesses (logs under `ui_logs/`), so CLI and UI behave
identically. Front end is one dependency-free HTML/JS page with a canvas 3D
structure viewer. Keep new engine features exposed through both the CLI
flags and, where user-facing, an `/api/*` endpoint.

GUI prerequisites (status as of 2026-06-11):

1. **Structured result objects** — still dicts (`build_row`, `parse_vasprun`);
   converting to dataclasses is open.
2. **Progress callbacks** — DONE: `run_vasp(..., on_progress=line_callback)`
   streams run.log lines while still writing the log file.
3. **Dry-run mode** — DONE: `job_manager.preview_job_from_case()` returns the
   full input set (INCAR/KPOINTS/POTCAR composition) without writing files;
   the CLI exposes it as `--dry-run`.
4. **Calculation type enum** — DONE: `calc_types.CalcType` (StrEnum) is used
   by the CLI argparser and is the list a GUI form should enumerate.

Entry points a GUI should call: `make_case_info`, `create_job_from_case`,
`preview_job_from_case`, `run_one_case`, `run_workflow_case`,
`converge_scf_case`, the builders in `ase_tools`/`structure`, and
`write_results_to_excel`.

---

## Development conventions

- Python 3.12+. Type hints encouraged; use `from __future__ import annotations`
  for forward references.
- No third-party imports beyond: `PyYAML`, `pandas`, `openpyxl`, `ase`
  (optional), `fairchem-core` (optional, lazy-imported inside `ml_tools.py`
  only). Keep the core engine installable without ASE or fairchem.
- `mpirun` is the only supported parallel launcher. Do not hardcode `srun`.
- Path handling: always use `pathlib.Path`; never `os.path.join`.
- Do not import `numpy` in the engine — calculations stay pure Python.
- Keep `runner.py` a thin subprocess wrapper; all logic lives in `workflow.py`
  or `convergence.py`.
- The `jobs/` directory is generated output. Never commit it.
- POTCAR files are proprietary. Never commit them; never print their content.

---

## Quick-start for a new feature

1. Identify which module owns the change (see layout table above).
2. Add or extend the relevant `--flag` in `cli.py:parse_args()`.
3. Wire the flag through `main()` into the appropriate module function.
4. Add a matching test in `tests/` (once the test suite exists).
5. Update `example/` with a representative INCAR template if the feature
   introduces a new calculation type.
6. **Update this CLAUDE.md every time you change the code** — the repository
   layout, the known-problem list, and the work loop below must always reflect
   the current state of the engine. This is mandatory, not optional.

---

## Work loop — next jobs to do

Pick the top unfinished item, do it, then move it to "Done" with a date and
add any follow-up that surfaced. Keep this list current on every code change.

### Remote / multi-machine control (highest priority)
- [ ] The engine currently assumes the **local** machine. Upgrade it to control
      multiple HPC machines and manage their files (submit, poll, fetch results)
      from one place. See `remotes.json` for the machine inventory.
- [ ] Workflow page does not reach the remote machine: clicking **Run Workflow**
      on a selected case must submit to the chosen remote, not run locally.

### Results page rebuild
- [ ] List results by date (no other sort option).
- [ ] Clicking a file name opens the remote folder, shows the file, allows download.
- [ ] Redesign the Results list; make all fonts clear.
- [ ] Machine filter: pick one machine (show its cases) or "all".
- [ ] Per-page count, from-date/to-date range, and search-by-case-name inputs.
- [ ] Remove the "Energy per case" box; clarify or remove the "Analysis" box.

### ML / MLIP
- [ ] fairchem-core 2.21.0 is installed; UMA weights are gated on Hugging Face.
      Once an HF token is available, run a UMA relax on `inputs/Au13_uma`
      (`--ml-model uma-s-1p1 --ml-task omat`) and compare against EMT and the
      DFT minimum (−27.33 eV).

### Done
- [x] 2026-06-11 — GUI layer (`vasp_auto_ui`) shipped; see Architecture notes.
- [x] 2026-06-11 — Known problems #1–#14 fixed (see list above).
