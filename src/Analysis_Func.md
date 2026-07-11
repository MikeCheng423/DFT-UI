# Plan: Analysis tab — local analysis of local **and remote** results (VASP + QE)

## Goal

Give the UI a dedicated **Analysis** tab. Every analysis runs **on the local
machine**; when the job lives on a remote (tlclab, apl2, …) the tab **captures
the result files automatically** and analyzes the local copy. The tab covers
the standard catalyst-discovery toolkit for both VASP and Quantum ESPRESSO
jobs: DOS/PDOS/bands, d-band center, Bader charges, charge-density difference,
spin density, adsorption energy, surface energy, work function, ZPE/Gibbs
corrections, NEB barriers, free-energy diagrams (overpotential), optics,
magnetic moments.

## What already exists — reuse it, don't rebuild it

The remote-capture problem is **already solved** in `vasp_auto_ui/server.py`:

- `_analysis_dir(path, machine, heavy)` (server.py:1068) — local machine:
  returns the path; remote machine: rsyncs the job into
  `REMOTE_RESULT_CACHE/<machine>/<job>-<hash>` via
  `runner.fetch_remote_results` (incremental, heavy files excluded), then
  pulls each named `heavy` file (CHGCAR, LOCPOT, AECCAR…) once on demand.
  Tested in `tests/test_remote_analysis.py`. **This is the capture mechanism.
  Every analysis endpoint routes through it — no new sync layer.**
- Already remote-aware endpoints: `/api/trajectory`, `/api/neb`, `/api/dos`,
  `/api/pdos`, `/api/bands`, `/api/volume`, `/api/thermo`, `/api/dband`,
  `/api/workfunction`, `/api/optics`, `/api/bader`.
- Analysis backends (all local, pure Python except the bader binary):
  - `analysis.py`: `adsorption_energy`, `thermo_from_job` (ZPE/U_vib/T·S/ΔG),
    `d_band_center`, `work_function`, `absorption_spectrum`, `read_job_energy`.
  - `chgcar.py`: `read_volumetric`, `charge_difference`, `charge_sum`,
    `planar_average`, `slice_volume`, `run_bader` (Henkelman binary on
    CHGCAR+AECCAR0+AECCAR2), `bader_net_charges`, `zval_from_potcar`.
  - `parser.py`: `parse_dos`/`parse_pdos`/`parse_bands`/`parse_dielectric`
    (vasprun.xml), `parse_pw_output` + `parse_pw_final_structure` (QE).
  - `py4vasp_tools.py`: DOS/step energies from vaspout.h5 (see memory: h5 has
    no density/step history in 6.4.2 — the vasprun/OSZICAR fallbacks stay).
  - `workflow.job_engine`: `.engine` marker says vasp/qe/ase per job dir.
- UI: the Results tab already holds an "analysis card" (`ana-dir` input,
  `ANA_MACHINE`, per-row 🧪 button) plus DOS/PDOS/bands/volume/chgdiff/NEB/
  trajectory viewers with PNG/CSV export. The new tab is a **reorganization
  plus gap-filling**, not a greenfield build.

## The gaps (what this plan actually adds)

1. **No dedicated tab** — analysis is buried inside Results.
2. **Multi-job analyses ignore remotes** — `/api/chgdiff` and
   `/api/adsorption` take bare local paths, so a charge difference between
   three jobs sitting on tlclab is impossible from the UI today.
3. **QE jobs can't be analyzed** — `read_job_energy` only reads
   OUTCAR/vasprun.xml; there is no QE DOS/bands path.
4. **Missing catalysis functions** — surface energy, free-energy diagram /
   overpotential (CHE), spin density, per-atom magnetic moments.

## Tab design

**Every analysis input is a (path, machine) pair** — one "job slot" widget,
reused everywhere: text input + 📁 local browse + remote job browse
(`/api/remote/jobs` exists) + fill-from-row (the existing 🧪 pattern), with a
machine badge. Multi-job analyses (charge difference, adsorption, surface
energy, ΔG diagram) render N slots. All slots resolve through
`_analysis_dir`, so mixing machines in one analysis (slab on tlclab, molecule
local) just works.

