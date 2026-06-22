"""Catalysis post-processing: adsorption energies, vibrational thermochemistry,
d-band centers, work functions, optical absorption.

Operates on finished job directories; runs no VASP itself. Pure Python.
"""
from __future__ import annotations

import math
from pathlib import Path

from vasp_auto.chgcar import planar_average, read_volumetric
from vasp_auto.parser import parse_dielectric, parse_pdos, parse_vasprun

BOLTZMANN_EV_K = 8.617333262e-5  # eV/K
HBARC_EV_CM = 1.973269804e-5     # ħc in eV·cm
DEFAULT_TEMPERATURE_K = 298.15


# --- energies from finished jobs --------------------------------------------

def read_job_energy(job_dir: Path) -> dict:
    """Final energy and convergence flag of a finished job directory.

    Prefers OUTCAR (free energy TOTEN); falls back to vasprun.xml. Raises
    when the directory holds neither, naming the directory.
    """
    from vasp_auto.workflow import parse_outcar_summary

    job_dir = Path(job_dir)
    outcar = job_dir / "OUTCAR"
    if outcar.exists():
        summary = parse_outcar_summary(outcar)
        if summary["energy_eV"] is not None:
            return {"energy_eV": summary["energy_eV"], "converged": summary["converged"]}

    vasprun = parse_vasprun(job_dir / "vasprun.xml")
    if vasprun and vasprun.get("energy_eV") is not None:
        return {"energy_eV": vasprun["energy_eV"], "converged": True}

    raise FileNotFoundError(f"No final energy found (OUTCAR/vasprun.xml) in {job_dir}")


def adsorption_energy(
    total_dir: Path,
    slab_dir: Path,
    molecule_dir: Path,
    molecule_scale: float = 1.0,
) -> dict:
    """E_ads = E(slab+adsorbate) − E(slab) − scale·E(reference molecule).

    `molecule_scale` references a fraction of the gas-phase molecule, e.g.
    0.5 with an H2 box for atomic H adsorption. Negative E_ads = exothermic.
    """
    total = read_job_energy(total_dir)
    slab = read_job_energy(slab_dir)
    molecule = read_job_energy(molecule_dir)

    e_ads = total["energy_eV"] - slab["energy_eV"] - molecule_scale * molecule["energy_eV"]
    return {
        "adsorption_energy_eV": e_ads,
        "total_energy_eV": total["energy_eV"],
        "slab_energy_eV": slab["energy_eV"],
        "molecule_energy_eV": molecule["energy_eV"],
        "molecule_scale": molecule_scale,
        "all_converged": total["converged"] and slab["converged"] and molecule["converged"],
    }


# --- vibrational frequencies and thermochemistry ----------------------------

