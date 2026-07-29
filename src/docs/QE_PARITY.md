# Quantum ESPRESSO backend

The `qe` engine presents the same preparation, execution, workflow, remote, and
analysis surfaces as the VASP engine while keeping engine-specific files and
scientific parameters isolated. No VASP input generation or execution path is
replaced by QE logic.

| User calculation | QE implementation |
| --- | --- |
| SCF, relax, variable-cell relax, MD, HSE06 | `pw.x` |
| DOS and projected DOS | SCF + NSCF `pw.x`, `dos.x`, `projwfc.x` |
| Bands | SCF + bands `pw.x`, `bands.x` |
| Phonons and frequencies | `pw.x`, `ph.x`, optionally `dynmat.x` |
| Optics | SCF + NSCF `pw.x`, `epsilon.x` |
| Charge density and Bader input | `pw.x`, `pp.x` Gaussian cube |
| Work function | `pw.x`, `pp.x`, `average.x` |
| Transition state / NEB | `neb.x` |

`qe_stages.json` records each job's ordered native programs. The same manifest
drives local MPI, direct SSH, Slurm/PBS, and detached remote runs. QE-specific
environment setup uses `qe_env_setup`; VASP continues to use `env_setup`.

## Configuration

```yaml
engine: qe
qe_executable: /opt/qe/bin/pw.x
pseudo_dir: /opt/qe/pseudo
pseudo_map:
  Si: Si_ONCV_PBE-1.1.upf
qe_ecutwfc: 50       # Ry
qe_ecutrho: 400      # Ry
qe_degauss: 0.01     # Ry
```

All companion executables must be installed beside `pw.x` or available on
`PATH`. A remote entry may specify its own `qe_executable`, `pseudo_dir`, and
`qe_env_setup` without changing its VASP executable or environment.

## Scientific guidance

Feature parity does not mean translating VASP tags into superficially similar
numbers. QE cutoffs and smearing widths use Rydberg, UPF recommendations govern
cutoff selection, and postprocessing uses QE's saved-state formats. Converge
each pseudopotential family independently. Use one curated, functional-consistent
UPF set for production rather than accepting the first filename that happens to
match an element.
