"""Shared, lossless primitives for calculation-specific VASP/QE resumes."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from vasp_auto.incar import get_incar_value, set_incar_value


# Result files are moved aside before VASP gets a chance to overwrite them.
# Checkpoints (CONTCAR/CHGCAR/WAVECAR/vaspwave.h5/vaspcheckfd.h5) stay in place.
RESULT_FILES = (
    "job.log", "run.log", "OUTCAR", "OSZICAR", "vasprun.xml", "vaspout.h5",
    "XDATCAR", "DOSCAR", "EIGENVAL", "PROCAR", "PCDAT", "LOCPOT", "CHG",
    "ELFCAR", "DYNMAT", "REPORT", "IBZKPT", "PARCHG", "WAVEDER",
)
INPUT_SNAPSHOTS = ("INCAR", "KPOINTS", "POSCAR")


def require_poscar(job_dir: Path) -> None:
    if not (job_dir / "POSCAR").is_file():
        raise FileNotFoundError(f"cannot resume {job_dir.name}: missing POSCAR")


def seed_from_contcar(work_dir: Path) -> bool:
    """Advance one moving geometry, retaining the previous POSCAR."""
    contcar = work_dir / "CONTCAR"
    poscar = work_dir / "POSCAR"
    if not contcar.is_file() or contcar.stat().st_size == 0:
        require_poscar(work_dir)
        return False
    if poscar.exists():
        shutil.copy2(poscar, work_dir / "POSCAR.bak")
    shutil.copy2(contcar, poscar)
    return True


def prepare_moving(job_dir: Path, name: str) -> str:
    seeded = seed_from_contcar(job_dir)
    source = "latest CONTCAR" if seeded else "existing POSCAR (no usable CONTCAR)"
    return f"{name}: continued geometry from {source}"


def prepare_static(job_dir: Path, name: str) -> str:
    require_poscar(job_dir)
    checkpoints = [name for name in ("WAVECAR", "CHGCAR", "vaspwave.h5")
                   if (job_dir / name).is_file()]
    suffix = f"; retained {', '.join(checkpoints)}" if checkpoints else "; no electronic checkpoint found"
    return f"{name}: retained POSCAR{suffix}"


def prepare_fixed_density(job_dir: Path, name: str) -> str:
    message = prepare_static(job_dir, name)
    incar = (job_dir / "INCAR").read_text(encoding="utf-8", errors="ignore")
    if get_incar_value(incar, "ICHARG") == "11" and not (job_dir / "CHGCAR").is_file():
        raise FileNotFoundError(
            f"cannot resume {job_dir.name}: {name} uses ICHARG=11 but CHGCAR is missing"
        )
    return message


def prepare_frequency(job_dir: Path) -> str:
    message = prepare_static(job_dir, "freq")
    incar_path = job_dir / "INCAR"
    incar = incar_path.read_text(encoding="utf-8", errors="ignore")
    if get_incar_value(incar, "IBRION") == "6" and (job_dir / "vaspcheckfd.h5").is_file():
        set_incar_value(incar_path, "CHECKPOINT_FD", "CONTINUE")
        return message + "; continuing completed finite-difference displacements"
    return message + "; finite-difference stage restarts (no compatible checkpoint)"


def archive_previous_outputs(
    job_dir: Path,
    work_dirs: list[Path],
    calculation_type: str,
) -> Path | None:
    """Move overwrite-prone results into the next resume_history segment."""
    sources = [job_dir, *work_dirs]
    if not any((directory / name).is_file() for directory in sources for name in RESULT_FILES):
        return None

    history = job_dir / "resume_history"
    number = max((int(p.name) for p in history.iterdir() if p.is_dir() and p.name.isdigit()), default=0) + 1 \
        if history.is_dir() else 1
    archive = history / f"{number:04d}"

    for directory in sources:
        relative = directory.relative_to(job_dir)
        target = archive / relative
        for name in INPUT_SNAPSHOTS:
            source = directory / name
            if source.is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target / name)
        for name in RESULT_FILES:
            source = directory / name
            if source.is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), target / name)

    (archive / "resume.json").write_text(json.dumps({
        "calculation_type": calculation_type,
        "archived_at": datetime.now().isoformat(timespec="seconds"),
    }, indent=2) + "\n", encoding="utf-8")
    return archive


def qe_stages(job_dir: Path) -> list[dict]:
    manifest = job_dir / "qe_stages.json"
    if not manifest.is_file():
        return [{"program": "pw.x", "input": "pw.in", "output": "pw.out", "mpi": True}]
    data = json.loads(manifest.read_text(encoding="utf-8"))
    stages = data.get("stages") if isinstance(data, dict) else None
    if not isinstance(stages, list) or not stages:
        raise ValueError(f"invalid or empty QE stage manifest: {manifest}")
    return stages


def qe_remaining_stages(job_dir: Path, force: bool = False) -> list[dict]:
    stages = qe_stages(job_dir)
    if force:
        return stages
    for index, stage in enumerate(stages):
        output = job_dir / stage["output"]
        text = output.read_text(encoding="utf-8", errors="ignore") if output.is_file() else ""
        if "JOB DONE." not in text:
            return stages[index:]
    return []


def _qe_value(path: Path, key: str, default: str = "") -> str:
    text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*([^,!\n]+)", text, re.M | re.I)
    return match.group(1).strip().strip("'\"") if match else default


def _set_qe_value(path: Path, section: str, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"(?ims)^\s*&{re.escape(section)}\b.*?^\s*/", text)
    if not match:
        raise ValueError(f"{path.name}: missing &{section} namelist")
    block = match.group(0)
    assignment = re.compile(rf"(?im)^\s*{re.escape(key)}\s*=\s*[^,!\n]+\s*,?")
    if assignment.search(block):
        block = assignment.sub(f"  {key} = {value}", block, count=1)
    else:
        block = re.sub(r"(?m)^\s*/", f"  {key} = {value}\n/", block, count=1)
    path.write_text(text[:match.start()] + block + text[match.end():], encoding="utf-8")


def _qe_save_dir(job_dir: Path, input_path: Path) -> Path:
    outdir = Path(_qe_value(input_path, "outdir", "./"))
    if not outdir.is_absolute():
        outdir = job_dir / outdir
    return outdir / f"{_qe_value(input_path, 'prefix', 'pwscf')}.save"


def _qe_has_pw_checkpoint(job_dir: Path, input_path: Path) -> bool:
    save = _qe_save_dir(job_dir, input_path)
    return save.is_dir() and any((save / name).is_file()
                                 for name in ("data-file-schema.xml", "data-file.xml"))


def qe_can_restart_pw(job_dir: Path, active_stage: dict | None) -> bool:
    if not active_stage or active_stage.get("program") != "pw.x":
        return False
    input_path = job_dir / active_stage["input"]
    calculation = _qe_value(input_path, "calculation", "scf").lower()
    output_path = job_dir / active_stage["output"]
    output = output_path.read_text(encoding="utf-8", errors="ignore") \
        if output_path.is_file() else ""
    clean_stop = "Maximum CPU time exceeded" in output or "Program stopped by user request" in output
    return calculation in {"scf", "relax", "vc-relax", "md", "vc-md"} \
        and clean_stop and _qe_has_pw_checkpoint(job_dir, input_path)


def prepare_qe_pw(
    job_dir: Path,
    name: str,
    active_stage: dict | None,
    allow_restart: bool = True,
) -> str:
    if not active_stage or active_stage.get("program") != "pw.x":
        program = active_stage.get("program") if active_stage else "completed workflow"
        return f"{name}: continuing at {program}"
    input_path = job_dir / active_stage["input"]
    calculation = _qe_value(input_path, "calculation", "scf").lower()
    restartable = calculation in {"scf", "relax", "vc-relax", "md", "vc-md"}
    if allow_restart and restartable and _qe_has_pw_checkpoint(job_dir, input_path):
        _set_qe_value(input_path, "CONTROL", "restart_mode", "'restart'")
        return f"{name}: continuing {calculation} from {input_path.name} checkpoint"
    _set_qe_value(input_path, "CONTROL", "restart_mode", "'from_scratch'")
    reason = "NSCF/bands stages are rerun" if not restartable else "no compatible clean checkpoint"
    return f"{name}: restarting {input_path.name} ({reason})"


def prepare_qe_phonon(
    job_dir: Path,
    name: str,
    active_stage: dict | None,
    allow_restart: bool = True,
) -> str:
    if not active_stage or active_stage.get("program") != "ph.x":
        return prepare_qe_pw(job_dir, name, active_stage, allow_restart)
    input_path = job_dir / active_stage["input"]
    outdir = Path(_qe_value(input_path, "outdir", "./"))
    if not outdir.is_absolute():
        outdir = job_dir / outdir
    prefix = _qe_value(input_path, "prefix", "pwscf")
    phsave = outdir / "_ph0" / f"{prefix}.phsave"
    reduce_io = _qe_value(input_path, "reduce_io", ".false.").lower().startswith(".t")
    recover = allow_restart and phsave.is_dir() and any(phsave.iterdir()) and not reduce_io
    _set_qe_value(input_path, "INPUTPH", "recover", ".true." if recover else ".false.")
    return f"{name}: {'recovering saved representations' if recover else 'restarting ph.x'}"


def prepare_qe_neb(
    job_dir: Path,
    active_stage: dict | None,
    allow_restart: bool = True,
) -> str:
    input_path = job_dir / ((active_stage or {}).get("input") or "neb.in")
    tmp = job_dir / "tmp"
    restart = allow_restart and tmp.is_dir() and any(tmp.iterdir())
    _set_qe_value(input_path, "PATH", "restart_mode", "'restart'" if restart else "'from_scratch'")
    return f"neb: {'continuing saved path' if restart else 'restarting path (no compatible checkpoint)'}"


def archive_qe_outputs(job_dir: Path, stages: list[dict], calculation_type: str) -> Path | None:
    all_stages = qe_stages(job_dir)
    names = {"run.log", ".qe_complete", *(stage["output"] for stage in all_stages)}
    patterns = (
        "*.dat", "*.dat.gnu", "*.cube", "*.axsf", "*.xyz", "pdos*",
        "dynamical-matrix*", "potential-average.dat", "avg.dat", "CRASH",
    )
    outputs = {job_dir / name for name in names if (job_dir / name).is_file()}
    for pattern in patterns:
        outputs.update(path for path in job_dir.glob(pattern) if path.is_file())
    if not outputs:
        return None

    history = job_dir / "resume_history"
    number = max((int(p.name) for p in history.iterdir() if p.is_dir() and p.name.isdigit()), default=0) + 1 \
        if history.is_dir() else 1
    archive = history / f"{number:04d}"
    archive.mkdir(parents=True)
    for source in job_dir.glob("*.in"):
        shutil.copy2(source, archive / source.name)
    for name in ("POSCAR", "qe_stages.json"):
        source = job_dir / name
        if source.is_file():
            shutil.copy2(source, archive / name)
    remaining_outputs = {stage["output"] for stage in stages}
    completed_outputs = {stage["output"] for stage in all_stages} - remaining_outputs
    for source in outputs:
        # Keep completed stage outputs and generated data in place: downstream
        # stages may consume them (dynmat.x needs dynamical-matrix; average.x
        # needs electrostatic-potential.dat). The archive still preserves a copy.
        if source.name in completed_outputs or source.name not in names:
            shutil.copy2(source, archive / source.name)
        else:
            shutil.move(str(source), archive / source.name)
    (archive / "resume.json").write_text(json.dumps({
        "engine": "qe", "calculation_type": calculation_type,
        "remaining_stages": [stage["program"] for stage in stages],
        "archived_at": datetime.now().isoformat(timespec="seconds"),
    }, indent=2) + "\n", encoding="utf-8")
    return archive