Cards, grouped the way a catalysis user thinks:

| Group | Function | Inputs | Backend | Status |
|---|---|---|---|---|
| Electronic structure | Total DOS | job | `py4vasp_tools.dos` → `parse_dos` | exists; add QE |
| | Projected DOS (element × s/p/d, atom selection) | job + atoms | `parse_pdos`/`aggregate_pdos` | exists (VASP) |
| | Band structure | job | `parse_bands` | exists; add QE |
| | d-band center & width | job + atoms + Emax | `d_band_center` | exists |
| Charge | Bader charges (+CSV) | job | `run_bader` | exists (VASP) |
| | Charge-density difference Δρ = ρ_tot − Σρ_part | total + N parts | `charge_difference` | exists, **local-only → fix** |
| | Spin density ρ↑ − ρ↓ | job | CHGCAR block 2 | **new** |
| | Planar average / 2D slice of any volumetric file | job + file + axis | `/api/volume` | exists |
| Surfaces & adsorption | Adsorption energy E_ads | total + slab + molecule + scale | `adsorption_energy` | exists, **local-only → fix** |
| | Surface energy γ | slab + bulk | — | **new** |
| | Work function W = V_vac − E_F | job (LVHAR) + axis | `work_function` | exists |
| Thermochemistry & reactions | ZPE / U_vib / T·S / ΔG correction | freq job + T | `thermo_from_job` | exists |
| | Reaction barrier (NEB profile) | neb job | `neb_energy_profile` | exists |
| | Free-energy diagram + overpotential (CHE) | ordered steps | — | **new** |
| Optics | Absorption spectrum α(E) | job (LOPTICS) | `absorption_spectrum` | exists |
| Magnetism | Per-atom magnetic moments | job | OUTCAR table | **new** |

## Changes

### 1. Machine-aware multi-job endpoints — the real "capture remote" gap

`/api/chgdiff` and `/api/adsorption` accept `{path, machine}` per job (keep
accepting a bare string = local, so nothing breaks). Each job resolves through
`_analysis_dir`; chgdiff parts use `heavy=("CHGCAR",)`. ~10 lines each. The
UI job slots send both fields. `CHGCAR_diff` is written into the resolved
(cache) dir and remains viewable via the existing volume endpoint.

### 2. QE parity for energies — one dispatch, many analyses unlocked

`read_job_energy` (analysis.py:21): when `job_engine(job_dir) == "qe"`, read
energy + convergence from `parse_pw_output(job_dir / "pw.out")`. That single
change makes adsorption energy, surface energy, and ΔG diagrams
engine-agnostic, because they all sum job energies through this one function.

### 3. QE DOS and bands

`pw.x` writes `<prefix>.save/data-file-schema.xml` with eigenvalues,
occupations, k-points, and Fermi energy. Add a parser (in `parser.py` or a
small `qe_parser.py`): total DOS by Gaussian-smearing the eigenvalues
locally; band plot when the job was a bands-type run. `/api/dos` and
`/api/bands` fall back to it when `job_engine == "qe"`.

Remote fetch: extend `runner.HEAVY_OUTPUTS` with QE wavefunction/density
patterns (`*.save/wfc*.dat`, `*.save/charge-density.dat`, `*.wfc*`) so the
rsync pulls the small XML but not the wavefunctions — today a QE `.save` dir
is not excluded at all and a remote fetch would drag gigabytes.

QE **PDOS and Bader** need `projwfc.x`/`pp.x` post-processing runs — phase 2
(see skipped list); the card shows "needs projwfc.x — not yet wired" for QE
jobs rather than a stack trace.

### 4. Surface energy (new, one formula)

`analysis.surface_energy(slab_dir, bulk_dir)`:
γ = (E_slab − (N_slab/N_bulk)·E_bulk) / (2A), A = |a⃗×b⃗| from the slab POSCAR
(axis parameter, default c ⇒ area from a,b). Atom counts from POSCAR line 7.
Report eV/Å² and J/m² (×16.0218). Uses `read_job_energy` ⇒ VASP + QE for free.

### 5. Free-energy diagram / overpotential (new — the key screening tool)

