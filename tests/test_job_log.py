"""Tests for the MedeA-style job.log summary."""

from vasp_auto.job_log import build_job_log, write_job_log


def test_job_log_finished(finished_job):
    (finished_job / "INCAR").write_text(
        "SYSTEM = Al test\nENCUT = 450\nIBRION = 2\nNSW = 50\nISMEAR = 1\nSIGMA = 0.2\n",
        encoding="utf-8",
    )
    text = build_job_log(finished_job, case_name="Al", calc_type="relax")
    assert "Status       : finished" in text
    assert "geometry optimization" in text
    assert "Cutoff ENCUT : 450 eV" in text
    assert "Methfessel-Paxton" in text
    assert "RESULTS" in text and "Final energy" in text


def test_job_log_failed(tmp_path):
    # No OUTCAR/energy + a fatal error signature → a 'failed' summary that still
    # surfaces the problem, so a failure leaves a readable result behind.
    (tmp_path / "INCAR").write_text("ENCUT = 400\nRWIGS = 1.34\n", encoding="utf-8")
    (tmp_path / "run.log").write_text(
        "Error reading item RWIGS from file INCAR.\n"
        "  ----> I REFUSE TO CONTINUE WITH THIS SICK JOB ... BYE!!! <----\n",
        encoding="utf-8",
    )
    text = build_job_log(tmp_path, case_name="bad", return_code=1)
    assert "Status       : failed" in text
    assert "DETECTED PROBLEMS" in text and "SICK_JOB" in text
    assert "No final energy" in text


def test_write_job_log_writes_file(finished_job):
    path = write_job_log(finished_job, case_name="Al")
    assert path is not None and path.name == "job.log"
    assert path.read_text(encoding="utf-8").startswith("=")


def test_write_job_log_never_raises(tmp_path):
    # An empty directory must not raise — a summary failure can't break a run.
    assert write_job_log(tmp_path) is not None
