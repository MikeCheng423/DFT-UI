# CLAUDE.md — vasp_auto

**Repository:** https://github.com/MikeCheng423/DFT-UI

## Project summary

`vasp_auto` is a Python CLI that automates preparing, running, and parsing VASP
DFT calculations. It eliminates manual file management: given a POSCAR it builds
INCAR, KPOINTS, POTCAR, launches VASP through `mpirun`, and writes an Excel
summary. It supports SCF, structure optimisation (treated as SCF with NSW>0),
NEB/TSS, ASE structure import, and an automatic NELM+KPOINTS convergence scan.

The long-term goal is a **workflow-builder GUI layer** on top of this engine — a
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
  incar_catalog.py      human-language INCAR option catalog (SCF/Calculation/
                        Functional/DFT+U/DOS groups) driving the GUI guided form,
                        /api/incar_options and the NL builder
  job_manager.py        input-file preparation, INCAR templates, dry-run preview
  kpoints.py            KPOINTS generation (gamma/MP mesh, density, line-mode)
  structure.py          pure-Python POSCAR tools (supercell, vacancy,
                        substitution, interstitial, cell<->parameters,
                        set_cell, wrap, coordination/bond analysis,
                        combine_structures for deposition/heterostructures,
                        make_prototype crystal library, match_supercells
                        commensurate-cell search, add_adsorbate)
  runner.py             execution layer, local + remote: mpirun invocation,
                        SLURM/PBS submit scripts, and all SSH/remote machinery
                        (see "Execution model — local vs remote")
  remote_setup.py       interactive remote-machine onboarding: SSH key
                        provisioning, connection verify, save to config/UI store
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

## Execution model — local vs remote

Every calculate path — plain run, convergence scan, chained workflow, resume —
must stay available on **both** the local machine and any configured remote
(standing rule, see Development conventions). This section is the map of which
function owns which side; the historical how-we-got-here notes stay in the
changelog below.

### Local

Jobs run in a numbered dir under `jobs_root` (`<NNNN>_<case>`).

| concern | function |
|---|---|
| launch VASP / QE / ASE | `runner.run_vasp` / `run_qe` / `run_ase` — thin `mpirun` subprocess wrappers; `on_progress` streams run.log |
| one case | `workflow.run_one_case` |
| convergence scan | `convergence.converge_scf_case` |
| chained workflow | `chain.run_workflow_case` |
| resume in place | `workflow.resume_job` (CONTCAR→POSCAR, WAVECAR/CHGCAR kept warm, no new job number) |
| local queue submit | `runner.submit_job` + `write_submit_script` (`scheduler: slurm\|pbs` writes submit.sh, `sbatch`/`qsub` from this host), `poll_job_status` |
| results | UI `_scan_result_jobs` builds rows straight from job dirs on disk |

### Remote

**Machine list (shared UI + CLI):** a `remote:` block or `remotes:` map in
config.yaml, merged with the UI Remote-tab's `remotes.json` by
`config_loader.load_ui_remotes` — one inventory for `--remote NAME` and the UI;
never duplicate a machine into config.yaml. `remote_setup.py` (interactive
`python -m vasp_auto.remote_setup`) provisions the SSH key and saves the entry.
Machine keys: host, user, port, ssh_key, ssh_options, remote_root,
vasp_executable (a directory means `<dir>/vasp_std`), env_setup, run_mode,
scheduler (+scheduler_options), potcar_root.

**Three run modes** (per-machine `run_mode:`, resolved by
`runner.resolve_remote_run_mode`; `scheduler: ssh|none|local` ⇒ direct ssh):

| mode | what happens | laptop-off safe |
|---|---|---|
| scheduler (`slurm`/`pbs`) | inputs rsync'd, `sbatch`/`qsub` over SSH — `submit_job_remote` | yes (queue owns it) |
| `ssh` (direct) | synchronous `mpirun` over SSH, results rsync'd back — `run_vasp_remote` is a drop-in for `run_vasp` | no |
| `ssh_detached` (offload) | the whole engine runs remotely under `setsid` — `submit_job_detached` ships an inputs bundle + generated config; one-time `setup_remote_engine` (`--remote-setup`) pip-installs the wheel into `<remote_root>/.vasp_auto/venv` | yes |

