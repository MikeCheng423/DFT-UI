# vasp_auto Improvement Memo

Backlog items remaining after v0.8.0 + tenth-pass additions (as of 2026-06-14).
Items resolved in this release (v0.9.0) are marked DONE.

---

## Done in v0.9.0

- **NEB endpoint fix**: `should_retry_failed` now correctly excludes both the
  first *and* last image directory (not just `00`) from the OUTCAR check.
  `_build_neb_row` tries OUTCAR → OSZICAR → vasprun.xml for endpoint energies
  and includes them in forward/backward barriers.
- **Phonon description**: `CALC_TYPE_INFO[CalcType.PHONON]` now says DFPT /
  IBRION=8 to match the actual `example/INCAR_phonon` template.
- **--ml-energy**: Single-point MLIP screen (`ml_tools.ml_energy`) exposed as
  `--ml-energy TARGET` CLI flag and `POST /api/mlenergy` UI endpoint; read-only,
  no files written.
- **--poll JOBID**: Query a SLURM/PBS scheduler for submitted job status
  (`runner.poll_job_status`); gracefully returns "unknown" when the binary is
  absent. `--poll` with `--scheduler` prints state and exits.
- **--kpath auto**: `kpoints.guess_lattice_type` (pure-Python, no spglib) +
  `auto_kpath` detect lattice type from cell vectors. `--kpath auto` routes
  through this in line mode; raises a clear error for generic lattices.
- **--solvation**: Implicit solvation via VASPsol — `--solvation` injects
  `LSOL = .TRUE.` and `EB_K` (default 78.4 for water) into the INCAR;
  `--solvation-eps` overrides the dielectric constant. Requires a
  VASPsol-patched VASP binary (see MANUAL.md).

---

## Open Items

### 1. Dataclass result rows
`build_row`, `parse_vasprun`, etc. return plain dicts. Converting to typed
dataclasses (or `TypedDict`) would give better IDE support and allow stricter
validation in the GUI layer. The Excel writer's `COLUMN_ORDER` would stay as-is.

### 2. Full symmetry detection beyond the new heuristic
`guess_lattice_type` uses length ratios and dot-product angles — it misses
body-centred tetragonal, rhombohedral, orthorhombic, and other lattice types.
The right fix is an optional `spglib` integration (similar to how ASE handles
space groups) to get the actual Bravais lattice and standard k-path, which then
takes precedence over the heuristic. seekpath or pymatgen could provide the
standard irreducible k-path automatically.

### 3. Phonon band post-processing
`example/INCAR_phonon` uses DFPT (IBRION=8); the OUTCAR contains force
constants. A `phonon_bands` analysis command that reads the force constants and
calls phonopy (optional dep) to compute and plot the phonon dispersion would
close the standard characterisation loop.

### 4. More solvation parameters
`--solvation` currently exposes only `EB_K` (solvent dielectric). VASPsol also
accepts `SIGMA_K` (cavity size), `NC_K` (charge smoothing), `TAU` (surface
tension), and `LRHOB` (reference density). These are less commonly changed but
a `--solvation-params KEY=VAL,...` catch-all would let power users tune them.

### 5. Queue auto-poll loop
`--poll JOBID` performs one synchronous query. A `--poll-wait` flag that
re-polls every N seconds and, when the job finishes, automatically runs
`--parse-only` to harvest results would complete the "submit and forget"
scheduler workflow without manual bookkeeping.

### 6. SLURM/PBS job-array support
Multi-case projects currently use `--parallel N` (local `ThreadPoolExecutor`).
A `--scheduler-array` flag that packs all cases into a single `sbatch
--array=0-N` job with case-index dispatch would use the cluster scheduler's
own fairshare policy and avoid saturating local memory.

### 7. Charged-slab / uniform background correction
Calculations on charged systems (defects, ions at surfaces) need a neutralising
background charge (`NELECT` tweak) and optionally a Makov–Payne or Freysoldt
finite-size correction. This is a common DFT pitfall; a `--charged N` flag that
sets NELECT and warns about corrections would cover the basic case.
