"""vasp_auto_ui — local web UI for the vasp_auto engine.

A MedeA-style front end: structure builders, calculation forms, workflow
builder, run console, and results table. Standard library only (http.server);
it imports vasp_auto for structure/preview/parse operations and launches the
vasp-auto CLI as a subprocess for runs, so UI and CLI behave identically.

Binds to 127.0.0.1 — this is a single-user local tool, not a public server.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from vasp_auto.calc_types import CALC_TYPE_INFO, CalcType
from vasp_auto.config_loader import load_config, merge_local_config
from vasp_auto.job_manager import load_incar_template, make_case_info, preview_job_from_case
from vasp_auto.kpoints import KPATH_PRESETS
from vasp_auto.structure import (
    add_adsorbate,
    add_interstitial,
    build_struct,
    cart_coords,
    cell_parameters,
    combine_structures,
    frac_coords,
    freeze_atoms,
    make_prototype,
    make_supercell,
    make_vacancy,
    match_supercells,
    move_atom,
    parse_atom_selection,
    per_atom_symbols,
    read_poscar,
    resolve_prototype,
    scale_cell,
    scaled_lattice,
    substitute,
    write_poscar,
)
from vasp_auto.parser import aggregate_pdos, parse_bands, parse_dos, parse_pdos
from vasp_auto.report import build_job_report, write_job_report
from vasp_auto.runner import (
    fetch_remote_file,
    fetch_remote_results,
    list_remote_cases,
    list_remote_dir,
    list_remote_jobs,
    poll_detached_job,
    poll_remote_job,
    read_remote_text,
    remote_engine_installed,
    remote_run_mode,
    setup_remote_engine,
    check_remote_connection,
)
from vasp_auto.target_utils import get_case_type, inspect_target
from vasp_auto.trajectory import job_trajectory
from vasp_auto.workflow import (
    build_row,
    neb_energy_profile,
    read_remote_marker,
    scan_vasp_errors,
)

STATIC_DIR = Path(__file__).parent / "static"
REPO_ROOT = Path(__file__).resolve().parents[2]
UI_LOG_DIR = REPO_ROOT / "ui_logs"
# UI-managed remote machines (writable). config.yaml remote:/remotes: are also
# surfaced (read-only) so CLI and UI share the same machines.
REMOTES_FILE = REPO_ROOT / "remotes.json"

# Fields a remote-machine config may carry (everything else is ignored).
# "cpus" is a per-machine default core count the Calculate-tab CPU field
# pre-fills from; the run still passes it through the usual -n argument.
REMOTE_FIELDS = ("host", "user", "port", "ssh_key", "remote_root",
                 "vasp_executable", "scheduler", "run_mode", "env_setup", "cpus")

EDITABLE_FILES = {"INCAR", "KPOINTS", "POSCAR", "workflow.yaml", "config.yaml"}

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _config() -> dict:
    explicit = REPO_ROOT / "config.yaml"
    return load_config(str(explicit)) if explicit.exists() else load_config()


# ---------------------------------------------------------------- API helpers

def api_meta(_query, _body):
    from vasp_auto.ai_providers import DEFAULT_PROVIDER, provider_catalog
    from vasp_auto.ase_engine import ASE_CALCULATORS, ASE_SUPPORTED_CALC_TYPES
    from vasp_auto.ml_tools import ML_MODELS

    config = _config()
    return {
        "calc_types": [t.value for t in CalcType],
        "calc_type_info": {t.value: CALC_TYPE_INFO.get(t, "") for t in CalcType},
        "kpath_presets": sorted(KPATH_PRESETS),
        "ml_models": ML_MODELS,
        "ai_providers": provider_catalog(),
        "ai_provider_default": DEFAULT_PROVIDER,
        "ase_calculators": list(ASE_CALCULATORS),
        "ase_calc_types": list(ASE_SUPPORTED_CALC_TYPES),
        # UI default: the user's configured model if set, else 'emt' (always runs,
        # no download) — the gated UMA models would otherwise fail on first click.
        "ml_model_default": config.get("ml_model") or "emt",
        "repo_root": str(REPO_ROOT),
        "inputs_root": str(REPO_ROOT / "inputs"),
        "config": {
            "engine": config.get("engine", "vasp"),
            "vasp_executable": config.get("vasp_executable"),
            "qe_executable": config.get("qe_executable", "pw.x"),
            "pseudo_dir": config.get("pseudo_dir"),
            "jobs_root": config.get("jobs_root"),
            "potcar_root": config.get("potcar_root"),
            "scheduler": config.get("scheduler", "local"),
            "potcar_map": config.get("potcar_map") or {},
            "ase_calculator": config.get("ase_calculator") or "emt",
            "ase_command": (config.get("ase_calc_params") or {}).get("command"),
        },
    }


def api_cases(query, _body):
    machine = (query.get("machine", ["local"])[0] or "local").strip()
    if _is_remote_machine(machine):
        # Browse cases that physically live on the selected machine over SSH.
        remote = _resolve_remote(machine)
        root = query.get("path", [None])[0] or _default_remote_cases_dir(remote)
        listing = list_remote_cases(remote, root)
        cases = [{"name": c["name"], "path": c["path"], "type": c["type"],
                  "machine": machine, "remote": True} for c in listing["cases"]]
        return {"path": listing["path"], "machine": machine, "cases": cases}

    root = Path(query.get("path", [str(REPO_ROOT / "inputs")])[0]).expanduser().resolve()
    if not root.exists():
        return {"path": str(root), "cases": []}

    def entry(case_dir: Path) -> dict | None:
        marker = _remote_case_marker(case_dir)
        if marker:
            return {"name": case_dir.name, "path": str(case_dir),
                    "type": marker.get("type", "single"),
                    "machine": marker.get("machine"), "remote": True}
        case_type = get_case_type(case_dir)
        if case_type:
            return {"name": case_dir.name, "path": str(case_dir), "type": case_type}
        return None

    cases = []
    own = entry(root)
    if own:
        cases.append(own)
    else:
        for child in sorted(root.iterdir()):
            if child.is_dir():
                info = entry(child)
                if info:
                    cases.append(info)
    return {"path": str(root), "cases": cases}


def _struct_payload(struct: dict, poscar: Path | None = None) -> dict:
    """Full editor model of a structure: lattice (Å), per-atom symbols,
    Cartesian + fractional coordinates, selective-dynamics flags, cell params."""
    lattice = scaled_lattice(struct)
    symbols = per_atom_symbols(struct)
    return {
        "comment": struct["comment"],
        "poscar": str(poscar) if poscar else None,
        "lattice": lattice,
        "symbols": symbols,
        "cartesian": cart_coords(struct),
        "frac": frac_coords(struct),
        "selective": struct["selective"],
        "flags": [list(f) if f else ["T", "T", "T"] for f in struct["flags"]]
                 if struct["selective"] else [[] for _ in symbols],
        "cell": cell_parameters(lattice),
        "counts": dict(zip(struct["elements"], struct["counts"])),
        "natoms": len(symbols),
    }


def _struct_from_payload(data: dict) -> dict:
    """Inverse of _struct_payload for editor → engine round trips (fractional)."""
    flags = data.get("flags") if data.get("selective") else None
    return build_struct(
        data.get("comment") or "structure",
        data["lattice"],
        data["symbols"],
        data["frac"],
        cartesian=False,
        flags=flags,
    )


def _find_poscar(case_dir: Path) -> Path:
    poscar = case_dir if case_dir.is_file() else case_dir / "POSCAR"
    if not poscar.exists():
        poscar = case_dir / "initial" / "POSCAR"
    if not poscar.exists():
        raise FileNotFoundError(f"No POSCAR in {case_dir}")
    return poscar


# ------------------------------------------------------ working-machine cases
#
# The Working-case selector picks a machine. When it is a remote, every case
# operation (list/load/edit/build/preview/run) targets a path *on that machine*
# over SSH — its files and results live there, nothing is kept on this computer.
# `_remote_loc` resolves an operation to that machine, and also still honours an
# older local .remote_case.json pointer (the previous build-on-remote flow) so
# any case created that way keeps working.

REMOTE_CASE_MARKER = ".remote_case.json"


def _remote_case_marker(case_dir: Path) -> dict | None:
    """The remote-case pointer for a case dir, or None for an ordinary local case."""
    f = Path(case_dir) / REMOTE_CASE_MARKER
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _default_remote_cases_dir(remote: dict) -> str:
    """Default working-cases directory on a machine (its <remote_root>/inputs)."""
    root = (remote.get("remote_root") or "").rstrip("/")
    return f"{root}/inputs" if root else "/"


def _is_remote_machine(machine) -> bool:
    machine = (machine or "").strip()
    return bool(machine) and machine != "local"


def _remote_loc(path_str: str, machine, case_type=None) -> dict | None:
    """Resolve a working-case operation to a remote location, or None for local.

    With a remote working `machine` (the Working-case selector), `path_str` is a
    path *on that machine*, used directly. Otherwise a local case dir that holds a
    .remote_case.json pointer still resolves to its remote (the build-on-remote
    flow). Returns a marker-shaped {machine, remote_dir, case_name, type} or None.
    """
    if _is_remote_machine(machine):
        remote_dir = str(path_str).rstrip("/")
        return {"machine": machine.strip(), "remote_dir": remote_dir,
                "case_name": remote_dir.rsplit("/", 1)[-1] or remote_dir,
                "type": case_type or "single"}
    return _remote_case_marker(Path(path_str).expanduser().resolve())


def _ship_dir_to_remote(local_dir: Path, machine: str, remote_dir: str) -> str:
    """Push a local directory's contents to an explicit remote directory."""
    import shlex
    from vasp_auto.runner import _run_checked, _ssh_options, _ssh_target, _transfer_dir
    remote = _resolve_remote(machine)
    remote_dir = remote_dir.rstrip("/")
    target = _ssh_target(remote)
    ssh_opts = _ssh_options(remote)
    _run_checked(["ssh", "-x", *ssh_opts, target, f"mkdir -p {shlex.quote(remote_dir)}"],
                 "remote mkdir case")
    _transfer_dir(local_dir, target, remote_dir, remote)
    return remote_dir


