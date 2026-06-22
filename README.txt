vasp_auto clean structure
=========================

Use from the project root:

    ./vasp_auto inputs/Fe --prepare

Use from the inputs directory:

    cd inputs
    ./vasp_auto Fe --prepare

Run a long calculation in the background:

    ./vasp_auto inputs/Fe -n 8 --background

or:

    ./vasp_auto inputs/Fe -n 8 --bg

The terminal returns immediately. vasp_auto prints the background process ID
and a log path like:

    vasp_auto_background_logs/vasp_auto_YYYYMMDD_HHMMSS.log

Follow the command output with:

    tail -f vasp_auto_background_logs/vasp_auto_YYYYMMDD_HHMMSS.log

The VASP stdout/stderr for each job is still written to that job's run.log.

Main folders:

    src/vasp_auto/
        Python source code for the command.

    inputs/
        Clean calculation inputs. A simple SCF case only needs POSCAR.
        Optional files: INCAR, KPOINTS, POTCAR. If INCAR, KPOINTS, or POTCAR
        are missing, prepare creates them here before making the job.

    inputs/<case>/
        One SCF case.

    inputs/<project>/<case>/
        One case inside a project folder.

    TSS/
        NEB/TSS examples. A TSS case can use initial/POSCAR and final/POSCAR.

    jobs/
        Calculation outputs when running from the project root. Single-case
        summaries are written inside the case folder, for example
        jobs/Fe/Fe.xlsx.

    inputs/jobs/
        Calculation outputs when running from inputs/. Single-case summaries
        are written inside the case folder, for example inputs/jobs/Fe/Fe.xlsx.

    POTCAR/
        POTCAR library. The command builds a combined input POTCAR from the
        elements listed in POSCAR, then copies it into the job.

    docs/
        Longer command and structure documentation.

    _archive/
        Old generated outputs and backup files moved out of the active input
        tree during cleanup.

Automatic SCF convergence
-------------------------

Run a sequence of static SCF calculations that first scans NELM, then scans
KPOINTS using the best NELM value:

    ./vasp_auto inputs/Fe --converge-scf -n 8

Optional controls:

    ./vasp_auto inputs/Fe --converge-scf \
        --nelm-values 40,60,80,100,120,160 \
        --kpoints-values 3,4,5,6,8,10 \
        --energy-tol 1e-4

For slab or low-dimensional systems, give explicit meshes:

    ./vasp_auto inputs/Fe --converge-scf --kpoints-values 3x3x1,5x5x1,7x7x1

Each trial is written under:

    jobs/<case>/scf_convergence/

The program writes:

    scf_convergence_report.md
    scf_convergence_steps.csv

ASE integration
---------------

The command can use ASE to create POSCAR-based cases before the normal
vasp_auto prepare/run flow.

ASE must be installed in the Python environment used by ./vasp_auto. In this
workspace that is normally venv/bin/python. If ASE is missing, the command
stops with an install message before writing any case.

Build a bulk crystal case:

    ./vasp_auto --ase-build-bulk Al --ase-crystalstructure fcc --ase-a 4.05 \
        --ase-output inputs/Al_ase --prepare

Useful bulk options:

    --ase-crystalstructure fcc|bcc|hcp|diamond|rocksalt|...
        Crystal structure name passed to ase.build.bulk.

    --ase-a VALUE
        Lattice constant a in Angstrom.

    --ase-c VALUE
        Lattice constant c in Angstrom, useful for structures such as hcp.

    --ase-cubic
        Ask ASE to build a cubic conventional cell when supported.

Convert any ASE-readable structure file, such as CIF or XYZ, to a case:

    ./vasp_auto --ase-import structure.cif --ase-output inputs/my_case --prepare

The generated case contains:

    inputs/my_case/POSCAR

After that, normal vasp_auto preparation can create missing INCAR, KPOINTS,
and POTCAR, then copy the complete input set into jobs/.

Optional import controls:

    --ase-format FORMAT
        Force the ASE input format, for example cif, xyz, or vasp.

    --ase-index INDEX
        Select one frame from a multi-frame file. The default is the last
        frame. Use values such as 0, 1, or -1.

Only write the POSCAR case and stop:

    ./vasp_auto --ase-import structure.cif --ase-output inputs/my_case --ase-only

 To open ASE GUI for a structure file:

  source venv/bin/activate
  ase gui inputs/Fe/POSCAR

  Or use the wrapper script in this repo:

  ./ase-gui inputs/Fe/POSCAR

This is useful when you want to inspect or edit POSCAR before preparing or
running VASP.

You can also build a bulk POSCAR only:

    ./vasp_auto --ase-build-bulk Si --ase-crystalstructure diamond \
        --ase-a 5.43 --ase-output inputs/Si_ase --ase-only

Use ASE for NEB interpolation when preparing TSS cases:

    ./vasp_auto TSS/cases/A --prepare --ase-neb --ase-neb-method idpp

For TSS/NEB, the input case should contain:

    TSS/cases/A/initial/POSCAR
    TSS/cases/A/final/POSCAR

vasp_auto writes image folders in the job directory:

    jobs/A/00/POSCAR
    jobs/A/01/POSCAR
    ...
    jobs/A/06/POSCAR

The default interpolation method is idpp. Use linear interpolation instead:

    ./vasp_auto TSS/cases/A --prepare --ase-neb --ase-neb-method linear

The number of intermediate images is controlled by --neb-images:

    ./vasp_auto TSS/cases/A --prepare --ase-neb --neb-images 7
