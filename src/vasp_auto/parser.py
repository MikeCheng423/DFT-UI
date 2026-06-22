"""vasprun.xml parsing (stdlib ElementTree only).

OUTCAR/OSZICAR parsing lives in workflow.py; this module is the structured
XML path used to enrich summary rows.
"""
import math
import xml.etree.ElementTree as ET
from pathlib import Path


# Occupations at or below this count a state as unoccupied for band-gap search.
OCCUPATION_THRESHOLD = 0.5


def _float_or_none(element) -> float | None:
    if element is None or element.text is None:
        return None
    try:
        return float(element.text.strip())
    except ValueError:
        return None


def _max_force(varray) -> float | None:
    if varray is None:
        return None
    max_force = None
    for vector in varray.findall("v"):
        parts = [float(x) for x in vector.text.split()]
        force = math.sqrt(sum(x * x for x in parts))
        if max_force is None or force > max_force:
            max_force = force
    return max_force


def _pressure_kB(varray) -> float | None:
    if varray is None:
        return None
    rows = [[float(x) for x in vector.text.split()] for vector in varray.findall("v")]
    if len(rows) != 3:
        return None
    return (rows[0][0] + rows[1][1] + rows[2][2]) / 3.0


def _band_edges(eigenvalues) -> tuple[float | None, float | None]:
    if eigenvalues is None:
        return None, None
    vbm = None
    cbm = None
    for record in eigenvalues.iter("r"):
        parts = record.text.split()
        if len(parts) < 2:
            continue
        energy, occupation = float(parts[0]), float(parts[1])
        if occupation > OCCUPATION_THRESHOLD:
            if vbm is None or energy > vbm:
                vbm = energy
        else:
            if cbm is None or energy < cbm:
                cbm = energy
    return vbm, cbm


def parse_vasprun(vasprun_path: Path) -> dict | None:
    """Parse vasprun.xml into a structured result dict.

    Returns None when the file is missing or truncated (interrupted run).
    """
    vasprun_path = Path(vasprun_path)
    if not vasprun_path.exists():
        return None

    try:
        root = ET.parse(vasprun_path).getroot()
    except ET.ParseError:
        return None

    calculations = root.findall("calculation")
    if not calculations:
        return None
    last = calculations[-1]

    energy = _float_or_none(last.find("energy/i[@name='e_fr_energy']"))
    fermi = _float_or_none(last.find("dos/i[@name='efermi']"))
    if fermi is None:
        fermi_nodes = root.findall(".//i[@name='efermi']")
        fermi = _float_or_none(fermi_nodes[-1]) if fermi_nodes else None

    vbm, cbm = _band_edges(last.find("eigenvalues"))
    band_gap = None
    if vbm is not None and cbm is not None:
        band_gap = max(0.0, cbm - vbm)

    return {
        "energy_eV": energy,
        "fermi_eV": fermi,
        "band_gap_eV": band_gap,
        "vbm_eV": vbm,
        "cbm_eV": cbm,
        "max_force_eV_A": _max_force(last.find("varray[@name='forces']")),
        "pressure_kB": _pressure_kB(last.find("varray[@name='stress']")),
        "ionic_steps": len(calculations),
    }


def parse_dos(vasprun_path: Path) -> dict | None:
    """Total density of states from vasprun.xml.

    Returns {"efermi", "energies", "total": [spin1, spin2?]} or None when the
    run wrote no DOS block (e.g. plain relaxations).
    """
    vasprun_path = Path(vasprun_path)
    if not vasprun_path.exists():
        return None
    try:
        root = ET.parse(vasprun_path).getroot()
    except ET.ParseError:
        return None

    dos_nodes = root.findall(".//dos")
    if not dos_nodes:
        return None
    dos = dos_nodes[-1]
    efermi = _float_or_none(dos.find("i[@name='efermi']"))

    spin_sets = dos.findall("total/array/set/set")
    if not spin_sets:
        return None

    energies = []
    total = []
    for spin_index, spin_set in enumerate(spin_sets):
        channel = []
        for record in spin_set.findall("r"):
            parts = record.text.split()
            if len(parts) < 2:
                continue
            if spin_index == 0:
                energies.append(float(parts[0]))
            channel.append(float(parts[1]))
        total.append(channel)

    if not energies or not total[0]:
        return None
    return {"efermi": efermi, "energies": energies, "total": total}