def _finalize_built_case(result: dict, body: dict, ctype: str = "single") -> dict:
    """Common tail for the direct-write builders (NEB/TSS, prototype, Materials
    Project, …): when the working machine is a remote, ship the freshly built case
    straight onto it under the working cases folder and leave nothing on this
    computer; otherwise return the local result unchanged."""
    machine = (body.get("machine") or "").strip()
    if not _is_remote_machine(machine):
        return result
    remote = _resolve_remote(machine)
    case_dir = Path(result["case"])
    base = (body.get("root") or _default_remote_cases_dir(remote)).rstrip("/")
    remote_case = f"{base}/{case_dir.name}"
    _ship_dir_to_remote(case_dir, machine, remote_case)
    rel_poscar = Path(result["poscar"]).relative_to(case_dir).as_posix()
    shutil.rmtree(case_dir, ignore_errors=True)  # nothing left on this computer
    return {**result, "case": remote_case, "machine": machine, "remote": True,
            "remote_dir": remote_case, "type": ctype,
            "poscar": f"{remote_case}/{rel_poscar}"}


def _fetch_remote_case(marker: dict, dest: Path, names=None) -> Path:
    """Pull a remote case's input files into dest; return dest. A single case
    needs POSCAR; a NEB/TSS case needs initial/POSCAR and final/POSCAR."""
    remote = _resolve_remote(marker["machine"])
    remote_dir = str(marker["remote_dir"]).rstrip("/")
    dest.mkdir(parents=True, exist_ok=True)
    if marker.get("type") == "tss":
        wanted = ["initial/POSCAR", "final/POSCAR", "INCAR", "KPOINTS"]
        required = {"initial/POSCAR", "final/POSCAR"}
    else:
        wanted = list(names or ["POSCAR", "INCAR", "KPOINTS", "workflow.yaml"])
        required = {"POSCAR"}
    got = set()
    for rel in wanted:
        local = dest / rel
        local.parent.mkdir(parents=True, exist_ok=True)
        try:
            fetch_remote_file(remote, f"{remote_dir}/{rel}", local)
            got.add(rel)
        except Exception:
            if rel in required:
                raise
    missing = required - got
    if missing:
        raise FileNotFoundError(f"Remote case {remote_dir} is missing {sorted(missing)}")
    return dest


@contextmanager
def _local_case(target, machine=None):
    """Yield a local case dir for `target`. For a case that lives on a remote
    machine (either a remote working machine, or a local .remote_case.json
    pointer) this fetches its inputs into a temp dir (cleaned up on exit); a plain
    local case is yielded unchanged. Returns (case_dir, loc-or-None)."""
    loc = _remote_loc(str(target), machine)
    if not loc:
        yield Path(target).expanduser().resolve(), None
        return
    tmp = tempfile.mkdtemp(prefix="vasp_auto_rc_")
    try:
        staging = Path(tmp) / (loc.get("case_name") or "case")
        staging.mkdir(parents=True)
        _fetch_remote_case(loc, staging)
        yield staging, loc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def api_structure(query, _body):
    path_str = query["path"][0]
    machine = query.get("machine", ["local"])[0]
    loc = _remote_loc(path_str, machine, (query.get("type", [None])[0]))
    if loc:
        with tempfile.TemporaryDirectory(prefix="vasp_auto_rc_") as tmp:
            dest = _fetch_remote_case(loc, Path(tmp))
            return _struct_payload(read_poscar(_find_poscar(dest)),
                                   Path(loc["remote_dir"]) / "POSCAR")
    poscar = _find_poscar(Path(path_str).expanduser().resolve())
    return _struct_payload(read_poscar(poscar), poscar)


def api_structure_save(_query, body):
    """Save the editor's working structure as a case POSCAR (the explicit
    Save button — building/editing alone never writes case folders)."""
    struct = _struct_from_payload(body["structure"])
    machine = (body.get("machine") or "").strip()
    if _is_remote_machine(machine):
        # Working machine is a remote: write the case straight onto it (under the
        # working cases folder) so the structure and every later calculation live
        # on that machine — nothing is kept on this computer.
        remote = _resolve_remote(machine)
        if body.get("dir") and str(body["dir"]).startswith("/"):
            remote_case = str(body["dir"]).rstrip("/")
        else:
            name = body.get("name")
            if not name:
                raise ValueError("Give a case name to save")
            base = (body.get("root") or _default_remote_cases_dir(remote)).rstrip("/")
            remote_case = f"{base}/{Path(str(name)).name}"
        with tempfile.TemporaryDirectory(prefix="vasp_auto_rc_") as tmp:
            write_poscar(struct, Path(tmp) / "POSCAR")
            _ship_dir_to_remote(Path(tmp), machine, remote_case)
        return {"case": remote_case, "poscar": f"{remote_case}/POSCAR",
                "machine": machine, "remote_dir": remote_case, "remote": True}

    target = body.get("dir") or body.get("name")
    if not target:
        raise ValueError("Give a case name or directory to save into")
    path = Path(str(target)).expanduser()
    case_dir = path if path.is_absolute() else REPO_ROOT / "inputs" / path
    write_poscar(struct, case_dir / "POSCAR")
    return {"case": str(case_dir), "poscar": str(case_dir / "POSCAR")}


def api_nl_build(_query, body):
    """AI builder chatbox: free text -> AI API -> JSON command -> ASE-built
    structure for the editor. Nothing is written. The endpoint, key and model
    come from the request (`provider`/`base_url`/`api_key`/`model`, set in the
    UI) or the provider's env var — any OpenAI-compatible API works."""
    from vasp_auto.nl_builder import build_from_text, describe_command

    cmd, struct = build_from_text(
        str(body.get("text", "")),
        api_key=(body.get("api_key") or None),
        provider=(body.get("provider") or None),
        base_url=(body.get("base_url") or None),
        model=(body.get("model") or None),
    )
    return {
        "command": cmd,
        "summary": describe_command(cmd),
        "structure": _struct_payload(struct),
    }


def api_nl_agent(_query, body):
    """AI builder, agentic mode: free text -> tool-calling worker that composes
    the structure primitives step by step. Returns the finished structure plus
    the transcript of tool calls. Nothing is written. `provider`/`base_url`/
    `model` pick the AI API and model (any OpenAI-compatible function-calling
    endpoint; needs a tool-capable model)."""
    from vasp_auto.nl_agent import agent_build_from_text

    struct, transcript = agent_build_from_text(
        str(body.get("text", "")),
        api_key=(body.get("api_key") or None),
        model=(body.get("model") or None),
        provider=(body.get("provider") or None),
        base_url=(body.get("base_url") or None),
    )
    return {"transcript": transcript, "structure": _struct_payload(struct)}


def api_combine(_query, body):
    """Combine two structures with different unit cells (stack/insert).

    Host and guest are case paths; either can instead be sent inline as
    `host_struct` / `guest_struct` (the editor's unsaved working structure).
    Returns the combined structure for the editor — nothing is written.
    """
    def load(key):
        inline = body.get(f"{key}_struct")
        if inline:
            return _struct_from_payload(inline)
        path = body.get(key)
        if not path:
            raise ValueError(f"Missing {key} structure")
        return read_poscar(_find_poscar(Path(str(path)).expanduser().resolve()))

    host, guest = load("host"), load("guest")
    # Optional in-plane supercells (from the cell-match suggestions) applied
    # before stacking, e.g. 9x9 graphene under a 4x4 TiO2 slab.
    if body.get("host_repeat"):
        i, j = (int(n) for n in body["host_repeat"][:2])
        host = make_supercell(host, (i, j, 1))
    if body.get("guest_repeat"):
        k, l = (int(n) for n in body["guest_repeat"][:2])
        guest = make_supercell(guest, (k, l, 1))

    shift = body.get("shift") or [0.0, 0.0]
    combined = combine_structures(
        host,
        guest,
        mode=body.get("mode") or "stack",
        gap=float(body.get("gap") if body.get("gap") is not None else 2.0),
        vacuum=float(body.get("vacuum") if body.get("vacuum") is not None else 10.0),
        shift=(float(shift[0]), float(shift[1])),
        strain_guest=bool(body.get("strain")),
    )
    return {"structure": _struct_payload(combined)}


def _output_dir(body, default: Path) -> Path:
    output = body.get("output")
    if output:
        path = Path(output).expanduser()
        return path if path.is_absolute() else REPO_ROOT / "inputs" / path
    return default