**Dispatch points** (where local vs remote is decided): `cli._process_case`
resolves `remote` once at the top; `ssh_detached` short-circuits to
`_run_detached_offload` (cli.py:2295), which forwards the calc flags via
`_forward_calc_flags` so the remote CLI re-branches — convergence and workflows
"just work" remotely. Otherwise the choice between `run_vasp` and
`run_vasp_remote` is made per run/step/trial in `workflow.run_one_case`
(workflow.py:703), `chain.py:192`, and `convergence.py:163` (`remote_subdir`
keeps trials from different cases from colliding). Scheduler-mode chained
workflows are rejected with a clear error; NEB/TSS offload is not supported yet
(needs a single POSCAR).

**runner.py remote inventory:**
- transport: `remote_command`, `_transfer_dir` (rsync, scp fallback),
  `fetch_remote_file`, `read_remote_text` (200 KB cap; POTCAR/binaries never
  printed), `check_remote_connection`
- submit/run: `submit_job_remote`, `run_vasp_remote`, `submit_job_detached`
- offload engine: `build_engine_wheel`, `setup_remote_engine`,
  `remote_engine_installed`
- track/fetch: `poll_remote_job`, `poll_detached_job`,
  `resolve_detached_job_dir`, `fetch_remote_results` (heavy binaries skipped
  unless asked)
- browse: `list_remote_jobs` (one-round-trip POSIX-sh walk; rows carry
  status + `calculation_type`/`converged`/`energy_eV` so remote rows fill the
  same Results columns as local ones), `list_remote_dir`, `list_remote_cases`
- resume: `resume_job_remote` (synchronous, in place, nothing re-shipped),
  `resume_job_detached` (setsid + control dir, power-off safe)
- job control: `kill_job_by_dir` (SSH kill by `.pid` group + cwd-matched
  processes), `kill_detached_job` (offload setsid group, rc=143),
  `delete_remote_dir` (rm -rf; caller must guard with
  `_assert_under_remote_root`), `clear_remote_terminated`

**State and markers:** every remote run writes `.remote.json` into the local
job dir (machine, mode, job_id/pid, remote_dir/control_dir); `build_row` and
the UI read it. Detached runs number their own job dir on the remote
(`<remote_root>/results/<NNNN>_<case>`), recorded through
`VASP_AUTO_JOBDIR_FILE` → `<control_dir>/job_dir` and resolved back by
`resolve_detached_job_dir`. `env_setup` (e.g.
`source /opt/intel/oneapi/setvars.sh`) is sourced before every remote command
so MKL/MPI resolve in non-interactive shells.

**POTCAR:** ssh/scheduler modes rsync the locally built job dir, POTCAR
included. Offload ships a locally pre-built POTCAR in the bundle — unless the
machine sets `potcar_root`, in which case the remote builds its own from its
library.