def parse_pdos(vasprun_path: Path) -> dict | None:
    """Site- and orbital-projected DOS from vasprun.xml (needs LORBIT=10/11).

    Returns {"efermi", "energies", "fields", "pdos"} where fields are the
    orbital labels after the energy column (s, py, pz, ... or s, p, d) and
    pdos[atom_index][spin_index][field_index] is a list over the energy grid.
    Atom indices are 1-based, POSCAR order. None when no partial DOS exists.
    """
    vasprun_path = Path(vasprun_path)
    if not vasprun_path.exists():
        return None
    try:
        root = ET.parse(vasprun_path).getroot()
    except ET.ParseError:
        return None

    dos_nodes = root.findall(".//dos")
    if not dos_nodes:
        return None
    dos = dos_nodes[-1]
    efermi = _float_or_none(dos.find("i[@name='efermi']"))

    partial = dos.find("partial/array")
    if partial is None:
        return None

    fields = [f.text.strip() for f in partial.findall("field")][1:]  # drop "energy"
    ion_sets = partial.findall("set/set")
    if not ion_sets or not fields:
        return None

    energies: list[float] = []
    pdos: dict[int, list[list[list[float]]]] = {}
    for ion_index, ion_set in enumerate(ion_sets, start=1):
        spins = []
        for spin_index, spin_set in enumerate(ion_set.findall("set")):
            channels: list[list[float]] = [[] for _ in fields]
            for record in spin_set.findall("r"):
                parts = record.text.split()
                if len(parts) < 1 + len(fields):
                    continue
                if ion_index == 1 and spin_index == 0:
                    energies.append(float(parts[0]))
                for field_index in range(len(fields)):
                    channels[field_index].append(float(parts[1 + field_index]))
            spins.append(channels)
        pdos[ion_index] = spins

    if not energies:
        return None
    return {"efermi": efermi, "energies": energies, "fields": fields, "pdos": pdos}


def aggregate_pdos(pdos: dict, symbols: list[str],
                   atoms: list[int] | None = None) -> dict:
    """Sum a parse_pdos result into per-element, per-shell (s/p/d/f) curves.

    `symbols` is the per-atom element list (POSCAR order); `atoms` optionally
    restricts to 1-based indices (e.g. surface atoms only). Returns
    {"efermi", "energies", "curves": [{"label", "element", "shell", "spin",
    "values"}, ...]} — the shape both the UI plots and pdos.csv export use.
    """
    selected = set(atoms) if atoms else set(range(1, len(symbols) + 1))
    shells = []  # per-field shell letter: "py" -> "p", "x2-y2" -> "d"
    for field in pdos["fields"]:
        first = field.strip()[0].lower()
        shells.append(first if first in "spdf" else "d")

    npoints = len(pdos["energies"])
    sums: dict[tuple[str, str, int], list[float]] = {}
    for ion_index, spins in pdos["pdos"].items():
        if ion_index not in selected or ion_index > len(symbols):
            continue
        element = symbols[ion_index - 1]
        for spin_index, channels in enumerate(spins):
            for field_index, channel in enumerate(channels):
                key = (element, shells[field_index], spin_index)
                if key not in sums:
                    sums[key] = [0.0] * npoints
                accumulator = sums[key]
                for i, value in enumerate(channel):
                    accumulator[i] += value

    curves = [
        {
            "label": f"{element} {shell}",
            "element": element,
            "shell": shell,
            "spin": spin_index,
            "values": values,
        }
        for (element, shell, spin_index), values in sorted(sums.items())
    ]
    return {"efermi": pdos["efermi"], "energies": pdos["energies"], "curves": curves}


