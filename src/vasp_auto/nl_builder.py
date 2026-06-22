"""Natural-language structure builder.

A chatbox sends a sentence ("Pt(111) slab, 4 layers, with O adsorbed on top");
Groq's free OpenAI-compatible API turns it into ONE JSON build command, and
ASE + this project's own structure primitives execute it.  The model only ever
chooses an action and fills parameters — it never emits atomic coordinates, so
geometry is always exact and a misread can't corrupt a cell.

No third-party SDK: the Groq call is a plain ``urllib`` POST.  The API key comes
from the ``GROQ_API_KEY`` environment variable or, for the UI, the per-request
``api_key`` argument — it is never hardcoded or written to disk here.
"""
from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from pathlib import Path

from .structure import (
    add_adsorbate,
    cart_coords,
    combine_structures,
    read_poscar,
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Fast, free, and reliable for JSON schema-filling.  Override with GROQ_MODEL.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

SYSTEM_PROMPT = """You convert a materials-science request into ONE JSON build
command. Respond with JSON only — no prose. Available actions and their fields:

bulk:      {"action":"bulk","element":"Pt","crystal":"fcc"|"bcc"|"hcp"|"diamond"|null,
            "a":3.92|null,"c":null,"supercell":[1,1,1]|null}
surface:   {"action":"surface","element":"Pt","crystal":null,"a":null,
            "miller":[1,1,1],"layers":4,"vacuum":12.0,"supercell":[3,3,1]|null}
molecule:  {"action":"molecule","name":"CO"}            // ASE g2 names (CO, H2O, CO2, NH3, O2...)
nanotube:  {"action":"nanotube","n":5,"m":5,"supercell":null}
adsorbate: {"action":"adsorbate","slab":{<a surface command>},
            "adsorbate_element":"O","height":1.8}        // ONE atom above the top surface atom
combine:   {"action":"combine","host":{<command>},"guest":{<command>},
            "mode":"stack"|"insert","gap":2.0,"vacuum":10.0,"shift":[0.0,0.0],"strain":false}

Rules:
- adsorbate adds a SINGLE atom (O, H, N, C...). For a molecular adsorbate, use
  combine with host=the slab (a surface command) and guest=the molecule, mode "insert".
- combine.host and combine.guest are themselves full commands (recurse).
- Use null for unknown numbers; pick sensible defaults (slab vacuum 12, layers 4).
- Lattice constants are in Angstrom. Never output coordinates or lattice vectors.
"""


def _ask_groq(text: str, api_key: str | None = None) -> dict:
    """POST the request to Groq and return the parsed JSON command."""
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError(
            "No Groq API key. Paste one in the AI builder box, or set the "
            "GROQ_API_KEY environment variable on the server."
        )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},  # forces valid JSON back
        "temperature": 0,
    }
    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # bad key, rate limit, bad model name
        detail = exc.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"Groq API error {exc.code}: {detail}") from None
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def _atoms_to_struct(atoms) -> dict:
    """Convert an ASE Atoms object to this project's POSCAR struct dict by
    round-tripping through a temporary POSCAR — reuses read_poscar exactly."""
    from ase.io import write

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "POSCAR"
        write(path, atoms, format="vasp")
        return read_poscar(path)


def _topmost_index(struct: dict) -> int:
    """1-based index of the highest atom along z — the default adsorption site."""
    zs = [c[2] for c in cart_coords(struct)]
    return max(range(len(zs)), key=zs.__getitem__) + 1


def _build_base(cmd: dict):
    """Build one of the four ASE-backed primitives, return an ASE Atoms."""
    from ase.build import bulk, molecule, nanotube, surface

    act = cmd.get("action")
    if act == "bulk":
        kw = {}
        if cmd.get("crystal"):
            kw["crystalstructure"] = cmd["crystal"]
        if cmd.get("a"):
            kw["a"] = float(cmd["a"])
        if cmd.get("c"):
            kw["c"] = float(cmd["c"])
        return bulk(cmd["element"], **kw)
    if act == "surface":
        base_kw = {}
        if cmd.get("crystal"):
            base_kw["crystalstructure"] = cmd["crystal"]
        if cmd.get("a"):
            base_kw["a"] = float(cmd["a"])
        base = bulk(cmd["element"], **base_kw)
        slab = surface(
            base,
            tuple(int(i) for i in cmd["miller"]),
            int(cmd.get("layers") or 4),
            vacuum=float(cmd.get("vacuum") or 12.0),
        )
        return slab
    if act == "molecule":
        atoms = molecule(cmd["name"])
        atoms.center(vacuum=6.0)
        return atoms
    if act == "nanotube":
        atoms = nanotube(int(cmd["n"]), int(cmd["m"]))
        atoms.center(vacuum=6.0)
        return atoms
    raise ValueError(f"Unsupported base action: {act!r}")


def _build_one(cmd: dict) -> dict:
    """Recursively execute a build command, always returning a struct dict."""
    act = cmd.get("action")
    if act in ("bulk", "surface", "molecule", "nanotube"):
        atoms = _build_base(cmd)
        if cmd.get("supercell"):
            atoms = atoms.repeat(tuple(int(n) for n in cmd["supercell"]))
        return _atoms_to_struct(atoms)
    if act == "adsorbate":
        slab = _build_one(cmd["slab"])
        anchor = _topmost_index(slab)
        return add_adsorbate(
            slab,
            str(cmd["adsorbate_element"]),
            anchor,
            float(cmd.get("height", 1.8)),
        )
    if act == "combine":
        host = _build_one(cmd["host"])
        guest = _build_one(cmd["guest"])
        shift = cmd.get("shift") or [0.0, 0.0]
        return combine_structures(
            host,
            guest,
            mode=cmd.get("mode") or "stack",
            gap=float(cmd.get("gap", 2.0)),
            vacuum=float(cmd.get("vacuum", 10.0)),
            shift=(float(shift[0]), float(shift[1])),
            strain_guest=bool(cmd.get("strain", False)),
        )
    raise ValueError(f"Unsupported action: {act!r}")


def build_from_text(text: str, api_key: str | None = None) -> tuple[dict, dict]:
    """Turn free text into (command, struct_dict). Nothing is written to disk;
    the struct dict is meant to load into the editor for preview-before-save."""
    if not text or not text.strip():
        raise ValueError("Describe the structure to build.")
    cmd = _ask_groq(text.strip(), api_key=api_key)
    struct = _build_one(cmd)
    return cmd, struct
