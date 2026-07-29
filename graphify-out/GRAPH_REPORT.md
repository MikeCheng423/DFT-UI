# Graph Report - .  (2026-07-22)

## Corpus Check
- 110 files · ~161,028 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1774 nodes · 4042 edges · 99 communities (81 shown, 18 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 198 edges (avg confidence: 0.68)
- Token cost: 251,055 input · 0 output

## Community Hubs (Navigation)
- Trajectory & Animation Extraction
- Engine Features & Capabilities (docs)
- Remote Offload Runner
- CLI Command Dispatch
- POSCAR Structure Editing
- Case Processing & Job Rows
- Design Decisions & Rationale
- Calc Types & INCAR Catalog
- Scheduler Submission & Polling
- AI / NL Structure Builder
- Web UI Case & Run Endpoints
- ASE Structure Builders
- QE/VASP Output Parsers
- Job Files & Results Endpoints
- Crystal Builder & PDOS
- ML Pre-relax & DB Fetch
- NEB Energy Profile
- Web Server & Provider Catalog
- Detached Offload Flag Forwarding
- Job Submission & Convergence Checks
- UI Server Tests
- PDOS/Bands Aggregation & Supercell Match
- Catalysis Analysis (adsorption/d-band)
- Chained Workflows
- Job Log Builder
- Job Manager (dir allocation)
- Remote Job Submission (QE/detached)
- Catalysis Analysis Tests
- Remote Directory & Job Control
- Remote Setup (SSH keys)
- SIGMA/Magmom & Solvation
- Structure Editor Endpoints
- Optics/XRD & Analysis Endpoints
- Adsorbate & Structure Geometry
- INCAR Editing Helpers
- Case Info & INCAR Templates
- Quantum ESPRESSO Engine
- Structure Combine & Supercell
- QE Engine Tests
- Job Report Builder
- VASP Error Fix Application
- KPOINTS/K-path Tests
- Config Loader
- POTCAR Finder
- CHGCAR / Bader Charge
- File Endpoint Tests
- ASE Engine Driver
- KPOINTS Generation
- Convergence Trial Selection
- MPI Command Building
- Restart File Handling
- VASP Error Scanning
- ML/Bader UI Endpoints
- Volumetric Planar Average
- Remote Connection Checks
- Prototype Crystal Builder
- Target Inspection Utils
- XML Parse Error Handling
- NL Agent Smoketest
- Generic ASE Engine
- SCF Convergence Runner
- KPOINTS Text / K-path Spec
- Remote Job Listing
- Remote Machine UI Endpoints
- Remote Job Fetch/Kill
- Excel Results Writer
- py4vasp Analysis Layer
- Self-check Script
- Resume MPI Rank Reuse
- NEB Rank Clamping
- Preview Endpoints
- Remote Files/Jobs Endpoints
- Remote Analysis Tests
- Surface Energy
- QE pw.out Parser
- Detached Job Dir Resolution
- Mesh Parsing
- Cell Parameters
- Remote Run Mode Detection
- Detached Job Polling
- Bader charges
- mpirun
- sbatch
- vasp_std
- _energy_job()
- Run an existing folder' against a machin
- With a remote working machine, saving wr
- With a remote working machine, combine r
- The Remote tab can add, list and delete
- A non-numeric default core count is igno
- Regression: a case under a cases folder
- Pointing Results at the jobs folder list
- Pointing Results at one job directory re
- /api/neb returns the reaction-coordinate
- /api/remote/jobs lists jobs on a machine
- /api/job/files lists a local job dir's f
- A remote filetext request reads over SSH
- vasp-auto

## God Nodes (most connected - your core abstractions)
1. `read_poscar()` - 51 edges
2. `make_case_info()` - 41 edges
3. `main()` - 31 edges
4. `create_job_from_case()` - 31 edges
5. `api_build()` - 29 edges
6. `build_row()` - 28 edges
7. `_get()` - 28 edges
8. `_process_case()` - 27 edges
9. `preview_job_from_case()` - 25 edges
10. `per_atom_symbols()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `test_cli_chg_diff()` --calls--> `read_volumetric()`  [INFERRED]
  tests/test_analysis.py → src/vasp_auto/chgcar.py
- `test_read_volumetric_spin_block()` --calls--> `read_volumetric()`  [INFERRED]
  tests/test_analysis.py → src/vasp_auto/chgcar.py
- `_analysis_dir Remote-capture Mechanism` --semantically_similar_to--> `Shared Machine List (config_loader.load_ui_remotes)`  [INFERRED] [semantically similar]
  src/Analysis_Func.md → memo.md
- `test_every_calc_type_has_chain_inputs()` --indirect_call--> `CalcType`  [INFERRED]
  tests/test_calc_types.py → src/vasp_auto/calc_types.py
- `test_every_calc_type_has_a_description()` --indirect_call--> `CalcType`  [INFERRED]
  tests/test_pass3_features.py → src/vasp_auto/calc_types.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **converge to relax to scf to dos pipeline** — docs_manual_convergence_scan, docs_manual_workflow_chaining, docs_manual_calc_types [INFERRED 0.75]
- **catalysis adsorption-to-free-energy workflow** — docs_tutorial_catalysis_adsorption_energy, docs_tutorial_catalysis_che, docs_manual_structure_building [INFERRED 0.75]
- **control-vs-remote two-machine architecture** — docs_install_two_machine_model, docs_install_extras_matrix, docs_install_lean_engine, docs_manual_offload_mode [INFERRED 0.75]
- **Remote Execution and Job Lifecycle (run modes, control, liveness, capture)** — src_docs_claude_execution_model, src_docs_claude_three_run_modes, src_docs_claude_job_control, src_docs_claude_job_liveness_status, src_analysis_func_analysis_dir [INFERRED 0.85]
- **Workflow-builder GUI Layer over the CLI Engine** — src_vasp_auto_ui_static_index_web_studio, src_vasp_auto_ui_static_index_seven_tabs, src_docs_claude_workflow_builder_gui, src_plan_incar_builder [INFERRED 0.75]
- **relax->scf->dos Chaining Pattern across templates, self-check, and docs** — example_readme_typical_workflow_order, selfcheck_workflow_case_workflow_relax_scf_dos_chain, src_docs_vasp_auto_capabilities_chained_workflows [INFERRED 0.75]

## Communities (99 total, 18 thin omitted)

### Community 0 - "Trajectory & Animation Extraction"
Cohesion: 0.05
Nodes (36): _frac_to_cart(), job_trajectory(), _neb_image_dirs(), oszicar_energies(), _poscar_frame(), Path, Trajectory extraction for animations: XDATCAR (relax/MD) and NEB images.  Pure P, Animation frames for a job directory, in cartesian Å.      NEB jobs: one frame p (+28 more)

### Community 1 - "Engine Features & Capabilities (docs)"
Cohesion: 0.08
Nodes (52): CI tests workflow (pytest + selfcheck), pip extras matrix, Lean remote engine, Two-machine model (control vs remote), Generic ASE-calculator engine (engine: ase), Automatic error recovery (--auto-retry), Calculation types / INCAR templates, Combine two structures (deposition/heterostructure) (+44 more)

### Community 2 - "Remote Offload Runner"
Cohesion: 0.09
Nodes (50): build_engine_wheel(), fetch_remote_results(), kill_detached_job(), _last_oszicar_e0(), _local_core_counts(), _mpi_command(), Path, Install vasp_auto into a venv on the remote machine (one-time per machine). (+42 more)

### Community 3 - "CLI Command Dispatch"
Cohesion: 0.08
Nodes (46): _apply_db_fetch(), _apply_db_prerelax(), _apply_ml_energy(), _apply_ml_relax(), _apply_remote_setup(), _builder_output_dir(), _bundle_qe_pseudos(), _bundle_tss_inputs() (+38 more)

### Community 4 - "POSCAR Structure Editing"
Cohesion: 0.06
Nodes (40): _apply_structure_edits(), _parse_adsorbate_spec(), _parse_cell_spec(), _parse_freeze_spec(), _parse_move_spec(), Cell-resize spec: '1.02', '1.02,1.02,1.0', or absolute 'a=4.1,c=22.5' (Å)., 5@x,y,z' places atom 5 (absolute); '5+dx,dy,dz' translates it., O@12+2.0' = element O above atom 12 at 2.0 Å (height defaults to 2.0). (+32 more)

### Community 5 - "Case Processing & Job Rows"
Cohesion: 0.10
Nodes (44): _print_preview(), _process_case(), Handle one case end to end; returns (case_info, rows)., _local_job_rows(), Local mirror of list_remote_jobs: job dirs under ``root`` (up to two     levels), _apply_remote_marker(), _build_ase_row(), _build_neb_row() (+36 more)

### Community 6 - "Design Decisions & Rationale"
Cohesion: 0.05
Nodes (43): INCAR Template Set (optimize/scf/charge_density/dos), Typical VASP Workflow Order (relax to scf to charge to dos), Detached-run Collapse Diagnosis (WSL2 host suspend/logoff), KeepWSL2Alive Keepalive Task, Per-machine POTCAR Libraries (tlclab / apl2 potcar_root), Build POTCAR on the Remote, Smoother First Run (example/Si + vasp-auto --init), Resume Unfinished Job In Place (CONTCAR to POSCAR, warm WAVECAR/CHGCAR) (+35 more)

### Community 7 - "Calc Types & INCAR Catalog"
Cohesion: 0.08
Nodes (24): BaseHTTPRequestHandler, CalcType, parse_calc_type(), Canonical calculation types shared by the CLI and future GUI., demo(), fields_by_group(), fields_for(), IncarField (+16 more)

### Community 8 - "Scheduler Submission & Polling"
Cohesion: 0.07
Nodes (38): fetch_remote_file(), poll_job_status(), Query a scheduler for the status of a submitted job.      Returns a dict with ke, Copy one file off the remote machine (for a UI download). Returns the path., Write a scheduler submit script into the job directory.      The executable path, write_submit_script(), _fake_run_pbs_not_found(), _fake_run_pbs_queued() (+30 more)

### Community 9 - "AI / NL Structure Builder"
Cohesion: 0.09
Nodes (31): chat(), Provider registry for the AI builder's OpenAI-compatible chat API.  Both AI-buil, Resolve a request to ``(url, api_key, model, supports_json_object)``.      ``bas, One OpenAI-compatible chat-completions POST, over plain ``urllib``., resolve(), _ai_chat(), Agentic natural-language structure builder ("the worker").  Where :mod:`nl_build, One OpenAI-compatible chat-completions call (with tools) to ``url``. (+23 more)

### Community 10 - "Web UI Case & Run Endpoints"
Cohesion: 0.09
Nodes (36): _analysis_dir(), api_cases(), api_job_delete(), api_report(), api_resume(), api_resume_job(), api_run(), api_structure_save() (+28 more)

### Community 11 - "ASE Structure Builders"
Cohesion: 0.10
Nodes (33): build_bulk_case(), build_molecule_case(), build_nanotube_case(), build_slab_case(), import_structure_to_case(), interpolate_neb_with_ase(), Path, Build an isolated molecule centred in a cubic box. (+25 more)

### Community 12 - "QE/VASP Output Parsers"
Cohesion: 0.10
Nodes (33): _band_edges(), _find_local(), _find_qe_save_xml(), _float_or_none(), _localname(), _max_force(), parse_dielectric(), parse_dos() (+25 more)

### Community 13 - "Job Files & Results Endpoints"
Cohesion: 0.08
Nodes (34): api_db_fetch(), api_db_prototype(), api_filetext(), api_job_files(), api_results(), _first_existing_excel(), _is_convergence_job(), _is_neb_job() (+26 more)

### Community 14 - "Crystal Builder & PDOS"
Cohesion: 0.11
Nodes (28): build_crystal_case(), Build a crystal from a space group + Wyckoff basis (ASE).      ``symbols`` is on, add_interstitial(), per_atom_symbols(), Path, Replace the element of atom `index` (1-based, POSCAR order)., Insert an `element` atom at `position` (in the structure's own     coordinate mo, read_poscar() (+20 more)

### Community 15 - "ML Pre-relax & DB Fetch"
Cohesion: 0.09
Nodes (28): _fetch_from_umat(), fetch_structure_from_db(), get_ml_calculator(), ml_energy(), ml_energy_from_db(), ml_relax_case(), ml_relax_from_db(), Path (+20 more)

### Community 16 - "NEB Energy Profile"
Cohesion: 0.09
Nodes (30): neb_energy_profile(), _neb_image_energy(), Try OUTCAR, then OSZICAR (last F= token), then vasprun.xml for an image energy., Energy profile along an NEB/TSS path — the reaction-coordinate ("energy     stag, _make_neb_job(), _no(), NEB 00–04 with OUTCARs only in interior 01-03 → converged, don't retry., NEB 00–04 with missing OUTCAR in one interior image → should retry. (+22 more)

### Community 17 - "Web Server & Provider Catalog"
Cohesion: 0.09
Nodes (29): provider_catalog(), Public, UI-facing summary of the providers (no secrets)., api_cache_clear(), api_cache_size(), api_databases(), api_job(), api_jobs(), api_meta() (+21 more)

### Community 18 - "Detached Offload Flag Forwarding"
Cohesion: 0.11
Nodes (27): _forward_calc_flags(), parse_args(), Reconstruct the calc-shaping CLI flags to forward to a remote offload run., Offload a full calculation to the remote engine (run_mode: ssh_detached).      P, _run_detached_offload(), _args(), Tests for the detached-offload flag forwarding (no SSH)., A TSS/NEB case offloads its initial/final endpoints + a pre-built POTCAR so (+19 more)

### Community 19 - "Job Submission & Convergence Checks"
Cohesion: 0.09
Nodes (22): Submit a job via sbatch/qsub; returns {"job_id", "script", "submit_output"}., Run mode for dispatch, auto-detecting when the machine pins nothing.      An exp, resolve_remote_run_mode(), submit_job(), geometry_converged(), Return True when the geometry appears to have reached its minimum.      Checks (, Print diagnostics for known VASP errors; return a summary string for Excel., report_vasp_errors() (+14 more)

### Community 20 - "UI Server Tests"
Cohesion: 0.11
Nodes (18): _get(), test_bands_endpoint(), test_browse_endpoint(), test_cases_listing(), test_dband_endpoint(), test_dband_endpoint_needs_selection(), test_meta_lists_calc_types(), test_neb_endpoint_missing() (+10 more)

### Community 21 - "PDOS/Bands Aggregation & Supercell Match"
Cohesion: 0.11
Nodes (27): aggregate_pdos(), parse_bands(), Sum a parse_pdos result into per-element, per-shell (s/p/d/f) curves.      `symb, High-symmetry labels from a line-mode KPOINTS file.      Returns [{"index", "lab, Band structure from vasprun.xml (typically a line-mode 'bands' run).      Return, read_kpoints_labels(), match_supercells(), Suggest in-plane supercell pairs that bring two different unit cells     into re (+19 more)

### Community 22 - "Catalysis Analysis (adsorption/d-band)"
Cohesion: 0.12
Nodes (26): adsorption_energy(), _cross_area(), d_band_center(), _d_field_indices(), _fermi_from_outcar(), free_energy_diagram(), harmonic_thermochemistry(), parse_frequencies() (+18 more)

### Community 23 - "Chained Workflows"
Cohesion: 0.14
Nodes (25): _converge_kwargs(), _link_previous_outputs(), load_workflow_spec(), parse_workflow_steps(), Path, Chained workflows: relax → scf → dos in one command.  Each step runs in its own, Build converge_scf_case keyword arguments from a converge step dict., Normalise a workflow spec into a list of step dicts.      Accepts 'relax,scf,dos (+17 more)

### Community 24 - "Job Log Builder"
Cohesion: 0.14
Nodes (23): build_job_log(), _cell_block(), _duration(), _fmt(), _formula(), _functional(), _neb_image_energies(), _oszicar_energies() (+15 more)

### Community 25 - "Job Manager (dir allocation)"
Cohesion: 0.16
Nodes (25): _allocate_numbered_dir(), _apply_solvation(), _copy_neb_inputs(), _copy_optional_inputs(), _copy_or_build_potcar(), _copy_or_default(), _copy_scf_inputs(), _interpolate_coords() (+17 more)

### Community 26 - "Remote Job Submission (QE/detached)"
Cohesion: 0.11
Nodes (26): Send a fully prepared job to a remote machine and submit it to its queue.      E, submit_job_remote(), fake_run(), A QE offload writes qe_executable (+ the machine's pseudo_dir) into the     remo, engine="qe" runs pw.x with -in pw.in and keeps pw.out + run.log., QE never sources the machine's VASP env_setup (an Intel MPI environment     sile, Scheduler submission writes the QE submit template; vasp_executable not needed., test_qe_remote_run_skips_vasp_env_setup() (+18 more)

### Community 27 - "Catalysis Analysis Tests"
Cohesion: 0.10
Nodes (10): _make_job(), _make_job_with_poscar(), Tests for analysis.py: adsorption energy, thermochemistry, d-band, work function, test_adsorption_energy(), test_adsorption_energy_missing_job(), test_cli_adsorption_energy(), test_cli_chg_diff(), test_free_energy_diagram_from_freq_and_ads() (+2 more)

### Community 28 - "Remote Directory & Job Control"
Cohesion: 0.08
Nodes (24): CompletedProcess, clear_remote_terminated(), delete_remote_dir(), kill_job_by_dir(), list_remote_cases(), list_remote_dir(), _parse_poll_output(), poll_remote_job() (+16 more)

### Community 29 - "Remote Setup (SSH keys)"
Cohesion: 0.14
Nodes (23): Namespace, _clean_entry(), _collect_interactive(), ensure_local_key(), install_public_key(), main(), parse_args(), print_verification() (+15 more)

### Community 30 - "SIGMA/Magmom & Solvation"
Cohesion: 0.10
Nodes (21): Pick the largest SIGMA whose entropy term T*S stays below tolerance.      The st, _select_sigma_trial(), parse_magmom_map(), Parse 'Fe:5.0,O:0.6' into {element: moment}., Tests for the 2026-06-12 build-out: spin, magmoms, auto-retry, SIGMA scan, inter, --solvation injects LSOL and EB_K into the INCAR., --solvation-eps overrides the default dielectric constant., Without --solvation, LSOL must not appear in the INCAR. (+13 more)

### Community 31 - "Structure Editor Endpoints"
Cohesion: 0.09
Nodes (24): api_combine(), api_file_get(), api_file_save(), api_match(), api_nl_agent(), api_nl_build(), api_structure(), _editable() (+16 more)

### Community 32 - "Optics/XRD & Analysis Endpoints"
Cohesion: 0.09
Nodes (23): absorption_spectrum(), Optical absorption coefficient α(E) in cm⁻¹ from a LOPTICS run.      α = 2 E k /, Simulated powder XRD pattern of a structure (Bragg-Brentano, pymatgen).      ``p, xrd_pattern(), _analysis_query_dir(), api_bands(), api_dband(), api_dos() (+15 more)

### Community 33 - "Adsorbate & Structure Geometry"
Cohesion: 0.16
Nodes (22): molecule_positions(), Cartesian geometry (Å) of an adsorbate. ``name`` is an ASE molecule     (CO2, H2, add_adsorbate(), cart_coords(), _cell_volume(), _check_index(), coordination(), _frac_coords() (+14 more)

### Community 34 - "INCAR Editing Helpers"
Cohesion: 0.15
Nodes (21): apply_incar_choices(), apply_spin_to_incar(), get_incar_value(), _is_comment_line(), magmom_line(), _poscar_composition(), Path, INCAR editing helpers shared by job preparation, chains, and convergence.  Pure (+13 more)

### Community 35 - "Case Info & INCAR Templates"
Cohesion: 0.14
Nodes (21): load_incar_template(), make_case_info(), Build the case/job descriptor.      ``job_mode`` controls how the job directory, Return the INCAR text for a calculation type.      Looks for example/INCAR_<type, api_template(), test_create_job_from_case_does_not_touch_case_dir(), test_create_job_from_case_scf(), test_create_job_from_case_tss_interpolates_images() (+13 more)

### Community 36 - "Quantum ESPRESSO Engine"
Cohesion: 0.17
Nodes (21): build_pw_input(), _copy_pseudos(), create_qe_job(), find_pseudo(), _fmt(), _kpoints_card(), preview_qe_job(), pseudo_files_for_struct() (+13 more)

### Community 37 - "Structure Combine & Supercell"
Cohesion: 0.16
Nodes (21): build_struct(), combine_structures(), make_supercell(), Wrap all atoms back into the [0,1) cell (fractional output)., Assemble a structure dict from per-atom data (lattice in Å, scale 1)., Merge two structures with different unit cells into one host cell.      mode="st, wrap_to_cell(), _rocksalt() (+13 more)

### Community 38 - "QE Engine Tests"
Cohesion: 0.13
Nodes (16): preview_job_from_case(), Build the full input set as a dict without writing any job files.      Used by -, test_preview_job_from_case(), _qe_dos_job(), Tests for the Quantum ESPRESSO (pw.x) engine path., test_bands_kpath_crystal_b(), test_bands_needs_kpath(), test_build_pw_input_namelists() (+8 more)

### Community 39 - "Job Report Builder"
Cohesion: 0.16
Nodes (20): build_job_report(), _fmt(), _incar_details(), _kpoints_summary(), _neb_section(), Path, Per-job calculation reports: a short Markdown summary of setup + results.  `vasp, Write report.md into the job directory; returns its path. (+12 more)

### Community 40 - "VASP Error Fix Application"
Cohesion: 0.18
Nodes (11): apply_error_fixes(), Apply the known fix for each finding; returns action strings.      For errors in, When CONTCAR != POSCAR and non-empty, apply_error_fixes copies CONTCAR., apply_error_fixes must include the restart action string in its return., IBRION INCAR fix is still applied alongside the CONTCAR restart., apply_error_fixes must NOT copy an empty CONTCAR., apply_error_fixes must NOT fail or copy when CONTCAR doesn't exist., apply_error_fixes must NOT copy CONTCAR when it is identical to POSCAR. (+3 more)

### Community 41 - "KPOINTS/K-path Tests"
Cohesion: 0.12
Nodes (20): _bcc_primitive_lattice(), _cubic_lattice(), _fcc_primitive_lattice(), _generic_lattice(), _hex_lattice(), Triclinic — no high-symmetry angles., POSCAR with a cubic cell → auto_kpath returns the cubic preset., Generic triclinic cell → auto_kpath raises ValueError. (+12 more)

### Community 42 - "Config Loader"
Cohesion: 0.21
Nodes (18): default_config(), find_config_file(), load_config(), load_ui_remotes(), load_yaml_file(), merge_local_config(), _normalize_path(), Path (+10 more)

### Community 43 - "POTCAR Finder"
Cohesion: 0.19
Nodes (18): build_potcar(), candidate_potcar_roots(), clean_species_symbol(), find_potcar_root(), get_elements_from_poscar(), map_potcar_dirs(), Path, Strip VASP/CONTCAR decoration from a species token, keeping El[_variant]. (+10 more)

### Community 44 - "CHGCAR / Bader Charge"
Cohesion: 0.21
Nodes (18): bader_net_charges(), charge_difference(), charge_sum(), _check_same_grid(), parse_acf(), Path, Volumetric VASP files (CHGCAR/LOCPOT/AECCAR): read, write, combine.  Pure Python, Write Δρ = ρ(total) − Σ ρ(parts), e.g. slab+adsorbate − slab − molecule.      Al (+10 more)

### Community 45 - "File Endpoint Tests"
Cohesion: 0.11
Nodes (19): _post(), /api/filetext returns the text of a local file for the in-browser viewer., POTCAR content is proprietary and must not be shown in the viewer., test_bader_endpoint_without_binary(), test_build_edit_supercell(), test_chgdiff_endpoint(), test_combine_accepts_inline_host(), test_combine_endpoint_stack() (+11 more)

### Community 46 - "ASE Engine Driver"
Cohesion: 0.16
Nodes (17): create_job_from_case(), Run the ASE engine driver (run_ase.py) locally as a subprocess.      The driver, run_ase(), ase_case(), Tests for the generic ASE-calculator engine (engine: ase).  EMT needs no externa, test_build_row_from_ase_results(), test_create_writes_driver_and_marker(), test_custom_calculator_params_carried() (+9 more)

### Community 47 - "KPOINTS Generation"
Cohesion: 0.21
Nodes (17): auto_kpath(), _cross(), _dot(), guess_lattice_type(), mesh_from_spacing(), _norm(), Path, KPOINTS generation: uniform meshes, density-based meshes, line-mode paths. (+9 more)

### Community 48 - "Convergence Trial Selection"
Cohesion: 0.19
Nodes (15): parse_kpoint_meshes(), parse_nelm_values(), Pick the cheapest setting whose energy stopped changing.      Returns the first, _select_converged_trial(), test_parse_encut_values(), test_parse_kpoint_meshes_rejects_pairs(), test_parse_kpoint_meshes_scalar_and_triplet(), test_parse_nelm_values_custom() (+7 more)

### Community 49 - "MPI Command Building"
Cohesion: 0.12
Nodes (16): _cores(), Pin the detected (physical, logical) core counts for a test., Ranks <= physical cores: a plain mpirun command, no warning, no flags., Ranks past physical cores but within threads -> --use-hwthread-cpus.      This i, Ranks beyond even the hardware threads -> --oversubscribe and warns., VASP_AUTO_OVERSUBSCRIBE=0 adds no flag even when over-committed, but warns., VASP_AUTO_OVERSUBSCRIBE=1 adds --oversubscribe even when ranks fit., Extra executable args (QE's -in pw.in) are appended after the exe. (+8 more)

### Community 50 - "Restart File Handling"
Cohesion: 0.16
Nodes (14): Move restart outputs aside before the job directory is cleaned., Seed the cleaned job: CONTCAR becomes POSCAR; WAVECAR/CHGCAR return as-is., _restore_restart_files(), _stash_restart_files(), set_incar_value(), Regression tests for the 2026-06-12 bug-hunt (v0.5.0).  Bug 1: negative-scale PO, test_get_incar_value_finds_tag_inside_compound_line(), test_read_poscar_negative_scale_resolves_to_volume() (+6 more)

### Community 51 - "VASP Error Scanning"
Cohesion: 0.17
Nodes (10): Scan run.log and OUTCAR for known VASP error signatures.      Returns a list of, scan_vasp_errors(), A log with ZBRENT AND the SICK_JOB banner must yield only ZBRENT., A log with EDDDAV AND the SICK_JOB banner must yield only EDDDAV., When SICK_JOB is the ONLY signal, it must still be returned., A clean convergence line must produce no findings., SICK_JOB hint must mention INCAR/POSCAR., TestSickJobFallback (+2 more)

### Community 52 - "ML/Bader UI Endpoints"
Cohesion: 0.14
Nodes (14): api_bader(), api_browse(), api_db_mlenergy(), api_db_mlrelax(), api_mlenergy(), api_mlrelax(), _config(), _downloadable() (+6 more)

### Community 53 - "Volumetric Planar Average"
Cohesion: 0.17
Nodes (13): cell_volume_of(), lattice_of(), planar_average(), Average the grid over the two perpendicular directions, plane by plane.      Ret, The scaled lattice (Å) from a volumetric file's POSCAR header., Cell volume in Å³ — divides CHGCAR-family grids (rho·V) into e/Å³., One grid plane perpendicular to `axis` at fractional position `fraction`.      R, slice_volume() (+5 more)

### Community 54 - "Remote Connection Checks"
Cohesion: 0.15
Nodes (13): check_remote_connection(), Check SSH reachability plus remote_root / VASP / scheduler availability.      Re, How a remote machine runs jobs.      Returns ``"ssh"`` for direct ``mpirun`` ove, The VASP binary path on the remote machine.      If ``vasp_executable`` points a, The DFT binary path on the remote machine for the given engine., _remote_exe(), remote_run_mode(), _remote_vasp_exe() (+5 more)

### Community 55 - "Prototype Crystal Builder"
Cohesion: 0.23
Nodes (13): cell_parameters(), _in_plane_params(), make_prototype(), The lattice in Å with the universal scale factor applied., a, b, c (Å) and alpha, beta, gamma (degrees) of a lattice matrix., Build a prototype crystal (graphene, graphite, rutile-TiO2,     anatase-TiO2, hB, |a|, |b| (Å) and gamma (degrees) of the in-plane lattice vectors., scaled_lattice() (+5 more)

### Community 56 - "Target Inspection Utils"
Cohesion: 0.28
Nodes (11): filter_case_dirs(), get_case_type(), inspect_target(), test_filter_case_dirs(), test_get_case_type_ignores_poscar_named_subdir(), test_get_case_type_scf(), test_get_case_type_tss(), test_get_case_type_unknown() (+3 more)

### Community 57 - "XML Parse Error Handling"
Cohesion: 0.15
Nodes (7): Tests for the four error-handling defects fixed in workflow.py / parser.py.  Def, parse_vasprun must return None (not raise) on truncated/malformed XML., parse_vasprun must return None when file does not exist., build_row must not raise when vasprun.xml is truncated; falls back to OUTCAR., build_row must not raise when vasprun.xml is completely empty., build_row must not raise on completely invalid XML., TestTruncatedVasprun

### Community 58 - "NL Agent Smoketest"
Cohesion: 0.24
Nodes (6): main(), run(), agent_build_from_text(), Holds the named structures the model builds and dispatches tool calls.      Tool, Run the tool-calling worker on free text.      Returns ``(struct, transcript)``, _Workspace

### Community 59 - "Generic ASE Engine"
Cohesion: 0.26
Nodes (11): _ase_spec_from_config(), _check_calc_type(), create_ase_job(), parse_ase_output(), preview_ase_job(), Path, Generic ASE-calculator engine for vasp-auto.  This is the ``engine: ase`` backen, The settings the driver needs, distilled from config. (+3 more)

### Community 60 - "SCF Convergence Runner"
Cohesion: 0.38
Nodes (11): converge_scf_case(), _copy_clean_inputs(), _energy_improvement(), _natoms_from_poscar(), Path, Run trials for one stage, stopping once |ΔE| <= tolerance (when stop_on_tol)., _run_trial(), _scan_stage() (+3 more)

### Community 61 - "KPOINTS Text / K-path Spec"
Cohesion: 0.17
Nodes (12): kpoints_text_from_spec(), line_mode_text(), parse_kpath(), Parse a preset name ('fcc') or 'G 0 0 0; X 0.5 0 0.5; ...' into points., Build KPOINTS text from a spec dict.      spec keys: mode (gamma|mp|line|spacing, kpoints_text_from_spec with kpath='auto' triggers auto-detection., test_kpoints_text_from_spec_auto_kpath(), test_kpoints_text_from_spec_line_requires_kpath() (+4 more)

### Community 62 - "Remote Job Listing"
Cohesion: 0.18
Nodes (11): list_remote_jobs(), list_running_jobs(), List VASP job directories that live on a remote machine, newest first.      Walk, Jobs across the local machine and every configured remote, newest first.      "r, list_remote_jobs parses the TSV the remote script prints, newest first., Aggregates local running job dirs + remotes; a down machine → errors., An SSH failure on one machine is captured, not raised., test_list_remote_jobs_parses_and_sorts() (+3 more)

### Community 63 - "Remote Machine UI Endpoints"
Cohesion: 0.20
Nodes (10): _all_remotes(), api_remote_setup(), api_remote_test(), api_remotes(), All known remote machines: config.yaml (read-only) + UI store (writable)., A remote config from explicit form fields, or by name from the store., List configured remote machines (newest editable ones from the UI store)., Verify SSH + remote_root/VASP/scheduler — the Test connection button. (+2 more)

### Community 64 - "Remote Job Fetch/Kill"
Cohesion: 0.22
Nodes (10): api_kill_remote(), api_remote_fetch(), api_remote_status(), Stop a running detached (offload) job on its remote machine, via its     local m, Find the saved machine (with credentials) a job was submitted to., The real job root on the remote, resolved from a detached offload's control dir., Poll the remote for a submitted job's state (scheduler or detached offload)., Pull result files back from the remote job dir so local viewers work. (+2 more)

### Community 65 - "Excel Results Writer"
Cohesion: 0.39
Nodes (7): DataFrame, _add_energy_chart(), Bar chart of energy per case, anchored to the right of the table., _style_worksheet(), write_results_to_excel(), test_write_results_to_excel_empty(), test_write_results_to_excel_styles_converged()

### Community 66 - "py4vasp Analysis Layer"
Cohesion: 0.33
Nodes (8): _calc(), dos(), Path, py4vasp-backed analysis of finished jobs (reads vaspout.h5).  Optional layer ove, A py4vasp Calculation for the job dir, or None when unavailable., Total DOS in the parse_dos payload shape: {efermi, energies, total}., Free energy (TOTEN) of every ionic step, for animation labels., step_energies()

### Community 67 - "Self-check Script"
Cohesion: 0.54
Nodes (7): check(), exists(), note(), okcmd(), PATH, run(), run_selfcheck.sh script

### Community 68 - "Resume MPI Rank Reuse"
Cohesion: 0.36
Nodes (7): _previous_run_ranks(), MPI rank count the previous run in ``job_dir`` used, read from the header     VA, Resume reuses the previous run's MPI rank count, read from OUTCAR., test_neb_image_outcar(), test_no_outcar_means_unknown(), test_vasp5_header(), test_vasp6_header()

### Community 69 - "NEB Rank Clamping"
Cohesion: 0.32
Nodes (7): _ranks_for_images(), Clamp an MPI rank count to what a NEB job can actually use.      VASP requires t, Resume must clamp MPI ranks to a multiple of IMAGES for NEB jobs.  Regression fo, _sh_ranks(), test_neb_ranks_shell_snippet(), test_ranks_for_images(), test_ranks_without_images_tag()

### Community 70 - "Preview Endpoints"
Cohesion: 0.29
Nodes (7): api_preview(), _case_info_for(), _local_case(), _overlay_ase_config(), _preview_for_target(), Yield a local case dir for `target`. For a case that lives on a remote     machi, Merge the UI's ASE-engine choices (calculator, command path, extra params)     o

### Community 71 - "Remote Files/Jobs Endpoints"
Cohesion: 0.29
Nodes (7): api_remote_files(), api_remote_jobs(), api_running(), _fmt_ts(), Jobs running now across the local machine + every configured remote.      ?all=1, List the job directories that live on a remote machine (newest first)., List the files/subdirs of one directory on a remote machine.

### Community 72 - "Remote Analysis Tests"
Cohesion: 0.33
Nodes (3): _local_job(), The analysis endpoints resolve remote jobs into a local cache dir, so the Result, test_api_adsorption_accepts_machine_slots()

### Community 73 - "Surface Energy"
Cohesion: 0.33
Nodes (6): Surface energy γ = (E_slab − (N_slab/N_bulk)·E_bulk) / (2A).      E from `read_j, surface_energy(), api_surface(), Resolve one analysis job slot to a local dir.      Accepts a bare path string (=, Surface energy γ from a slab job and a bulk job (VASP or QE)., _slot_dir()

### Community 74 - "QE pw.out Parser"
Cohesion: 0.33
Nodes (6): parse_pw_output(), Parse a Quantum ESPRESSO pw.x output (pw.out) into a summary dict.      Returns, Extract the Ry number from a '... total energy = -123.45 Ry' line., _ry_value(), test_parse_pw_output(), test_parse_pw_output_missing()

### Community 75 - "Detached Job Dir Resolution"
Cohesion: 0.33
Nodes (6): The real (numbered) job root a detached offload chose, or None if not yet known., resolve_detached_job_dir(), The real numbered job root is read back from <control_dir>/job_dir over SSH., No control dir, or the file not yet written, resolves to None (caller falls back, test_resolve_detached_job_dir_reads_control_file(), test_resolve_detached_job_dir_returns_none_when_absent()

### Community 77 - "Mesh Parsing"
Cohesion: 0.50
Nodes (4): parse_mesh(), Parse '4', '4x4x1', or '4 4 1' into a 3-tuple of subdivisions., test_parse_mesh_rejects_pairs(), test_parse_mesh_scalar_and_triplet()

### Community 78 - "Cell Parameters"
Cohesion: 0.50
Nodes (4): cell_from_parameters(), Lattice matrix (rows = a, b, c vectors, Å) from cell parameters.      Standard c, test_cell_from_parameters_rejects_impossible(), test_cell_parameters_roundtrip()

### Community 79 - "Remote Run Mode Detection"
Cohesion: 0.67
Nodes (3): detect_remote_run_mode(), Probe a remote once for a batch scheduler and pick a run mode.      ``sbatch`` p, test_detect_remote_run_mode_reads_probe()

### Community 80 - "Detached Job Polling"
Cohesion: 0.67
Nodes (3): poll_detached_job(), Status of a detached offload job from its control dir (pid + rc files).      Ret, test_poll_detached_job_states()

## Knowledge Gaps
- **27 isolated node(s):** `vasp-auto`, `PATH`, `Numbered job folders`, `KPOINTS generation`, `Excel results summary` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `parse_vasprun()` connect `QE/VASP Output Parsers` to `Case Processing & Job Rows`, `Job Report Builder`, `NEB Energy Profile`, `Job Submission & Convergence Checks`, `Catalysis Analysis (adsorption/d-band)`, `Job Log Builder`, `XML Parse Error Handling`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `make_case_info()` connect `Case Info & INCAR Templates` to `CLI Command Dispatch`, `Case Processing & Job Rows`, `Preview Endpoints`, `QE Engine Tests`, `Web UI Case & Run Endpoints`, `Job Files & Results Endpoints`, `ASE Engine Driver`, `Web Server & Provider Catalog`, `Detached Offload Flag Forwarding`, `Chained Workflows`, `Target Inspection Utils`, `Job Manager (dir allocation)`, `SIGMA/Magmom & Solvation`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `read_poscar()` connect `Crystal Builder & PDOS` to `Trajectory & Animation Extraction`, `CLI Command Dispatch`, `POSCAR Structure Editing`, `AI / NL Structure Builder`, `ASE Structure Builders`, `ML Pre-relax & DB Fetch`, `Web Server & Provider Catalog`, `PDOS/Bands Aggregation & Supercell Match`, `Catalysis Analysis (adsorption/d-band)`, `Job Log Builder`, `Structure Editor Endpoints`, `Optics/XRD & Analysis Endpoints`, `Adsorbate & Structure Geometry`, `Quantum ESPRESSO Engine`, `Structure Combine & Supercell`, `CHGCAR / Bader Charge`, `Restart File Handling`, `Prototype Crystal Builder`, `NL Agent Smoketest`, `Surface Energy`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `make_case_info()` (e.g. with `test_offload_bundles_neb_endpoints()` and `test_offload_bundles_workflow_yaml()`) actually correct?**
  _`make_case_info()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `vasp-auto`, `PATH`, `Numbered job folders` to the rest of the system?**
  _27 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Trajectory & Animation Extraction` be split into smaller, more focused modules?**
  _Cohesion score 0.05185185185185185 - nodes in this community are weakly interconnected._
- **Should `Engine Features & Capabilities (docs)` be split into smaller, more focused modules?**
  _Cohesion score 0.08069381598793364 - nodes in this community are weakly interconnected._