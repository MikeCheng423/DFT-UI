# Plan: human-language INCAR builder (guided option picker)

## Goal

Let a user build an INCAR by **picking from labelled choices**, not by typing VASP
tags. Every INCAR variable that VASP defines as a fixed set of values (an enum)
becomes a **dropdown of human-language options**; every free numeric variable
becomes a **number field with a unit and a default**. The UI shows the plain
meaning; the program writes the correct tag.

Key point from the request: **it is not only `ALGO`**. Many tags are enums
(`ISMEAR`, `IBRION`, `ISIF`, `PREC`, `LREAL`, `GGA`, `ICHARG`, `INIWAV`, `LORBIT`,
`IVDW`, `PRECFOCK`, `SMASS`/thermostat, `VOSKOWN` …). Each needs its own option
list taken from the VASP wiki.

## Approach — one declarative catalog, no per-field code

Reuse the existing pattern in `calc_types.py` (StrEnum + a plain-language `info`
dict, "no VASP tag names in the label"). Add **one data file** describing every
exposed variable. The GUI, the CLI `--help`, and the NL builder all read it.

`incar.py` already writes tags via `set_incar_value`; the catalog just supplies
*what* to write. No new writing logic.

### The catalog entry shape

```python
# incar_catalog.py  (data only, no logic)
@dataclass(frozen=True)
class IncarOption:
    label: str        # human text shown in the dropdown, e.g. "Conjugate Gradient"
    value: str        # what goes in INCAR, e.g. "CG" (for ALGO) or "2" (for IBRION)
    hint: str = ""    # one-line tooltip, plain language

@dataclass(frozen=True)
class IncarField:
    tag: str                     # VASP tag, e.g. "ALGO"
    label: str                   # UI label, e.g. "Electronic algorithm"
    group: str                   # which form tab: "SCF", "Calculation", ...
    kind: str                    # "choice" | "number" | "bool" | "text"
    options: list[IncarOption]   # for kind="choice"
    default: str | None          # default value or None
    unit: str = ""               # for numbers, e.g. "eV"
    doc: str = ""                # VASP wiki URL for "learn more"
```

A `choice` field renders as a dropdown, a `number` as a box+unit, a `bool` as a
checkbox. That is the whole UI mapping — three widget kinds cover the dialog.

## Enum variables and their option lists (from the VASP wiki)

Source: https://www.vasp.at/wiki/ — one page per tag. Fill from there, don't
invent values. Starting set (the ones visible in the docx tabs):

| UI group | Field label | tag | options (label → value) |
|---|---|---|---|
| Calculation | Type of calculation | (drives IBRION/NSW/ISIF) | Single Point → SCF; Structure Optimization → relax; Molecular Dynamics → MD |
| Calculation | Precision | `PREC` | Normal→Normal; Accurate→Accurate; Single→Single; Low→Low |
| Calculation | Projection | `LREAL` | Reciprocal space→.FALSE.; Real space (auto)→Auto |
| Functional | DFT exchange-correlation | `GGA` | GGA-PBE→PE; PBEsol→PS; revPBE→RP; AM05→AM; (LDA→omit GGA) |
| Interaction | Van der Waals | `IVDW` | None→0; DFT-D2→1; DFT-D3 (Grimme)→11; DFT-D3 (BJ)→12; TS→2; dDsC→4 |
| Interaction | Magnetism | `ISPIN`(+`MAGMOM`) | Non-magnetic→1; Spin-polarised→2 |
| Structure Opt | Update algorithm | `IBRION` | Conjugate Gradient→2; Quasi-Newton (RMM-DIIS)→1; Damped MD→3 |
| Structure Opt | What can move | `ISIF` | Atoms only→2; Atoms+volume→7*; Atoms+cell shape+volume→3 |
| MD | Ensemble | `MDALGO`/`SMASS` | micro canonical nVE; canonical nVT; nPT (pick per wiki) |
| MD | Thermostat | `MDALGO` | Nosé-Hoover→2; Andersen→1; Langevin→3 |
| SCF | Type of smearing | `ISMEAR` | Methfessel-Paxton→1 (needs order N); Gaussian→0; Tetrahedron+Bloechl→-5; Fermi→-1 |
| SCF | Electronic algorithm | `ALGO` | Normal (blocked Davidson)→Normal; Fast→Fast; VeryFast (RMM-DIIS)→VeryFast; All→All; Damped→Damped |
| DOS/Optics | DOS projection | `LORBIT` | automatic/off→(omit); site+l projected→11; +m projected→12 |
| Advanced | Initial wave functions | `INIWAV` | Random numbers→1; Lowest eigenvectors→0 |
| Advanced | Initial charge density | `ICHARG` | Atomic densities→2; From CHGCAR→1; From WAVECAR→0; Fixed (non-SC)→11 |
| Advanced | Spin interpolation | `VOSKOWN` | Vosko-Wilk-Nusair→1; VASP default→0 |
| Advanced | Strong correlation | `LDAU`/`LHFCALC` | Standard LDA/GGA→off; DFT+U→LDAU; Hybrid HSE06→LHFCALC |

\* verify `ISIF` mapping against the wiki table (ISIF 0–7 differ by what's
relaxed and what stress is computed); the "allow volume / allow shape"
checkboxes in the docx map onto ISIF, not separate tags.

Number/bool fields (no option list, just default+unit): `ENCUT` (eV, default from
POTCAR), `NSW`, `EDIFF` (eV), `EDIFFG` (eV/Å), `SIGMA` (eV), `NELM`, `NELMIN`,
`NBANDS`, `POTIM`, `TEBEG`/`TEEND` (K), `LWAVE`, `LCHARG`, `ADDGRID`, `LREAL`.

## How the pieces connect

```
incar_catalog.py  (data: fields + options + wiki URLs)
        │
        ├──► GUI form      : render dropdown/number/checkbox per field.kind
        ├──► CLI/--help    : list fields and their choices
        └──► builder       : chosen {tag: value} → incar.set_incar_value()  (already exists)
```

The NL builder (`nl_builder.py`) can also target the catalog: map a phrase like
"use conjugate gradient relaxation" onto `IBRION=2` by matching option labels.

## Steps

1. Write `incar_catalog.py` with the dataclasses above and the fields for the
   **SCF + Calculation** tabs only (smallest useful slice: ISMEAR, ALGO, IBRION,
   ISIF, PREC, ENCUT, EDIFF, SIGMA, ISPIN). Include the wiki URL per field.
2. Add a tiny `demo()`/`__main__` self-check: every `choice` field has ≥2
   options, every option `value` is non-empty, and defaults resolve to a real
   option. (One assert-based check, the thing that breaks if the table rots.)
3. Point one consumer at it first — extend `nl_builder` or a `--list-options`
   CLI flag — to prove the catalog drives real INCAR output through the existing
   `set_incar_value`.
4. Grow the table tab-by-tab (Functional, Interaction/vdW, MD, DOS/Optics,
   Advanced) once the shape holds. Verify every enum's values against the wiki
   page for that tag — do not trust memory for the numeric codes.

## Deliberately skipped for now

- No live "Preview Input" INCAR renderer — `set_incar_value` already produces the
  text; wire a preview only once a GUI exists.
- No validation of physically-inconsistent combos (e.g. ISMEAR=-5 with small
  cells) beyond what VASP itself warns; add when a user actually hits it.
- No auto-defaulting of ENCUT from POTCAR in the catalog; POTCAR handling lives
  in `potcar_finder.py` — reference it, don't duplicate.

skipped: GUI widgets + full tab coverage, add once the SCF slice proves the catalog shape.
