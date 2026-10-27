import pytest

import vasp_auto.job_manager as job_manager
import vasp_auto.neb_endpoints as neb_endpoints

POSCAR = """test cell
1.0
10.0 0.0 0.0
0.0 10.0 0.0
0.0 0.0 10.0
O H
1 1
Direct
0.1000000000 0.1000000000 0.1000000000
0.3000000000 0.3000000000 0.3000000000
"""

OSZICAR = """       N       E                     dE             d eps       ncg     rms
DAV:   1    -0.100000000000E+02   -0.10E+02   -0.36E+02  1234
   1 F= -.10000000E+02 E0= -.10000000E+02  d E =-.100000E+02
   2 F= -.12500000E+02 E0= -.12500000E+02  d E =-.250000E+01
"""


def _run_dir(tmp_path, name, energy, converged=True):
    run = tmp_path / name
    run.mkdir()
    (run / "CONTCAR").write_text(POSCAR, encoding="utf-8")
    (run / "OSZICAR").write_text(OSZICAR.replace("-.12500000E+02", f"{energy:.8E}"),
                                 encoding="utf-8")
    if converged:
        (run / "OUTCAR").write_text("reached required accuracy - stopping\n", encoding="utf-8")
    return run


def test_collect_endpoints_then_prepare_fills_efirst_elast(tmp_path):
    case = tmp_path / "neb_case"
    report = neb_endpoints.collect_endpoints(
        case,
        _run_dir(tmp_path, "0041_initial", -12.5),
        _run_dir(tmp_path, "0042_final", -11.25, converged=False),
    )
    assert report["initial"]["energy_eV"] == pytest.approx(-12.5)
    assert report["final"]["energy_eV"] == pytest.approx(-11.25)
    assert report["initial"]["converged"] and not report["final"]["converged"]

    job = tmp_path / "job"
    job.mkdir()
    job_manager._write_neb_incar(case, job, 5)
    incar = (job / "INCAR").read_text(encoding="utf-8")
    assert "EFIRST = -12.5" in incar
    assert "ELAST = -11.25" in incar


def test_endpoints_without_energies_leave_incar_alone(tmp_path, capsys):
    case = tmp_path / "neb_case"
    (case / "initial").mkdir(parents=True)
    (case / "initial" / "POSCAR").write_text(POSCAR, encoding="utf-8")

    job = tmp_path / "job"
    job.mkdir()
    job_manager._write_neb_incar(case, job, 5)
    incar = (job / "INCAR").read_text(encoding="utf-8")
    assert "EFIRST" not in incar and "ELAST" not in incar
    assert "no endpoint energies" in capsys.readouterr().out


def test_collect_endpoints_rejects_mismatched_endpoints(tmp_path):
    initial = _run_dir(tmp_path, "0041_initial", -12.5)
    final = _run_dir(tmp_path, "0042_final", -11.25)
    (final / "CONTCAR").write_text(POSCAR.replace("O H", "H O"), encoding="utf-8")
    with pytest.raises(ValueError, match="same element order"):
        neb_endpoints.collect_endpoints(tmp_path / "neb_case", initial, final)
