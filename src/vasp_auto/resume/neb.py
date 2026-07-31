from pathlib import Path
from .common import prepare_qe_neb, seed_from_contcar


def prepare(_job_dir: Path, image_dirs=()) -> str:
    seeded = sum(seed_from_contcar(path) for path in image_dirs)
    return f"neb: continued {seeded}/{len(image_dirs)} image geometries from CONTCAR"


def prepare_qe(job_dir: Path, active_stage=None, allow_restart=True) -> str:
    return prepare_qe_neb(job_dir, active_stage, allow_restart)