def read_kpoints_labels(kpoints_path: Path) -> list[dict] | None:
    """High-symmetry labels from a line-mode KPOINTS file.

    Returns [{"index", "label"}, ...] (0-based k-point indices into the run's
    k-point list) or None when the file is missing or not line-mode.
    """
    kpoints_path = Path(kpoints_path)
    if not kpoints_path.exists():
        return None
    lines = kpoints_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 4 or not lines[2].strip().lower().startswith("l"):
        return None
    try:
        divisions = int(lines[1].split()[0])
    except (ValueError, IndexError):
        return None

    # Segment endpoints: "kx ky kz ! LABEL" pairs, blank lines between segments.
    endpoint_labels = []
    for line in lines[4:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        label = line.partition("!")[2].strip() if "!" in line else ""
        endpoint_labels.append(label or "?")
    if len(endpoint_labels) < 2:
        return None

    labels = []
    for segment in range(len(endpoint_labels) // 2):
        start, end = endpoint_labels[2 * segment], endpoint_labels[2 * segment + 1]
        start_index = segment * divisions
        end_index = start_index + divisions - 1
        if labels and labels[-1]["index"] == start_index - 1:
            if labels[-1]["label"] != start:
                # Discontinuous path (e.g. X|K): show both at the joint.
                labels[-1]["label"] += "|" + start
        else:
            labels.append({"index": start_index, "label": start})
        labels.append({"index": end_index, "label": end})
    return labels


def parse_bands(vasprun_path: Path, kpoints_path: Path | None = None) -> dict | None:
    """Band structure from vasprun.xml (typically a line-mode 'bands' run).

    Returns {"efermi", "kpoints", "distances", "bands", "labels"} where
    bands[spin][band] is a list over k-points (eV, absolute — subtract efermi
    to plot), distances are cumulative |Δk| along the path (1/Å) and labels
    come from the line-mode KPOINTS file when available. None when the run
    wrote no eigenvalues.
    """
    vasprun_path = Path(vasprun_path)
    if not vasprun_path.exists():
        return None
    try:
        root = ET.parse(vasprun_path).getroot()
    except ET.ParseError:
        return None

    calculations = root.findall("calculation")
    if not calculations:
        return None
    eigenvalues = calculations[-1].find("eigenvalues/array/set")
    if eigenvalues is None:
        return None

    fermi_nodes = root.findall(".//i[@name='efermi']")
    efermi = _float_or_none(fermi_nodes[-1]) if fermi_nodes else None

    kpoint_list = root.find("kpoints/varray[@name='kpointlist']")
    if kpoint_list is None:
        return None
    kpoints = [[float(x) for x in v.text.split()] for v in kpoint_list.findall("v")]

    rec_basis = root.find("structure[@name='finalpos']/crystal/varray[@name='rec_basis']")
    if rec_basis is None:
        rec_basis = root.find(".//varray[@name='rec_basis']")
    basis = (
        [[float(x) for x in v.text.split()] for v in rec_basis.findall("v")]
        if rec_basis is not None
        else [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )

    def to_cart(frac):
        return [sum(frac[i] * basis[i][k] for i in range(3)) for k in range(3)]

    distances = [0.0]
    for previous, current in zip(kpoints, kpoints[1:]):
        p, q = to_cart(previous), to_cart(current)
        step = math.sqrt(sum((q[k] - p[k]) ** 2 for k in range(3)))
        distances.append(distances[-1] + step)

    bands: list[list[list[float]]] = []
    for spin_set in eigenvalues.findall("set"):
        kpoint_sets = spin_set.findall("set")
        if not kpoint_sets:
            continue
        nbands = len(kpoint_sets[0].findall("r"))
        spin_bands = [[] for _ in range(nbands)]
        for kpoint_set in kpoint_sets:
            for band_index, record in enumerate(kpoint_set.findall("r")):
                if band_index < nbands:
                    spin_bands[band_index].append(float(record.text.split()[0]))
        bands.append(spin_bands)
    if not bands or not bands[0]:
        return None

    labels = None
    if kpoints_path is not None:
        labels = read_kpoints_labels(kpoints_path)
        if labels and labels[-1]["index"] >= len(kpoints):
            labels = None  # KPOINTS file does not match this run

    return {
        "efermi": efermi,
        "kpoints": kpoints,
        "distances": distances,
        "bands": bands,
        "labels": labels or [],
    }


def parse_dielectric(vasprun_path: Path) -> dict | None:
    """Frequency-dependent dielectric function from a LOPTICS run.

    Returns {"energies", "real", "imag"} where real/imag are the direction-
    averaged (trace/3) parts of the dielectric tensor on the energy grid.
    None when the run wrote no <dielectricfunction> block.
    """
    vasprun_path = Path(vasprun_path)
    if not vasprun_path.exists():
        return None
    try:
        root = ET.parse(vasprun_path).getroot()
    except ET.ParseError:
        return None

    dielectric = root.find(".//dielectricfunction")
    if dielectric is None:
        return None

    def _read_part(tag: str) -> tuple[list[float], list[float]]:
        energies = []
        averaged = []
        part = dielectric.find(f"{tag}/array/set")
        if part is None:
            return energies, averaged
        for record in part.findall("r"):
            parts = [float(x) for x in record.text.split()]
            if len(parts) < 4:
                continue
            energies.append(parts[0])
            averaged.append((parts[1] + parts[2] + parts[3]) / 3.0)
        return energies, averaged

    energies, imag = _read_part("imag")
    real_energies, real = _read_part("real")
    if not energies or not real_energies:
        return None
    return {"energies": energies, "real": real, "imag": imag}


# --------------------------------------------------------- Quantum ESPRESSO

# 1 Rydberg in eV — pw.x reports energies in Ry; the summary rows are in eV.
RY_TO_EV = 13.605693122994


def parse_pw_output(pw_out_path: Path) -> dict | None:
    """Parse a Quantum ESPRESSO pw.x output (pw.out) into a summary dict.

    Returns the same row keys the VASP path emits so the Excel/Results columns
    line up: energy_eV, converged, ionic_steps, max_force_eV_A, pressure_kB.
    None when the file is missing.
    """
    pw_out_path = Path(pw_out_path)
    if not pw_out_path.exists():
        return None

    summary: dict = {
        "energy_eV": None,
        "converged": False,
        "ionic_steps": 0,
        "max_force_eV_A": None,
        "pressure_kB": None,
    }

    with open(pw_out_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            # Final SCF total energy lines start with "!".
            if line.lstrip().startswith("!") and "total energy" in line:
                value = _ry_value(line)
                if value is not None:
                    summary["energy_eV"] = value * RY_TO_EV
            elif "convergence has been achieved" in line:
                summary["converged"] = True
            elif "Total force =" in line:
                # "Total force =     0.001234     Total SCF correction = ..."
                try:
                    force_ry_au = float(line.split("=")[1].split()[0])
                    # Ry/Bohr -> eV/Angstrom (1 Bohr = 0.529177 A).
                    summary["max_force_eV_A"] = force_ry_au * RY_TO_EV / 0.529177210903
                except (IndexError, ValueError):
                    pass
            elif "P=" in line and "total   stress" in line:
                # "total   stress  (Ry/bohr**3) ...  P=   12.34" — QE prints kbar.
                try:
                    summary["pressure_kB"] = float(line.split("P=")[1].split()[0]) / 10.0
                except (IndexError, ValueError):
                    pass
            elif "number of bfgs steps" in line.lower():
                try:
                    summary["ionic_steps"] = int(line.split("=")[-1].split()[0])
                except (IndexError, ValueError):
                    pass

    # An scf-only run has no bfgs steps; report 1 when it produced an energy.
    if summary["ionic_steps"] == 0 and summary["energy_eV"] is not None:
        summary["ionic_steps"] = 1
    return summary


def _ry_value(line: str) -> float | None:
    """Extract the Ry number from a '... total energy = -123.45 Ry' line."""
    try:
        after = line.split("=", 1)[1]
    except IndexError:
        return None
    for token in after.split():
        try:
            return float(token)
        except ValueError:
            continue
    return None


def parse_pw_final_structure(pw_out_path: Path) -> dict | None:
    """Read the relaxed cell + positions from a pw.x 'Begin final coordinates'.

    Returns a dict in structure.read_poscar shape (lattice, elements, counts,
    coords, cartesian, …) so it can be written back to a POSCAR for chaining.
    None when no final-coordinates block is present (e.g. an scf run).
    """
    pw_out_path = Path(pw_out_path)
    if not pw_out_path.exists():
        return None

    lines = pw_out_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = None
    for i, line in enumerate(lines):
        if "Begin final coordinates" in line:
            start = i
    if start is None:
        return None

    lattice = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    cartesian = False
    symbols: list[str] = []
    coords: list[list[float]] = []
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if "End final coordinates" in line:
            break
        upper = line.strip().upper()
        if upper.startswith("CELL_PARAMETERS"):
            lattice = [
                [float(x) for x in lines[i + 1].split()[:3]],
                [float(x) for x in lines[i + 2].split()[:3]],
                [float(x) for x in lines[i + 3].split()[:3]],
            ]
            i += 4
            continue
        if upper.startswith("ATOMIC_POSITIONS"):
            cartesian = "ANGSTROM" in upper or "BOHR" in upper
            i += 1
            while i < len(lines):
                parts = lines[i].split()
                if len(parts) < 4 or "End final coordinates" in lines[i]:
                    break
                try:
                    xyz = [float(parts[1]), float(parts[2]), float(parts[3])]
                except ValueError:
                    break
                symbols.append(parts[0])
                coords.append(xyz)
                i += 1
            continue
        i += 1

    if not symbols:
        return None

    elements: list[str] = []
    counts: list[int] = []
    for sym in symbols:
        if elements and elements[-1] == sym:
            counts[-1] += 1
        else:
            elements.append(sym)
            counts.append(1)

    return {
        "comment": "QE final coordinates",
        "scale": 1.0,
        "lattice": lattice,
        "elements": elements,
        "counts": counts,
        "selective": False,
        "cartesian": cartesian,
        "coords": coords,
        "flags": [[] for _ in coords],
    }