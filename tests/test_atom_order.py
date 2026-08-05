import pytest

import vasp_auto.atom_order as atom_order
import vasp_auto.job_manager as job_manager

def _poscar(elements, counts, coords):
    header = [
        "test cell",
        "1.0",
        "10.0 0.0 0.0",
        "0.0 10.0 0.0",
        "0.0 0.0 10.0",
        "  ".join(elements),
        "  ".join(str(c) for c in counts),
        "Selective dynamics",
        "Direct",
    ]
    body = [f"{x:.10f} {y:.10f} {z:.10f}  T  T  T" for x, y, z in coords]
    return "\n".join(header + body) + "\n"


def _parse(tmp_path, name, elements, counts, coords):
    path = tmp_path / name
    path.write_text(_poscar(elements, counts, coords), encoding="utf-8")
    return job_manager._read_poscar_for_interpolation(path)


def test_match_atom_order_reorders_species_blocks(tmp_path):
    # Same structure, but the target lists H before O (how ASE/pymatgen sort it).
    o1, o2, h = (0.1, 0.1, 0.1), (0.2, 0.2, 0.2), (0.3, 0.3, 0.3)
    reference = _parse(tmp_path, "ref", ["O", "H"], [2, 1], [o1, o2, h])
    target = _parse(tmp_path, "tgt", ["H", "O"], [1, 2], [h, o1, o2])

    fixed, moves = atom_order.match_atom_order(reference, target)

    assert fixed["elements"] == ["O", "H"]
    assert fixed["counts"] == [2, 1]
    assert fixed["coords"] == [list(o1), list(o2), list(h)]
    assert dict(moves) == pytest.approx({"O": 0.0, "H": 0.0})


def test_match_atom_order_repairs_permutation_within_a_species(tmp_path):
    a, b = (0.10, 0.10, 0.10), (0.60, 0.60, 0.60)
    reference = _parse(tmp_path, "ref", ["O"], [2], [a, b])
    # Target holds the same two sites, swapped, and one has drifted 1 A.
    target = _parse(tmp_path, "tgt", ["O"], [2], [(0.60, 0.60, 0.70), a])

    fixed, moves = atom_order.match_atom_order(reference, target)

    assert fixed["coords"] == [list(a), [0.60, 0.60, 0.70]]
    assert moves == [("O", pytest.approx(1.0))]


def test_match_atom_order_uses_minimum_image(tmp_path):
    # 0.02 and 0.98 are 0.4 A apart across the boundary, not 9.6 A through the box.
    reference = _parse(tmp_path, "ref", ["O"], [1], [(0.02, 0.0, 0.0)])
    target = _parse(tmp_path, "tgt", ["O"], [1], [(0.98, 0.0, 0.0)])

    _, moves = atom_order.match_atom_order(reference, target)

    assert moves is None  # identity mapping, nothing to reorder


def test_match_atom_order_leaves_matching_endpoints_alone(tmp_path):
    coords = [(0.1, 0.1, 0.1), (0.2, 0.2, 0.2)]
    reference = _parse(tmp_path, "ref", ["O", "H"], [1, 1], coords)
    target = _parse(tmp_path, "tgt", ["O", "H"], [1, 1], coords)

    fixed, moves = atom_order.match_atom_order(reference, target)

    assert fixed is target and moves is None


def test_match_atom_order_ignores_different_compositions(tmp_path):
    reference = _parse(tmp_path, "ref", ["O"], [2], [(0.1, 0.1, 0.1), (0.2, 0.2, 0.2)])
    target = _parse(tmp_path, "tgt", ["O"], [1], [(0.1, 0.1, 0.1)])

    fixed, moves = atom_order.match_atom_order(reference, target)

    assert fixed is target and moves is None
