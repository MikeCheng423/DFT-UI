"""The per-machine 'max jobs at once' gate (Remote tab → max_jobs).

Runs the real bash prologue locally: with a limit of 1, the second job must wait
at the gate instead of starting alongside the first. Without this the setting
degrades silently — every submission launches immediately and the machine is
oversubscribed.
"""
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from vasp_auto.runner import _remote_slot_lines, remote_concurrency_limit

pytestmark = pytest.mark.skipif(shutil.which("flock") is None, reason="gate needs flock")


def _gated_job(tmp_path: Path, remote: dict, name: str, work: float):
    """Launch a job behind the gate; it stamps start/end around `work` seconds."""
    job = tmp_path / name
    job.mkdir()
    script = "\n".join([
        "#!/bin/bash",
        *_remote_slot_lines(remote, str(job / "state")),
        f"date +%s.%N > {job}/start",
        f"sleep {work}",
        f"date +%s.%N > {job}/end",
    ])
    (job / "run.sh").write_text(script, encoding="utf-8")
    return job, subprocess.Popen(["bash", str(job / "run.sh")])


def test_second_job_queues_until_the_first_releases_its_slot(tmp_path):
    remote = {"remote_root": str(tmp_path), "max_jobs": 1}
    first, p1 = _gated_job(tmp_path, remote, "first", 0.6)
    second, p2 = _gated_job(tmp_path, remote, "second", 0.1)

    time.sleep(0.3)  # first has the only slot by now
    assert (first / "state").read_text().strip() == "running"
    assert (second / "state").read_text().strip() == "pending"
    assert not (second / "start").exists(), "queued job started anyway"

    p1.wait(timeout=30)
    p2.wait(timeout=30)
    assert (second / "state").read_text().strip() == "running"
    # The runs must not overlap: the second only starts once the first is done.
    assert float((second / "start").read_text()) >= float((first / "end").read_text())


def test_no_limit_means_no_gate(tmp_path):
    assert _remote_slot_lines({"remote_root": str(tmp_path)}, "state") == []
    assert remote_concurrency_limit({"max_jobs": "not a number"}) is None
    assert remote_concurrency_limit({"max_jobs": 0}) is None
    assert remote_concurrency_limit({"max_jobs": "3"}) == 3
