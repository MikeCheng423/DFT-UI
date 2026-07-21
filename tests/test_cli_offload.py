"""Tests for the detached-offload flag forwarding (no SSH)."""

from __future__ import annotations

import sys
from pathlib import Path

from vasp_auto.cli import _forward_calc_flags, parse_args


def _args(argv):
    old = sys.argv
    sys.argv = ["vasp-auto", *argv]
    try:
        return parse_args()
    finally:
        sys.argv = old


def test_forward_calc_flags_convergence():
    args = _args([
        "inputs/H2O", "--converge-encut", "300,400", "--converge-sigma", "0.2",
        "--nelm-values", "40,50", "--kpoints-values", "3,4", "--energy-tol", "0.001",
        "--reuse-wavecar",
    ])
    flags = _forward_calc_flags(args)
    assert "--converge-encut" in flags and "300,400" in flags
    assert "--converge-sigma" in flags and "0.2" in flags
    assert "--nelm-values" in flags and "40,50" in flags
    assert "--kpoints-values" in flags and "3,4" in flags
    assert "--energy-tol" in flags and "0.001" in flags
    assert "--reuse-wavecar" in flags
    # target/remote-style flags are never forwarded (remote runs the case locally)
    assert "inputs/H2O" not in flags
    assert not any(f.startswith("--remote") for f in flags)


def test_forward_calc_flags_minimal_scf():
    # A plain SCF forwards nothing extra (defaulted tolerances stay implicit).
    args = _args(["inputs/H2O"])
    assert _forward_calc_flags(args) == []


def test_forward_calc_flags_calc_type_and_spin():
    args = _args(["inputs/Fe", "--calc-type", "relax", "--spin", "--magmom", "Fe=3"])
    flags = _forward_calc_flags(args)
    assert flags[:2] == ["--calc-type", "relax"]
    assert "--spin" in flags
    assert "--magmom" in flags and "Fe=3" in flags


def test_forward_calc_flags_solvation_only_with_flag():
    plain = _forward_calc_flags(_args(["inputs/H2O"]))
    assert "--solvation-eps" not in plain  # default eps not forwarded without --solvation
    solv = _forward_calc_flags(_args(["inputs/H2O", "--solvation", "--solvation-eps", "36.6"]))
    assert "--solvation" in solv and "--solvation-eps" in solv and "36.6" in solv


def test_offload_bundles_workflow_yaml(tmp_path, monkeypatch):
    """A workflow offload ships POSCAR + workflow.yaml so the chain runs remotely."""
    import vasp_auto.runner as runner
    import vasp_auto.potcar_finder as potcar_finder
    from vasp_auto.cli import _run_detached_offload
    from vasp_auto.job_manager import make_case_info

    case = tmp_path / "Au13"
    case.mkdir()
    (case / "POSCAR").write_text("Au\n1.0\n10 0 0\n0 10 0\n0 0 10\nAu\n1\nCartesian\n0 0 0\n")
    (case / "INCAR").write_text("ENCUT = 400\n")
    (case / "workflow.yaml").write_text("steps:\n  - calc_type: relax\n  - calc_type: scf\n")

    captured = {}

    def fake_submit(case_dir, remote, case_name, cpus, calc_flags, local_job_dir=None,
                    on_progress=None, engine="vasp"):
        captured["files"] = sorted(p.name for p in Path(case_dir).iterdir())
        captured["flags"] = list(calc_flags)
        return {"machine": remote.get("name"), "remote_dir": "/r/" + case_name,
                "inputs_dir": "/r/in", "control_dir": "/r/ctl", "pid": "123", "log": "/r/log"}

    monkeypatch.setattr(runner, "submit_job_detached", fake_submit)
    monkeypatch.setattr(potcar_finder, "build_potcar",
                        lambda **kw: Path(kw["output_path"]).write_text("POTCAR\n"))

    args = _args(["inputs/Au13", "--workflow", "relax,scf"])
    args.cpus = 8
    config = {"potcar_root": str(tmp_path / "pot"), "vasp_executable": "vasp_std"}
    case_info = make_case_info(case, tmp_path / "jobs", single_mode=True)
    remote = {"name": "apl2", "host": "h", "remote_root": "/r", "vasp_executable": "/v"}

    _run_detached_offload(case, case_info, args, config, remote, None, None, "single", "Au13")

    assert "POSCAR" in captured["files"]
    assert "workflow.yaml" in captured["files"]
    assert "INCAR" in captured["files"]
    assert "--workflow" in captured["flags"] and "relax,scf" in captured["flags"]