**UI:** the Remote tab manages machines (`/api/remotes`,
`/api/remote/{save,delete,test,status,fetch,setup}`); Calculate and Workflow
tabs have run-on-machine selectors; the Results tab has a machine selector
("All machines" aggregates local + every remote in the browser), a live remote
job/file browser with per-file view/download (`/api/remote/jobs`,
`/api/remote/files`, `/api/filetext`, `/download_remote` — constrained to the
machine's `remote_root`), and `_analysis_dir` fetches a remote job into a local
cache (`ui_logs/remote_results/<machine>/…`) so every analysis viewer
(DOS/PDOS/bands/volume/report) works on remote jobs unchanged.

**Caveat:** detached offload records the *wrapper's* return code — `rc=0` does
not mean VASP succeeded. When a job "didn't run", read the remote `run.log`
under the control dir.

**QE parity:** `engine: qe` works through all three modes (pw.x on the
remote); the `.engine` marker file travels with the job.

**"What's running now" (cross-machine):**
`runner.list_running_jobs(config, running_only=True, machine=None)` aggregates
a local `jobs_root` scan (`_local_job_rows`, a pure-Python mirror of the
`list_remote_jobs` shell walk) with each configured remote's
`list_remote_jobs`; `machine=` narrows to `"local"` or one remote name (the
Running tab's selector — "Local" never opens SSH). A machine that is
unreachable or has no `remote_root` is collected into `errors` instead of
aborting the listing. Surfaced as CLI `--list-jobs` (`--all` includes
done/prepared) and the UI **Running** tab (GET `/api/running`,
`?all=1&machine=NAME`), which auto-refreshes over SSH only while open and has
a per-row 🛑 (see job control below).

**Job status is a liveness check, not file existence.** A job dir reads:

| status | meaning |
|---|---|
| `running` | something is *actually alive*: the PID recorded in `<job>/.pid` exists (`kill -0`), **or** a live process has its cwd inside the job dir (one `/proc/*/cwd` snapshot per scan — catches NEB/convergence subdir work and jobs with no `.pid`) |
| `done` | genuinely finished per `workflow.job_finished`: `job.log` (written by `run_one_case` *before* `build_row`, so the returned row is already "done"), the OUTCAR `General timing` footer (legacy runs), QE `JOB DONE.`, or `ase_results.json` |
| `stalled` | output or a `.pid` exists but nothing is alive — crashed or killed outside the app; kept on the Running board so dead jobs don't vanish |
| `terminated` | stopped through the app (a `.terminated` marker in the job dir) |
| `prepared` | inputs only, never started |

The same rule lives in three places so every view agrees: `_local_job_rows`
(local Python), the `list_remote_jobs` POSIX-sh walk (checked *on* the remote,
so PIDs are never misread across machines), and `workflow.terminal_status`
(Results rows via `build_row`). `run_one_case` writes `.pid` around every
engine run (vasp/qe/ase and the remote-ssh wrapper) and clears it on return;
rows carry `pid` and the UI shows it (Running rows, job-chip tooltips).

**Job control — terminate / delete / resume. The UI drives local AND every
remote machine identically:** one endpoint per action; the row's `machine`
field selects the side, and the server acts over SSH for remote rows.

| action | local | remote | surfaced as |
|---|---|---|---|
| terminate | `server._kill_local_job`: `os.killpg` of the `.pid` group + SIGTERM every process whose cwd is in the dir (`workflow.pids_in_dir`) | `runner.kill_job_by_dir` over SSH — same two signals, works for jobs this host never launched; detached offload via `runner.kill_detached_job` (setsid group from the `.remote.json` PID, stamps `rc=143` so polls read completed) | POST `/api/terminate` `{job_dir[,machine]}` — Running-tab 🛑 per row (on a `stalled` row it just drops `.terminated` to clear the board), Results bulk 🛑; CLI `--kill JOB_DIR` (detached offload) |
| delete folder | `shutil.rmtree`, strictly inside `jobs_root` | `rm -rf` over SSH via `runner.delete_remote_dir`, strictly inside that machine's `remote_root` (`_assert_under_remote_root`; the boundary comes from server config, never the client — root itself and `..` refused) | POST `/api/job_delete` `{job_dir[,machine]}` — Results bulk 🗑 |
| resume in place | `--resume-job-dir` (newest CONTCAR, own INCAR/KPOINTS/POTCAR, no new job number) | a remote-browsed dir resumes on its machine (`--remote-config`; offload machines resume detached + `--resume-local-mirror`); `runner.clear_remote_terminated` removes a stale marker first | POST `/api/resume_job` `{job_dir[,machine,cpus]}` — Results bulk ▶ |

The Results tab has a checkbox per row — local **and** remote-browsed rows —
feeding a bulk-action bar (▶ Resume / 🛑 Terminate / 🗑 Delete folder);
remote rows send `{machine, job_dir}` so the same endpoints run over SSH.
UI job chips (`_spawn_cli_job`) start their own session
(`start_new_session=True`) so the ✕ stop kills the whole mpirun/vasp tree via
`os.killpg`, not just the CLI wrapper. Markers: `.pid` (live), `.terminated`
(app-killed). Caveat: jobs started before `.pid` existed can still be
terminated through the cwd match, but only while a process is alive in the dir.

---

## Known problems (as of 2026-07-03)

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
> A fourteenth pass (2026-07-03) fixed the **adsorbate builder for molecules**:
> `--adsorbate "CO2@12+2.0"` and the Build-tab quick-build used to add one atom
> *named* "CO2" instead of a molecule. `ase_tools.molecule_positions(name)` now
> returns the ASE `molecule()` geometry (CO2/H2O/NH3/CH4…, lowest atom at z=0;
> single-atom fallback for a bare element), and `structure.add_adsorbate` places
> **every** atom of it (a bare element in `COVALENT_RADII` still takes the
> no-ASE single-atom path) — fixing all callers at once (CLI, `/api/build`,
> `nl_builder`, `nl_agent`). New server route `/api/molecule` feeds the JS
> quick-build (`adsorptionBuild` fetches the geometry and pushes all atoms).
> Test: `test_add_adsorbate_molecule_places_all_atoms`.
> A fifteenth pass (2026-07-03, in the working tree) added a **DFT+U group to
> the INCAR catalog** (`incar_catalog.py`: LDAU/LDAUTYPE/LDAUL/LDAUU/LDAUJ/
> LMAXMIX with plain-language options, per-species vectors in POSCAR order)
> and made **remote result rows match local columns**: the `list_remote_jobs`
> POSIX-sh walk now also emits calc type (scf/convergence/tss), a
> reached-required-accuracy converged flag, and the last OSZICAR `E0=` energy,
> parsed into `calculation_type`/`converged`/`energy_eV` per row.
> `tests/test_remote_analysis.py` covers the remote analysis cache
> (`_analysis_dir` → `ui_logs/remote_results/<machine>/…`). 439 tests.
> A sixteenth pass (2026-07-03) added a **cross-machine "what's running now"
> view**: `runner.list_running_jobs(config)` aggregates a local jobs_root scan
> (`_local_job_rows`) + every configured remote's `list_remote_jobs`, filtered
> to running, with unreachable machines collected into `errors`. CLI
> `--list-jobs` (`--all` for done/prepared too) and the UI **Running** tab
> (GET `/api/running`, auto-refresh only while open). See *Execution model —
> local vs remote*. Tests: `test_list_running_jobs_*` in `tests/test_runner.py`;
> 441 tests.
> A seventeenth pass (2026-07-03) built **job control across machines — real
> status, terminate, delete, resume; the UI drives local + every remote the
> same way**. Status became a *liveness check, not file existence*: every
> engine run records its PID in `<job>/.pid` (workflow `_write_pid`/
> `_clear_pid` around vasp/qe/ase and the remote-ssh wrapper) and a job reads
> "running" only if that PID is alive or a live process has its cwd inside the
> dir (`workflow.proc_cwds`/`dir_active`; one `/proc` snapshot per scan; same
> rule in `_local_job_rows`, the `list_remote_jobs` shell walk — evaluated on
> the remote — and `workflow.terminal_status`). "done" needs a genuine finish
> signal (`workflow.job_finished`: `job.log` — now written *before*
> `build_row` — OUTCAR `General timing`, QE `JOB DONE.`, `ase_results.json`;
> test fixtures gained the real footers); dead-without-finishing reads
> "stalled" (kept on the board); app-killed jobs leave `.terminated` →
> "terminated". **Terminate**: POST `/api/terminate` (Running-tab 🛑 per row,
> Results bulk 🛑, CLI `--kill JOB_DIR` for detached offload) — local kill is
> killpg(`.pid`) + SIGTERM of cwd-matched PIDs (`workflow.pids_in_dir`);
> remote kill is `runner.kill_job_by_dir` over SSH (same two signals) or
> `kill_detached_job` for offload markers (setsid group, stamps rc=143).
> **Delete**: POST `/api/job_delete` — `shutil.rmtree` strictly inside
> `jobs_root`, or `rm -rf` over SSH strictly inside the machine's
> `remote_root` (`_assert_under_remote_root`; boundary from server config,
> never the client). **Resume**: POST `/api/resume_job` resumes one dir in
> place — local, detached offload (local mirror), or a dir browsed on a
> remote (`--remote-config`), clearing stale `.terminated` first. UI: Results
> rows (local *and* remote-browsed) got checkboxes + a bulk bar (▶/🛑/🗑);
> the Running tab got a machine selector (`/api/running?machine=`; "Local"
> never SSHes), per-row PID display, and 🛑; job chips spawn with
> `start_new_session=True` so ✕ kills the whole mpirun tree (`os.killpg`).
> Also fixed: a NUL byte my own edit had left in `index.html` (made grep
> treat it as binary). Tests: 441 (list-jobs/status tests reworked for the
> new semantics; kill/delete/resume verified end-to-end incl. running the
> remote shell walk locally through bash).

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

### 7 — No workflow chaining — FIXED 2026-06-11

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

**Remote execution** — machine config, the three run modes
(scheduler / `ssh` / `ssh_detached` offload), remote resume, POTCAR shipping,
markers, and the UI surface are documented in **Execution model — local vs
remote** above. History: remote scheduler submission `--remote` 2026-06-15;
direct-SSH `run_mode: ssh` 2026-06-17 (fixed convergence/workflow silently
running locally when a remote was selected); detached offload
`run_mode: ssh_detached` 2026-06-18 (verified live on apl2 + tlclab); resume
in place (local, ssh, detached; `--resume`/`--resume-job-dir`, UI ⏯)
2026-06-30 — that pass also gave the Save-structure card a location 📁 picker
(`sv-loc`/`saveBrowse`, local or remote over SSH). CLI selectors: `--remote`
uses `remote:`, `--remote NAME` uses `remotes[NAME]`, `--remote-config FILE`
loads one machine from JSON/YAML (the UI uses this). Tests:
`tests/test_runner.py`, `tests/test_workflow.py`, `tests/test_cli_offload.py`.

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

> **Results: remote machine browser + per-file downloads (2026-06-18):** see
> the Remote half of *Execution model — local vs remote* (machine selector,
> `list_remote_jobs`/`list_remote_dir`/`fetch_remote_file`, `/download_remote`,
> job-detail modal with ⬇ links and ↘ folder navigation). Tests:
> `tests/test_runner.py` + `tests/test_ui_server.py`; 391 total, selfcheck 55/0.

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
- `runner.py` owns *execution* (local subprocesses + everything SSH/remote);
  calculation logic lives in `workflow.py` or `convergence.py`. Don't put
  parsing or INCAR logic in runner.py, and don't put SSH calls anywhere else.
- Every calculate function must work on both the local and remote machines
  when you modify or add one — wire all three remote run modes or reject them
  with a clear error (see "Execution model — local vs remote").
- Same rule for **job control**: status, terminate, delete, and resume must
  work from the UI on the local machine *and* every saved remote through one
  endpoint each (`/api/terminate`, `/api/job_delete`, `/api/resume_job`,
  `/api/running?machine=`) — the row's `machine` field selects the side.
  Job status must reflect real liveness (`.pid` / process-cwd), never mere
  file existence. Destructive remote paths are validated against the
  machine's `remote_root` (`_assert_under_remote_root`), local ones against
  `jobs_root` — the boundary always comes from server config, never the client.
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

### ML / MLIP
- [ ] fairchem-core 2.21.0 is installed; UMA weights are gated on Hugging Face.
      Once an HF token is available, run a UMA relax on `inputs/Au13_uma`
      (`--ml-model uma-s-1p1 --ml-task omat`) and compare against EMT and the
      DFT minimum (−27.33 eV).

### Done
- [x] 2026-06-11 — GUI layer (`vasp_auto_ui`) shipped; see Architecture notes.
- [x] 2026-06-11 — Known problems #1–#14 fixed (see list above).
- [x] 2026-06-18 — Remote / multi-machine control: submit, poll, fetch, browse
      files across saved machines from CLI + UI; Workflow tab runs on the
      chosen remote. See *Execution model — local vs remote*.
- [x] 2026-06-18 — Results page rebuild: date-sorted, machine filter with
      "All machines", search/date-range/per-page filters, inline file view +
      downloads, energy chart removed, analysis cards hidden until invoked.
- [x] 2026-07-03 — Remote result rows carry calculation_type/converged/
      energy_eV so the Results columns match local rows.
- [x] 2026-07-03 — Cross-machine "what's running now": CLI `--list-jobs` +
      UI Running tab (`runner.list_running_jobs`, `/api/running`).
- [x] 2026-07-03 — Job control across machines, UI drives local + every
      remote: real liveness status (`.pid` + `/proc` cwd →
      running/stalled/terminated/done, PID shown), terminate / delete folder /
      resume from the Results bulk bar and the Running tab's per-row 🛑,
      machine selector on Running, CLI `--kill`. Guards: `jobs_root` /
      `remote_root`. See *Execution model — local vs remote → Job control*.


Push the code once a week to the Github: https://github.com/MikeCheng423/DFT-UI
