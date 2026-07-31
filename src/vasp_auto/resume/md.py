from pathlib import Path
from .common import prepare_moving, prepare_qe_pw


def prepare(job_dir: Path, _image_dirs=()) -> str:
    return prepare_moving(job_dir, "md (coordinates/velocities)")


def prepare_qe(job_dir: Path, active_stage=None, allow_restart=True) -> str:
    return prepare_qe_pw(job_dir, "md", active_stage, allow_restart)