def api_build(_query, body):
    action = body["action"]
    inputs = REPO_ROOT / "inputs"

    if body.get("to_editor") and action not in ("tss", "prototype", "mp"):
        # Build into a throw-away directory and hand the structure to the
        # editor instead of creating a case (cases are made by Save only). Force
        # a local build here — the eventual Save is what ships it to a remote.
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vasp_auto_build_") as tmp:
            result = api_build(_query, {**body, "to_editor": False, "machine": "local",
                                        "output": str(Path(tmp) / "editor_build")})
            return {"structure": _struct_payload(read_poscar(Path(result["poscar"])))}

    if action == "mp":
        # Materials Project prototype: fetch a structure by material_id or
        # formula, optionally substitute elements, and hand to the editor.
        from vasp_auto.ml_tools import prototype_from_mp

        subs = body.get("substitutions") or {}
        struct = prototype_from_mp(
            body["query"],
            substitutions=subs or None,
            api_key=body.get("api_key"),
        )
        if body.get("to_editor"):
            return {"structure": _struct_payload(struct)}
        safe = str(body["query"]).replace("/", "_")
        if subs:
            safe += "_" + "".join(f"{k}{v}" for k, v in subs.items())
        case_dir = _output_dir(body, inputs / safe)
        write_poscar(struct, case_dir / "POSCAR")
        return _finalize_built_case(
            {"case": str(case_dir), "poscar": str(case_dir / "POSCAR")}, body)

    if action == "prototype":
        # Pure-Python prototype crystals (graphene, graphite, rutile/anatase
        # TiO2, hBN) — no ASE needed.
        name = resolve_prototype(body["name"])
        struct = make_prototype(
            name,
            a=float(body["a"]) if body.get("a") else None,
            c=float(body["c"]) if body.get("c") else None,
            vacuum=float(body["vacuum"]) if body.get("vacuum") else None,
        )
        if body.get("to_editor"):
            return {"structure": _struct_payload(struct)}
        case_dir = _output_dir(body, inputs / name)
        write_poscar(struct, case_dir / "POSCAR")
        return _finalize_built_case(
            {"case": str(case_dir), "poscar": str(case_dir / "POSCAR")}, body)

    if action == "bulk":
        from vasp_auto.ase_tools import build_bulk_case
        symbol = body["symbol"]
        poscar = build_bulk_case(
            symbol=symbol,
            case_dir=_output_dir(body, inputs / symbol),
            crystalstructure=body.get("crystalstructure") or None,
            a=body.get("a") or None,
            c=body.get("c") or None,
            cubic=bool(body.get("cubic")),
        )
    elif action == "slab":
        from vasp_auto.ase_tools import build_slab_case
        miller = tuple(int(i) for i in body.get("miller", [1, 1, 1]))
        name = f"{body['source']}_slab" + "".join(str(abs(i)) for i in miller)
        poscar = build_slab_case(
            source=body["source"],
            case_dir=_output_dir(body, inputs / name),
            miller=miller,
            layers=int(body.get("layers") or 4),
            vacuum=float(body.get("vacuum") or 12.0),
            crystalstructure=body.get("crystalstructure") or None,
            a=body.get("a") or None,
            repeat=tuple(body["repeat"]) if body.get("repeat") else None,
        )
    elif action == "molecule":
        from vasp_auto.ase_tools import build_molecule_case
        poscar = build_molecule_case(
            body["name"],
            _output_dir(body, inputs / body["name"]),
            box=float(body.get("box") or 12.0),
        )
    elif action == "crystal":
        from vasp_auto.ase_tools import build_crystal_case
        symbols = body["symbols"]
        if isinstance(symbols, str):
            symbols = symbols.replace(",", " ").split()
        name = "".join(symbols) + f"_sg{int(body['spacegroup'])}"
        poscar = build_crystal_case(
            symbols=symbols,
            basis=[tuple(float(x) for x in site) for site in body["basis"]],
            spacegroup=int(body["spacegroup"]),
            case_dir=_output_dir(body, inputs / name),
            a=float(body["a"]),
            b=float(body["b"]) if body.get("b") else None,
            c=float(body["c"]) if body.get("c") else None,
            alpha=float(body.get("alpha") or 90.0),
            beta=float(body.get("beta") or 90.0),
            gamma=float(body.get("gamma") or 90.0),
        )
    elif action == "nanotube":
        from vasp_auto.ase_tools import build_nanotube_case
        symbol = body.get("symbol") or "C"
        n, m = int(body["n"]), int(body["m"])
        poscar = build_nanotube_case(
            symbol=symbol,
            n=n,
            m=m,
            case_dir=_output_dir(body, inputs / f"{symbol}_nt{n}{m}"),
            length=int(body.get("length") or 1),
            bond=float(body["bond"]) if body.get("bond") else None,
            vacuum=float(body.get("vacuum") or 10.0),
        )
    elif action == "import":
        from vasp_auto.ase_tools import import_structure_to_case
        machine = (body.get("machine") or "").strip()
        if machine and machine != "local":
            # Pull the structure file off a remote machine over SSH into a local
            # temp file. Editing always happens in the local engine; the edited
            # structure re-ships to the remote when you run it from Calculate.
            import shutil
            import tempfile
            from vasp_auto.runner import fetch_remote_file
            remote = _resolve_remote(machine)
            remote_path = str(body["source"])
            rtmp = tempfile.mkdtemp(prefix="vasp_auto_import_")
            try:
                source = Path(fetch_remote_file(
                    remote, remote_path, Path(rtmp) / Path(remote_path).name))
                poscar = import_structure_to_case(
                    structure_path=source,
                    case_dir=_output_dir(body, inputs / source.stem),
                    input_format=body.get("format") or None,
                )
            finally:
                shutil.rmtree(rtmp, ignore_errors=True)
        else:
            source = Path(body["source"]).expanduser()
            poscar = import_structure_to_case(
                structure_path=source,
                case_dir=_output_dir(body, inputs / source.stem),
                input_format=body.get("format") or None,
            )
    elif action == "tss":
        case_dir = _output_dir(body, inputs / (body.get("output") or "neb_case"))
        for endpoint, source_text in (("initial", body["initial"]), ("final", body["final"])):
            source = Path(source_text).expanduser().resolve()
            poscar_src = source if source.is_file() else source / "POSCAR"
            if not poscar_src.exists():
                raise FileNotFoundError(f"No POSCAR for the {endpoint} state: {source}")
            target = case_dir / endpoint / "POSCAR"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(poscar_src.read_bytes())
        case_dir = case_dir.resolve()
        return _finalize_built_case(
            {"case": str(case_dir), "poscar": str(case_dir / "initial" / "POSCAR")},
            body, ctype="tss")
    elif action == "edit":
        source = Path(body["source"]).expanduser().resolve()
        struct = read_poscar(source / "POSCAR")
        suffix = ""
        if body.get("supercell"):
            repeat = tuple(int(n) for n in body["supercell"])
            struct = make_supercell(struct, repeat)
            suffix += "_sc" + "x".join(str(n) for n in repeat)
        if body.get("vacancy"):
            struct = make_vacancy(struct, int(body["vacancy"]))
            suffix += f"_vac{body['vacancy']}"
        if body.get("substitute"):
            index, element = body["substitute"]
            struct = substitute(struct, int(index), str(element))
            suffix += f"_sub{index}{element}"
        if body.get("interstitial"):
            element, position = body["interstitial"]
            struct = add_interstitial(struct, str(element), tuple(float(x) for x in position))
            suffix += f"_int{element}"
        if body.get("adsorbate"):
            element, anchor, height = body["adsorbate"]
            struct = add_adsorbate(struct, str(element), int(anchor), float(height))
            suffix += f"_ads{element}{anchor}"
        if body.get("move_atom"):
            index, vector, absolute = body["move_atom"]
            struct = move_atom(struct, int(index), tuple(float(x) for x in vector),
                               absolute=bool(absolute))
            suffix += f"_mv{index}"
        if body.get("scale_cell"):
            from vasp_auto.cli import _parse_cell_spec
            struct = scale_cell(struct, _parse_cell_spec(struct, str(body["scale_cell"])))
            suffix += "_cell"
        if body.get("freeze"):
            selection, axes = body["freeze"]
            indices = parse_atom_selection(struct, str(selection))
            struct = freeze_atoms(struct, indices, axes=str(axes or "XYZ"))
            suffix += "_frz"
        if not suffix:
            raise ValueError("No structure edit requested")
        case_dir = _output_dir(body, source.parent / (source.name + suffix))
        write_poscar(struct, case_dir / "POSCAR")
        poscar = case_dir / "POSCAR"
    else:
        raise ValueError(f"Unknown build action: {action}")

    return _finalize_built_case({"case": str(poscar.parent), "poscar": str(poscar)}, body)


def _case_info_for(target: Path, config: dict):
    info = inspect_target(target)
    # Jobs live directly under the jobs root (jobs/NNNN_<case>), no project
    # sub-folder; the numbered run is resolved by make_case_info's "latest" mode.
    output_root = Path(config["jobs_root"])
    case_infos = [
        make_case_info(case_dir, output_root, single_mode=(info["mode"] == "single"),
                       job_mode="latest")
        for case_dir in info["case_dirs"]
    ]
    return info, case_infos


def _job_has_output(job_dir: Path) -> bool:
    """True if a job directory holds run output worth pointing the viewers at."""
    if not job_dir.is_dir():
        return False
    for name in ("OUTCAR", "vasprun.xml", "OSZICAR", "run.log", "CONTCAR"):
        if (job_dir / name).exists():
            return True
    # NEB/TSS keep output in numbered image dirs; convergence scans in a subdir.
    try:
        return any(
            p.is_dir() and (p.name.isdigit() or p.name == "scf_convergence")
            for p in job_dir.iterdir()
        )
    except OSError:
        return False


def _is_neb_job(job_dir: Path) -> bool:
    if (job_dir / "initial" / "POSCAR").exists() and (job_dir / "final" / "POSCAR").exists():
        return True
    return sum(1 for p in job_dir.iterdir() if p.is_dir() and p.name.isdigit()) >= 2


def _is_convergence_job(job_dir: Path) -> bool:
    """A convergence scan leaves its trials under a scf_convergence/ subdirectory."""
    return (job_dir / "scf_convergence").is_dir()


def _result_calc_type(job_dir: Path) -> str:
    if _is_neb_job(job_dir):
        return "tss"
    if _is_convergence_job(job_dir):
        return "convergence"
    return "scf"


def _job_dir_case_info(job_dir: Path) -> dict:
    """A minimal case_info built straight from a finished job directory, so the
    Results table and every per-row button operate on the real VASP output dir."""
    job_dir = Path(job_dir)
    return {
        "case_name": job_dir.name,
        "case_dir": job_dir,
        "job_dir": job_dir,
        "calculation_type": _result_calc_type(job_dir),
        "single_mode": True,
    }


