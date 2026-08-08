"""Pull two relaxed endpoint runs into a NEB case: structures, energies, checks.

VASP never computes images 00 and NN, and it does *not* read 00/OUTCAR. A band
whose INCAR leaves EFIRST/ELAST unset therefore treats both endpoints as
E = 0 eV, which corrupts the terminal-image tangents and the climbing-image
choice — that is what destroyed run 0036. So the endpoint energies have to be
handed to VASP explicitly.

This module copies each relaxed run's CONTCAR into ``<case>/{initial,final}/POSCAR``
and its OSZICAR alongside; :func:`vasp_auto.job_manager._write_neb_incar` then
fills EFIRST/ELAST from those OSZICARs every time the case is prepared, locally
or on a remote. Same energies the NEB tab's endpoint pickers ship.

    python -m vasp_auto.neb_endpoints inputs/neb_case results/0041_A results/0042_B

Endpoints relaxed separately usually also need
``python -m vasp_auto.atom_order`` first — this only *checks* the ordering.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ENDPOINTS = ("initial", "final")


def endpoint_energy(endpoint_dir) -> float | None:
    """Relaxed energy of a NEB endpoint folder (OUTCAR, else OSZICAR, else vasprun)."""
    from vasp_auto.workflow import _neb_image_energy

    return _neb_image_energy(Path(endpoint_dir))


def endpoint_energies(case_dir) -> dict[str, float | None]:
    """``{"initial": E, "final": E}`` for a NEB case, None where unknown."""
    case_dir = Path(case_dir)
    return {name: endpoint_energy(case_dir / name) for name in ENDPOINTS}


def collect_endpoints(case_dir, initial_run, final_run) -> dict:
    """Copy two finished relaxations into ``case_dir`` as its NEB endpoints.

    Takes the relaxed CONTCAR (falling back to POSCAR) plus the OSZICAR, which is
    what carries the energy into EFIRST/ELAST at prepare time. Raises if the two
    endpoints disagree on composition or atom ordering — that band is invalid
    however good the energies are. Returns a per-endpoint report:
    ``{"initial": {"run", "structure", "energy_eV", "converged"}, "final": {...}}``.
    """
    from vasp_auto.job_manager import (
        _read_poscar_for_interpolation,
        _validate_interpolation_inputs,
    )
    from vasp_auto.workflow import parse_outcar_summary

    case_dir = Path(case_dir)
    report = {}
    for name, run in zip(ENDPOINTS, (Path(initial_run), Path(final_run))):
        structure = next(
            (run / n for n in ("CONTCAR", "POSCAR")
             if (run / n).is_file() and (run / n).stat().st_size),
            None,
        )
        if structure is None:
            raise FileNotFoundError(f"No CONTCAR or POSCAR in the {name} run: {run}")

        destination = case_dir / name
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(structure, destination / "POSCAR")
        if (run / "OSZICAR").is_file():
            shutil.copy2(run / "OSZICAR", destination / "OSZICAR")

        report[name] = {
            "run": str(run),
            "structure": str(structure),
            "energy_eV": endpoint_energy(destination),
            "converged": parse_outcar_summary(run / "OUTCAR")["converged"],
        }

    _validate_interpolation_inputs(
        _read_poscar_for_interpolation(case_dir / "initial" / "POSCAR"),
        _read_poscar_for_interpolation(case_dir / "final" / "POSCAR"),
        case_dir / "initial" / "POSCAR",
        case_dir / "final" / "POSCAR",
    )
    return report


def main(argv=None):
    """``python -m vasp_auto.neb_endpoints CASE INITIAL_RUN FINAL_RUN``"""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("case", type=Path, help="NEB case directory (gets initial/, final/)")
    parser.add_argument("initial_run", type=Path, help="finished relaxation of the initial state")
    parser.add_argument("final_run", type=Path, help="finished relaxation of the final state")
    args = parser.parse_args(argv)

    report = collect_endpoints(args.case, args.initial_run, args.final_run)
    for name, info in report.items():
        energy = info["energy_eV"]
        tag = "EFIRST" if name == "initial" else "ELAST "
        print(f"{tag} = {energy if energy is not None else 'UNKNOWN (no OSZICAR/OUTCAR)'}"
              f"   <- {info['run']}")
        if not info["converged"]:
            print(f"  !! {info['run']}: OUTCAR never printed 'reached required accuracy' — "
                  "restart it from CONTCAR before trusting this barrier.")
    print(f"Copied endpoints into {args.case}/{{initial,final}}; "
          "EFIRST/ELAST are written when the case is prepared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
