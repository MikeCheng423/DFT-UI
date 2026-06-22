# vasp_auto — Capabilities Reference for Research Planning

This document describes what `vasp_auto` can do so that an AI assistant can help
a researcher design and execute a complete DFT study without writing VASP input
files by hand.  Every feature maps to a concrete CLI flag or web-UI action.

---

## 1. Supported Calculation Types

`--calc-type <type>` selects a pre-built INCAR template.  All types can be
chained in a single automated workflow (see §6).

| Type | Purpose |
|---|---|
| `scf` | Single-point total energy at a fixed geometry |
| `relax` | Geometry optimisation (IBRION=2, NSW>0) |
| `dos` | Density of states (requires prior SCF/charge step) |
| `bands` | Band structure along a k-path (requires prior charge step) |
| `charge` | Writes CHGCAR/CHGCAR for downstream dos/bands |
| `neb` | Nudged-elastic-band / transition-state search |
| `md` | Ab-initio molecular dynamics |
| `phonon` | Phonons via DFPT (IBRION=8; needs tight relaxation first) |
| `hse06` | Hybrid HSE06 functional (accurate band gaps, slower) |
| `freq` | Vibrational frequencies → ZPE and Gibbs corrections |
| `optics` | Frequency-dependent dielectric function / optical absorption |
| `workfunction` | Planar-averaged electrostatic potential of a slab |

---

## 2. Structure Building

vasp_auto can build any starting geometry without external tools.

### 2a. Prototype crystals (no dependencies)

```bash
vasp-auto --build-prototype graphene           # graphene, a=2.46 Å
vasp-auto --build-prototype rutile-TiO2        # rutile, a=4.59 c=2.96 Å
vasp-auto --build-prototype "graphene:a=2.46,vacuum=18"
# also: graphite, anatase-TiO2, hBN
```

### 2b. ASE-backed builders

```bash
# Bulk crystal
vasp-auto --ase-build-bulk Al --ase-crystalstructure fcc --ase-a 4.05

# Surface slab
vasp-auto --ase-build-slab Al --ase-miller 1,1,1 --ase-layers 5 \
          --ase-vacuum 15 --ase-repeat 3x3

# Isolated molecule in a box
vasp-auto --ase-build-molecule H2O --ase-box 14

# Crystal from space-group + Wyckoff basis
vasp-auto --ase-build-crystal "Na Cl" --ase-spacegroup 225 \
          --ase-basis "0,0,0;0.5,0.5,0.5" --ase-a 5.64

# Single-wall nanotube
vasp-auto --ase-build-nanotube C --ase-nt-n 5 --ase-nt-m 5 --ase-nt-length 3

# Import any ASE-readable file (CIF, XYZ, CONTCAR, …)
vasp-auto --ase-import structure.cif --ase-format cif
```

### 2c. Structure manipulation (composable, pure Python)

```bash
--supercell 2x2x2          # expand
--vacancy 12               # remove atom 12
--substitute 12=Mg         # replace atom 12 with Mg
--interstitial "H@0.5,0.5,0.5"   # add atom at fractional position
--adsorbate "O@12+2.0"     # place O 2 Å above atom 12
--delete "z>0.6"           # delete top half (e.g. for charge-diff fragments)
--move-atom "5@0.5,0.5,0.6"      # reposition atom 5
--scale-cell 1.02          # isotropic cell expansion
--freeze "z<0.3:XY"        # freeze bottom layers in x,y (selective dynamics)
--combine PATH --combine-mode stack --combine-gap 2.0   # deposit one slab on another
--match-cells PATH         # find commensurate supercell pairs before combining
```

---

## 3. KPOINTS Control

```bash
--kpoints-mode gamma       # Gamma-centred uniform mesh
--kpoints-mode mp          # Monkhorst-Pack
--kmesh 6x6x1              # explicit mesh; "6" means 6x6x6
--kspacing 0.25            # density in 1/Å (VASP KSPACING convention)
--kpoints-mode line --kpath fcc --kpath-divisions 30   # band-structure path
--kpath "G 0 0 0; X 0.5 0 0; M 0.5 0.5 0"            # custom k-path
--kpath auto               # heuristic lattice-type detection → preset path
```

---

## 4. Convergence Testing

Run before production calculations to choose ENCUT, SIGMA, NELM, and k-mesh.

```bash
# Full convergence scan (ENCUT → SIGMA → NELM → KPOINTS)
vasp-auto inputs/Al --converge-scf \
    --converge-encut 300,350,400,450,500 \
    --converge-sigma 0.2,0.1,0.05,0.02 \
    --nelm-values 40,60,80,100 \
    --kpoints-values "3,4,5,6,7" \
    --energy-tol 1e-4 --sigma-tol 1e-3 \
    --reuse-wavecar        # seed each trial with the previous WAVECAR
```

Convergence is also a first-class **workflow step** (see §6):

```bash
--workflow "converge,relax,scf,dos"
# The converge step runs the scan and passes the chosen
# ENCUT/SIGMA/NELM/KPOINTS into all subsequent steps automatically.
```