def parse_frequencies(outcar_path: Path) -> list[dict]:
    """Vibrational modes from an IBRION=5/6/7/8 OUTCAR.

    Returns [{"index", "meV", "cm1", "THz", "imaginary"}], imaginary modes
    flagged (VASP prints them as 'f/i='). Empty when no frequency block exists.
    """
    outcar_path = Path(outcar_path)
    modes = []
    if not outcar_path.exists():
        return modes

    with open(outcar_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            # e.g. "   4 f  =   91.546624 THz   575.204660 2PiTHz 3053.668884 cm-1   378.617346 meV"
            #      "  12 f/i=    0.022552 THz     0.141698 2PiTHz    0.752259 cm-1     0.093268 meV"
            if "2PiTHz" not in line or "meV" not in line:
                continue
            imaginary = "f/i" in line
            tokens = line.replace("f/i=", " ").replace("f", " ").replace("=", " ").split()
            try:
                index = int(tokens[0])
                thz = float(tokens[tokens.index("THz") - 1])
                cm1 = float(tokens[tokens.index("cm-1") - 1])
                mev = float(tokens[tokens.index("meV") - 1])
            except (IndexError, ValueError):
                continue
            modes.append(
                {"index": index, "THz": thz, "cm1": cm1, "meV": mev, "imaginary": imaginary}
            )
    return modes


def harmonic_thermochemistry(
    modes: list[dict],
    temperature: float = DEFAULT_TEMPERATURE_K,
) -> dict:
    """ZPE and harmonic-oscillator thermal corrections from vibrational modes.

    Imaginary modes are excluded (their count is reported — more than zero on
    a supposed minimum means the geometry is not fully relaxed). Returns all
    terms in eV: zpe, u_vib (thermal vibrational energy), ts (T·S_vib), and
    g_correction = ZPE + U_vib − T·S_vib, the term added to the electronic
    energy in computational-hydrogen-electrode free-energy diagrams.
    """
    real_mev = [mode["meV"] for mode in modes if not mode["imaginary"]]
    kT = BOLTZMANN_EV_K * temperature

    zpe = sum(0.001 * mev / 2.0 for mev in real_mev)
    u_vib = 0.0
    entropy = 0.0  # S in eV/K
    for mev in real_mev:
        energy = 0.001 * mev
        x = energy / kT
        occupation = 1.0 / (math.expm1(x))
        u_vib += energy * occupation
        entropy += BOLTZMANN_EV_K * (x * occupation - math.log(-math.expm1(-x)))

    ts = temperature * entropy
    return {
        "temperature_K": temperature,
        "n_modes": len(real_mev),
        "n_imaginary": sum(1 for mode in modes if mode["imaginary"]),
        "zpe_eV": zpe,
        "u_vib_eV": u_vib,
        "ts_eV": ts,
        "g_correction_eV": zpe + u_vib - ts,
    }


def thermo_from_job(job_dir: Path, temperature: float = DEFAULT_TEMPERATURE_K) -> dict:
    """Frequencies + thermochemistry of a finished freq job directory."""
    job_dir = Path(job_dir)
    modes = parse_frequencies(job_dir / "OUTCAR")
    if not modes:
        raise ValueError(
            f"No vibrational modes found in {job_dir}/OUTCAR — "
            "run with --calc-type freq (IBRION=5) first."
        )
    result = harmonic_thermochemistry(modes, temperature)
    result["modes"] = modes
    try:
        result["energy_eV"] = read_job_energy(job_dir)["energy_eV"]
        result["g_total_eV"] = result["energy_eV"] + result["g_correction_eV"]
    except FileNotFoundError:
        pass
    return result


# --- d-band center -----------------------------------------------------------

def _d_field_indices(fields: list[str]) -> list[int]:
    # LORBIT=11 labels: dxy, dyz, dz2, dxz, x2-y2 (older VASP: dx2); LORBIT=10: d.
    return [
        i for i, name in enumerate(fields)
        if name.lower().startswith("d") or "x2" in name.lower()
    ]


def d_band_center(
    vasprun_path: Path,
    atom_indices: list[int],
    emax_eV: float | None = None,
) -> dict:
    """d-band center (and width) of selected atoms, relative to the Fermi level.

    First moment of the d-projected DOS summed over `atom_indices` (1-based,
    POSCAR order) and both spins. `emax_eV` (relative to E_F) truncates the
    integral, e.g. 0.0 for the occupied d-band only; default integrates the
    whole grid. Needs a DOS run with LORBIT=11.
    """
    pdos = parse_pdos(vasprun_path)
    if pdos is None:
        raise ValueError(f"No projected DOS in {vasprun_path} — run a dos job with LORBIT=11.")

    d_indices = _d_field_indices(pdos["fields"])
    if not d_indices:
        raise ValueError(f"No d orbitals in projected DOS fields: {pdos['fields']}")

    efermi = pdos["efermi"] or 0.0
    energies = [e - efermi for e in pdos["energies"]]

    density = [0.0] * len(energies)
    for atom in atom_indices:
        spins = pdos["pdos"].get(atom)
        if spins is None:
            raise ValueError(f"Atom index {atom} not present in projected DOS (1-based)")
        for channels in spins:
            for field_index in d_indices:
                channel = channels[field_index]
                for i in range(len(density)):
                    density[i] += channel[i]

    # Trapezoidal moments over the (optionally truncated) energy grid.
    norm = 0.0
    first = 0.0
    second = 0.0
    for i in range(1, len(energies)):
        if emax_eV is not None and energies[i] > emax_eV:
            break
        de = energies[i] - energies[i - 1]
        rho = 0.5 * (density[i] + density[i - 1])
        e_mid = 0.5 * (energies[i] + energies[i - 1])
        norm += rho * de
        first += e_mid * rho * de
        second += e_mid * e_mid * rho * de

    if norm <= 0.0:
        raise ValueError("d-projected DOS integrates to zero over the selected window")

    center = first / norm
    width = math.sqrt(max(second / norm - center * center, 0.0))
    return {
        "d_band_center_eV": center,
        "d_band_width_eV": width,
        "atoms": list(atom_indices),
        "efermi_eV": efermi,
        "n_electrons_d": norm,
    }


# --- work function ------------------------------------------------------------

def _fermi_from_outcar(outcar_path: Path) -> float | None:
    if not Path(outcar_path).exists():
        return None
    fermi = None
    with open(outcar_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "E-fermi" in line:
                try:
                    fermi = float(line.split(":")[1].split()[0])
                except (IndexError, ValueError):
                    pass
    return fermi


def work_function(job_dir: Path, axis: int = 2) -> dict:
    """Work function W = V_vacuum − E_Fermi from a LOCPOT slab run.

    The vacuum level is the maximum of the planar-averaged potential along
    `axis` (0=a, 1=b, 2=c). With LDIPOL the two vacuum sides of an asymmetric
    slab differ; the higher plateau (the reported maximum) is the work
    function of the surface facing it. Needs LVHAR = .TRUE. (the
    'workfunction' calc type).
    """
    job_dir = Path(job_dir)
    locpot = job_dir / "LOCPOT"
    if not locpot.exists():
        raise FileNotFoundError(
            f"No LOCPOT in {job_dir} — run with --calc-type workfunction (LVHAR = .TRUE.)"
        )

    fermi = None
    vasprun = parse_vasprun(job_dir / "vasprun.xml")
    if vasprun:
        fermi = vasprun.get("fermi_eV")
    if fermi is None:
        fermi = _fermi_from_outcar(job_dir / "OUTCAR")
    if fermi is None:
        raise ValueError(f"No Fermi level found (vasprun.xml/OUTCAR) in {job_dir}")

    volume = read_volumetric(locpot)
    profile = planar_average(volume, axis=axis)
    vacuum = max(profile)
    return {
        "work_function_eV": vacuum - fermi,
        "vacuum_level_eV": vacuum,
        "fermi_eV": fermi,
        "axis": axis,
        "profile_eV": profile,
    }


# --- optical absorption --------------------------------------------------------

def absorption_spectrum(vasprun_path: Path) -> dict:
    """Optical absorption coefficient α(E) in cm⁻¹ from a LOPTICS run.

    α = 2 E k / ħc with the extinction coefficient k built from the
    direction-averaged dielectric function. Returns {"energies_eV",
    "alpha_cm1", "real", "imag"}.
    """
    dielectric = parse_dielectric(vasprun_path)
    if dielectric is None:
        raise ValueError(
            f"No dielectric function in {vasprun_path} — run with --calc-type optics "
            "(LOPTICS = .TRUE.) first."
        )

    alpha = []
    for energy, e1, e2 in zip(dielectric["energies"], dielectric["real"], dielectric["imag"]):
        modulus = math.sqrt(e1 * e1 + e2 * e2)
        k = math.sqrt(max(modulus - e1, 0.0) / 2.0)
        alpha.append(2.0 * energy * k / HBARC_EV_CM)

    return {
        "energies_eV": dielectric["energies"],
        "alpha_cm1": alpha,
        "real": dielectric["real"],
        "imag": dielectric["imag"],
    }