def _scan_result_jobs(root: Path) -> list[Path]:
    """Find the actual VASP job directories under a results folder.

    Handles both layouts: flat ``<jobs_root>/<case>`` and nested
    ``<jobs_root>/<project>/<case>`` (descends one level into folders that are
    not jobs themselves). Returns the directories that hold real output.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    if _job_has_output(root):
        return [root]
    jobs: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if _job_has_output(child):
            jobs.append(child)
        else:
            # A project folder that itself contains job directories.
            for sub in sorted(child.iterdir()):
                if sub.is_dir() and _job_has_output(sub):
                    jobs.append(sub)
    return jobs


def _result_case_infos(info: dict, config: dict):
    """Resolve each case to the job directory it was actually run in.

    Every job lives directly under the jobs root as ``<jobs_root>/<NNNN>_<case>``
    (one global number list per machine; no project sub-folder). ``"latest"``
    picks the highest-numbered run, falling back to a legacy bare ``<case>`` dir.
    """
    jobs_root = Path(config["jobs_root"])
    case_infos = [
        make_case_info(case_dir, jobs_root, single_mode=False, job_mode="latest")
        for case_dir in info["case_dirs"]
    ]
    return info, case_infos


def _overlay_ase_config(config: dict, body: dict) -> dict:
    """Merge the UI's ASE-engine choices (calculator, command path, extra params)
    onto a config dict — the same overlay the CLI's resolve_engine does, so a
    dry-run preview matches the eventual run."""
    overlay = dict(config)
    if body.get("ase_calculator"):
        overlay["ase_calculator"] = str(body["ase_calculator"])
    if body.get("ase_fmax"):
        overlay["ase_fmax"] = float(body["ase_fmax"])
    if body.get("ase_steps"):
        overlay["ase_steps"] = int(body["ase_steps"])
    params = dict(config.get("ase_calc_params") or {})
    extra = body.get("ase_params")
    if isinstance(extra, str) and extra.strip():
        extra = json.loads(extra)
    if isinstance(extra, dict):
        params.update(extra)
    if body.get("ase_command"):
        params["command"] = str(body["ase_command"])
    if params:
        overlay["ase_calc_params"] = params
    return overlay


def api_preview(_query, body):
    with _local_case(body["target"], body.get("machine")) as (target, _loc):
        return _preview_for_target(target, body)


def _preview_for_target(target: Path, body):
    config = merge_local_config(_config(), target)
    _info, case_infos = _case_info_for(target, config)

    engine = body.get("engine") or config.get("engine", "vasp")
    if body.get("pseudo_dir"):
        config = {**config, "pseudo_dir": body["pseudo_dir"]}
    if engine == "ase":
        config = _overlay_ase_config(config, body)
    kpoints = body.get("kpoints") or None
    previews = [
        preview_job_from_case(
            case_info,
            potcar_root=config.get("potcar_root"),
            potcar_map=config.get("potcar_map"),
            calc_type=body.get("calc_type") or None,
            kpoints_spec=kpoints,
            spin=bool(body.get("spin")),
            magmom_map=config.get("magmom_map"),
            engine=engine,
            config=config,
        )
        for case_info in case_infos
    ]
    return {"previews": previews}


def _job_mtime(job_dir: Path) -> float | None:
    """Most recent modification time of a job's output (for sorting by date)."""
    job_dir = Path(job_dir)
    times: list[float] = []
    for name in ("OUTCAR", "vasprun.xml", "OSZICAR", "run.log", "CONTCAR"):
        f = job_dir / name
        try:
            if f.exists():
                times.append(f.stat().st_mtime)
        except OSError:
            pass
    if not times:  # convergence/NEB keep output in subdirs
        try:
            times = [p.stat().st_mtime for p in job_dir.iterdir() if p.is_dir()]
        except OSError:
            times = []
    if not times:
        try:
            times = [job_dir.stat().st_mtime]
        except OSError:
            return None
    return max(times) if times else None


