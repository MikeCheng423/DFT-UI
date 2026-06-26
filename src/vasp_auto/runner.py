from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Commands used to poll job status for each scheduler.
# squeue: query by job ID (-h = no header, -j = job list).
# qstat: query by job ID (prints to stdout, may error when job is done).
POLL_COMMANDS: dict[str, list[str]] = {
    "slurm": ["squeue", "-h", "-j"],
    "pbs": ["qstat"],
}


DEFAULT_SLURM_TEMPLATE = """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --ntasks={cpus}
#SBATCH --output=run.log
{extra}
cd "{job_dir}"
mpirun -np {cpus} "{exe}"
"""

DEFAULT_PBS_TEMPLATE = """#!/bin/bash
#PBS -N {job_name}
#PBS -l nodes=1:ppn={cpus}
#PBS -o run.log
#PBS -j oe
{extra}
cd "{job_dir}"
mpirun -np {cpus} "{exe}"
"""

DEFAULT_SLURM_QE_TEMPLATE = """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --ntasks={cpus}
#SBATCH --output=run.log
{extra}
cd "{job_dir}"
mpirun -np {cpus} "{exe}" -in pw.in > pw.out
"""

DEFAULT_PBS_QE_TEMPLATE = """#!/bin/bash
#PBS -N {job_name}
#PBS -l nodes=1:ppn={cpus}
#PBS -o run.log
#PBS -j oe
{extra}
cd "{job_dir}"
mpirun -np {cpus} "{exe}" -in pw.in > pw.out
"""

SCHEDULER_COMMANDS = {"slurm": "sbatch", "pbs": "qsub"}


def _resolve_executable(vasp_executable: str) -> str:
    exe_path = Path(vasp_executable)
    if exe_path.parent == Path("."):
        resolved = shutil.which(str(exe_path))
        if resolved is None:
            raise FileNotFoundError(
                f"VASP executable not found: {vasp_executable}. "
                "Set vasp_executable in config.yaml or export VASP_EXECUTABLE."
            )
        return resolved
    if exe_path.exists():
        return str(exe_path)
    raise FileNotFoundError(f"VASP executable not found: {vasp_executable}")


def _local_core_counts() -> tuple[int, int]:
    """Return ``(physical_cores, logical_cpus)`` for this machine.

    Open MPI counts *physical cores* as slots by default, so ``-np N`` aborts
    with "not enough slots" once N exceeds the physical-core count — even when
    idle hardware threads (hyperthreads) remain. ``os.cpu_count()`` reports the
    logical count, so we read ``/proc/cpuinfo`` for the physical count (Linux),
    falling back to the logical count when that is unavailable.
    """
    logical = os.cpu_count() or 1
    physical = logical
    try:
        pairs: set[tuple[str | None, str | None]] = set()
        phys_id = core_id = None
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("physical id"):
                phys_id = line.split(":", 1)[1].strip()
            elif line.startswith("core id"):
                core_id = line.split(":", 1)[1].strip()
                pairs.add((phys_id, core_id))
            elif not line.strip():
                phys_id = core_id = None
        if pairs:
            physical = len(pairs)
    except OSError:
        pass
    return physical, logical


def _mpi_command(launcher: str, mpi_ranks: int, exe: str, *exe_args: str):
    """Build the mpirun command, picking the right flag when ranks exceed slots.

    Open MPI aborts when ``-np N`` is larger than the number of slots (physical
    cores by default). We honour the requested rank count so the job still runs:

    * ranks within the hardware-thread count -> ``--use-hwthread-cpus`` (treats
      hyperthreads as slots; no oversubscription),
    * ranks beyond even the hardware threads -> ``--oversubscribe``.

    ``VASP_AUTO_OVERSUBSCRIBE`` overrides the choice: ``1`` always adds
    ``--oversubscribe``; ``0`` adds nothing (let Open MPI enforce its slot
    limit). The flags are OpenMPI-specific, so they are skipped for other
    launchers (e.g. ``mpiexec`` for Intel/MS-MPI, which have no slot concept).

    Returns ``(cmd, warning_or_None)``.
    """
    physical, logical = _local_core_counts()
    pref = os.environ.get("VASP_AUTO_OVERSUBSCRIBE")
    is_mpirun = Path(launcher).name == "mpirun"

    cmd = [launcher, "-np", str(mpi_ranks)]
    warning = None

    if pref == "1":
        if is_mpirun:
            cmd.append("--oversubscribe")
    elif pref == "0":
        if mpi_ranks > physical:
            warning = (
                f"[vasp_auto] requested {mpi_ranks} MPI ranks but this machine "
                f"has {physical} physical core(s); the run will fail unless you "
                f"lower CPU cores or unset VASP_AUTO_OVERSUBSCRIBE."
            )
    elif mpi_ranks > logical:
        if is_mpirun:
            cmd.append("--oversubscribe")
        warning = (
            f"[vasp_auto] requested {mpi_ranks} MPI ranks but this machine has "
            f"{logical} hardware thread(s); running with --oversubscribe "
            f"(slower — set CPU cores <= {physical} for best performance)."
        )
    elif mpi_ranks > physical:
        if is_mpirun:
            cmd.append("--use-hwthread-cpus")
        warning = (
            f"[vasp_auto] requested {mpi_ranks} MPI ranks but this machine has "
            f"{physical} physical core(s); using hardware threads "
            f"(--use-hwthread-cpus). Set CPU cores <= {physical} to avoid this."
        )

    cmd += [exe, *exe_args]
    return cmd, warning


