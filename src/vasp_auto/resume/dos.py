from pathlib import Path
from .common import prepare_fixed_density, prepare_qe_pw


def prepare(job_dir: Path, _image_dirs=()) -> str:
    return prepare_fixed_density(job_dir, "dos")


def prepare_qe(job_dir: Path, active_stage=None, allow_restart=True) -> str:
    return prepare_qe_pw(job_dir, "dos", active_stage, allow_restart)