`analysis.free_energy_diagram(steps, temperature, potential)`: input is an
ordered list of steps, each `{label, energy_source, freq_job?, n_electrons?}`
where `energy_source` is either an explicit ΔE (number) or
`{total, slab, molecule, scale}` job dirs resolved via `adsorption_energy`.
Per step: ΔG = ΔE + ΔZPE − TΔS (from `thermo_from_job` when a freq job is
given) − n·e·U (computational hydrogen electrode). Output: cumulative ΔG
staircase at U=0 and at U, the potential-determining step, limiting potential
U_L = −max(ΔG_i)/e, and overpotential η vs. an equilibrium potential the user
supplies (1.23 V OER default). It is a pure composition of two existing
functions — no new physics parsing. UI card: N step rows (each a job-slot
trio or a typed ΔE), T, U, U_eq → staircase plot + table, PNG/CSV via the
existing export buttons.

### 6. Spin density and magnetic moments (new, small)

- `read_volumetric`: after the first grid block, if a second block follows
  (spin-polarized CHGCAR: ρ↑−ρ↓, incl. its augmentation lines to skip),
  return it as `"spin_data"`. `/api/volume` gains `component=total|spin` and
  reuses `_volume_payload` unchanged.
- `analysis.atom_magnetic_moments(job_dir)`: parse the last
  `magnetization (x)` table from OUTCAR → per-atom s/p/d/tot moments.
  QE: total magnetization line from pw.out (per-atom needs projwfc — phase 2).

### 7. The tab itself

Add nav button **"7 · Analysis"** (Results stays for run summaries/report).
Move the existing analysis card and the DOS/PDOS/bands/volume/chgdiff viewer
cards from Results into it — the JS functions already exist; this is moving
HTML sections and replacing the single `ana-dir`+`ANA_MACHINE` global with the
job-slot component (which fixes today's quirk where typing a path silently
clears the remote machine). Add the four new cards (surface energy, ΔG
diagram, spin density option in the volume card, magnetic moments). Keep the
one shared output pane + PNG/CSV export exactly as-is.

Cache hygiene: show the cache dir size on the tab and add a "clear cache"
button (`rm -rf` of `REMOTE_RESULT_CACHE/<machine>/<job>` via one endpoint) —
volumetric pulls are hundreds of MB per job. One endpoint, one button.

## Steps (ordered; each lands with its test)

1. `read_job_energy` QE dispatch — test with a pw.out fixture (fixtures exist
   in `tests/test_qe.py`).
2. Machine-aware `/api/chgdiff` + `/api/adsorption` — tests mirror the
   monkeypatch pattern in `tests/test_remote_analysis.py`.
3. `surface_energy`, `atom_magnetic_moments`, spin block in
   `read_volumetric` + `component=` in `/api/volume` — unit tests with small
   synthetic CHGCAR/OUTCAR fixtures.
4. `free_energy_diagram` + `/api/gdiagram` — test the staircase math against
   a hand-computed 4-step ORR example.
5. QE DOS/bands parser + endpoint fallbacks + `HEAVY_OUTPUTS` QE patterns —
   test with a minimal data-file-schema.xml fixture.
6. UI: new tab, job-slot component, move existing cards, add new cards.
7. Verify live against tlclab and apl2 (remember: offload rc=0 can mask
   failures — check the fetched run.log, per memory).

## Deliberately skipped

- **COHP/COOP (LOBSTER)** — external binary + WAVECAR transfers; add when a
  user asks for bond analysis.
- **QE PDOS / QE Bader** — require orchestrating `projwfc.x`/`pp.x` runs
  (remote, then fetch cube files); phase 2 once the tab exists.
- **3D isosurface viewer** — planar average + 2D slice cover the screening
  workflow; the fetched CHGCAR/CHGCAR_diff sits in the cache dir for VESTA.
  Add a "download volumetric file" link, not a renderer.
- **Microkinetics / scaling-relation batch screening** — separate project on
  top of the ΔG-diagram backend.
- **STM simulation (Tersoff-Hamann)** — PARCHG is already viewable through
  the volume card; a dedicated card only if asked.