def test_offload_bundles_neb_endpoints(tmp_path, monkeypatch):
    """A TSS/NEB case offloads its initial/final endpoints + a pre-built POTCAR so
    the remote engine interpolates the images and runs NEB detached."""
    import vasp_auto.potcar_finder as potcar_finder
    import vasp_auto.runner as runner
    from vasp_auto.cli import _run_detached_offload
    from vasp_auto.job_manager import make_case_info

    poscar = "Au\n1.0\n10 0 0\n0 10 0\n0 0 10\nAu\n1\nCartesian\n0 0 0\n"
    case = tmp_path / "neb_case"
    (case / "initial").mkdir(parents=True)
    (case / "final").mkdir(parents=True)
    (case / "initial" / "POSCAR").write_text(poscar)
    (case / "final" / "POSCAR").write_text(poscar)

    captured = {}

    def fake_submit(case_dir, remote, case_name, cpus, calc_flags, local_job_dir=None,
                    on_progress=None, engine="vasp"):
        root = Path(case_dir)
        captured["tree"] = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
        captured["flags"] = list(calc_flags)
        return {"machine": remote.get("name"), "remote_dir": "/r/" + case_name,
                "inputs_dir": "/r/in", "control_dir": "/r/ctl", "pid": "9", "log": "/r/log"}

    monkeypatch.setattr(runner, "submit_job_detached", fake_submit)
    monkeypatch.setattr(potcar_finder, "build_potcar",
                        lambda **kw: Path(kw["output_path"]).write_text("POTCAR\n"))

    args = _args(["inputs/neb_case", "--calc-type", "neb", "--neb-images", "3"])
    args.cpus = 6
    config = {"potcar_root": str(tmp_path / "pot"), "vasp_executable": "vasp_std"}
    case_info = make_case_info(case, tmp_path / "jobs", single_mode=True)
    assert case_info["calculation_type"] == "tss"
    remote = {"name": "apl2", "host": "h", "remote_root": "/r", "vasp_executable": "/v"}

    _run_detached_offload(case, case_info, args, config, remote, None, None, "single", "neb_case")

    assert "initial/POSCAR" in captured["tree"]
    assert "final/POSCAR" in captured["tree"]
    assert "POTCAR" in captured["tree"]
    assert "--neb-images" in captured["flags"] and "3" in captured["flags"]


def test_offload_wait_for_slot_blocks_until_job_finishes(tmp_path, monkeypatch):
    """A project run with more cases than --parallel needs each offloaded case to
    hold its worker slot until the remote job actually finishes — otherwise every
    case launches within moments of each other and the cap does nothing."""
    import vasp_auto.runner as runner
    import vasp_auto.potcar_finder as potcar_finder
    from vasp_auto.cli import _run_detached_offload
    from vasp_auto.job_manager import make_case_info

    case = tmp_path / "case"
    case.mkdir()
    (case / "POSCAR").write_text("Au\n1.0\n10 0 0\n0 10 0\n0 0 10\nAu\n1\nCartesian\n0 0 0\n")

    monkeypatch.setattr(runner, "submit_job_detached", lambda *a, **kw: {
        "machine": "apl2", "remote_dir": "/r/case", "inputs_dir": "/r/in",
        "control_dir": "/r/ctl", "pid": "123", "log": "/r/log",
    })
    monkeypatch.setattr(potcar_finder, "build_potcar",
                        lambda **kw: Path(kw["output_path"]).write_text("POTCAR\n"))

    polls = []

    def fake_poll(remote, control_dir, pid):
        polls.append((control_dir, pid))
        return {"state": "running" if len(polls) < 3 else "completed", "return_code": None}

    monkeypatch.setattr(runner, "poll_detached_job", fake_poll)
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    args = _args(["inputs/case"])
    args.cpus = 8
    config = {"potcar_root": str(tmp_path / "pot"), "vasp_executable": "vasp_std"}
    case_info = make_case_info(case, tmp_path / "jobs", single_mode=True)
    remote = {"name": "apl2", "host": "h", "remote_root": "/r", "vasp_executable": "/v"}

    case_info_out, rows = _run_detached_offload(
        case, case_info, args, config, remote, None, None, "single", "case",
        wait_for_slot=True,
    )

    # Polled until "completed" (3 calls: running, running, completed) and slept
    # once per poll — the slot was held, not freed the moment submission returned.
    assert len(polls) == 3
    assert polls[0] == ("/r/ctl", "123")
    assert len(sleeps) == 3
    assert rows[0]["remote_dir"] == "/r/case"


def test_offload_no_wait_when_slot_not_capped(tmp_path, monkeypatch):
    """Without wait_for_slot (the default — a lone case, or a batch that already
    fits under --parallel), offload still returns the moment submission is done."""
    import vasp_auto.runner as runner
    import vasp_auto.potcar_finder as potcar_finder
    from vasp_auto.cli import _run_detached_offload
    from vasp_auto.job_manager import make_case_info

    case = tmp_path / "case"
    case.mkdir()
    (case / "POSCAR").write_text("Au\n1.0\n10 0 0\n0 10 0\n0 0 10\nAu\n1\nCartesian\n0 0 0\n")

    monkeypatch.setattr(runner, "submit_job_detached", lambda *a, **kw: {
        "machine": "apl2", "remote_dir": "/r/case", "inputs_dir": "/r/in",
        "control_dir": "/r/ctl", "pid": "123", "log": "/r/log",
    })
    monkeypatch.setattr(potcar_finder, "build_potcar",
                        lambda **kw: Path(kw["output_path"]).write_text("POTCAR\n"))

    def fail_poll(*a, **kw):
        raise AssertionError("poll_detached_job must not be called without wait_for_slot")

    monkeypatch.setattr(runner, "poll_detached_job", fail_poll)

    args = _args(["inputs/case"])
    args.cpus = 8
    config = {"potcar_root": str(tmp_path / "pot"), "vasp_executable": "vasp_std"}
    case_info = make_case_info(case, tmp_path / "jobs", single_mode=True)
    remote = {"name": "apl2", "host": "h", "remote_root": "/r", "vasp_executable": "/v"}

    _run_detached_offload(case, case_info, args, config, remote, None, None, "single", "case")
