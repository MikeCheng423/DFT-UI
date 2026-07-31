from pathlib import Path
from .common import prepare_qe_pw, prepare_static


def prepare(job_dir: Path, _image_dirs=()) -> str:
    return prepare_static(job_dir, "hse06")


def prepare_qe(job_dir: Path, active_stage=None, allow_restart=True) -> str:
    return prepare_qe_pw(job_dir, "hse06", active_stage, allow_restart)
