from pathlib import Path
from .common import prepare_frequency, prepare_qe_phonon


def prepare(job_dir: Path, _image_dirs=()) -> str:
    return prepare_frequency(job_dir)


def prepare_qe(job_dir: Path, active_stage=None, allow_restart=True) -> str:
    return prepare_qe_phonon(job_dir, "freq", active_stage, allow_restart)