def run_vasp(job_dir: str, vasp_executable: str, cpus: int | None = None, on_progress=None):
    """Run VASP locally via mpirun. on_progress(line) streams output lines."""
    job_dir = Path(job_dir)
    log_file = job_dir / "run.log"
    exe = _resolve_executable(vasp_executable)

    env = os.environ.copy()

    # MPI 版 VASP：cpus 當作 MPI ranks，用 mpirun 啟動
    mpi_ranks = cpus if cpus is not None else 1

    # 避免 BLAS / OMP 自己再亂開 threads
    env["OMP_NUM_THREADS"] = "1"
    env["BLIS_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"

    # mpirun by default; VASP_AUTO_MPI=mpiexec covers MS-MPI / Intel MPI hosts.
    mpi_launcher = os.environ.get("VASP_AUTO_MPI", "mpirun")
    cmd, warning = _mpi_command(mpi_launcher, mpi_ranks, exe)

    with open(log_file, "w", encoding="utf-8") as log:
        if warning:
            log.write(warning + "\n")
            log.flush()  # land before the subprocess writes to the same fd
            if on_progress is not None:
                on_progress(warning)
        if on_progress is None:
            result = subprocess.run(
                cmd,
                cwd=job_dir,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            return result.returncode

        process = subprocess.Popen(
            cmd,
            cwd=job_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in process.stdout:
            log.write(line)
            on_progress(line.rstrip("\n"))
        return process.wait()


def run_qe(job_dir: str, qe_executable: str, cpus: int | None = None, on_progress=None):
    """Run Quantum ESPRESSO pw.x locally via mpirun.

    pw.x reads ``pw.in`` and writes its results to stdout, which we capture as
    ``pw.out`` (the file the QE parser reads). Output is also streamed to
    ``run.log`` so the progress callback and the UI log viewer behave exactly as
    they do for VASP. on_progress(line) streams output lines.
    """
    job_dir = Path(job_dir)
    log_file = job_dir / "run.log"
    pw_out = job_dir / "pw.out"
    exe = _resolve_executable(qe_executable)

    env = os.environ.copy()
    mpi_ranks = cpus if cpus is not None else 1
    env["OMP_NUM_THREADS"] = "1"
    env["BLIS_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"

    mpi_launcher = os.environ.get("VASP_AUTO_MPI", "mpirun")
    cmd, warning = _mpi_command(mpi_launcher, mpi_ranks, exe, "-in", "pw.in")

    with open(pw_out, "w", encoding="utf-8") as out, open(log_file, "w", encoding="utf-8") as log:
        if warning:
            log.write(warning + "\n")
            if on_progress is not None:
                on_progress(warning)
        process = subprocess.Popen(
            cmd, cwd=job_dir, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in process.stdout:
            out.write(line)
            log.write(line)
            if on_progress is not None:
                on_progress(line.rstrip("\n"))
        return process.wait()


def run_ase(job_dir: str, python_exe: str | None = None, cpus: int | None = None,
            on_progress=None):
    """Run the ASE engine driver (run_ase.py) locally as a subprocess.

    The driver reads POSCAR + ase_calc.json, runs the chosen ASE calculator, and
    writes ase_results.json (the parse contract) + CONTCAR. Output is streamed to
    run.log so the progress callback and UI log viewer behave as for VASP/QE.
    ``cpus`` is exported as OMP_NUM_THREADS for threaded calculators (EMT and the
    like ignore it). on_progress(line) streams output lines.
    """
    job_dir = Path(job_dir)
    log_file = job_dir / "run.log"
    driver = job_dir / "run_ase.py"
    if not driver.exists():
        raise FileNotFoundError(f"no run_ase.py in {job_dir}; prepare the ASE job first")
    python = python_exe or sys.executable or "python3"

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(cpus if cpus is not None else 1)

    with open(log_file, "w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [python, "run_ase.py"], cwd=job_dir, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in process.stdout:
            log.write(line)
            if on_progress is not None:
                on_progress(line.rstrip("\n"))
        return process.wait()


def write_submit_script(
    job_dir: str,
    vasp_executable: str,
    cpus: int | None = None,
    scheduler: str = "slurm",
    template_path: str | None = None,
    options: list[str] | None = None,
    run_dir: str | None = None,
    engine: str = "vasp",
) -> Path:
    """Write a scheduler submit script into the job directory.

    The executable path is embedded as given (compute nodes may resolve paths
    differently from the launch host). ``run_dir`` overrides the directory the
    script ``cd``s into at run time — set it to the *remote* job path when the
    script will execute on another machine; it defaults to the local job_dir.
    """
    if scheduler not in SCHEDULER_COMMANDS:
        raise ValueError(f"Unknown scheduler: {scheduler} (use slurm or pbs)")

    job_dir = Path(job_dir).resolve()
    if template_path:
        template = Path(template_path).read_text(encoding="utf-8")
    elif engine == "qe":
        template = DEFAULT_SLURM_QE_TEMPLATE if scheduler == "slurm" else DEFAULT_PBS_QE_TEMPLATE
    else:
        template = DEFAULT_SLURM_TEMPLATE if scheduler == "slurm" else DEFAULT_PBS_TEMPLATE

    script_text = template.format(
        job_name=job_dir.name,
        cpus=cpus if cpus is not None else 1,
        exe=vasp_executable,
        job_dir=run_dir if run_dir is not None else job_dir,
        extra="\n".join(options or []),
    )

    script_path = job_dir / "submit.sh"
    script_path.write_text(script_text, encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def submit_job(
    job_dir: str,
    vasp_executable: str,
    cpus: int | None = None,
    scheduler: str = "slurm",
    template_path: str | None = None,
    options: list[str] | None = None,
    engine: str = "vasp",
) -> dict:
    """Submit a job via sbatch/qsub; returns {"job_id", "script", "submit_output"}."""
    script_path = write_submit_script(
        job_dir, vasp_executable, cpus=cpus, scheduler=scheduler,
        template_path=template_path, options=options, engine=engine,
    )

    command = SCHEDULER_COMMANDS[scheduler]
    result = subprocess.run(
        [command, str(script_path)],
        cwd=script_path.parent,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{command} failed: {result.stderr.strip() or result.stdout.strip()}")

    output = result.stdout.strip()
    # sbatch: "Submitted batch job 12345"; qsub: "12345.hostname"
    job_id = output.split()[-1] if scheduler == "slurm" else output.splitlines()[0].strip()

    return {"job_id": job_id, "script": str(script_path), "submit_output": output}


# ---------------------------------------------------------------- remote submit

def _ssh_target(remote: dict) -> str:
    """Build the ``user@host`` (or bare ``host``) destination from a remote config."""
    host = remote.get("host")
    if not host:
        raise ValueError("remote config needs a 'host' (the machine to submit to)")
    user = remote.get("user")
    return f"{user}@{host}" if user else host


def _ssh_options(remote: dict) -> list[str]:
    """ssh-style option flags (-p PORT, -i KEY, plus any extra ssh_options)."""
    opts: list[str] = []
    port = remote.get("port")
    if port:
        opts += ["-p", str(port)]
    key = remote.get("ssh_key")
    if key:
        opts += ["-i", str(Path(key).expanduser())]
    opts += list(remote.get("ssh_options") or [])
    return opts


def _run_checked(cmd: list[str], what: str) -> str:
    """Run a command, raising RuntimeError with stderr context on failure."""
    # Decode as UTF-8 (not the host locale) so non-ASCII paths/errors from the
    # remote survive; errors="replace" keeps a stray byte from crashing us.
    result = subprocess.run(
        cmd, capture_output=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{what} failed: {detail}")
    return result.stdout


def _transfer_dir(local_dir: Path, target: str, remote_dir: str, remote: dict) -> None:
    """Copy a whole job directory to the remote host (rsync if present, else scp)."""
    ssh_opts = _ssh_options(remote)
    if shutil.which("rsync"):
        cmd = ["rsync", "-az"]
        if ssh_opts:
            cmd += ["-e", "ssh " + " ".join(shlex.quote(o) for o in ssh_opts)]
        # trailing slash on source copies the contents into remote_dir
        cmd += [f"{local_dir}/", f"{target}:{remote_dir}/"]
        _run_checked(cmd, "rsync")
        return

    # scp fallback: it uses -P (uppercase) for the port, unlike ssh's -p.
    scp_opts: list[str] = []
    port = remote.get("port")
    if port:
        scp_opts += ["-P", str(port)]
    key = remote.get("ssh_key")
    if key:
        scp_opts += ["-i", str(Path(key).expanduser())]
    scp_opts += list(remote.get("ssh_options") or [])
    cmd = ["scp", "-r", *scp_opts, f"{local_dir}/.", f"{target}:{remote_dir}/"]
    _run_checked(cmd, "scp")


# Run modes that mean "execute directly over SSH" rather than submit to a queue.
SSH_RUN_MODES = {"ssh", "direct", "none", "local", ""}


def remote_run_mode(remote: dict) -> str:
    """How a remote machine runs jobs.

    Returns ``"ssh"`` for direct ``mpirun`` over SSH (no scheduler), or the
    scheduler name (``"slurm"``/``"pbs"``) for queue submission. An explicit
    ``run_mode`` wins; otherwise the ``scheduler`` field decides, with the
    pseudo-schedulers ``ssh``/``direct``/``none``/``local`` meaning direct SSH.
    """
    mode = (remote.get("run_mode") or "").strip().lower()
    if mode in {"ssh_detached", "detached", "offload"}:
        return "ssh_detached"
    if mode in {"ssh", "direct"}:
        return "ssh"
    if mode in SCHEDULER_COMMANDS:
        return mode
    scheduler = (remote.get("scheduler") or "slurm").strip().lower()
    if scheduler in SSH_RUN_MODES:
        return "ssh"
    return scheduler


def _remote_vasp_exe(remote: dict) -> str:
    """The VASP binary path on the remote machine.

    If ``vasp_executable`` points at a directory (e.g. ``.../bin``) rather than a
    binary, fall back to ``<dir>/vasp_std`` so a common misconfiguration still
    works.
    """
    exe = remote.get("vasp_executable")
    if not exe:
        raise ValueError(
            "remote config needs a 'vasp_executable' (the VASP path on the remote machine)"
        )
    exe = exe.rstrip("/")
    base = exe.rsplit("/", 1)[-1].lower()
    if "vasp" not in base and "pw" not in base:
        exe = exe + "/vasp_std"
    return exe


def run_vasp_remote(
    job_dir: str,
    remote: dict,
    cpus: int | None = None,
    on_progress=None,
    fetch_heavy: bool = True,
    remote_subdir: str | None = None,
) -> int:
    """Run VASP on a remote machine via direct ``mpirun`` over SSH (no scheduler).

    Unlike :func:`submit_job_remote` (fire-and-forget queue submission), this runs
    synchronously: it ships the prepared inputs to ``<remote_root>/<job name>``,
    runs ``mpirun`` there (sourcing the machine's ``env_setup`` first so MKL/MPI
    libraries are on the path), waits for it to finish, then copies the results
    back so the local parsers and viewers work unchanged. A ``.remote.json`` marker
    tags the job with the machine and remote directory. Returns the VASP exit code,
    mirroring :func:`run_vasp`.

    Useful when the remote machine has no working scheduler (e.g. a single
    workstation) but can run ``mpirun`` directly. Required remote keys: ``host``,
    ``remote_root``, ``vasp_executable``. Optional: ``user``, ``port``,
    ``ssh_key``, ``ssh_options``, ``env_setup`` (a shell snippet sourced before the
    run, e.g. ``source /opt/intel/oneapi/setvars.sh``).
    """
    job_dir = Path(job_dir).resolve()
    if not remote.get("remote_root"):
        raise ValueError(
            "remote config needs a 'remote_root' (base directory on the remote machine)"
        )
    target = _ssh_target(remote)
    ssh_opts = _ssh_options(remote)
    # remote_subdir keeps multi-case / multi-trial jobs from colliding on the
    # remote (e.g. two cases both with an "encut_400" convergence trial).
    subpath = (remote_subdir or job_dir.name).strip("/")
    remote_dir = remote["remote_root"].rstrip("/") + "/" + subpath
    exe = _remote_vasp_exe(remote)
    ranks = cpus if cpus is not None else 1
    env_setup = (remote.get("env_setup") or "").strip()
    machine = remote.get("name") or remote.get("host")

    quoted_dir = shlex.quote(remote_dir)
    _run_checked(["ssh", "-x", *ssh_opts, target, f"mkdir -p {quoted_dir}"], "remote mkdir")
    _transfer_dir(job_dir, target, remote_dir, remote)

    # One non-interactive shell: set up the toolchain, then launch mpirun. Its
    # output goes to run.log on the remote (fetched back below).
    parts = ["unset DISPLAY"]
    if env_setup:
        parts.append(f"{{ {env_setup} ; }} >/dev/null 2>&1 || true")
    parts.append("ulimit -s unlimited 2>/dev/null || true")
    parts.append(f"cd {quoted_dir}")
    parts.append(f"mpirun -np {ranks} {shlex.quote(exe)} > run.log 2>&1")
    remote_script = "\n".join(parts)

    if on_progress is not None:
        on_progress(f"[remote] running on {machine}: {remote_dir}")
    result = subprocess.run(
        ["ssh", "-x", *ssh_opts, target, f"bash -lc {shlex.quote(remote_script)}"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return_code = result.returncode

    # Bring the results home so build_row / the viewers see local files.
    try:
        fetch_remote_results(remote, remote_dir, str(job_dir), include_heavy=fetch_heavy)
    except (RuntimeError, OSError):
        pass

    marker = {
        "machine": machine,
        "host": remote.get("host"),
        "remote_dir": remote_dir,
        "scheduler": "ssh",
        "mode": "ssh",
        "ran_at": datetime.now().isoformat(timespec="seconds"),
    }
    (job_dir / ".remote.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return return_code


def submit_job_remote(
    job_dir: str,
    remote: dict,
    cpus: int | None = None,
    job_template: str | None = None,
) -> dict:
    """Send a fully prepared job to a remote machine and submit it to its queue.

    Every input file VASP needs (INCAR, KPOINTS, POSCAR, POTCAR, submit.sh) is
    copied to the remote host first, then ``sbatch``/``qsub`` is invoked there
    over SSH. Once this returns the job is queued on the remote scheduler, so the
    local host can be powered off.

    ``remote`` is the config.yaml ``remote:`` mapping. Required keys: ``host`` and
    ``remote_root`` (a base directory on the remote machine). Recommended:
    ``vasp_executable`` (the VASP path *on the remote*). Optional: ``user``,
    ``port``, ``ssh_key``, ``ssh_options`` (list), ``scheduler`` (slurm|pbs,
    default slurm), ``scheduler_options`` (list of extra script lines).

    Returns {"job_id", "scheduler", "host", "remote_dir", "submit_output"}.
    """
    job_dir = Path(job_dir).resolve()
    remote_root = remote.get("remote_root")
    if not remote_root:
        raise ValueError(
            "remote config needs a 'remote_root' (base directory on the remote machine)"
        )
    scheduler = remote.get("scheduler", "slurm")
    if scheduler not in SCHEDULER_COMMANDS:
        raise ValueError(f"Unknown remote scheduler: {scheduler} (use slurm or pbs)")
    exe = remote.get("vasp_executable")
    if not exe:
        raise ValueError(
            "remote config needs a 'vasp_executable' (the VASP path on the remote machine)"
        )

    target = _ssh_target(remote)
    remote_dir = remote_root.rstrip("/") + "/" + job_dir.name
    template = job_template or remote.get("job_template")

    # Write the submit script with the remote run directory baked in.
    write_submit_script(
        str(job_dir),
        str(exe),
        cpus=cpus,
        scheduler=scheduler,
        template_path=template,
        options=remote.get("scheduler_options"),
        run_dir=remote_dir,
    )

    ssh_opts = _ssh_options(remote)
    quoted_dir = shlex.quote(remote_dir)

    # 1. make sure the destination exists, 2. copy everything, 3. submit there.
    _run_checked(
        ["ssh", *ssh_opts, target, f"mkdir -p {quoted_dir}"],
        "remote mkdir",
    )
    _transfer_dir(job_dir, target, remote_dir, remote)
    submit_cmd = SCHEDULER_COMMANDS[scheduler]
    output = _run_checked(
        ["ssh", *ssh_opts, target, f"cd {quoted_dir} && {submit_cmd} submit.sh"],
        f"remote {submit_cmd}",
    ).strip()

    # sbatch: "Submitted batch job 12345"; qsub: "12345.hostname"
    if scheduler == "slurm":
        job_id = output.split()[-1] if output else ""
    else:
        job_id = output.splitlines()[0].strip() if output else ""

    machine = remote.get("name") or remote.get("host")
    result = {
        "job_id": job_id,
        "scheduler": scheduler,
        "machine": machine,
        "host": remote.get("host"),
        "remote_dir": remote_dir,
        "submit_output": output,
    }

    # Tag the local job dir so the UI/results know this case ran on a remote
    # machine (the output files themselves stay on that machine).
    marker = {**result, "submitted_at": datetime.now().isoformat(timespec="seconds")}
    (job_dir / ".remote.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return result


# ---------------------------------------------------------- detached offload mode
#
# "Offload" runs install the full vasp_auto engine in a venv on the remote
# machine and drive the whole calculation there detached (setsid), so the local
# host can be powered off. Unlike run_vasp_remote (synchronous, local stays on)
# or submit_job_remote (needs a working scheduler), this works on a plain
# workstation and supports the iterative paths (convergence scans, workflows)
# because the engine itself runs remotely.

ENGINE_SUBDIR = ".vasp_auto"   # under remote_root: venv/ + runs/ control dirs


def _scp_options(remote: dict) -> list[str]:
    """scp option flags (-P PORT, -i KEY, extra ssh_options). scp uses -P, not -p."""
    opts: list[str] = []
    if remote.get("port"):
        opts += ["-P", str(remote["port"])]
    if remote.get("ssh_key"):
        opts += ["-i", str(Path(remote["ssh_key"]).expanduser())]
    opts += list(remote.get("ssh_options") or [])
    return opts


def _ship_file(local: Path, target: str, remote_path: str, remote: dict, ssh_opts: list[str]) -> None:
    """Copy a single local file to remote_path (rsync if present, else scp)."""
    if shutil.which("rsync"):
        cmd = ["rsync", "-az"]
        if ssh_opts:
            cmd += ["-e", "ssh " + " ".join(shlex.quote(o) for o in ssh_opts)]
        cmd += [str(local), f"{target}:{remote_path}"]
        _run_checked(cmd, "rsync file")
    else:
        _run_checked(["scp", *_scp_options(remote), str(local), f"{target}:{remote_path}"], "scp file")


def _remote_engine_paths(remote: dict) -> dict:
    """Standard locations of the remote-installed engine and its run state."""
    root = remote.get("remote_root")
    if not root:
        raise ValueError("remote config needs a 'remote_root' (base directory on the remote)")
    root = root.rstrip("/")
    home = f"{root}/{ENGINE_SUBDIR}"
    return {
        "root": root,
        "home": home,
        "venv": f"{home}/venv",
        "vasp_auto": f"{home}/venv/bin/vasp-auto",
        "runs": f"{home}/runs",
    }


def build_engine_wheel(dest_dir: str | Path) -> Path:
    """Build a vasp_auto wheel from the source repo; return the wheel path."""
    repo_root = Path(__file__).resolve().parents[2]
    if not (repo_root / "pyproject.toml").exists():
        raise FileNotFoundError(
            f"cannot build a wheel: no pyproject.toml at {repo_root}. Remote engine "
            "setup needs vasp_auto installed from source."
        )
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    _run_checked(
        [sys.executable, "-m", "pip", "wheel", str(repo_root), "-w", str(dest), "--no-deps"],
        "build wheel",
    )
    wheels = sorted(dest.glob("vasp_auto-*.whl"))
    if not wheels:
        raise RuntimeError("wheel build produced no vasp_auto-*.whl")
    return wheels[-1]


def setup_remote_engine(remote: dict, timeout: int = 600, on_progress=None) -> dict:
    """Install vasp_auto into a venv on the remote machine (one-time per machine).

    Builds a wheel locally, ships it, creates a venv (bootstrapping pip via
    get-pip.py when the distro lacks ensurepip / python3-venv), and pip-installs
    the wheel with its dependencies. After this, detached/offload runs
    (submit_job_detached) can drive the full engine on the remote so the local
    host can be powered off. Returns {"ok", "vasp_auto", "detail"}.
    """
    paths = _remote_engine_paths(remote)
    target = _ssh_target(remote)
    ssh_opts = _ssh_options(remote)

    def log(msg):
        if on_progress is not None:
            on_progress(msg)

    with tempfile.TemporaryDirectory() as tmp:
        log("building wheel…")
        wheel = build_engine_wheel(tmp)
        _run_checked(["ssh", "-x", *ssh_opts, target, f"mkdir -p {shlex.quote(paths['home'])}"],
                     "remote mkdir engine home")
        log(f"shipping {wheel.name}…")
        _ship_file(wheel, target, f"{paths['home']}/{wheel.name}", remote, ssh_opts)
        wheel_remote = f"{paths['home']}/{wheel.name}"

        log("creating venv + installing dependencies (may take a minute)…")
        script = "\n".join([
            "set -e",
            f"cd {shlex.quote(paths['home'])}",
            "rm -rf venv",
            "python3 -m venv --without-pip venv",
            "if [ ! -x venv/bin/pip ]; then "
            "(curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py "
            "|| wget -q https://bootstrap.pypa.io/get-pip.py -O get-pip.py); "
            "venv/bin/python get-pip.py --quiet; fi",
            f"venv/bin/pip install --quiet {shlex.quote(wheel_remote)}",
            # Verify only the lean engine: vasp_auto plus its sole core dep (PyYAML).
            # pandas/openpyxl live in the [results] extra and are intentionally NOT
            # installed here — the offload engine is lean (docs/INSTALL.md, "Why the
            # engine is lean"). Importing them in the check made setup always fail.
            "venv/bin/python -c 'import vasp_auto, yaml; print(\"ENGINE_OK\")'",
        ])
        res = subprocess.run(
            ["ssh", "-x", *ssh_opts, target, f"bash -lc {shlex.quote(script)}"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
        )

    ok = res.returncode == 0 and "ENGINE_OK" in res.stdout
    detail = (res.stdout + res.stderr).strip()
    return {"ok": ok, "vasp_auto": paths["vasp_auto"], "detail": detail[-2000:]}


def remote_engine_installed(remote: dict) -> bool:
    """True if the offload engine (vasp-auto) is present in the remote venv."""
    paths = _remote_engine_paths(remote)
    target = _ssh_target(remote)
    ssh_opts = _ssh_options(remote)
    try:
        res = subprocess.run(
            ["ssh", "-x", *ssh_opts, target,
             f"test -x {shlex.quote(paths['vasp_auto'])} && echo yes || echo no"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return "yes" in res.stdout


def submit_job_detached(
    case_dir: str,
    remote: dict,
    case_name: str,
    cpus: int | None,
    calc_flags: list[str],
    local_job_dir: str | None = None,
    on_progress=None,
) -> dict:
    """Offload a full calculation to the remote engine and return immediately.

    The remote-installed engine (see setup_remote_engine) runs the calculation
    detached via setsid, so the local machine can be powered off. Ships the case
    inputs (POSCAR + POTCAR + optional INCAR/KPOINTS) and a remote config.yaml,
    then launches ``vasp-auto inputs/<case> <calc_flags> -n <cpus>`` under setsid,
    records its PID, and writes a ``.remote.json`` marker into ``local_job_dir``.
    Results stay under ``<remote_root>/jobs/<case>`` until fetched. Returns
    {"machine","remote_dir","inputs_dir","control_dir","pid","log"}.
    """
    case_dir = Path(case_dir)
    paths = _remote_engine_paths(remote)
    target = _ssh_target(remote)
    ssh_opts = _ssh_options(remote)
    exe = _remote_vasp_exe(remote)
    ranks = cpus if cpus is not None else 1
    env_setup = (remote.get("env_setup") or "").strip()
    machine = remote.get("name") or remote.get("host")

    # A dedicated results/ dir (absolute jobs_root) so output never lands in a
    # doubled path when remote_root itself already ends in e.g. "jobs".
    results_base = f"{paths['root']}/results"
    inputs_remote = f"{paths['root']}/inputs/{case_name}"
    jobs_remote = f"{results_base}/{case_name}"
    control_dir = f"{paths['runs']}/{case_name}"

    if not remote_engine_installed(remote):
        raise RuntimeError(
            f"the offload engine is not installed on {machine}. Run remote setup first "
            "(CLI: --remote-setup NAME, or the UI Remote tab's 'Set up offload engine' button)."
        )

    _run_checked(
        ["ssh", "-x", *ssh_opts, target,
         f"mkdir -p {shlex.quote(inputs_remote)} {shlex.quote(control_dir)} {shlex.quote(results_base)}"],
        "remote mkdir",
    )

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.yaml"
        cfg.write_text(
            f"vasp_executable: {exe}\njobs_root: {results_base}\nneb_images: 5\n",
            encoding="utf-8",
        )
        _ship_file(cfg, target, f"{paths['root']}/config.yaml", remote, ssh_opts)

    # Ship the INCAR templates (example/INCAR_*) so the remote engine can build
    # INCARs for every calc type (relax/dos/bands/freq/…), not only the built-in
    # scf/neb. VASP_AUTO_ROOT (set in run.sh below) points the loader at them.
    repo_example = Path(__file__).resolve().parents[2] / "example"
    templates_root = ""
    if repo_example.is_dir():
        _run_checked(
            ["ssh", "-x", *ssh_opts, target, f"mkdir -p {shlex.quote(paths['home'] + '/example')}"],
            "remote mkdir example",
        )
        _transfer_dir(repo_example, target, f"{paths['home']}/example", remote)
        templates_root = paths["home"]

    # Inputs bundle: POSCAR + a pre-built POTCAR (+ INCAR/KPOINTS if supplied) so
    # the remote engine never needs the POTCAR library.
    _transfer_dir(case_dir, target, inputs_remote, remote)

    flags_str = " ".join(shlex.quote(f) for f in calc_flags)
    env_line = env_setup if env_setup else "true"
    pid_f = f"{control_dir}/pid"
    rc_f = f"{control_dir}/rc"
    log_f = f"{control_dir}/run.log"
    script = "\n".join([
        "#!/bin/bash",
        f"echo $$ > {shlex.quote(pid_f)}",
        f"cd {shlex.quote(paths['root'])}",
        *([f"export VASP_AUTO_ROOT={shlex.quote(templates_root)}"] if templates_root else []),
        f"{{ {env_line} ; }} >/dev/null 2>&1 || true",
        "ulimit -s unlimited 2>/dev/null || true",
        f"{shlex.quote(paths['vasp_auto'])} {shlex.quote('inputs/' + case_name)} "
        f"{flags_str} -n {ranks} > {shlex.quote(log_f)} 2>&1",
        f"echo $? > {shlex.quote(rc_f)}",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmp:
        sh = Path(tmp) / "run.sh"
        sh.write_text(script, encoding="utf-8")
        _ship_file(sh, target, f"{control_dir}/run.sh", remote, ssh_opts)

    launch = (
        f"rm -f {shlex.quote(rc_f)} {shlex.quote(pid_f)}; "
        f"setsid bash {shlex.quote(control_dir + '/run.sh')} </dev/null >/dev/null 2>&1 & "
        f"sleep 1; cat {shlex.quote(pid_f)} 2>/dev/null"
    )
    out = _run_checked(["ssh", "-x", *ssh_opts, target, launch], "remote launch")
    pid = out.strip().splitlines()[-1].strip() if out.strip() else ""

    result = {
        "machine": machine,
        "host": remote.get("host"),
        "remote_dir": jobs_remote,
        "inputs_dir": inputs_remote,
        "control_dir": control_dir,
        "pid": pid,
        "log": log_f,
        "scheduler": "ssh_detached",
        "mode": "ssh_detached",
    }
    if local_job_dir:
        marker = {**result, "submitted_at": datetime.now().isoformat(timespec="seconds")}
        Path(local_job_dir).mkdir(parents=True, exist_ok=True)
        (Path(local_job_dir) / ".remote.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return result


def poll_detached_job(remote: dict, control_dir: str, pid: str | None = None) -> dict:
    """Status of a detached offload job from its control dir (pid + rc files).

    Returns {"state", "return_code", "raw"} with state running/completed/unknown.
    """
    target = _ssh_target(remote)
    ssh_opts = _ssh_options(remote)
    rc_f = f"{control_dir}/rc"
    cmd = (
        f"if [ -f {shlex.quote(rc_f)} ]; then echo DONE; cat {shlex.quote(rc_f)}; "
        f"elif [ -n {shlex.quote(pid or '')} ] && kill -0 {shlex.quote(pid or '0')} 2>/dev/null; "
        f"then echo RUNNING; else echo UNKNOWN; fi"
    )
    try:
        res = subprocess.run(["ssh", "-x", *ssh_opts, target, cmd],
                             capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"state": "unknown", "return_code": None, "raw": str(exc)}
    lines = res.stdout.strip().splitlines()
    if lines and lines[0] == "DONE":
        return {"state": "completed", "return_code": lines[1] if len(lines) > 1 else None,
                "raw": res.stdout.strip()}
    if lines and lines[0] == "RUNNING":
        return {"state": "running", "return_code": None, "raw": res.stdout.strip()}
    return {"state": "unknown", "return_code": None, "raw": res.stdout.strip() or res.stderr.strip()}


def poll_job_status(job_id: str, scheduler: str = "slurm") -> dict:
    """Query a scheduler for the status of a submitted job.

    Returns a dict with keys:
      - job_id: the queried job ID
      - scheduler: the scheduler used
      - state: one of "running", "pending", "completed", "unknown"
      - raw: the raw stdout from the poll command (empty string if unavailable)

    Gracefully returns state="unknown" when:
      - the scheduler binary is not on PATH
      - the scheduler is not in POLL_COMMANDS
      - the command fails (e.g. job ID no longer in the queue = completed)
    """
    if scheduler not in POLL_COMMANDS:
        return {"job_id": job_id, "scheduler": scheduler, "state": "unknown", "raw": ""}

    base_cmd = POLL_COMMANDS[scheduler]
    binary = base_cmd[0]

    if shutil.which(binary) is None:
        return {"job_id": job_id, "scheduler": scheduler, "state": "unknown", "raw": ""}

    cmd = base_cmd + [str(job_id)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return {"job_id": job_id, "scheduler": scheduler, "state": "unknown", "raw": ""}

    return _parse_poll_output(scheduler, job_id, result.returncode, result.stdout, result.stderr)


def _parse_poll_output(scheduler, job_id, returncode, stdout, stderr):
    """Turn squeue/qstat output into a {state, raw, ...} dict (local or remote)."""
    raw = (stdout + stderr).strip()

    if scheduler == "slurm":
        # squeue -h -j <id> prints nothing when the job is done/absent.
        if returncode != 0 or not stdout.strip():
            if "Invalid job id" in raw or not raw:
                return {"job_id": job_id, "scheduler": scheduler, "state": "completed", "raw": raw}
            return {"job_id": job_id, "scheduler": scheduler, "state": "unknown", "raw": raw}
        # With -h (no header) each line is: JOBID PARTITION NAME USER ST TIME NODES NODELIST
        fields = stdout.split()
        st = fields[4] if len(fields) > 4 else ""
        state_map = {"R": "running", "CG": "running", "PD": "pending", "CF": "pending"}
        return {"job_id": job_id, "scheduler": scheduler,
                "state": state_map.get(st, "unknown"), "raw": raw}

    if scheduler == "pbs":
        if returncode != 0:
            # qstat fails when the job is not found (finished and purged).
            return {"job_id": job_id, "scheduler": scheduler, "state": "completed", "raw": raw}
        # qstat output: job_id.host owner queue job_name session NDS TSK mem time status
        for line in stdout.splitlines():
            if str(job_id) in line:
                parts = line.split()
                st = parts[-2] if len(parts) >= 2 else ""
                state_map = {"R": "running", "E": "running", "Q": "pending",
                             "H": "pending", "C": "completed"}
                return {"job_id": job_id, "scheduler": scheduler,
                        "state": state_map.get(st, "unknown"), "raw": raw}
        return {"job_id": job_id, "scheduler": scheduler, "state": "unknown", "raw": raw}

    return {"job_id": job_id, "scheduler": scheduler, "state": "unknown", "raw": raw}


# ------------------------------------------------- remote connection / status / fetch

# Large binaries that are not worth pulling back across the network by default.
HEAVY_OUTPUTS = ["WAVECAR", "CHG", "CHGCAR", "vaspout.h5", "AECCAR0", "AECCAR1", "AECCAR2"]


def remote_command(remote: dict, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a shell command on the remote host over SSH and return the result."""
    target = _ssh_target(remote)
    ssh_opts = _ssh_options(remote)
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", *ssh_opts, target, command],
        capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


def check_remote_connection(remote: dict) -> dict:
    """Check SSH reachability plus remote_root / VASP / scheduler availability.

    Returns {"ok", "host", "message", "checks": [{"name","ok","detail"}, ...]}.
    Never raises for a normal SSH failure — it reports it in the result so the
    UI button can show what went wrong.
    """
    checks: list[dict] = []
    try:
        target = _ssh_target(remote)
    except ValueError as exc:
        return {"ok": False, "host": remote.get("host"), "message": str(exc), "checks": checks}

    try:
        probe = remote_command(remote, "echo vasp_auto_ok", timeout=20)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "host": remote.get("host"),
                "message": f"SSH to {target} failed: {exc}", "checks": checks}

    if probe.returncode != 0 or "vasp_auto_ok" not in probe.stdout:
        return {"ok": False, "host": remote.get("host"),
                "message": probe.stderr.strip() or "SSH connection failed", "checks": checks}
    checks.append({"name": "ssh", "ok": True, "detail": f"connected to {target}"})

    root = remote.get("remote_root")
    if root:
        res = remote_command(remote, f"test -d {shlex.quote(root)} && echo yes || echo no")
        ok = "yes" in res.stdout
        checks.append({"name": "remote_root", "ok": True,
                       "detail": f"{root} exists" if ok else f"{root} will be created on submit"})

    if remote.get("vasp_executable"):
        exe = _remote_vasp_exe(remote)  # resolves a bin directory to <dir>/vasp_std
        res = remote_command(remote, f"test -x {shlex.quote(exe)} && echo yes || echo no")
        ok = "yes" in res.stdout
        checks.append({"name": "vasp_executable", "ok": ok,
                       "detail": f"{exe} found" if ok else f"{exe} not found or not executable"})

    # ssh run mode launches mpirun directly; scheduler modes need their submit cmd.
    if remote_run_mode(remote) == "ssh":
        res = remote_command(remote, "command -v mpirun >/dev/null 2>&1 && echo yes || echo no")
        ok = "yes" in res.stdout
        checks.append({"name": "mpirun", "ok": ok,
                       "detail": "mpirun available" if ok else "mpirun not on PATH"})
    else:
        scheduler = remote.get("scheduler", "slurm")
        submit_cmd = SCHEDULER_COMMANDS.get(scheduler)
        if submit_cmd:
            res = remote_command(remote, f"command -v {submit_cmd} >/dev/null 2>&1 && echo yes || echo no")
            ok = "yes" in res.stdout
            checks.append({"name": scheduler, "ok": ok,
                           "detail": f"{submit_cmd} available" if ok else f"{submit_cmd} not on PATH"})

    # remote_root is allowed to be missing (created on submit); everything else must pass.
    overall = all(c["ok"] for c in checks if c["name"] != "remote_root")
    return {
        "ok": overall,
        "host": remote.get("host"),
        "message": "Connection OK" if overall else "Connected, but some checks failed",
        "checks": checks,
    }


def poll_remote_job(remote: dict, job_id: str) -> dict:
    """Query the remote scheduler for a job's status over SSH."""
    scheduler = remote.get("scheduler", "slurm")
    if scheduler not in POLL_COMMANDS:
        return {"job_id": job_id, "scheduler": scheduler, "state": "unknown", "raw": ""}
    base_cmd = POLL_COMMANDS[scheduler] + [str(job_id)]
    command = " ".join(shlex.quote(part) for part in base_cmd)
    try:
        res = remote_command(remote, command, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return {"job_id": job_id, "scheduler": scheduler, "state": "unknown", "raw": ""}
    return _parse_poll_output(scheduler, job_id, res.returncode, res.stdout, res.stderr)


def fetch_remote_results(
    remote: dict,
    remote_dir: str,
    local_dir: str,
    include_heavy: bool = False,
) -> dict:
    """Copy result files from the remote job directory back to the local one.

    The files stay on the remote machine — this pulls a copy so the local
    analysis buttons (report, DOS, trajectory, …) work. Heavy binaries
    (WAVECAR/CHGCAR/…) are skipped unless ``include_heavy`` is set.

    Returns {"local_dir", "remote_dir", "transferred": bool}.
    """
    local = Path(local_dir)
    local.mkdir(parents=True, exist_ok=True)
    target = _ssh_target(remote)
    ssh_opts = _ssh_options(remote)
    src = f"{target}:{remote_dir.rstrip('/')}/"

    if shutil.which("rsync"):
        cmd = ["rsync", "-az"]
        if ssh_opts:
            cmd += ["-e", "ssh " + " ".join(shlex.quote(o) for o in ssh_opts)]
        if not include_heavy:
            for name in HEAVY_OUTPUTS:
                cmd += ["--exclude", name]
        cmd += [src, f"{local}/"]
        _run_checked(cmd, "rsync fetch")
        return {"local_dir": str(local), "remote_dir": remote_dir, "transferred": True}

    # scp fallback: pull a known set of result files, ignoring any that are absent.
    wanted = ["OUTCAR", "CONTCAR", "OSZICAR", "vasprun.xml", "run.log", "job.log",
              "DOSCAR", "EIGENVAL", "XDATCAR", "INCAR", "KPOINTS", "POSCAR", "LOCPOT"]
    if include_heavy:
        wanted += HEAVY_OUTPUTS
    scp_opts: list[str] = []
    port = remote.get("port")
    if port:
        scp_opts += ["-P", str(port)]
    key = remote.get("ssh_key")
    if key:
        scp_opts += ["-i", str(Path(key).expanduser())]
    scp_opts += list(remote.get("ssh_options") or [])
    # A single scp call pulling each wanted file; missing files just warn (rc may be !=0).
    subprocess.run(
        ["scp", *scp_opts, *[f"{target}:{remote_dir.rstrip('/')}/{n}" for n in wanted], f"{local}/"],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    return {"local_dir": str(local), "remote_dir": remote_dir, "transferred": True}


def list_remote_jobs(remote: dict, root: str) -> list[dict]:
    """List VASP job directories that live on a remote machine, newest first.

    Walks up to two levels under ``root`` — flat ``root/<case>`` and nested
    ``root/<project>/<case>`` — and keeps directories that hold VASP I/O. Each
    entry carries the newest output mtime (so the UI can sort by date) and a
    coarse status. One ``ssh`` round-trip; raises RuntimeError on failure.
    """
    root = (root or "").rstrip("/") or "/"
    rq = shlex.quote(root)
    # POSIX sh: a job dir has any VASP I/O; emit "<mtime>\t<o><v><z>\t<path>".
    script = (
        f"r={rq}; "
        'isjob() { [ -e "$1/OUTCAR" ] || [ -e "$1/vasprun.xml" ] || '
        '[ -e "$1/OSZICAR" ] || [ -e "$1/INCAR" ] || [ -e "$1/POSCAR" ]; }; '
        'emit() { d=$1; n=0; '
        'for f in OUTCAR vasprun.xml OSZICAR run.log CONTCAR INCAR POSCAR; do '
        '[ -e "$d/$f" ] && { t=$(stat -c %Y "$d/$f" 2>/dev/null || echo 0); '
        '[ "$t" -gt "$n" ] && n=$t; }; done; '
        '[ "$n" = 0 ] && n=$(stat -c %Y "$d" 2>/dev/null || echo 0); '
        'o=0; [ -e "$d/OUTCAR" ] && o=1; v=0; [ -e "$d/vasprun.xml" ] && v=1; '
        'z=0; [ -e "$d/OSZICAR" ] && z=1; '
        'printf "%s\\t%s%s%s\\t%s\\n" "$n" "$o" "$v" "$z" "$d"; }; '
        'for d in "$r"/*/; do d=${d%/}; [ -d "$d" ] || continue; '
        'if isjob "$d"; then emit "$d"; else '
        'for s in "$d"/*/; do s=${s%/}; [ -d "$s" ] || continue; '
        'isjob "$s" && emit "$s"; done; fi; done'
    )
    try:
        res = remote_command(remote, script, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f"could not reach {remote.get('host')}: {exc}") from exc
    if res.returncode != 0 and not res.stdout.strip():
        raise RuntimeError(res.stderr.strip() or f"could not list {root} on {remote.get('host')}")
    rows: list[dict] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        mt, flags, path = parts
        flags = (flags + "000")[:3]
        has_out, has_vr, has_osz = flags[0] == "1", flags[1] == "1", flags[2] == "1"
        rel = path[len(root):].lstrip("/") if path.startswith(root) else path
        rows.append({
            "path": path,
            "name": Path(path).name,
            "rel": rel or Path(path).name,
            "modified_ts": int(mt) if mt.isdigit() else 0,
            "status": "done" if has_out else ("running" if has_osz else "prepared"),
            "has_outcar": has_out,
            "has_vasprun": has_vr,
        })
    rows.sort(key=lambda r: r["modified_ts"], reverse=True)
    return rows


def list_remote_dir(remote: dict, path: str) -> dict:
    """List the immediate entries (files + subdirs) of a remote directory.

    Backs the per-job file browser: each entry has name/path/is_dir/size/mtime.
    """
    p = (path or "").rstrip("/") or "/"
    pq = shlex.quote(p)
    script = (
        f"d={pq}; for e in \"$d\"/* \"$d\"/.[!.]*; do [ -e \"$e\" ] || continue; "
        'if [ -d "$e" ]; then '
        'printf "d\\t0\\t%s\\t%s\\n" "$(stat -c %Y "$e" 2>/dev/null || echo 0)" "$e"; '
        'else '
        'printf "f\\t%s\\t%s\\t%s\\n" "$(stat -c %s "$e" 2>/dev/null || echo 0)" '
        '"$(stat -c %Y "$e" 2>/dev/null || echo 0)" "$e"; fi; done'
    )
    try:
        res = remote_command(remote, script, timeout=45)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f"could not reach {remote.get('host')}: {exc}") from exc
    if res.returncode != 0 and not res.stdout.strip():
        raise RuntimeError(res.stderr.strip() or f"could not list {p} on {remote.get('host')}")
    entries: list[dict] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        kind, size, mt, epath = parts
        entries.append({
            "name": Path(epath).name,
            "path": epath,
            "is_dir": kind == "d",
            "size": int(size) if size.isdigit() else 0,
            "modified_ts": int(mt) if mt.isdigit() else 0,
        })
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    parent = str(Path(p).parent) if str(Path(p).parent) != p else None
    return {"path": p, "parent": parent, "entries": entries}


def list_remote_cases(remote: dict, path: str) -> dict:
    """List VASP case directories under a remote directory (one SSH round-trip).

    A "case" is a directory with a POSCAR file (single) or initial/POSCAR plus
    final/POSCAR (TSS/NEB). If ``path`` itself is a case it is returned alone;
    otherwise its immediate subdirectories are scanned. Returns
    {"path", "cases": [{"name", "path", "type"}]}.
    """
    p = (path or "").rstrip("/") or "/"
    pq = shlex.quote(p)
    script = (
        f"r={pq}; "
        'emit() { if [ -f "$1/POSCAR" ]; then printf "scf\\t%s\\n" "$1"; '
        'elif [ -f "$1/initial/POSCAR" ] && [ -f "$1/final/POSCAR" ]; then '
        'printf "tss\\t%s\\n" "$1"; fi; }; '
        'if [ -f "$r/POSCAR" ] || { [ -f "$r/initial/POSCAR" ] && [ -f "$r/final/POSCAR" ]; }; '
        'then emit "$r"; '
        'else for d in "$r"/*/; do d="${d%/}"; [ -d "$d" ] && emit "$d"; done; fi'
    )
    try:
        res = remote_command(remote, script, timeout=45)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f"could not reach {remote.get('host')}: {exc}") from exc
    cases: list[dict] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        ctype, cpath = parts
        cases.append({"name": cpath.rstrip("/").rsplit("/", 1)[-1], "path": cpath, "type": ctype})
    cases.sort(key=lambda c: c["name"].lower())
    return {"path": p, "cases": cases}


def fetch_remote_file(remote: dict, remote_path: str, local_path) -> Path:
    """Copy one file off the remote machine (for a UI download). Returns the path."""
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    target = _ssh_target(remote)
    scp_opts: list[str] = []
    port = remote.get("port")
    if port:
        scp_opts += ["-P", str(port)]
    key = remote.get("ssh_key")
    if key:
        scp_opts += ["-i", str(Path(key).expanduser())]
    scp_opts += list(remote.get("ssh_options") or [])
    # Single-quote the remote path so the remote shell takes it literally.
    cmd = ["scp", *scp_opts, f"{target}:{shlex.quote(remote_path)}", str(local)]
    _run_checked(cmd, "scp file")
    return local


def read_remote_text(remote: dict, remote_path: str, max_bytes: int = 200_000) -> dict:
    """Read up to ``max_bytes`` of a remote text file over SSH (for the UI viewer).

    Returns ``{"text", "size", "truncated"}``. One ``ssh`` round-trip: it prints
    the byte size, a marker, then a capped ``head`` of the file. Callers should
    only pass text files (binary content is mangled by text-mode decoding).
    """
    q = shlex.quote(remote_path)
    marker = "==VASP_AUTO_SPLIT=="
    script = f"wc -c < {q} 2>/dev/null || echo 0; echo {marker}; head -c {int(max_bytes)} {q} 2>/dev/null"
    try:
        res = remote_command(remote, script, timeout=45)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f"could not reach {remote.get('host')}: {exc}") from exc
    out = res.stdout
    if (marker + "\n") in out:
        head, text = out.split(marker + "\n", 1)
    elif marker in out:
        head, text = out.split(marker, 1)
    else:
        head, text = "", out
    try:
        size = int(head.strip().splitlines()[-1])
    except (ValueError, IndexError):
        size = len(text.encode("utf-8", "replace"))
    return {"text": text, "size": size, "truncated": size > max_bytes}
