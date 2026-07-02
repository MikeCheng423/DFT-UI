"""Human-language INCAR option catalog (human-readable picker).

Data only — no VASP knowledge beyond these tables. The GUI, CLI `--help`, and
NL builder read this; writing stays in `incar.set_incar_value`.

Each field is either a `choice` (dropdown of labelled options → VASP value),
a `number` (box + unit + default), or a `bool` (checkbox). Labels are plain
language; the `value` is what lands in the INCAR.

This module is the SCF + Calculation slice. Enum codes are taken from the VASP
wiki (one page per tag, linked in `doc`); verify there before adding more.
"""
from __future__ import annotations

from dataclasses import dataclass, field

WIKI = "https://www.vasp.at/wiki/index.php"


@dataclass(frozen=True)
class IncarOption:
    label: str        # shown in the dropdown, e.g. "Conjugate Gradient"
    value: str        # goes in INCAR, e.g. "CG" or "2"
    hint: str = ""    # one-line plain-language tooltip


@dataclass(frozen=True)
class IncarField:
    tag: str                                    # VASP tag, e.g. "ALGO"
    label: str                                  # UI label, plain language
    group: str                                  # GUI tab: "Calculation" | "SCF"
    kind: str                                   # "choice" | "number" | "bool"
    default: str | None = None                  # default value (an option.value for choices)
    options: list[IncarOption] = field(default_factory=list)
    unit: str = ""                              # for numbers, e.g. "eV"
    doc: str = ""                               # wiki URL for "learn more"
    applies_to: frozenset[str] | None = None    # CalcType values; None = every type


# Calculation-type groups a field belongs to (values match CalcType). A field
# with applies_to=None is universal — shown for every calculation type.
RELAXING = frozenset({"relax", "vcrelax"})   # ions/cell actually move


# --- SCF + Calculation slice ------------------------------------------------

FIELDS: list[IncarField] = [
    IncarField(
        tag="PREC", label="Precision", group="Calculation", kind="choice",
        default="Normal", doc=f"{WIKI}/PREC",
        options=[
            IncarOption("Normal", "Normal", "Balanced grids — the usual choice"),
            IncarOption("Accurate", "Accurate", "Denser grids; avoids wrap-around errors"),
            IncarOption("Single", "Single", "Single-point grids, no augmentation extras"),
            IncarOption("Low", "Low", "Coarse grids, fast and rough"),
        ],
    ),
    IncarField(
        tag="ENCUT", label="Planewave cutoff", group="Calculation", kind="number",
        default=None, unit="eV", doc=f"{WIKI}/ENCUT",
    ),
    IncarField(
        tag="ISPIN", label="Magnetism", group="Calculation", kind="choice",
        default="1", doc=f"{WIKI}/ISPIN",
        options=[
            IncarOption("Non-magnetic", "1", "Spin-unpolarised"),
            IncarOption("Spin-polarised", "2", "Also writes a MAGMOM guess"),
        ],
    ),
    IncarField(
        tag="IBRION", label="Ionic update algorithm", group="Calculation", kind="choice",
        default="2", doc=f"{WIKI}/IBRION", applies_to=RELAXING,
        options=[
            IncarOption("Conjugate Gradient", "2", "Robust default for relaxations"),
            IncarOption("Quasi-Newton (RMM-DIIS)", "1", "Fast near a good minimum"),
            IncarOption("Damped molecular dynamics", "3", "For hard-to-converge cells"),
            IncarOption("No ionic update (fixed atoms)", "-1", "Single-point / SCF only"),
        ],
    ),
    IncarField(
        tag="ISIF", label="What is allowed to move", group="Calculation", kind="choice",
        default="2", doc=f"{WIKI}/ISIF", applies_to=RELAXING,
        options=[
            IncarOption("Atoms only", "2", "Relax ions, cell fixed"),
            IncarOption("Atoms + cell shape (constant volume)", "4", "Ions and shape, volume fixed"),
            IncarOption("Atoms + cell shape + volume (full)", "3", "Relax everything"),
        ],
    ),
    IncarField(
        tag="NSW", label="Maximum ionic steps", group="Calculation", kind="number",
        default="100", doc=f"{WIKI}/NSW", applies_to=RELAXING,
    ),
    IncarField(
        tag="EDIFFG", label="Ionic convergence", group="Calculation", kind="number",
        default="-0.02", unit="eV/Ang", doc=f"{WIKI}/EDIFFG", applies_to=RELAXING,
    ),
    IncarField(
        tag="GGA", label="DFT exchange-correlation", group="Functional", kind="choice",
        default="PE", doc=f"{WIKI}/GGA",
        options=[
            IncarOption("GGA-PBE", "PE", "The standard general-purpose GGA"),
            IncarOption("PBEsol", "PS", "PBE revised for solids/lattice constants"),
            IncarOption("RPBE", "RE", "Better for molecular adsorption energies"),
            IncarOption("revPBE", "RP", "Revised PBE exchange"),
            IncarOption("PW91", "91", "The older Perdew-Wang 91 GGA"),
            IncarOption("AM05", "AM", "Armiento-Mattsson 05"),
            IncarOption("LDA", "CA", "Local density (Ceperley-Alder), no gradient"),
        ],
    ),
    IncarField(
        tag="ISMEAR", label="Type of smearing", group="SCF", kind="choice",
        default="1", doc=f"{WIKI}/ISMEAR",
        options=[
            IncarOption("Methfessel-Paxton", "1", "Metals; set order with SIGMA small"),
            IncarOption("Gaussian", "0", "Safe general choice, molecules"),
            IncarOption("Fermi", "-1", "Fermi-Dirac smearing"),
            IncarOption("Tetrahedron + Blöchl", "-5", "Insulators/DOS; needs a dense k-mesh"),
        ],
    ),
    IncarField(
        tag="SIGMA", label="Smearing width", group="SCF", kind="number",
        default="0.2", unit="eV", doc=f"{WIKI}/SIGMA",
    ),
    IncarField(
        tag="ALGO", label="Electronic algorithm", group="SCF", kind="choice",
        default="Normal", doc=f"{WIKI}/ALGO",
        options=[
            IncarOption("Normal (blocked Davidson)", "Normal", "Reliable default"),
            IncarOption("Fast (Davidson + RMM-DIIS)", "Fast", "Faster, usually fine"),
            IncarOption("VeryFast (RMM-DIIS)", "VeryFast", "Fastest, can be unstable"),
            IncarOption("All (all bands simultaneously)", "All", "For difficult systems"),
            IncarOption("Damped", "Damped", "Damped MD for the electrons"),
        ],
    ),
    IncarField(
        tag="EDIFF", label="Electronic convergence", group="SCF", kind="number",
        default="1.0e-05", unit="eV", doc=f"{WIKI}/EDIFF",
    ),
    IncarField(
        tag="NELM", label="Maximum electronic steps", group="SCF", kind="number",
        default="60", doc=f"{WIKI}/NELM",
    ),
    IncarField(
        tag="NELMIN", label="Minimum electronic steps", group="SCF", kind="number",
        default="2", doc=f"{WIKI}/NELMIN",
    ),
    # --- DOS-only fields (shown when the calculation type is "dos") ----------
    IncarField(
        tag="LORBIT", label="Orbital projection", group="DOS", kind="choice",
        default="11", doc=f"{WIKI}/LORBIT", applies_to=frozenset({"dos"}),
        options=[
            IncarOption("s/p/d per atom (l-decomposed)", "10", "Site- and l-projected DOS"),
            IncarOption("+ m-decomposed (px, py, ...)", "11", "Also splits by magnetic quantum number"),
            IncarOption("+ phase factors", "12", "Adds phase for character analysis"),
        ],
    ),
    IncarField(
        tag="NEDOS", label="Number of DOS grid points", group="DOS", kind="number",
        default="3000", doc=f"{WIKI}/NEDOS", applies_to=frozenset({"dos"}),
    ),
    IncarField(
        tag="EMIN", label="DOS energy window — minimum", group="DOS", kind="number",
        default=None, unit="eV", doc=f"{WIKI}/EMIN", applies_to=frozenset({"dos"}),
    ),
    IncarField(
        tag="EMAX", label="DOS energy window — maximum", group="DOS", kind="number",
        default=None, unit="eV", doc=f"{WIKI}/EMAX", applies_to=frozenset({"dos"}),
    ),
]


