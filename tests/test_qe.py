"""Tests for the Quantum ESPRESSO (pw.x) engine path."""
import pytest

from vasp_auto import qe_tools
from vasp_auto.config_loader import default_config, load_config
from vasp_auto.job_manager import create_job_from_case, make_case_info, preview_job_from_case
from vasp_auto.parser import parse_pw_final_structure, parse_pw_output
from vasp_auto.workflow import build_row, job_engine, should_retry_failed


POSCAR_SI = """Si bulk
5.43
0.0 0.5 0.5
0.5 0.0 0.5
0.5 0.5 0.0
Si
2
Direct
0.0 0.0 0.0
0.25 0.25 0.25
"""

PW_OUT = """
     Program PWSCF v.7.2 starts ...
     Self-consistent Calculation
     convergence has been achieved in  11 iterations
!    total energy              =     -15.83792000 Ry
     Total force =     0.000100     Total SCF correction =     0.000001
     number of bfgs steps      =      4
"""


@pytest.fixture
def qe_case(tmp_path):
    case = tmp_path / "Si"
    case.mkdir()
    (case / "POSCAR").write_text(POSCAR_SI, encoding="utf-8")
    pseudo = tmp_path / "pseudo"
    pseudo.mkdir()
    (pseudo / "Si.pbe-n-kjpaw_psl.1.0.0.UPF").write_text("<UPF/>", encoding="utf-8")
    config = {"pseudo_dir": str(pseudo), "pseudo_map": {}, "qe_executable": "pw.x"}
    case_info = make_case_info(case, tmp_path / "jobs")
    return case, config, case_info


# ----------------------------------------------------------------- pseudos

def test_find_pseudo_auto(tmp_path):
    pseudo = tmp_path / "p"
    pseudo.mkdir()
    (pseudo / "Fe.pbe-spn-kjpaw.UPF").write_text("x")
    assert qe_tools.find_pseudo("Fe", pseudo) == "Fe.pbe-spn-kjpaw.UPF"


def test_find_pseudo_map_wins(tmp_path):
    pseudo = tmp_path / "p"
    pseudo.mkdir()
    (pseudo / "Fe.default.UPF").write_text("x")
    name = qe_tools.find_pseudo("Fe", pseudo, {"Fe": "Fe.special.UPF"})
    assert name == "Fe.special.UPF"


def test_find_pseudo_missing_raises(tmp_path):
    pseudo = tmp_path / "p"
    pseudo.mkdir()
    with pytest.raises(FileNotFoundError):
        qe_tools.find_pseudo("Au", pseudo)


# ----------------------------------------------------------------- input gen

def test_build_pw_input_namelists(qe_case):
    case, config, case_info = qe_case
    preview = preview_job_from_case(
        case_info, calc_type="scf",
        kpoints_spec={"mode": "gamma", "mesh": "4x4x4"},
        engine="qe", config=config,
    )
    text = preview["pw.in"]
    assert "calculation = 'scf'" in text
    assert "ibrav = 0" in text
    assert "nat = 2" in text and "ntyp = 1" in text
    assert "ATOMIC_SPECIES" in text
    assert "Si.pbe-n-kjpaw_psl.1.0.0.UPF" in text
    assert "CELL_PARAMETERS angstrom" in text
    assert "ATOMIC_POSITIONS crystal" in text
    assert "K_POINTS automatic" in text and "4 4 4" in text


def test_ecutwfc_from_config_override(qe_case):
    case, config, case_info = qe_case
    config = {**config, "qe_ecutwfc": 80.0, "qe_ecutrho": 640.0}
    preview = preview_job_from_case(case_info, calc_type="scf", engine="qe", config=config)
    assert "ecutwfc = 80" in preview["pw.in"]
    assert "ecutrho = 640" in preview["pw.in"]


def test_calc_type_mapping():
    assert qe_tools.QE_CALC_MAP["vcrelax"] == "vc-relax"
    assert qe_tools.QE_CALC_MAP["dos"] == "nscf"
    assert qe_tools.QE_CALC_MAP["bands"] == "bands"


def test_vcrelax_emits_cell_namelist(qe_case):
    case, config, case_info = qe_case
    preview = preview_job_from_case(case_info, calc_type="vcrelax", engine="qe", config=config)
    assert "calculation = 'vc-relax'" in preview["pw.in"]
    assert "&CELL" in preview["pw.in"]
    assert "&IONS" in preview["pw.in"]


def test_bands_needs_kpath(qe_case):
    case, config, case_info = qe_case
    with pytest.raises(ValueError):
        preview_job_from_case(case_info, calc_type="bands", engine="qe", config=config)


def test_bands_kpath_crystal_b(qe_case):
    case, config, case_info = qe_case
    preview = preview_job_from_case(
        case_info, calc_type="bands",
        kpoints_spec={"mode": "line", "kpath": "fcc", "divisions": 20},
        engine="qe", config=config,
    )
    assert "K_POINTS crystal_b" in preview["pw.in"]


