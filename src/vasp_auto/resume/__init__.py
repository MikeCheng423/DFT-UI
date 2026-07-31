"""Calculation-specific VASP and Quantum ESPRESSO resume policies."""
from __future__ import annotations

from pathlib import Path

from . import bands, charge, dos, freq, hse06, md, neb, optics, phonon, relax, scf, vcrelax, workfunction
from .common import (
    archive_previous_outputs,
    archive_qe_outputs,
    qe_can_restart_pw,
    qe_remaining_stages,
    seed_from_contcar,
)
from .detect import calculation_type


PREPARERS = {
    "scf": scf.prepare,
    "relax": relax.prepare,
    "vcrelax": vcrelax.prepare,
    "md": md.prepare,
    "neb": neb.prepare,
    "tss": neb.prepare,
    "dos": dos.prepare,
    "bands": bands.prepare,
    "charge": charge.prepare,
    "hse06": hse06.prepare,
    "freq": freq.prepare,
    "phonon": phonon.prepare,
    "optics": optics.prepare,
    "workfunction": workfunction.prepare,
}

MODULES = {
    "scf": scf, "relax": relax, "vcrelax": vcrelax, "md": md,
    "neb": neb, "tss": neb, "dos": dos, "bands": bands, "charge": charge,
    "hse06": hse06, "freq": freq, "phonon": phonon, "optics": optics,
    "workfunction": workfunction,
}


def prepare(calculation: str, job_dir: Path, image_dirs=()) -> str:
    try:
        handler = PREPARERS[calculation]
    except KeyError:
        raise ValueError(
            f"resume is not implemented for calculation type {calculation!r}; "
            f"supported: {', '.join(PREPARERS)}"
        ) from None
    return handler(job_dir, image_dirs)


def prepare_qe(
    calculation: str,
    job_dir: Path,
    active_stage: dict | None,
    allow_restart: bool = True,
) -> str:
    try:
        module = MODULES[calculation]
    except KeyError:
        raise ValueError(f"QE resume is not implemented for {calculation!r}") from None
    return module.prepare_qe(job_dir, active_stage, allow_restart)


__all__ = [
    "archive_previous_outputs", "archive_qe_outputs", "calculation_type", "prepare",
    "prepare_qe", "qe_can_restart_pw", "qe_remaining_stages", "seed_from_contcar",
]