def fields_for(calc_type: str | None) -> list[IncarField]:
    """Fields relevant to a calculation type.

    ``None`` returns the whole catalog (the CLI reference listing). A given type
    returns the universal fields (``applies_to is None``) plus that type's own
    fields — so a single-point SCF run drops the ionic-movement settings, while
    a DOS run gains its projection/energy-window fields.
    """
    if not calc_type:
        return list(FIELDS)
    ct = str(calc_type).strip().lower()
    return [f for f in FIELDS if f.applies_to is None or ct in f.applies_to]


def fields_by_group(calc_type: str | None = None) -> dict[str, list[IncarField]]:
    """Fields grouped by GUI tab, in declaration order — for form rendering."""
    groups: dict[str, list[IncarField]] = {}
    for f in fields_for(calc_type):
        groups.setdefault(f.group, []).append(f)
    return groups


def demo():
    """Self-check: the catalog is well-formed enough to drive a form."""
    from vasp_auto.calc_types import CalcType
    valid_types = {t.value for t in CalcType}
    tags = [f.tag for f in FIELDS]
    assert len(tags) == len(set(tags)), "duplicate tag in catalog"
    for f in FIELDS:
        assert f.kind in {"choice", "number", "bool"}, f"{f.tag}: bad kind {f.kind}"
        if f.applies_to is not None:
            unknown = set(f.applies_to) - valid_types
            assert not unknown, f"{f.tag}: unknown calc types {unknown}"
        if f.kind == "choice":
            assert len(f.options) >= 2, f"{f.tag}: a choice needs >=2 options"
            values = [o.value for o in f.options]
            assert all(v.strip() for v in values), f"{f.tag}: empty option value"
            assert len(values) == len(set(values)), f"{f.tag}: duplicate option value"
            assert f.default in values, f"{f.tag}: default {f.default!r} not an option"
        else:
            assert not f.options, f"{f.tag}: only choices carry options"
    # A single-point SCF hides ionic-movement tags; relax shows them; DOS adds its own.
    scf = {f.tag for f in fields_for("scf")}
    assert not ({"IBRION", "ISIF", "NSW", "NEDOS"} & scf), scf
    relax = {f.tag for f in fields_for("relax")}
    assert {"IBRION", "ISIF"} <= relax, relax
    dos = {f.tag for f in fields_for("dos")}
    assert "NEDOS" in dos and "IBRION" not in dos, dos
    print(f"OK: {len(FIELDS)} fields; scf={len(scf)}, relax={len(relax)}, dos={len(dos)}")


if __name__ == "__main__":
    demo()
