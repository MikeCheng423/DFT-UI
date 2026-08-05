# vasp-auto

Automated preparation, execution, and parsing of **VASP** DFT calculations —
plus open-source backends: **Quantum ESPRESSO** (`engine: qe`) and **any ASE
calculator** (`engine: ase`). Comes with a command-line tool, a local web UI
(structure builders, job console, results browser), and one-command offloading
to remote clusters.

vasp-auto is built around a **two-machine model**:

- **Control machine** (your laptop/workstation) — the web UI, structure builders,
  results/Excel parsing, and SSH orchestration. Install the full stack here.
- **Remote compute node** (an HPC login/compute node) — a *lean engine* that runs
  VASP or Quantum ESPRESSO. Install just the engine here; no UI or heavy dependencies.

The two installs are separated by pip *extras* so each machine pulls only what it
needs. See **[docs/INSTALL.md](docs/INSTALL.md)** for the full matrix.

---

## Install

Requires Python ≥ 3.12.

### Control machine (full stack)

```bash
git clone https://github.com/MikeCheng423/DFT-UI vasp-auto
cd vasp-auto
python -m venv venv && source venv/bin/activate
pip install -e ".[local]"        # UI + structure builders + Excel results
```

Then start the web UI:

```bash
vasp-auto-ui                     # opens http://localhost:8800
```

### Remote compute node (lean engine)

On the cluster, install only the engine — runs VASP, depends on `PyYAML` alone:

```bash
pip install -e .                 # or:  pip install -e ".[remote]"
```

In most cases you don't install on the remote by hand at all: from the control
machine, `vasp-auto-setup-remote` (or the UI Remote tab) **builds an engine wheel,
ships it over SSH, and creates a venv on the remote for you**, so offloaded
("detached") jobs run on the cluster while your laptop is off.

> **VASP licence / POTCAR:** VASP and its POTCAR pseudopotentials are proprietary
> and are **not** included in this repository. Point `potcar_root` in `config.yaml`
> at your own licensed POTCAR library. Quantum ESPRESSO (`engine: qe`) is free.

---

## Configure

```bash
vasp-auto --init                            # create config.yaml from the example
#                                           # (or by hand: cp config.yaml.example config.yaml)
```

Then edit `config.yaml` and set the three paths for your machine:
`vasp_executable` (your VASP binary), `potcar_root` (your licensed POTCAR
library), and `jobs_root` (where job folders are written).

```bash
cp remotes.json.example remotes.json        # optional: or add machines in the UI
```

Both `config.yaml` and `remotes.json` are git-ignored so your local paths and
private cluster details never get committed.

---

## Quickstart (CLI)

The repo ships a ready-made case, `example/Si` (a silicon POSCAR), so these run
against a real structure straight after install — put your own cases under
`inputs/`:

```bash
vasp-auto example/Si --prepare              # build INCAR/KPOINTS/POTCAR + job dir
vasp-auto example/Si -n 8 --background      # run on 8 cores, return immediately
vasp-auto example/Si --remote mycluster     # prepare + submit to a remote queue

# Quantum ESPRESSO uses the same commands and job layout
vasp-auto example/Si --engine qe --prepare
vasp-auto example/Si --engine qe --calc-type phonon --remote mycluster
```

### Quantum ESPRESSO feature parity

The QE backend supports SCF, relax, variable-cell relax, MD, HSE06, DOS/PDOS,
bands, charge density, phonons/frequencies, optics, work functions, and NEB.
Multi-stage calculations invoke QE's native companion programs (`dos.x`,
`projwfc.x`, `bands.x`, `ph.x`, `dynmat.x`, `epsilon.x`, `pp.x`, `average.x`,
and `neb.x`). Chained workflows, cutoff/smearing/k-point convergence, CLI/UI
analysis, direct SSH, scheduler submission, and detached offload are engine-aware.