def test_unsupported_calc_type_rejected(qe_case):
    case, config, case_info = qe_case
    with pytest.raises(ValueError):
        preview_job_from_case(case_info, calc_type="phonon", engine="qe", config=config)


def test_spin_adds_starting_magnetization(qe_case):
    case, config, case_info = qe_case
    preview = preview_job_from_case(
        case_info, calc_type="scf", engine="qe", config=config,
        spin=True, magmom_map={"Si": 0.3},
    )
    assert "nspin = 2" in preview["pw.in"]
    assert "starting_magnetization(1) = 0.3" in preview["pw.in"]


# ----------------------------------------------------------------- job dir

def test_create_qe_job_writes_inputs(qe_case):
    case, config, case_info = qe_case
    job_dir = create_job_from_case(
        case_info, calc_type="relax",
        kpoints_spec={"mode": "mp", "mesh": "6x6x6"},
        engine="qe", config=config,
    )
    assert (job_dir / "pw.in").exists()
    assert (job_dir / ".engine").read_text().strip() == "qe"
    assert (job_dir / "POSCAR").exists()
    assert (job_dir / "pseudo" / "Si.pbe-n-kjpaw_psl.1.0.0.UPF").exists()
    assert job_engine(job_dir) == "qe"


def test_user_pw_in_takes_precedence(qe_case):
    case, config, case_info = qe_case
    (case / "pw.in").write_text("&CONTROL\n  calculation = 'scf'\n/\nCUSTOM\n", encoding="utf-8")
    job_dir = create_job_from_case(case_info, calc_type="scf", engine="qe", config=config)
    assert "CUSTOM" in (job_dir / "pw.in").read_text()


def test_qe_tss_rejected(tmp_path):
    case = tmp_path / "tss"
    for end in ("initial", "final"):
        (case / end).mkdir(parents=True)
        (case / end / "POSCAR").write_text(POSCAR_SI, encoding="utf-8")
    case_info = make_case_info(case, tmp_path / "jobs")
    with pytest.raises(ValueError):
        create_job_from_case(case_info, engine="qe", config={"pseudo_dir": str(tmp_path)})


# ----------------------------------------------------------------- parsing

def test_parse_pw_output(tmp_path):
    pw_out = tmp_path / "pw.out"
    pw_out.write_text(PW_OUT, encoding="utf-8")
    summary = parse_pw_output(pw_out)
    assert summary["converged"] is True
    assert summary["ionic_steps"] == 4
    assert summary["energy_eV"] == pytest.approx(-15.83792 * qe_tools.RY_TO_EV)
    assert summary["max_force_eV_A"] is not None


def test_parse_pw_output_missing(tmp_path):
    assert parse_pw_output(tmp_path / "none.out") is None


def test_parse_pw_final_structure(tmp_path):
    pw_out = tmp_path / "pw.out"
    pw_out.write_text(
        "Begin final coordinates\n"
        "CELL_PARAMETERS (angstrom)\n"
        "  3.0 0.0 0.0\n  0.0 3.0 0.0\n  0.0 0.0 3.0\n"
        "ATOMIC_POSITIONS (crystal)\n"
        "  Si 0.0 0.0 0.0\n  Si 0.5 0.5 0.5\n"
        "End final coordinates\n",
        encoding="utf-8",
    )
    struct = parse_pw_final_structure(pw_out)
    assert struct["elements"] == ["Si"]
    assert struct["counts"] == [2]
    assert struct["lattice"][0][0] == 3.0


# ----------------------------------------------------------------- rows

def test_build_row_qe(tmp_path):
    job_dir = tmp_path / "jobs" / "Si"
    job_dir.mkdir(parents=True)
    (job_dir / ".engine").write_text("qe\n")
    (job_dir / "pw.out").write_text(PW_OUT, encoding="utf-8")
    case = tmp_path / "Si"
    case.mkdir()
    (case / "POSCAR").write_text(POSCAR_SI, encoding="utf-8")
    case_info = make_case_info(case, tmp_path / "jobs")
    row = build_row("p", "project", case_info)
    assert row["engine"] == "qe"
    assert row["converged"] is True
    assert row["status"] == "done"
    assert should_retry_failed(case_info) is False


def test_should_retry_unconverged_qe(tmp_path):
    job_dir = tmp_path / "jobs" / "Si"
    job_dir.mkdir(parents=True)
    (job_dir / ".engine").write_text("qe\n")
    (job_dir / "pw.out").write_text("!    total energy = -1.0 Ry\n", encoding="utf-8")
    case = tmp_path / "Si"
    case.mkdir()
    (case / "POSCAR").write_text(POSCAR_SI, encoding="utf-8")
    case_info = make_case_info(case, tmp_path / "jobs")
    assert should_retry_failed(case_info) is True


# ----------------------------------------------------------------- config

def test_default_config_has_engine():
    config = default_config()
    assert config["engine"] == "vasp"
    assert config["qe_executable"] == "pw.x"


def test_load_config_engine_default():
    config = load_config()
    assert config.get("engine", "vasp") in ("vasp", "qe")