---

## 5. Spin Polarisation and Magnetic Systems

```bash
--spin                         # ISPIN=2, auto MAGMOM from element defaults
--magmom "Fe:5.0,O:0.6"       # explicit per-element moments
# or set magmom_map: in config.yaml for project-wide defaults
```

---

## 6. Chained Workflows

Multi-step calculations with automatic file passing (CONTCAR → POSCAR,
CHGCAR for dos/bands) in a single command:

```bash
# Common patterns
vasp-auto inputs/Fe --workflow "relax,scf,dos"
vasp-auto inputs/Fe --workflow "converge,relax,scf,dos"
vasp-auto inputs/TiO2_slab --workflow "relax,scf,dos,bands"

# workflow.yaml in the case directory gives per-step INCAR/KPOINTS overrides:
# steps:
#   - type: converge
#     encut: [400,450,500]
#     sigma: [0.1,0.05]
#   - type: relax
#     incar: {EDIFFG: -0.01}
#   - type: scf
#   - type: dos
#     incar: {NEDOS: 3000, LORBIT: 11}
```

---

## 7. Running Jobs

```bash
# Local, serial
vasp-auto inputs/Al -n 8

# Local, parallel (multiple cases at once)
vasp-auto inputs/ -n 8 --parallel 4

# Submit to SLURM/PBS queue
vasp-auto inputs/Al --scheduler slurm -n 32

# Remote machine (copies inputs over SSH, submits to remote queue, then exits)
vasp-auto inputs/Al --remote cluster1 -n 64

# Background (detach, write logs to vasp_auto_background_logs/)
vasp-auto inputs/ --background
```

Error recovery:

```bash
--auto-retry 3      # apply known INCAR fix for detected VASP error, re-run up to 3×
--retry-failed      # rerun only the cases that previously failed
--poll JOBID        # query queue status of a submitted job
```

---

## 8. Machine-Learning Pre-Relaxation (optional)

Speeds up VASP relaxation by starting from an MLIP-relaxed geometry.

```bash
# Quick screen (read-only, no VASP)
vasp-auto --ml-energy inputs/Al --ml-model emt

# Pre-relax with Meta OMat24/UMA, then continue to DFT
vasp-auto inputs/Al --ml-relax --ml-model uma-s-1p1 --calc-type relax

# Pre-relax only (no VASP), EMT demo backend (no fairchem needed)
vasp-auto inputs/Al --ml-relax --ml-model emt --ml-only
```

---

## 9. Transition-State Search (NEB)

```bash
# Case layout: TSS/cases/A/initial/POSCAR + TSS/cases/A/final/POSCAR
vasp-auto TSS/cases/A --calc-type neb --neb-images 7 --ase-neb

# After the run, plot the minimum-energy path:
# GET /api/neb  →  forward/backward barriers, ΔE, per-image energies
```

---

## 10. Post-Processing and Analysis

All commands below are read-only (no VASP is run); they parse finished job dirs.

### Electronic structure
```bash
vasp-auto --dos-export jobs/Fe_dos         # → dos.csv, pdos.csv
vasp-auto --bands-export jobs/Fe_bands     # → bands.csv with k-labels
```

### Catalysis and surface science
```bash
# Adsorption energy:  E(slab+ads) − E(slab) − scale × E(mol)
vasp-auto --adsorption-energy "jobs/PtH,jobs/Pt,jobs/H2" --molecule-scale 0.5

# Vibrational thermochemistry (from a --calc-type freq job)
vasp-auto --thermo jobs/PtH_freq --temperature 298.15
# prints: vibrational modes, ZPE, T*S, Gibbs correction

# Work function (from a --calc-type workfunction job on a slab)
vasp-auto --work-function jobs/Pt_wf       # V_vacuum − E_Fermi

# d-band center and width (from a dos job with LORBIT=11)
vasp-auto --d-band "jobs/Pt_dos:z>0.5" --d-band-emax 0
```

### Charge density
```bash
# Charge-density difference rho(AB) − rho(A) − rho(B)
vasp-auto --chg-diff "jobs/AB,jobs/A,jobs/B"    # → CHGCAR_diff

# Bader charge analysis (needs Henkelman bader binary)
vasp-auto --bader jobs/AB                        # → bader_charges.csv
```

### Optics
```bash
# Absorption coefficient α(E) from a --calc-type optics job
vasp-auto --optics-parse jobs/TiO2_optics        # → absorption.csv
```

### Solvation
```bash
# Implicit solvent (requires VASPsol-patched VASP binary)
vasp-auto inputs/Pt_slab --calc-type scf --solvation --solvation-eps 78.4
```

---

## 11. Output

- **Excel summary** (`jobs/<project>_results.xlsx`) — one row per case:
  total energy, convergence flag, band gap, max force, pressure, magnetisation,
  detected errors, NEB barriers.  Includes an energy bar chart.
- **Markdown report** (`--report` → `jobs/<case>/report.md`) — per-job setup
  and results in a human-readable format.
