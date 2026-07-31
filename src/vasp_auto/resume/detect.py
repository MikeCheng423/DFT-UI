"""Backward-compatible calculation-type detection for existing VASP jobs."""
from __future__ import annotations

import re
import json
from pathlib import Path

from vasp_auto.incar import get_incar_value


SYSTEM_TYPES = {
    "structure optimization": "relax", "scf single-point": "scf",
    "density of states": "dos", "band structure": "bands",
    "charge density": "charge", "molecular dynamics": "md",
    "phonon": "phonon", "vibrational frequency": "freq",
    "optical absorption": "optics", "work function": "workfunction",
    "vasp_auto_hse06": "hse06",
}


def calculation_type(job_dir: Path, requested: str | None = None) -> str:
    if requested:
        return str(requested).strip().lower()
    manifest = job_dir / "qe_stages.json"
    if manifest.is_file():
        try:
            calc_type = json.loads(manifest.read_text(encoding="utf-8")).get("calc_type")
        except (json.JSONDecodeError, OSError, AttributeError):
            calc_type = None
        if calc_type:
            return str(calc_type).lower()
    if sum(p.is_dir() and p.name.isdigit() for p in job_dir.iterdir()) >= 2:
        return "tss"

    incar = (job_dir / "INCAR").read_text(encoding="utf-8", errors="ignore") \
        if (job_dir / "INCAR").is_file() else ""
    system = get_incar_value(incar, "SYSTEM") or ""
    for marker, calc_type in SYSTEM_TYPES.items():
        if marker in system.lower():
            return calc_type

    log = (job_dir / "job.log").read_text(encoding="utf-8", errors="ignore") \
        if (job_dir / "job.log").is_file() else ""
    match = re.search(r"^\s*Calculation\s*:.*\[([a-z0-9_-]+)\]", log, re.M | re.I)
    if match:
        return match.group(1).lower()

    ibrion = get_incar_value(incar, "IBRION") or ""
    truthy = lambda tag: (get_incar_value(incar, tag) or "").upper().startswith(".T")
    if truthy("LHFCALC"):
        return "hse06"
    if truthy("LOPTICS"):
        return "optics"
    if truthy("LVTOT") or truthy("LVHAR"):
        return "workfunction"
    if ibrion == "0":
        return "md"
    if ibrion in {"1", "2", "3"} and get_incar_value(incar, "NSW") not in {None, "0"}:
        return "relax"
    if ibrion in {"5", "6"}:
        return "freq"
    if ibrion in {"7", "8"}:
        return "phonon"
    if get_incar_value(incar, "ICHARG") == "11":
        kpoints = (job_dir / "KPOINTS").read_text(encoding="utf-8", errors="ignore") \
            if (job_dir / "KPOINTS").is_file() else ""
        return "bands" if re.search(r"line[- ]?mode", kpoints, re.I) else "dos"
    if truthy("LCHARG"):
        return "charge"
    return "scf"