QE numerical settings retain QE units and meaning: `ecutwfc` and `degauss` are
Rydberg values and are not converted from VASP `ENCUT` or `SIGMA`. Configure a
consistent UPF library; mixing pseudopotential families or exchange-correlation
functionals invalidates comparisons even when a calculation runs successfully.

A simple SCF case only needs a `POSCAR`; missing `INCAR`, `KPOINTS`, and `POTCAR`
are generated during `--prepare`. Background runs print a log path under
`vasp_auto_background_logs/`; each job's VASP stdout/stderr stays in its `run.log`.

Each run is written to a **numbered job folder** (`jobs/<project>/0001_Fe`,
`0002_Si`, …) using one global counter, so re-running never overwrites an earlier
result. `--retry-failed` and `--parse-only` act on the latest numbered run.

### Transition states (NEB)

A `tss` case holds its two endpoints as `initial/POSCAR` and `final/POSCAR`;
`--prepare` interpolates the images between them.

Endpoints that came from **separate relaxations** usually do not share one atom
ordering — ASE and pymatgen sort species alphabetically, VASP keeps whatever
order it was handed — and a band built from mismatched endpoints is rejected
before it runs. Re-index the final endpoint onto the initial one first:

```bash
python -m vasp_auto.atom_order inputs/A_to_B/initial/POSCAR \
                               inputs/A_to_B/final/POSCAR
# largest displacement per species: Au 0.58 A, C 0.66 A, O 3.11 A, H 3.72 A
```

It matches atoms per species by minimum-image distance and rewrites the target
in place (pass a third path to write elsewhere). **Read the reported
displacements**: one species far above the rest either genuinely moves in the
reaction — the O and H above are an OH group leaving a carbon — or was paired
wrong. Nothing re-indexes automatically for exactly that reason; in the web UI
the same repair is the NEB tab's **⇄ Match atom order** button.

### Automatic SCF convergence

Scan `NELM`, then `KPOINTS` using the best `NELM`:

```bash
vasp-auto inputs/Fe --converge-scf -n 8 \
    --nelm-values 40,60,80,100,120 \
    --kpoints-values 3,4,5,6,8         # a single N → cubic NxNxN

# slabs / low-dimensional: give explicit meshes (keep the c-axis at 1)
vasp-auto inputs/Fe --converge-scf --kpoints-values 3x3x1,5x5x1,7x7x1
```

Trials and a `scf_convergence_report.md` / `.csv` are written under
`jobs/<case>/scf_convergence/`.

---

## Web UI highlights

`vasp-auto-ui` provides a front end:

- **Structure builders** — bulk, surface/slab, molecule, nanotube, space-group
  crystal, Materials Project search, interface combine, adsorption.
- **AI builder** — describe a structure in plain words and a (Groq) LLM turns it
  into an exact ASE-built structure. Bring your own free Groq API key (pasted in
  the UI, kept in your browser). See [docs](docs/).
- **NEB tab** — pick both endpoints (each can live on a different machine), see
  them side by side, and repair mismatched atom ordering with **⇄ Match atom
  order** before building the band.
- **Run an existing folder** (Calculate and NEB tabs) — point at a folder that
  already has inputs and run it as-is, skipping the builder. While that panel is
  open the tab's INCAR editor and a verbatim KPOINTS box read and write *that
  folder* rather than the working case; the editors say which one they target,
  and closing the panel hands them back.
- **Workflow builder, run console, results table** — with remote offload and a
  live remote job/file browser.

---

## Repository layout

```
src/vasp_auto/        engine: prepare/run/parse, convergence, workflow, remote
src/vasp_auto_ui/     local web UI (pure-stdlib server + static front end)
tests/                unit tests (no VASP needed)
selfcheck/            end-to-end checks with fake mpirun/vasp (run in CI)
docs/                 tutorials and reference (incl. INSTALL.md)
example/              small example case(s)
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q                 # unit tests
bash selfcheck/run_selfcheck.sh     # end-to-end with fake binaries
```

## License

Released under the [MIT License](LICENSE). Note that VASP and its POTCAR
pseudopotentials are separately licensed and are **not** distributed here.