- **Trajectory animation** — XDATCAR/NEB frames exposed via `/api/trajectory`
  and rendered in the web-UI viewer.
- **NEB minimum-energy path graph** — smooth Catmull-Rom curve, forward/backward
  barriers, CSV/PNG export.

---

## 12. Typical Research Workflows

### A. Bulk property study
1. Build geometry: `--ase-build-bulk` or `--build-prototype`
2. Converge parameters: `--converge-scf --converge-encut … --converge-sigma …`
3. Relax + SCF: `--workflow "relax,scf"`
4. Electronic structure: `--workflow "relax,scf,dos,bands"`
5. Export: `--dos-export`, `--bands-export`

### B. Surface catalysis (adsorption energy + CHE)
1. Build slab: `--ase-build-slab` with vacuum and layers
2. Freeze bottom layers: `--freeze "z<0.3:XY"`
3. Place adsorbate: `--adsorbate "O@12+1.8"`
4. Relax slab+ads, bare slab, and molecule references: `--workflow "relax,scf"`
5. Adsorption energy: `--adsorption-energy`
6. Zero-point + entropy corrections: `--thermo` on a `freq` job
7. d-band analysis: `--d-band` on a `dos` job (LORBIT=11)
8. Charge transfer: `--chg-diff`, `--bader`
9. Work function (if needed): `--calc-type workfunction --work-function`

### C. Transition-state search
1. Optimise reactant and product structures (`--workflow "relax,scf"`)
2. Set up NEB case (`initial/POSCAR`, `final/POSCAR`)
3. Run: `--calc-type neb --neb-images 7 --ase-neb`
4. Plot MEP and extract barriers: `/api/neb` or results table 📉 button

### D. Heterostructure / van-der-Waals stacking
1. Build each layer: `--build-prototype graphene`, `--build-prototype rutile-TiO2`
2. Find commensurate supercells: `--match-cells PATH --match-max 6 --match-strain 0.05`
3. Stack: `--combine PATH --combine-mode stack --combine-gap 3.2`
4. Relax: `--workflow "relax,scf"`
5. Charge redistribution: `--chg-diff`

### E. Optical / optoelectronic properties
1. Converge + relax: `--workflow "converge,relax"`
2. Hybrid SCF for accurate gap: `--calc-type hse06`
3. Optical spectrum: `--calc-type optics` → `--optics-parse`
4. (Optional) solvation correction: `--solvation --solvation-eps 80`

---

## 13. Configuration

`config.yaml` (project root) controls defaults; per-case or per-project
overrides via a local `config.yaml` in the case/project directory.

Key settings:
```yaml
vasp_executable: /path/to/vasp_std
jobs_root: /path/to/jobs
potcar_root: /path/to/POTCAR_library
neb_images: 7
scheduler: slurm          # local | slurm | pbs
potcar_map:               # pseudopotential variants
  Fe: Fe_pv
  O: O_s
magmom_map:               # default magnetic moments
  Fe: 5.0
  Ni: 5.0
ml_model: uma-s-1p1       # MLIP model
bader_executable: bader   # Henkelman binary
workflow: "relax,scf,dos" # default chain when --workflow not given
remote:                   # default SSH remote machine
  host: cluster.example.com
  remote_root: /scratch/user
  vasp_executable: vasp_std
  scheduler: slurm
```

---

## 14. Web UI (vasp-auto-ui)

Start with `vasp-auto-ui` (default port 8800, localhost only).  The UI wraps
every engine function above in a point-and-click interface:

- **Build tab** — searchable catalogue of all structure builders; 3D canvas
  viewer with drag-move, bond/label/axes overlays, POSCAR panel, undo/redo.
- **Calculate tab** — pick case + calc type + workflow + convergence settings;
  run on local machine or a remote machine selected from the Remote tab.
- **Workflow tab** — preset chains (Converge→Relax→SCF→DOS, NEB, etc.)
  or custom YAML steps.
- **Results tab** — reads the `jobs/` folder directly; per-row buttons for
  report, DOS, PDOS, bands, volumetrics, trajectory, NEB MEP graph, remote
  status/fetch.
- **Remote tab** — manage SSH machines, test connection, poll jobs, pull
  results back.

---

## 15. Asking Claude to Make a Research Plan

When you share this document with Claude, describe your research goal and
provide:

1. **System**: elements, crystal structure or prototype name, bulk/slab/molecule.
2. **Property of interest**: total energy, band gap, adsorption energy, work
   function, reaction barrier, phonon spectrum, optical absorption, etc.
3. **Conditions**: spin-polarised?, hybrid functional?, solvation?, temperature?
4. **Computational resources**: local VASP, SLURM cluster, number of CPUs.
5. **What you already have**: finished relaxations, existing POTCAR library,
   config.yaml settings.

Claude will propose a concrete sequence of `vasp-auto` commands (or web-UI
steps) covering structure building → convergence → production run(s) →
post-processing, with the rationale for each choice.
