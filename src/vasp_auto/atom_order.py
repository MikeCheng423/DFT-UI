"""Re-index one POSCAR's atoms onto another's ordering.

Endpoints relaxed in separate runs come back with their atoms in different
orders — ASE and pymatgen sort species alphabetically, VASP keeps whatever order
it was handed — and an NEB band built from mismatched endpoints either aborts on
validation or, worse, interpolates atom 5 into atom 12's site.

This is a deliberate, user-triggered repair: nothing in the run path calls it.
Run it from the NEB tab's *Match atom order* button, or from the shell::

    python -m vasp_auto.atom_order initial/POSCAR final/POSCAR

Pure stdlib — the remote compute nodes install the engine without numpy or ase.
"""

from __future__ import annotations

from pathlib import Path

from vasp_auto.job_manager import _read_poscar_for_interpolation, _write_poscar


def _poscar_cell(header):
    """Lattice vectors (scaled) from a POSCAR header block."""
    scale = float(header[1].split()[0])
    if scale < 0:  # negative scale means "target volume"; our builders never emit it
        scale = 1.0
    return [[float(x) * scale for x in header[i].split()[:3]] for i in (2, 3, 4)]


def _distance(a, b, cell, direct: bool):
    """Distance between two coordinate triples, minimum-image if fractional."""
    delta = [x - y for x, y in zip(a, b)]
    if direct:
        delta = [d - round(d) for d in delta]
        delta = [sum(delta[k] * cell[k][j] for k in range(3)) for j in range(3)]
    return sum(d * d for d in delta) ** 0.5


def _pair_species(ref_coords, tgt_coords, cell, direct: bool):
    """Pair each reference atom with a target atom of the same species.

    ponytail: global greedy over the sorted distance list, not Hungarian — the two
    endpoints of one reaction sit nearly on top of each other apart from the few
    atoms that actually move, so greedy and optimal agree. Swap in an assignment
    solver if a band ever comes out with two atoms trading places.
    """
    pairs = sorted(
        (_distance(a, b, cell, direct), i, j)
        for i, a in enumerate(ref_coords)
        for j, b in enumerate(tgt_coords)
    )
    mapping = [None] * len(ref_coords)
    taken = set()
    for dist, i, j in pairs:
        if mapping[i] is None and j not in taken:
            mapping[i] = (j, dist)
            taken.add(j)
    return mapping


def match_atom_order(reference, target):
    """Reorder ``target``'s atoms onto ``reference``'s indexing.

    Both are dicts from :func:`~vasp_auto.job_manager._read_poscar_for_interpolation`.
    Covers the two ways endpoints drift apart: species blocks written in a
    different order, and atoms permuted within a block. Returns
    ``(new_target, moves)``, where ``moves`` is a list of
    ``(element, largest_displacement)`` per species — inspect it, a value far
    above the others means that species genuinely moves in the reaction, or that
    the pairing is wrong. Returns ``(target, None)`` when nothing changed.
    """
    same_blocks = (
        reference["elements"] == target["elements"]
        and reference["counts"] == target["counts"]
    )
    if not same_blocks and sorted(zip(reference["elements"], reference["counts"])) != sorted(
        zip(target["elements"], target["counts"])
    ):
        return target, None  # genuinely different composition — nothing to match

    direct = target["coord_mode"].strip().lower().startswith("d")
    cell = _poscar_cell(target["header"])

    def blocks(poscar):
        out, start = {}, 0
        for element, count in zip(poscar["elements"], poscar["counts"]):
            out[element] = list(range(start, start + count))
            start += count
        return out

    ref_blocks, tgt_blocks = blocks(reference), blocks(target)

    order, moves = [], []
    for element in reference["elements"]:
        mapping = _pair_species(
            [reference["coords"][i] for i in ref_blocks[element]],
            [target["coords"][j] for j in tgt_blocks[element]],
            cell,
            direct,
        )
        order += [tgt_blocks[element][j] for j, _ in mapping]
        moves.append((element, max(d for _, d in mapping)))

    if same_blocks and order == list(range(len(order))):
        return target, None

    header = list(target["header"])
    header[5] = reference["header"][5]
    header[6] = reference["header"][6]
    return {
        **target,
        "header": header,
        "elements": list(reference["elements"]),
        "counts": list(reference["counts"]),
        "coords": [target["coords"][j] for j in order],
        "suffixes": [target["suffixes"][j] for j in order],
        # Per-atom trailing blocks (velocities, predictor-corrector) no longer line
        # up with the new ordering and mean nothing for an NEB endpoint.
        "tail": [],
    }, moves


def reindex_poscar_text(reference_text: str, target_text: str, tmp_dir: Path):
    """:func:`match_atom_order` over POSCAR text. Returns ``(text, moves)``.

    ``text`` is None when the orderings already agree. ``tmp_dir`` is scratch
    space for the parser, which works on files.
    """
    reference_path, target_path = tmp_dir / "ref", tmp_dir / "tgt"
    reference_path.write_text(reference_text, encoding="utf-8")
    target_path.write_text(target_text, encoding="utf-8")

    reference = _read_poscar_for_interpolation(reference_path)
    target = _read_poscar_for_interpolation(target_path)
    fixed, moves = match_atom_order(reference, target)
    if moves is None:
        return None, None

    out = tmp_dir / "fixed"
    _write_poscar(fixed, fixed["coords"], out)
    return out.read_text(encoding="utf-8"), moves


def main(argv=None):
    """``python -m vasp_auto.atom_order REFERENCE TARGET [OUTPUT]``"""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reference", type=Path, help="POSCAR whose ordering wins")
    parser.add_argument("target", type=Path, help="POSCAR to re-index")
    parser.add_argument("output", type=Path, nargs="?",
                        help="where to write it (default: overwrite the target)")
    args = parser.parse_args(argv)

    reference = _read_poscar_for_interpolation(args.reference)
    target = _read_poscar_for_interpolation(args.target)
    fixed, moves = match_atom_order(reference, target)
    if moves is None:
        print(f"{args.target}: already matches {args.reference}, nothing written")
        return 0

    output = args.output or args.target
    _write_poscar(fixed, fixed["coords"], output)
    print("largest displacement per species: "
          + ", ".join(f"{element} {dist:.2f} A" for element, dist in moves))
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