def _result_row(project: str, mode: str, case_info: dict) -> dict:
    job_dir = Path(case_info["job_dir"])
    row = build_row(project, mode, case_info)
    findings = scan_vasp_errors(job_dir)
    if findings:
        row["errors"] = "; ".join(f"{f['code']}: {f['hint']}" for f in findings)
    ts = _job_mtime(job_dir)
    if ts is not None:
        row["modified_ts"] = ts
        row["modified"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    return row


def _first_existing_excel(*paths) -> str | None:
    for path in paths:
        if path and Path(path).exists():
            return str(path)
    return None


def api_results(query, _body):
    target = Path(query["target"][0]).expanduser().resolve()
    config = merge_local_config(_config(), target)
    jobs_root = Path(config["jobs_root"]).resolve()

    # --- Results-folder mode --------------------------------------------------
    # When the target is the jobs/results folder (or any folder holding finished
    # job dirs rather than input cases), build rows straight from the real output
    # directories. This guarantees every row — and every per-row button — points
    # at the folder VASP actually wrote to, including jobs run under a name that
    # no longer matches an inputs case.
    is_jobs_location = target == jobs_root or target.is_relative_to(jobs_root)
    if not is_jobs_location:
        try:
            inspect_target(target)  # a valid inputs project/case → use inputs mode
        except (FileNotFoundError, ValueError):
            is_jobs_location = bool(_scan_result_jobs(target))

    if is_jobs_location:
        job_dirs = _scan_result_jobs(target)
        rows = []
        for job_dir in job_dirs:
            project = job_dir.parent.name if job_dir.parent != jobs_root else jobs_root.name
            rows.append(_result_row(project, "project", _job_dir_case_info(job_dir)))
        excel = None
        if target.is_dir():
            xlsx = sorted(target.glob("*.xlsx"))
            excel = str(xlsx[0]) if xlsx else None
        return {"project": target.name, "rows": rows, "excel": excel}

    # --- Inputs mode (linked view) -------------------------------------------
    info, case_infos = _result_case_infos(inspect_target(target), config)
    rows = [_result_row(info["project_name"], info["mode"], ci) for ci in case_infos]

    first = case_infos[0] if case_infos else None
    excel = _first_existing_excel(
        Path(first["job_dir"]) / f"{first['case_name']}.xlsx" if first else None,
        jobs_root / f"{info['project_name']}.xlsx",
    )
    return {"project": info["project_name"], "rows": rows, "excel": excel}


def api_template(query, _body):
    return {"text": load_incar_template(query["type"][0])}


def api_trajectory(query, _body):
    job_dir = Path(query["path"][0]).expanduser().resolve()
    traj = job_trajectory(job_dir)
    if traj is None:
        raise FileNotFoundError(
            "No trajectory found — a relaxation needs XDATCAR (or POSCAR+CONTCAR), "
            "an NEB job needs image directories 00…NN."
        )
    return traj


def api_neb(query, _body):
    """Energy profile (reaction-coordinate plot) for an NEB/TSS job."""
    job_dir = Path(query["path"][0]).expanduser().resolve()
    profile = neb_energy_profile(job_dir)
    if profile is None:
        raise FileNotFoundError(
            "No NEB energy profile — a TSS/NEB job needs at least two image "
            "directories (00, 01, … NN) with energies (OUTCAR/OSZICAR/vasprun.xml)."
        )
    return profile


def api_dos(query, _body):
    job_dir = Path(query["path"][0]).expanduser().resolve()
    dos = parse_dos(job_dir / "vasprun.xml")
    if dos is None:
        raise FileNotFoundError(
            "No DOS in this job — run a 'dos' calculation (vasprun.xml must contain a DOS block)."
        )
    return dos


def api_pdos(query, _body):
    """Projected DOS aggregated to per-element s/p/d curves.

    Optional `atoms` query restricts to a selection ("1-4", "z>0.5", ...)
    resolved against the job POSCAR.
    """
    job_dir = Path(query["path"][0]).expanduser().resolve()
    pdos = parse_pdos(job_dir / "vasprun.xml")
    if pdos is None:
        raise FileNotFoundError(
            "No projected DOS in this job — run a 'dos' calculation (LORBIT=11 "
            "is set by the dos template; vasprun.xml must contain a partial DOS)."
        )
    struct = read_poscar(job_dir / "POSCAR")
    symbols = per_atom_symbols(struct)
    atoms = None
    selection = (query.get("atoms") or [""])[0].strip()
    if selection:
        atoms = parse_atom_selection(struct, selection)
    result = aggregate_pdos(pdos, symbols, atoms=atoms)
    result["selection"] = selection or None
    result["natoms"] = len(symbols)
    return result


def api_bands(query, _body):
    job_dir = Path(query["path"][0]).expanduser().resolve()
    bands = parse_bands(job_dir / "vasprun.xml", job_dir / "KPOINTS")
    if bands is None:
        raise FileNotFoundError(
            "No eigenvalues in this job — run a 'bands' calculation "
            "(line-mode KPOINTS) there first."
        )
    return bands


# Volumetric files the /api/volume endpoint may open, and how to label them.
VOLUME_FILES = {
    "CHGCAR": "charge density", "CHGCAR_diff": "charge-density difference",
    "CHGCAR_sum": "all-electron density", "LOCPOT": "local potential",
    "AECCAR0": "core density", "AECCAR2": "valence density", "PARCHG": "partial charge",
}
MAX_SLICE_POINTS = 160  # per direction, keeps the JSON payload bounded


def _volume_payload(volume: dict, file_name: str, axis: int, fraction: float) -> dict:
    from vasp_auto.chgcar import cell_volume_of, lattice_of, planar_average, slice_volume

    lattice = lattice_of(volume)
    lengths = [sum(x * x for x in row) ** 0.5 for row in lattice]
    # CHGCAR-family grids store rho*V_cell; LOCPOT stores eV directly.
    is_potential = file_name.upper().startswith("LOCPOT")
    factor = 1.0 if is_potential else 1.0 / cell_volume_of(volume)

    profile = [value * factor for value in planar_average(volume, axis=axis)]
    coords = [i * lengths[axis] / len(profile) for i in range(len(profile))]

    plane = slice_volume(volume, axis=axis, fraction=fraction)
    n1, n2 = plane["shape"]
    stride1 = max(1, -(-n1 // MAX_SLICE_POINTS))
    stride2 = max(1, -(-n2 // MAX_SLICE_POINTS))
    rows = [
        [plane["data"][j][i] * factor for i in range(0, n1, stride1)]
        for j in range(0, n2, stride2)
    ]
    axis1, axis2 = plane["axes"]
    return {
        "file": file_name,
        "kind": VOLUME_FILES.get(file_name, file_name),
        "unit": "eV" if is_potential else "e/Å³",
        "grid": list(volume["grid"]),
        "axis": axis,
        "profile": profile,
        "profile_coords_A": coords,
        "slice": {
            "data": rows,
            "position": plane["position"],
            "extent_A": [lengths[axis1], lengths[axis2]],
        },
    }


def api_volume(query, _body):
    """Planar average + one slice of a volumetric file (CHGCAR/LOCPOT/...)."""
    job_dir = Path(query["path"][0]).expanduser().resolve()
    file_name = (query.get("file") or ["CHGCAR"])[0]
    if file_name not in VOLUME_FILES:
        raise ValueError(f"Not a known volumetric file: {file_name}")
    axis = "abc".index((query.get("axis") or ["c"])[0].lower())
    fraction = float((query.get("frac") or ["0.5"])[0])

    path = job_dir / file_name
    if not path.exists():
        available = [name for name in VOLUME_FILES if (job_dir / name).exists()]
        raise FileNotFoundError(
            f"No {file_name} in this job"
            + (f" — available: {', '.join(available)}" if available else
               " — run with LCHARG (charge type) or LVHAR (workfunction type) first.")
        )
    from vasp_auto.chgcar import read_volumetric
    return _volume_payload(read_volumetric(path), file_name, axis, fraction)


def api_chgdiff(_query, body):
    """Δρ = ρ(total) − Σρ(parts) from job dirs/CHGCAR paths; writes CHGCAR_diff."""
    from vasp_auto.chgcar import charge_difference

    def chgcar_path(text):
        path = Path(str(text)).expanduser().resolve()
        return path if path.is_file() else path / "CHGCAR"

    total = chgcar_path(body["total"])
    parts = [chgcar_path(p) for p in body.get("parts") or [] if str(p).strip()]
    if not parts:
        raise ValueError("Charge difference needs at least one part to subtract")
    output = total.parent / "CHGCAR_diff"
    diff = charge_difference(total, parts, output)
    payload = _volume_payload(diff, "CHGCAR_diff", 2, 0.5)
    payload["path"] = str(output)
    return payload


def api_adsorption(_query, body):
    """E_ads = E(slab+adsorbate) − E(slab) − scale·E(molecule) from job dirs."""
    from vasp_auto.analysis import adsorption_energy

    def job_dir(key):
        path = body.get(key)
        if not path:
            raise ValueError(f"Missing {key} job directory")
        return Path(str(path)).expanduser().resolve()

    return adsorption_energy(
        job_dir("total"), job_dir("slab"), job_dir("molecule"),
        molecule_scale=float(body.get("scale") or 1.0),
    )


def api_thermo(query, _body):
    """ZPE / U_vib / T·S / ΔG correction from a finished freq job."""
    from vasp_auto.analysis import DEFAULT_TEMPERATURE_K, thermo_from_job

    job_dir = Path(query["path"][0]).expanduser().resolve()
    temperature = float((query.get("T") or [DEFAULT_TEMPERATURE_K])[0])
    return thermo_from_job(job_dir, temperature=temperature)


def api_dband(query, _body):
    """d-band center/width of selected atoms from a finished dos job."""
    from vasp_auto.analysis import d_band_center

    job_dir = Path(query["path"][0]).expanduser().resolve()
    selection = (query.get("atoms") or [""])[0].strip()
    if not selection:
        raise ValueError('Give an atom selection, e.g. "1-4" or "z>0.5"')
    struct = read_poscar(job_dir / "POSCAR")
    atoms = parse_atom_selection(struct, selection)
    emax_text = (query.get("emax") or [""])[0].strip()
    result = d_band_center(
        job_dir / "vasprun.xml", atoms,
        emax_eV=float(emax_text) if emax_text else None,
    )
    result["selection"] = selection
    return result


def api_workfunction(query, _body):
    """Work function W = V_vacuum − E_Fermi from a LOCPOT slab run."""
    from vasp_auto.analysis import work_function

    job_dir = Path(query["path"][0]).expanduser().resolve()
    axis = "abc".index((query.get("axis") or ["c"])[0].lower())
    return work_function(job_dir, axis=axis)


def api_optics(query, _body):
    """Absorption coefficient α(E) from a finished LOPTICS run."""
    from vasp_auto.analysis import absorption_spectrum

    job_dir = Path(query["path"][0]).expanduser().resolve()
    return absorption_spectrum(job_dir / "vasprun.xml")


def api_bader(_query, body):
    """Run the Henkelman bader binary on a job's CHGCAR; like the CLI it
    writes bader_charges.csv next to it (downloadable)."""
    import csv

    from vasp_auto.chgcar import run_bader

    job_dir = Path(body["path"]).expanduser().resolve()
    config = _config()
    result = run_bader(job_dir, config.get("bader_executable", "bader"))
    csv_path = job_dir / "bader_charges.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "element", "electrons", "net_charge_e"])
        for charge in result["charges"]:
            writer.writerow([charge["index"], charge["element"],
                             charge["electrons"], charge["net_charge"]])
    result["csv"] = str(csv_path)
    return result


def api_match(_query, body):
    """Supercell suggestions for combining two structures with different cells."""
    def load(key):
        inline = body.get(f"{key}_struct")
        if inline:
            return _struct_from_payload(inline)
        path = body.get(key)
        if not path:
            raise ValueError(f"Missing {key} structure")
        return read_poscar(_find_poscar(Path(str(path)).expanduser().resolve()))

    matches = match_supercells(
        load("host"), load("guest"),
        max_repeat=int(body.get("max_repeat") or 6),
        max_strain=float(body.get("max_strain") or 0.1),
        gamma_tol=float(body.get("gamma_tol") or 8.0),
    )
    return {"matches": matches}


def api_browse(query, _body):
    """Directory listing for the folder picker (single-user local tool)."""
    raw = (query.get("path") or [str(REPO_ROOT / "inputs")])[0]
    base = Path(raw).expanduser().resolve()
    if not base.is_dir():
        base = base.parent if base.parent.is_dir() else REPO_ROOT
    want_files = (query.get("files") or ["0"])[0] not in ("0", "", "false")

    directories = []
    files = []
    try:
        children = sorted(base.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        children = []
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir():
            directories.append({
                "name": child.name,
                "path": str(child),
                "type": get_case_type(child),
                "has_poscar": (child / "POSCAR").exists(),
            })
        elif want_files and child.is_file():
            files.append({"name": child.name, "path": str(child)})

    config = _config()
    return {
        "path": str(base),
        "parent": str(base.parent) if base.parent != base else None,
        "dirs": directories[:500],
        "files": files[:500],
        "roots": [
            {"name": "inputs", "path": str(REPO_ROOT / "inputs")},
            {"name": "jobs", "path": str(Path(config["jobs_root"]).expanduser().resolve())},
            {"name": "repo", "path": str(REPO_ROOT)},
            {"name": "home", "path": str(Path.home())},
        ],
    }


def api_mlenergy(_query, body):
    """Single-point MLIP energy/forces — cheap read-only screen (no files written)."""
    from vasp_auto.ml_tools import DEFAULT_ML_MODEL, DEFAULT_ML_TASK, ml_energy

    poscar_path = Path(body["case"]).expanduser().resolve()
    config = _config()
    return ml_energy(
        poscar_path,
        model=body.get("model") or config.get("ml_model") or DEFAULT_ML_MODEL,
        task=body.get("task") or config.get("ml_task") or DEFAULT_ML_TASK,
        checkpoint=body.get("checkpoint") or config.get("ml_checkpoint"),
    )


def api_mlrelax(_query, body):
    """Pre-relax a case POSCAR with an MLIP (Meta OMat24/UMA, or 'emt' demo)."""
    from vasp_auto.ml_tools import DEFAULT_ML_MODEL, DEFAULT_ML_TASK, ml_relax_case

    case_dir = Path(body["case"]).expanduser().resolve()
    config = _config()
    result = ml_relax_case(
        case_dir,
        model=body.get("model") or config.get("ml_model") or DEFAULT_ML_MODEL,
        task=body.get("task") or config.get("ml_task") or DEFAULT_ML_TASK,
        checkpoint=body.get("checkpoint") or config.get("ml_checkpoint"),
        fmax=float(body.get("fmax") or 0.05),
        steps=int(body.get("steps") or 200),
        relax_cell=bool(body.get("relax_cell")),
    )
    return result


def api_databases(_query, _body):
    """Return the list of available external structure databases."""
    from vasp_auto.ml_tools import DATABASES

    return {"databases": DATABASES}


def api_db_fetch(_query, body):
    """Fetch a structure from an external material database and return POSCAR text.

    Body fields:
        query     — material_id (mp-1234) or formula/chemsys (Fe2O3, Fe-O)
        db_source — "mp" or "umat" (default: "mp")
        api_key   — optional API key (MP: overrides MP_API_KEY env var)
        save_dir  — optional path; if set, POSCAR is written there and
                    the path is included in the response.

    Returns {poscar, label, db_source, saved_path?}.
    """
    from vasp_auto.ml_tools import fetch_structure_from_db

    query = body["query"]
    db_source = body.get("db_source") or "mp"
    api_key = body.get("api_key")
    poscar_text, label = fetch_structure_from_db(query, db_source=db_source, api_key=api_key)

    result: dict = {"poscar": poscar_text, "label": label, "db_source": db_source}
    if save_dir := body.get("save_dir"):
        dest = Path(save_dir).expanduser().resolve()
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "POSCAR").write_text(poscar_text, encoding="utf-8")
        result["saved_path"] = str(dest / "POSCAR")

    return result


def api_db_mlenergy(_query, body):
    """Fetch a structure from a database and compute a single-point MLIP energy.

    Body fields: query, db_source, api_key (optional), model, task, checkpoint.
    Returns the same dict as /api/mlenergy plus db_source, db_query, db_label.
    """
    from vasp_auto.ml_tools import DEFAULT_ML_MODEL, DEFAULT_ML_TASK, ml_energy_from_db

    config = _config()
    return ml_energy_from_db(
        body["query"],
        db_source=body.get("db_source") or "mp",
        api_key=body.get("api_key"),
        model=body.get("model") or config.get("ml_model") or DEFAULT_ML_MODEL,
        task=body.get("task") or config.get("ml_task") or DEFAULT_ML_TASK,
        checkpoint=body.get("checkpoint") or config.get("ml_checkpoint"),
    )


def api_db_search(_query, body):
    """Search a material database and return a ranked list of candidate materials.

    Body fields:
        query     — material_id (mp-1234), formula (SnO2), or chemsys (Fe-O)
        db_source — "mp" (default) or "umat" (pending access)
        api_key   — optional API key
        max       — optional result cap (default 20)

    Returns {results: [{material_id, formula, energy_above_hull, is_stable,
    spacegroup, nsites}, ...], db_source}.
    """
    db_source = body.get("db_source") or "mp"
    query = (body.get("query") or "").strip()
    if not query:
        raise ValueError("Enter a formula, chemical system, or material ID to search.")

    if db_source == "mp":
        from vasp_auto.ml_tools import search_mp

        results = search_mp(
            query,
            api_key=body.get("api_key"),
            max_results=int(body.get("max") or 20),
        )
    elif db_source == "umat":
        raise NotImplementedError(
            "META UMAT search is pending access grant. Use db_source 'mp' for now."
        )
    else:
        raise ValueError(f"Unknown database source {db_source!r}.")

    return {"results": results, "db_source": db_source}


def api_db_prototype(_query, body):
    """Fetch an MP structure as a prototype, with optional element substitution.

    Body fields:
        query          — material_id (mp-1234) or formula (SnO2, Fe2O3)
        substitutions  — optional dict {"Ti": "Sn"} for isostructural replacement
        api_key        — optional MP API key
        save_dir       — optional path; if set, POSCAR is written there

    Returns {poscar, comment, db_label, saved_path?}.
    """
    from vasp_auto.ml_tools import prototype_from_mp
    from vasp_auto.structure import write_poscar

    query = body["query"]
    substitutions = body.get("substitutions") or {}
    api_key = body.get("api_key")
    struct = prototype_from_mp(query, substitutions=substitutions or None, api_key=api_key)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".poscar", delete=False) as f:
        tmp = Path(f.name)
    write_poscar(struct, tmp)
    poscar_text = tmp.read_text(encoding="utf-8")
    tmp.unlink(missing_ok=True)

    result: dict = {"poscar": poscar_text, "comment": struct["comment"], "db_label": query}
    if save_dir := body.get("save_dir"):
        dest = Path(save_dir).expanduser().resolve()
        dest.mkdir(parents=True, exist_ok=True)
        write_poscar(struct, dest / "POSCAR")
        result["saved_path"] = str(dest / "POSCAR")
    return result


def api_db_mlrelax(_query, body):
    """Fetch a structure from a database and ML-relax it.

    Body fields: query, db_source, api_key (optional), model, task, checkpoint,
    fmax, steps, relax_cell, output_dir (optional).
    Returns the same dict as /api/mlrelax plus db_source, db_query, db_label.
    """
    from vasp_auto.ml_tools import DEFAULT_ML_MODEL, DEFAULT_ML_TASK, ml_relax_from_db

    config = _config()
    output_dir = body.get("output_dir")
    return ml_relax_from_db(
        body["query"],
        output_dir=Path(output_dir).expanduser().resolve() if output_dir else None,
        db_source=body.get("db_source") or "mp",
        api_key=body.get("api_key"),
        model=body.get("model") or config.get("ml_model") or DEFAULT_ML_MODEL,
        task=body.get("task") or config.get("ml_task") or DEFAULT_ML_TASK,
        checkpoint=body.get("checkpoint") or config.get("ml_checkpoint"),
        fmax=float(body.get("fmax") or 0.05),
        steps=int(body.get("steps") or 200),
        relax_cell=bool(body.get("relax_cell")),
    )


def api_report(_query, body):
    job_dir = Path(body["job_dir"]).expanduser().resolve()
    if not job_dir.is_dir():
        raise FileNotFoundError(f"Job directory not found: {job_dir}")
    case_name = body.get("case") or job_dir.name
    path = write_job_report(job_dir, case_name=case_name)
    return {"path": str(path), "text": build_job_report(job_dir, case_name=case_name)}


def api_file_get(query, _body):
    name = query["name"][0]
    if name not in EDITABLE_FILES:
        raise ValueError(f"Not an editable file: {name}")
    dir_str = query["dir"][0]
    loc = _remote_loc(dir_str, query.get("machine", ["local"])[0])
    if loc:
        remote = _resolve_remote(loc["machine"])
        remote_path = f"{str(loc['remote_dir']).rstrip('/')}/{name}"
        try:
            with tempfile.TemporaryDirectory(prefix="vasp_auto_rc_") as tmp:
                local = fetch_remote_file(remote, remote_path, Path(tmp) / name)
                return {"exists": True, "text": local.read_text(encoding="utf-8")}
        except Exception:
            return {"exists": False, "text": ""}
    path = Path(dir_str).expanduser().resolve() / name
    return {"exists": path.exists(), "text": path.read_text(encoding="utf-8") if path.exists() else ""}


def api_file_save(_query, body):
    name = body["name"]
    if name not in EDITABLE_FILES:
        raise ValueError(f"Not an editable file: {name}")
    loc = _remote_loc(body["dir"], body.get("machine"))
    if loc:
        from vasp_auto.runner import _ship_file, _ssh_options, _ssh_target
        remote = _resolve_remote(loc["machine"])
        remote_dir = str(loc["remote_dir"]).rstrip("/")
        with tempfile.TemporaryDirectory(prefix="vasp_auto_rc_") as tmp:
            src = Path(tmp) / name
            src.write_text(body["text"], encoding="utf-8")
            _ship_file(src, _ssh_target(remote), f"{remote_dir}/{name}", remote, _ssh_options(remote))
        return {"saved": f"{loc['machine']}:{remote_dir}/{name}"}
    directory = Path(body["dir"]).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")
    (directory / name).write_text(body["text"], encoding="utf-8")
    return {"saved": str(directory / name)}


def build_cli_args(body: dict) -> list[str]:
    args = [body["target"]]
    mode = body.get("mode", "run")
    if mode == "prepare":
        args.append("--prepare")
    elif mode == "dry":
        args.append("--dry-run")
    elif mode == "parse":
        args.append("--parse-only")

    if body.get("calc_type"):
        args += ["--calc-type", str(body["calc_type"])]
    if body.get("engine") and body["engine"] != "vasp":
        args += ["--engine", str(body["engine"])]
        if body.get("qe_executable"):
            args += ["--qe-executable", str(body["qe_executable"])]
        if body.get("pseudo_dir"):
            args += ["--pseudo-dir", str(body["pseudo_dir"])]
        if body.get("ase_calculator"):
            args += ["--ase-calculator", str(body["ase_calculator"])]
        if body.get("ase_command"):
            args += ["--ase-command", str(body["ase_command"])]
        if body.get("ase_params"):
            params = body["ase_params"]
            args += ["--ase-params", params if isinstance(params, str) else json.dumps(params)]
        if body.get("ase_fmax"):
            args += ["--ase-fmax", str(body["ase_fmax"])]
        if body.get("ase_steps"):
            args += ["--ase-steps", str(body["ase_steps"])]
    kpoints = body.get("kpoints") or {}
    if kpoints.get("mode"):
        args += ["--kpoints-mode", kpoints["mode"]]
    if kpoints.get("mesh"):
        args += ["--kmesh", str(kpoints["mesh"])]
    if kpoints.get("spacing"):
        args += ["--kspacing", str(kpoints["spacing"])]
    if kpoints.get("kpath"):
        args += ["--kpath", str(kpoints["kpath"])]
    if kpoints.get("divisions"):
        args += ["--kpath-divisions", str(kpoints["divisions"])]
    if body.get("cpus"):
        args += ["-n", str(body["cpus"])]
    if body.get("parallel"):
        args += ["--parallel", str(body["parallel"])]
    if body.get("workflow"):
        args += ["--workflow", str(body["workflow"])]
    if body.get("scheduler") and body["scheduler"] != "local":
        args += ["--scheduler", body["scheduler"]]
    if body.get("converge_encut"):
        args += ["--converge-encut", str(body["converge_encut"])]
    if body.get("converge_sigma"):
        args += ["--converge-sigma", str(body["converge_sigma"])]
    if body.get("converge_scf"):
        args.append("--converge-scf")
    if body.get("nelm_values"):
        args += ["--nelm-values", str(body["nelm_values"])]
    if body.get("kpoints_values"):
        args += ["--kpoints-values", str(body["kpoints_values"])]
    if body.get("energy_tol"):
        args += ["--energy-tol", str(body["energy_tol"])]
    if body.get("sigma_tol"):
        args += ["--sigma-tol", str(body["sigma_tol"])]
    if body.get("reuse_wavecar"):
        args.append("--reuse-wavecar")
    if body.get("spin"):
        args.append("--spin")
    if body.get("magmom"):
        args += ["--magmom", str(body["magmom"])]
    if body.get("auto_retry"):
        args += ["--auto-retry", str(body["auto_retry"])]
    if body.get("retry_failed"):
        args.append("--retry-failed")
    if body.get("neb_images"):
        args += ["--neb-images", str(body["neb_images"])]
    return args


def api_run(_query, body):
    # A case that lives on a remote machine (the working machine, or a local
    # pointer) has no local POSCAR — fetch its inputs into a staging dir to run
    # from, and force its machine as the run target so the calculation happens and
    # is stored on that machine. (The staging dir is read by the async CLI
    # subprocess, so it is left for the OS temp cleaner rather than removed here.)
    loc = _remote_loc(body["target"], body.get("machine"), body.get("case_type"))
    if loc:
        staging = Path(tempfile.mkdtemp(prefix="vasp_auto_rc_")) / (loc.get("case_name") or "case")
        staging.mkdir(parents=True)
        _fetch_remote_case(loc, staging)
        body = {**body, "target": str(staging), "remote": loc["machine"]}

    # A structured workflow (e.g. one with a convergence step that carries its
    # own scan settings) is written to the case's workflow.yaml, which the CLI
    # then loads automatically — so no --workflow string is added.
    if body.get("workflow_yaml"):
        target = Path(body["target"]).expanduser().resolve()
        case_dir = target if target.is_dir() else target.parent
        (case_dir / "workflow.yaml").write_text(body["workflow_yaml"], encoding="utf-8")
        body = {k: v for k, v in body.items() if k != "workflow"}

    args = build_cli_args(body)
    UI_LOG_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    log_path = UI_LOG_DIR / f"{token}.log"

    # Run on a remote machine: write the chosen machine's config to a temp file
    # and hand it to the CLI, which ships the inputs over SSH and submits there.
    remote_name = body.get("remote")
    if remote_name and remote_name != "local":
        remotes = _all_remotes()
        if remote_name not in remotes:
            raise ValueError(f"Unknown remote machine: {remote_name}")
        remote_cfg = {k: v for k, v in remotes[remote_name].items() if k != "source"}
        remote_file = UI_LOG_DIR / f"remote_{token}.json"
        remote_file.write_text(json.dumps(remote_cfg), encoding="utf-8")
        args += ["--remote-config", str(remote_file)]

    command = [sys.executable, "-u", "-m", "vasp_auto.cli", *args]
    log_handle = log_path.open("w", encoding="utf-8")
    log_handle.write("$ vasp-auto " + " ".join(args) + "\n\n")
    log_handle.flush()
    process = subprocess.Popen(
        command, cwd=REPO_ROOT, stdout=log_handle, stderr=subprocess.STDOUT, text=True
    )

    with JOBS_LOCK:
        JOBS[token] = {
            "token": token,
            "args": args,
            "target": body["target"],
            "started": datetime.now().strftime("%H:%M:%S"),
            "started_at": datetime.now(),
            "finished_at": None,
            "stopped": False,
            "process": process,
            "log_path": log_path,
        }
    return {"token": token}


def _job_state(job: dict) -> dict:
    returncode = job["process"].poll()
    if returncode is not None and job["finished_at"] is None:
        job["finished_at"] = datetime.now()
    end = job["finished_at"] or datetime.now()
    return {
        "token": job["token"],
        "target": job["target"],
        "args": job["args"],
        "started": job["started"],
        "elapsed_s": int((end - job["started_at"]).total_seconds()),
        "running": returncode is None,
        "stopped": job["stopped"],
        "returncode": returncode,
    }


def api_stop(_query, body):
    token = body["token"]
    with JOBS_LOCK:
        job = JOBS.get(token)
    if job is None:
        raise KeyError(f"Unknown job: {token}")
    if job["process"].poll() is None:
        job["stopped"] = True
        job["process"].terminate()
    return {"token": token, "stopped": True}


def api_jobs(_query, _body):
    with JOBS_LOCK:
        jobs = [_job_state(job) for job in JOBS.values()]
    jobs.sort(key=lambda j: j["started"], reverse=True)
    return {"jobs": jobs}


def api_job(query, _body):
    token = query["token"][0]
    with JOBS_LOCK:
        job = JOBS.get(token)
    if job is None:
        raise KeyError(f"Unknown job: {token}")
    state = _job_state(job)
    log_path: Path = job["log_path"]
    text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
    state["log"] = text[-20000:]
    return state


# ---------------------------------------------------------------- remote machines

def _load_remotes_store() -> dict:
    if REMOTES_FILE.exists():
        try:
            return json.loads(REMOTES_FILE.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def _save_remotes_store(data: dict) -> None:
    REMOTES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _all_remotes() -> dict:
    """All known remote machines: config.yaml (read-only) + UI store (writable)."""
    config = _config()
    remotes: dict[str, dict] = {}
    for name, entry in (config.get("remotes") or {}).items():
        remotes[name] = {**entry, "name": name, "source": "config"}
    if config.get("remote"):
        remotes.setdefault("default", {**config["remote"], "name": "default", "source": "config"})
    for name, entry in _load_remotes_store().items():
        remotes[name] = {**entry, "name": name, "source": "ui"}
    return remotes


def _remote_from_body(body: dict) -> dict:
    """A remote config from explicit form fields, or by name from the store."""
    if body.get("host"):
        remote = {k: body[k] for k in REMOTE_FIELDS if body.get(k) not in (None, "")}
        for key in ("ssh_options", "scheduler_options"):
            if body.get(key):
                remote[key] = body[key]
        if body.get("name"):
            remote["name"] = body["name"]
        return remote
    name = body.get("name")
    remotes = _all_remotes()
    if name and name in remotes:
        return remotes[name]
    raise ValueError("Provide machine details (at least host) or a saved machine name.")


def _remote_for_marker(marker: dict) -> dict:
    """Find the saved machine (with credentials) a job was submitted to."""
    remotes = _all_remotes()
    name = marker.get("machine") or marker.get("host")
    if name in remotes:
        return remotes[name]
    for entry in remotes.values():
        if entry.get("host") == marker.get("host"):
            return entry
    # Last resort: host only (works if SSH config supplies user/key).
    return {"host": marker.get("host"), "scheduler": marker.get("scheduler", "slurm")}


def api_remotes(_query, _body):
    """List configured remote machines (newest editable ones from the UI store)."""
    return {"remotes": sorted(_all_remotes().values(), key=lambda r: r["name"])}


def api_remote_save(_query, body):
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("Give the machine a name.")
    if not body.get("host"):
        raise ValueError("host is required.")
    if not body.get("remote_root"):
        raise ValueError("remote_root is required (a base directory on the remote).")
    if not body.get("vasp_executable"):
        raise ValueError("vasp_executable is required (the VASP path on the remote).")
    entry = {k: body[k] for k in REMOTE_FIELDS if body.get(k) not in (None, "")}
    if "cpus" in entry:
        try:
            entry["cpus"] = max(1, int(entry["cpus"]))
        except (TypeError, ValueError):
            del entry["cpus"]
    if body.get("scheduler_options"):
        entry["scheduler_options"] = body["scheduler_options"]
    store = _load_remotes_store()
    store[name] = entry
    _save_remotes_store(store)
    return {"saved": name, "remote": {**entry, "name": name, "source": "ui"}}


def api_remote_delete(_query, body):
    name = body.get("name")
    store = _load_remotes_store()
    if name in store:
        del store[name]
        _save_remotes_store(store)
        return {"deleted": name}
    raise ValueError(f"No UI-managed machine named '{name}' to delete "
                     "(machines defined in config.yaml are read-only).")


def api_remote_test(_query, body):
    """Verify SSH + remote_root/VASP/scheduler — the Test connection button."""
    return check_remote_connection(_remote_from_body(body))


def api_remote_setup(_query, body):
    """Install the vasp_auto engine venv on a machine (the offload setup button)."""
    remote = _remote_from_body(body)
    result = setup_remote_engine(remote)
    result["machine"] = remote.get("name") or remote.get("host")
    return result


def api_remote_status(_query, body):
    """Poll the remote for a submitted job's state (scheduler or detached offload)."""
    job_dir = Path(body["job_dir"]).expanduser().resolve()
    marker = read_remote_marker(job_dir)
    if not marker:
        raise ValueError("This case was not submitted to a remote machine.")
    remote = _remote_for_marker(marker)
    # Detached offload jobs are tracked by a PID + control dir, not a queue id.
    if marker.get("mode") == "ssh_detached":
        if not marker.get("control_dir"):
            raise ValueError("No control directory recorded for this offload job.")
        result = poll_detached_job(remote, marker["control_dir"], marker.get("pid"))
    else:
        if not marker.get("job_id"):
            raise ValueError("No remote job id recorded for this case.")
        result = poll_remote_job(remote, marker["job_id"])
    result["machine"] = marker.get("machine") or marker.get("host")
    result["remote_dir"] = marker.get("remote_dir")
    return result


def api_remote_fetch(_query, body):
    """Pull result files back from the remote job dir so local viewers work."""
    job_dir = Path(body["job_dir"]).expanduser().resolve()
    marker = read_remote_marker(job_dir)
    if not marker:
        raise ValueError("This case was not submitted to a remote machine.")
    remote_dir = marker.get("remote_dir")
    if not remote_dir:
        raise ValueError("No remote directory recorded for this case.")
    result = fetch_remote_results(
        _remote_for_marker(marker), remote_dir, job_dir,
        include_heavy=bool(body.get("heavy")),
    )
    # Build a fresh job.log from the pulled files so a readable summary exists even
    # when the remote engine predates job.log (or only wrote partial output).
    if (job_dir / "OUTCAR").exists():
        from vasp_auto.job_log import write_job_log
        write_job_log(job_dir, job_dir.name)
    result["machine"] = marker.get("machine") or marker.get("host")
    result["has_outcar"] = (job_dir / "OUTCAR").exists()
    result["has_vasprun"] = (job_dir / "vasprun.xml").exists()
    return result


# ----------------------------------------------------- browse + download files

def _fmt_ts(ts) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


def _resolve_remote(name: str) -> dict:
    """Look up a saved/config remote machine (with credentials) by name."""
    remotes = _all_remotes()
    if not name or name not in remotes:
        raise ValueError(f"Unknown remote machine: {name!r}")
    return remotes[name]


def api_remote_jobs(_query, body):
    """List the job directories that live on a remote machine (newest first)."""
    remote = _resolve_remote(body.get("machine"))
    root = (body.get("dir") or "").strip() or remote.get("remote_root")
    if not root:
        raise ValueError("This machine has no remote_root set — type a jobs directory.")
    rows = list_remote_jobs(remote, root)
    machine = remote.get("name") or remote.get("host")
    for r in rows:
        r["modified"] = _fmt_ts(r.get("modified_ts"))
        r["machine"] = machine
    return {"machine": machine, "dir": root,
            "remote_root": remote.get("remote_root"), "rows": rows}


def api_remote_files(_query, body):
    """List the files/subdirs of one directory on a remote machine."""
    remote = _resolve_remote(body.get("machine"))
    path = (body.get("dir") or body.get("job_dir") or "").strip()
    if not path:
        raise ValueError("No remote directory given.")
    data = list_remote_dir(remote, path)
    for e in data["entries"]:
        e["modified"] = _fmt_ts(e.get("modified_ts"))
    data["machine"] = remote.get("name") or remote.get("host")
    return data


def _local_dir_entries(directory: Path) -> list[dict]:
    entries: list[dict] = []
    try:
        children = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return entries
    for child in children:
        try:
            st = child.stat()
        except OSError:
            continue
        is_dir = child.is_dir()
        entries.append({
            "name": child.name,
            "path": str(child),
            "is_dir": is_dir,
            "size": 0 if is_dir else st.st_size,
            "modified_ts": int(st.st_mtime),
            "modified": _fmt_ts(int(st.st_mtime)),
        })
    return entries


def api_job_files(_query, body):
    """List the files/subdirs of one local job directory (for download)."""
    directory = Path(body["dir"]).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")
    parent = str(directory.parent) if directory.parent != directory else None
    return {"path": str(directory), "parent": parent,
            "entries": _local_dir_entries(directory)}


# Maximum bytes shown in the in-browser file viewer (download for the full file).
TEXT_PREVIEW_MAX = 200_000
# Suffixes / names we never preview inline: pure binary, or proprietary (POTCAR).
_BINARY_SUFFIXES = {".xlsx", ".png", ".jpg", ".jpeg", ".pdf", ".gz", ".zip",
                    ".tar", ".bz2", ".xz", ".npy", ".h5", ".hdf5", ".pkl", ".bin", ".so"}
_NO_PREVIEW_NAMES = {"POTCAR", "WAVECAR", "CHGCAR", "CHG", "AECCAR0", "AECCAR1",
                     "AECCAR2", "WAVEDER", "TMPCAR", "PROOUT"}


def _previewable(name: str) -> bool:
    """Whether a file can be shown in the text viewer (vs download-only).

    POTCAR and the bulky volumetric/wavefunction binaries are never previewed —
    POTCAR content is proprietary and must not be printed.
    """
    if name in _NO_PREVIEW_NAMES:
        return False
    return Path(name).suffix.lower() not in _BINARY_SUFFIXES


def api_filetext(_query, body):
    """Return the text of one file (local or remote) for the in-browser viewer.

    Body: ``{"path": ..., "name"?: ..., "machine"?: ...}``. A ``machine`` other
    than "local" reads it over SSH (kept inside the machine's remote_root).
    Binary/proprietary files return ``{"previewable": False}`` (download only).
    """
    path_str = body.get("path") or ""
    name = body.get("name") or Path(path_str).name
    if not _previewable(name):
        return {"previewable": False, "name": name,
                "reason": "Binary or proprietary file — use the download button."}
    machine = body.get("machine")
    if machine and machine != "local":
        remote = _resolve_remote(machine)
        root = (remote.get("remote_root") or "").rstrip("/")
        if root and not (path_str == root or path_str.startswith(root + "/")):
            raise ValueError("Path is outside the machine's remote_root")
        data = read_remote_text(remote, path_str, TEXT_PREVIEW_MAX)
        return {"previewable": True, "name": name, **data}
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    size = path.stat().st_size
    text = path.read_bytes()[:TEXT_PREVIEW_MAX].decode("utf-8", "replace")
    return {"previewable": True, "name": name, "text": text,
            "size": size, "truncated": size > TEXT_PREVIEW_MAX}


GET_ROUTES = {
    "/api/meta": api_meta,
    "/api/remotes": api_remotes,
    "/api/cases": api_cases,
    "/api/structure": api_structure,
    "/api/results": api_results,
    "/api/template": api_template,
    "/api/file": api_file_get,
    "/api/jobs": api_jobs,
    "/api/job": api_job,
    "/api/trajectory": api_trajectory,
    "/api/neb": api_neb,
    "/api/dos": api_dos,
    "/api/pdos": api_pdos,
    "/api/bands": api_bands,
    "/api/volume": api_volume,
    "/api/browse": api_browse,
    "/api/thermo": api_thermo,
    "/api/dband": api_dband,
    "/api/workfunction": api_workfunction,
    "/api/optics": api_optics,
}

POST_ROUTES = {
    "/api/build": api_build,
    "/api/structure": api_structure_save,
    "/api/combine": api_combine,
    "/api/nl_build": api_nl_build,
    "/api/nl_agent": api_nl_agent,
    "/api/match": api_match,
    "/api/chgdiff": api_chgdiff,
    "/api/adsorption": api_adsorption,
    "/api/bader": api_bader,
    "/api/preview": api_preview,
    "/api/run": api_run,
    "/api/stop": api_stop,
    "/api/report": api_report,
    "/api/mlrelax": api_mlrelax,
    "/api/mlenergy": api_mlenergy,
    "/api/databases": api_databases,
    "/api/db_search": api_db_search,
    "/api/db_fetch": api_db_fetch,
    "/api/db_prototype": api_db_prototype,
    "/api/db_mlenergy": api_db_mlenergy,
    "/api/db_mlrelax": api_db_mlrelax,
    "/api/file": api_file_save,
    "/api/remote/save": api_remote_save,
    "/api/remote/delete": api_remote_delete,
    "/api/remote/test": api_remote_test,
    "/api/remote/setup": api_remote_setup,
    "/api/remote/status": api_remote_status,
    "/api/remote/fetch": api_remote_fetch,
    "/api/remote/jobs": api_remote_jobs,
    "/api/remote/files": api_remote_files,
    "/api/job/files": api_job_files,
    "/api/filetext": api_filetext,
}

# File types the /download endpoint will serve (summaries and reports only).
DOWNLOADABLE_SUFFIXES = {".xlsx", ".csv", ".md"}


def _downloadable(path: Path) -> bool:
    if path.suffix.lower() not in DOWNLOADABLE_SUFFIXES:
        return False
    config = _config()
    allowed_roots = [REPO_ROOT, Path(config["jobs_root"])]
    return any(path.is_relative_to(root) for root in allowed_roots)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # keep the terminal quiet; the UI has its own logs

    def _send_json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, routes, body):
        parsed = urlparse(self.path)
        handler = routes.get(parsed.path)
        if handler is None:
            self._send_json({"error": f"Unknown endpoint: {parsed.path}"}, status=404)
            return
        try:
            result = handler(parse_qs(parsed.query), body)
            self._send_json(result)
        except Exception as exc:  # surfaced to the UI as a banner
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, status=400)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            page = (STATIC_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        if parsed.path == "/download":
            self._send_download(parse_qs(parsed.query))
            return
        if parsed.path == "/download_local":
            self._send_download_local(parse_qs(parsed.query))
            return
        if parsed.path == "/download_remote":
            self._send_download_remote(parse_qs(parsed.query))
            return
        self._dispatch(GET_ROUTES, None)

    def _send_download(self, query):
        try:
            path = Path(query["path"][0]).expanduser().resolve()
        except (KeyError, IndexError):
            self._send_json({"error": "Missing path parameter"}, status=400)
            return
        if not path.exists() or not _downloadable(path):
            self._send_json({"error": f"Not downloadable: {path}"}, status=404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, data: bytes, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_download_local(self, query):
        """Serve any individual file from a local job directory."""
        try:
            path = Path(query["path"][0]).expanduser().resolve()
        except (KeyError, IndexError):
            self._send_json({"error": "Missing path parameter"}, status=400)
            return
        if not path.is_file():
            self._send_json({"error": f"Not a file: {path}"}, status=404)
            return
        self._send_bytes(path.read_bytes(), path.name)

    def _send_download_remote(self, query):
        """Pull one file off a remote machine (scp) and stream it to the browser."""
        try:
            machine = query["machine"][0]
            rpath = query["path"][0]
        except (KeyError, IndexError):
            self._send_json({"error": "Missing machine/path parameter"}, status=400)
            return
        try:
            remote = _resolve_remote(machine)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        # Keep downloads inside the machine's work dir when one is configured.
        root = (remote.get("remote_root") or "").rstrip("/")
        if root and not (rpath == root or rpath.startswith(root + "/")):
            self._send_json({"error": "Path is outside the machine's remote_root"}, status=403)
            return
        import tempfile
        try:
            with tempfile.TemporaryDirectory() as td:
                local = fetch_remote_file(remote, rpath, Path(td) / Path(rpath).name)
                data = local.read_bytes()
        except Exception as exc:  # surfaced to the browser
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, status=400)
            return
        self._send_bytes(data, Path(rpath).name)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON body"}, status=400)
            return
        self._dispatch(POST_ROUTES, body)


def create_server(host: str = "127.0.0.1", port: int = 8800) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Local web UI for vasp_auto.")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    httpd = create_server(args.host, args.port)
    url = f"http://{args.host}:{httpd.server_address[1]}/"
    print(f"vasp_auto UI running at {url}  (Ctrl-C to stop)")
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
