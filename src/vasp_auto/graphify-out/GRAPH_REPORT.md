# Graph Report - .  (2026-07-22)

## Corpus Check
- 31 files · ~58,742 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 752 nodes · 1594 edges · 29 communities (28 shown, 1 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 188 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Job Reports & Workflow
- CLI Argument Parsing
- ASE Structure Builders
- Job Directory Manager
- KPOINTS Generation
- INCAR Editing
- Output Parsing (VASP/QE)
- Chained Workflows & Convergence
- POSCAR Structure Tools
- Remote Job Polling
- AI Provider & NL Agent
- Catalysis Analysis
- Volumetric Files (CHGCAR)
- POSCAR Editing
- Remote Machine Setup
- NL Structure Builder
- Local MPI Runners
- Remote Engine Offload
- Detached Remote Jobs
- Calc Types & INCAR Catalog
- Remote Job Submission
- ASE Engine Backend
- Trajectory Extraction
- Config Loading
- Prototype & Materials Project
- py4vasp Analysis
- Remote Connection Checks
- Excel Export
- Cell Parameters

## God Nodes (most connected - your core abstractions)
1. `main()` - 31 edges
2. `_process_case()` - 27 edges
3. `_apply_structure_edits()` - 22 edges
4. `_run_builders()` - 20 edges
5. `build_job_log()` - 19 edges
6. `_ssh_target()` - 18 edges
7. `_ssh_options()` - 18 edges
8. `build_row()` - 17 edges
9. `run_one_case()` - 17 edges
10. `read_poscar()` - 16 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `filter_case_dirs()`  [INFERRED]
  cli.py → target_utils.py
- `read_job_energy()` --calls--> `parse_pw_output()`  [INFERRED]
  analysis.py → parser.py
- `read_job_energy()` --calls--> `parse_vasprun()`  [INFERRED]
  analysis.py → parser.py
- `surface_energy()` --calls--> `read_poscar()`  [INFERRED]
  analysis.py → structure.py
- `d_band_center()` --calls--> `parse_pdos()`  [INFERRED]
  analysis.py → parser.py

## Import Cycles
- None detected.

## Communities (29 total, 1 thin omitted)

### Community 0 - "Job Reports & Workflow"
Cohesion: 0.06
Nodes (73): Final energy and convergence flag of a finished job directory.      QE jobs (``., read_job_energy(), build_job_report(), _fmt(), _incar_details(), _kpoints_summary(), _neb_section(), Path (+65 more)

### Community 1 - "CLI Argument Parsing"
Cohesion: 0.05
Nodes (67): _apply_db_fetch(), _apply_db_prerelax(), _apply_ml_energy(), _apply_ml_relax(), _apply_remote_setup(), _builder_output_dir(), _bundle_qe_pseudos(), _bundle_tss_inputs() (+59 more)

### Community 2 - "ASE Structure Builders"
Cohesion: 0.07
Nodes (46): build_bulk_case(), build_crystal_case(), build_molecule_case(), build_nanotube_case(), build_slab_case(), import_structure_to_case(), interpolate_neb_with_ase(), molecule_positions() (+38 more)

### Community 3 - "Job Directory Manager"
Cohesion: 0.09
Nodes (44): _allocate_numbered_dir(), _apply_solvation(), _copy_neb_inputs(), _copy_optional_inputs(), _copy_or_build_potcar(), _copy_or_default(), _copy_scf_inputs(), create_job_from_case() (+36 more)

### Community 4 - "KPOINTS Generation"
Cohesion: 0.08
Nodes (45): auto_kpath(), _cross(), _dot(), guess_lattice_type(), kpoints_text_from_spec(), line_mode_text(), mesh_from_spacing(), mesh_kpoints_text() (+37 more)

### Community 5 - "INCAR Editing"
Cohesion: 0.10
Nodes (35): apply_incar_choices(), apply_spin_to_incar(), get_incar_value(), _is_comment_line(), magmom_line(), parse_magmom_map(), _poscar_composition(), Path (+27 more)

### Community 6 - "Output Parsing (VASP/QE)"
Cohesion: 0.09
Nodes (36): aggregate_pdos(), _band_edges(), _find_local(), _find_qe_save_xml(), _float_or_none(), _localname(), _max_force(), parse_bands() (+28 more)

### Community 7 - "Chained Workflows & Convergence"
Cohesion: 0.12
Nodes (31): _converge_kwargs(), _link_previous_outputs(), load_workflow_spec(), parse_workflow_steps(), Path, Chained workflows: relax → scf → dos in one command.  Each step runs in its own, Build converge_scf_case keyword arguments from a converge step dict., Normalise a workflow spec into a list of step dicts.      Accepts 'relax,scf,dos (+23 more)

### Community 8 - "POSCAR Structure Tools"
Cohesion: 0.12
Nodes (31): add_adsorbate(), cart_coords(), cell_parameters(), _cell_volume(), combine_structures(), _frac_coords(), _in_plane_params(), _invert3() (+23 more)

### Community 9 - "Remote Job Polling"
Cohesion: 0.10
Nodes (27): CompletedProcess, clear_remote_terminated(), delete_remote_dir(), kill_job_by_dir(), list_remote_cases(), list_remote_dir(), list_remote_jobs(), list_running_jobs() (+19 more)

### Community 10 - "AI Provider & NL Agent"
Cohesion: 0.11
Nodes (19): chat(), provider_catalog(), Provider registry for the AI builder's OpenAI-compatible chat API.  Both AI-buil, Public, UI-facing summary of the providers (no secrets)., Resolve a request to ``(url, api_key, model, supports_json_object)``.      ``bas, One OpenAI-compatible chat-completions POST, over plain ``urllib``., resolve(), agent_build_from_text() (+11 more)

### Community 11 - "Catalysis Analysis"
Cohesion: 0.12
Nodes (26): absorption_spectrum(), adsorption_energy(), _cross_area(), d_band_center(), _d_field_indices(), _fermi_from_outcar(), free_energy_diagram(), harmonic_thermochemistry() (+18 more)

### Community 12 - "Volumetric Files (CHGCAR)"
Cohesion: 0.13
Nodes (26): bader_net_charges(), cell_volume_of(), charge_difference(), charge_sum(), _check_same_grid(), lattice_of(), parse_acf(), planar_average() (+18 more)

### Community 13 - "POSCAR Editing"
Cohesion: 0.12
Nodes (24): _apply_structure_edits(), _parse_cell_spec(), Cell-resize spec: '1.02', '1.02,1.02,1.0', or absolute 'a=4.1,c=22.5' (Å)., Pure-Python POSCAR edits: supercell, vacancy, substitution, add-atom,     adsorb, add_interstitial(), _check_index(), coordination(), delete_atoms() (+16 more)

### Community 14 - "Remote Machine Setup"
Cohesion: 0.14
Nodes (23): Namespace, _clean_entry(), _collect_interactive(), ensure_local_key(), install_public_key(), main(), parse_args(), print_verification() (+15 more)

### Community 15 - "NL Structure Builder"
Cohesion: 0.13
Nodes (21): _ask_ai(), _build_base(), build_from_text(), _build_one(), describe_command(), _json_text(), _miller(), _normalize_command() (+13 more)

### Community 16 - "Local MPI Runners"
Cohesion: 0.14
Nodes (18): fetch_remote_file(), _last_oszicar_e0(), _local_core_counts(), _mpi_command(), Path, Build the mpirun command, picking the right flag when ranks exceed slots.      O, Run VASP locally via mpirun. on_progress(line) streams output lines., Last ionic step's E0 from an OSZICAR (matches the awk in list_remote_jobs). (+10 more)

### Community 17 - "Remote Engine Offload"
Cohesion: 0.19
Nodes (16): build_engine_wheel(), Install vasp_auto into a venv on the remote machine (one-time per machine)., True if the offload engine (vasp-auto) is present in the remote venv., Offload a full calculation to the remote engine and return immediately.      The, Run a command, raising RuntimeError with stderr context on failure., Resume an unfinished VASP job *in place* on a remote machine, detached.      The, Copy a single local file to remote_path (rsync if present, else scp)., Standard locations of the remote-installed engine and its run state. (+8 more)

### Community 18 - "Detached Remote Jobs"
Cohesion: 0.17
Nodes (16): detect_remote_run_mode(), fetch_remote_results(), kill_detached_job(), poll_detached_job(), Status of a detached offload job from its control dir (pid + rc files).      Ret, Terminate a detached offload job by its recorded PID over SSH.      Detached job, The real (numbered) job root a detached offload chose, or None if not yet known., Copy result files from the remote job directory back to the local one.      The (+8 more)

### Community 19 - "Calc Types & INCAR Catalog"
Cohesion: 0.19
Nodes (13): CalcType, parse_calc_type(), Canonical calculation types shared by the CLI and future GUI., demo(), fields_by_group(), fields_for(), IncarField, IncarOption (+5 more)

### Community 20 - "Remote Job Submission"
Cohesion: 0.15
Nodes (14): Write a scheduler submit script into the job directory.      The executable path, Submit a job via sbatch/qsub; returns {"job_id", "script", "submit_output"}., Copy a whole job directory to the remote host (rsync if present, else scp)., The shell snippet sourced before a remote run, per engine.      ``env_setup`` is, Canonical results directory on a remote machine: ``<remote_root>/results``., Run VASP (or QE pw.x, ``engine="qe"``) on a remote machine via ``mpirun`` over S, Send a fully prepared job to a remote machine and submit it to its queue.      E, _remote_env_setup() (+6 more)

### Community 21 - "ASE Engine Backend"
Cohesion: 0.26
Nodes (11): _ase_spec_from_config(), _check_calc_type(), create_ase_job(), parse_ase_output(), preview_ase_job(), Path, Generic ASE-calculator engine for vasp-auto.  This is the ``engine: ase`` backen, The settings the driver needs, distilled from config. (+3 more)

### Community 22 - "Trajectory Extraction"
Cohesion: 0.29
Nodes (11): _frac_to_cart(), job_trajectory(), _neb_image_dirs(), oszicar_energies(), _poscar_frame(), Path, Trajectory extraction for animations: XDATCAR (relax/MD) and NEB images.  Pure P, Animation frames for a job directory, in cartesian Å.      NEB jobs: one frame p (+3 more)

### Community 23 - "Config Loading"
Cohesion: 0.42
Nodes (10): default_config(), find_config_file(), load_config(), load_ui_remotes(), load_yaml_file(), merge_local_config(), _normalize_path(), Path (+2 more)

### Community 24 - "Prototype & Materials Project"
Cohesion: 0.25
Nodes (9): prototype_from_mp(), Fetch a crystal structure from Materials Project and return a structure dict., build_struct(), make_prototype(), Assemble a structure dict from per-atom data (lattice in Å, scale 1)., Build a prototype crystal (graphene, graphite, rutile-TiO2,     anatase-TiO2, hB, Replace all atoms of one element with another throughout the structure.      ``m, resolve_prototype() (+1 more)

### Community 25 - "py4vasp Analysis"
Cohesion: 0.33
Nodes (8): _calc(), dos(), Path, py4vasp-backed analysis of finished jobs (reads vaspout.h5).  Optional layer ove, A py4vasp Calculation for the job dir, or None when unavailable., Total DOS in the parse_dos payload shape: {efermi, energies, total}., Free energy (TOTEN) of every ionic step, for animation labels., step_energies()

### Community 26 - "Remote Connection Checks"
Cohesion: 0.25
Nodes (8): check_remote_connection(), Check SSH reachability plus remote_root / VASP / scheduler availability.      Re, How a remote machine runs jobs.      Returns ``"ssh"`` for direct ``mpirun`` ove, The VASP binary path on the remote machine.      If ``vasp_executable`` points a, The DFT binary path on the remote machine for the given engine., _remote_exe(), remote_run_mode(), _remote_vasp_exe()

### Community 27 - "Excel Export"
Cohesion: 0.60
Nodes (5): DataFrame, _add_energy_chart(), Bar chart of energy per case, anchored to the right of the table., _style_worksheet(), write_results_to_excel()

## Knowledge Gaps
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_process_case()` connect `CLI Argument Parsing` to `Job Reports & Workflow`, `Job Directory Manager`, `INCAR Editing`, `Chained Workflows & Convergence`, `Config Loading`?**
  _High betweenness centrality (0.186) - this node is a cross-community bridge._
- **Why does `read_poscar()` connect `POSCAR Editing` to `CLI Argument Parsing`, `KPOINTS Generation`, `INCAR Editing`, `POSCAR Structure Tools`, `AI Provider & NL Agent`, `Catalysis Analysis`, `Volumetric Files (CHGCAR)`, `NL Structure Builder`, `Trajectory Extraction`?**
  _High betweenness centrality (0.150) - this node is a cross-community bridge._
- **Why does `main()` connect `CLI Argument Parsing` to `Job Directory Manager`, `ASE Structure Builders`, `Calc Types & INCAR Catalog`, `Config Loading`?**
  _High betweenness centrality (0.102) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `main()` (e.g. with `parse_calc_type()` and `load_config()`) actually correct?**
  _`main()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `_process_case()` (e.g. with `load_workflow_spec()` and `run_workflow_case()`) actually correct?**
  _`_process_case()` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Should `Job Reports & Workflow` be split into smaller, more focused modules?**
  _Cohesion score 0.06054054054054054 - nodes in this community are weakly interconnected._
- **Should `CLI Argument Parsing` be split into smaller, more focused modules?**
  _Cohesion score 0.053994732221246705 - nodes in this community are weakly interconnected._