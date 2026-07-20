# Update memo — 2026-06-30

Changes pushed to `main` in this update, newest first. Tests after the update:
**419 passed, 1 skipped.**

## TL;DR

- **Easier first run** — a ready-made `example/Si` case now ships, and
  `vasp-auto --init` writes your `config.yaml`, so the Quickstart works straight
  after install.
- **Resume unfinished jobs in place** — restart a job from its newest `CONTCAR`
  without a new job number, locally / over SSH / detached on an offload machine,
  via a ⏯ **Resume** button or `--resume` flags.
- **One "working case" in the UI** + the CLI now shares the UI's `remotes.json`.

---

## 1. Smoother first run — `505f10f`

**Why:** a fresh clone could not run the README's own Quickstart. It pointed at
`inputs/Fe`, but `inputs/` is git-ignored and `example/` shipped only INCAR
templates, so the first command failed with *"target not found."* And with no
`config.yaml`, the engine silently fell back to bare defaults (`vasp_std` on
PATH, `./POTCAR`) that fail cryptically.

**What changed:**

- **`example/Si/POSCAR`** — a ready-made silicon case ships with the repo. The
  README Quickstart now uses `vasp-auto example/Si …`. Your own cases still go
  under `inputs/`.
- **`vasp-auto --init`** — copies `config.yaml.example` → `config.yaml` at the
  repo root, never overwriting an existing one, and prints next steps. The
  README *Configure* section leads with it.
- **First-run nudge** — a one-line note (to stderr) when a VASP run starts with
  no `config.yaml` found, pointing at `--init`. Silent for the QE/ASE engines and
  whenever any config (global or per-case) is present.

**How to use:**

```bash
vasp-auto --init                 # create config.yaml, then edit the three paths
vasp-auto example/Si --prepare   # build INCAR/KPOINTS/POTCAR into a job folder
vasp-auto example/Si -n 8        # run on 8 cores
```

Verified end to end: `--dry-run` detects `example/Si` as a single SCF case;
`--prepare` assembles INCAR/KPOINTS and a real Si POTCAR.

## 2. Resume an unfinished job in place — `04733e2`

**Why:** restart a job from the latest geometry VASP wrote, **without** allocating
a new `NNNN_` job number or rebuilding inputs from the case directory.

**What it does:** reuses the job directory's own INCAR/KPOINTS/POTCAR verbatim;
only `POSCAR` advances (`CONTCAR` → `POSCAR`, old kept as `POSCAR.bak`);
`WAVECAR`/`CHGCAR` are left for a warm start; NEB/TSS jobs reseed each image
subdir. A finished job is skipped unless forced.

**Where it lives:**

- Engine: `workflow.resume_job` (local).
- Runner: `runner.resume_job_remote` (synchronous over SSH, nothing re-shipped)
  and `runner.resume_job_detached` (offload machines: re-runs `mpirun` under
  `setsid` with a poll-able control dir, so the local host can power off).
- CLI: `--resume` (latest local job dir for the case) and `--resume-job-dir DIR`
  (explicit dir, local **or** remote; `--resume-local-mirror DIR` records a local
  marker so the UI can track a remote run).
- UI: a ⏯ **Resume** button on the Calculate tab → `/api/resume`, streaming to the
  live log like a normal run.

**Also in this commit:**

- **Working-case UI model** — the Working-case area no longer asks for a
  cases-folder and a case to select. Whatever you **build, import or 💾 Save**
  becomes the working case, and Calculate / Workflow / Remote all act on it. Save
  gained a location 📁 picker.
- **Shared machine list** — `config_loader.load_ui_remotes` folds the UI's
  `remotes.json` into the CLI config, so `--remote NAME` sees machines added in
  the UI (one source of truth, no drift).

---

## Follow-ups (not done in this update)

From the onboarding review, still open:

- A README "UI-first" intro + a screenshot/GIF of the Build → Calculate → Results
  flow.
- Relax `requires-python` for the lean remote engine (clusters often run Python
  3.8–3.11); add lower bounds to dependencies.
- A `vasp-auto doctor` self-check (Python / VASP binary / `potcar_root` / remotes).
