#!/usr/bin/env bash
# vasp_auto self-check
# ====================
# Exercises every CLI feature against the fake VASP in bin/ (no real VASP or
# cluster needed). Everything it writes stays inside selfcheck/ (jobs/, build/,
# logs/, derived cases). Exit code 0 means all checks passed.
#
# Usage:  ./run_selfcheck.sh
set -u
cd "$(dirname "$0")"
export PATH="$PWD/bin:$PATH"

REPO_ROOT="$(cd .. && pwd)"
PYTHON="$REPO_ROOT/venv/bin/python"
CMD="$(command -v vasp-auto || true)"
[ -n "$CMD" ] || CMD="$REPO_ROOT/venv/bin/vasp-auto"

rm -rf jobs build logs
mkdir -p logs build

PASS=0
FAIL=0

note()  { printf '%-4s %s\n' "$1" "$2"; }
run()   { local log="$1"; shift; "$@" > "logs/$log.log" 2>&1; }
check() { # check <description> <file> <grep pattern>
  local desc="$1" file="$2" pattern="$3"
  if [ -e "$file" ] && grep -q "$pattern" "$file"; then
    PASS=$((PASS + 1)); note PASS "$desc"
  else
    FAIL=$((FAIL + 1)); note FAIL "$desc  (wanted '$pattern' in $file)"
  fi
}
exists() { # exists <description> <file>
  local desc="$1" file="$2"
  if [ -e "$file" ]; then
    PASS=$((PASS + 1)); note PASS "$desc"
  else
    FAIL=$((FAIL + 1)); note FAIL "$desc  (missing $file)"
  fi
}
okcmd() { # okcmd <description> <cmd...>
  local desc="$1"; shift
  if "$@" >> logs/okcmd.log 2>&1; then
    PASS=$((PASS + 1)); note PASS "$desc"
  else
    FAIL=$((FAIL + 1)); note FAIL "$desc  (see logs/okcmd.log)"
  fi
}

echo "vasp_auto selfcheck — using $CMD"
echo

# 01 — dry-run preview (nothing written)
run 01_dry_run "$CMD" cases/A --dry-run
check "01 dry-run shows INCAR preview"            logs/01_dry_run.log "ENCUT"
check "01 dry-run shows POTCAR composition"       logs/01_dry_run.log "Al, O_s"
[ ! -d jobs/A ] && PASS=$((PASS+1)) && note PASS "01 dry-run wrote nothing" \
  || { FAIL=$((FAIL+1)); note FAIL "01 dry-run wrote files"; }

# 02 — calc-type template + Monkhorst-Pack mesh
run 02_calc_type "$CMD" cases/A --calc-type relax --kpoints-mode mp --kmesh 4x4x4 --prepare
check "02 relax INCAR template selected"          jobs/A/INCAR "IBRION = 2"
check "02 Monkhorst-Pack KPOINTS generated"       jobs/A/KPOINTS "Monkhorst-Pack"

# 03 — full single-case run with the fake VASP (potcar_map applied)
run 03_run_scf "$CMD" cases/A
exists "03 OUTCAR produced"                       jobs/A/OUTCAR
exists "03 Excel summary written"                 jobs/A/A.xlsx
check  "03 run finished"                          logs/03_run_scf.log "Finished"
check  "03 potcar_map picked O_s variant"         jobs/A/POTCAR "O_s"

# 04 — vasprun.xml results reach the Excel summary
okcmd "04 band gap parsed from vasprun.xml" "$PYTHON" -c "
import pandas
df = pandas.read_excel('jobs/A/A.xlsx')
assert abs(df['band_gap_eV'][0] - 2.5) < 1e-6, df['band_gap_eV'][0]
assert abs(df['fermi_eV'][0] - 2.0) < 1e-6
assert df['converged'][0]
"

# 05 — retry-failed skips a converged case
run 05_retry "$CMD" cases/A --retry-failed
check "05 retry-failed skips converged case"      logs/05_retry.log "already converged"

# 06 — error detection with a known signature
run 06_error env FAKE_VASP_ERROR=1 "$CMD" cases/B
check "06 ZBRENT error detected with hint"        logs/06_error.log "VASP error: ZBRENT"

# 07 — project mode with parallel execution (cases A, B, C)
run 07_parallel "$CMD" cases --parallel 2
exists "07 project Excel written"                 jobs/cases/cases.xlsx
check  "07 all three cases processed"             logs/07_parallel.log "Case      : C"

# 08 — chained workflow relax -> scf -> dos (from workflow.yaml)
run 08_workflow "$CMD" workflow_case
check  "08 relax step ran"                        logs/08_workflow.log "01_relax"
check  "08 scf step starts from relaxed CONTCAR"  jobs/workflow_case/02_scf/POSCAR "fake relaxed"
check  "08 scf step INCAR override applied"       jobs/workflow_case/02_scf/INCAR "ENCUT = 450"
exists "08 dos step received CHGCAR"              jobs/workflow_case/03_dos/CHGCAR
check  "08 dos step is non-SCF (ICHARG=11)"       jobs/workflow_case/03_dos/INCAR "ICHARG = 11"
check  "08 dos step kpoints override"             jobs/workflow_case/03_dos/KPOINTS "6 6 6"

# 28 — convergence as a workflow step: scan first, then run scf with the result
run 28_convwf "$CMD" cases/B --workflow "converge,scf"
check  "28 converge step ran a scan"              logs/28_convwf.log "convergence scan"
exists "28 convergence report written"            jobs/B/01_converge/scf_convergence/scf_convergence_report.md
exists "28 scf step ran after converge"           jobs/B/02_scf/OUTCAR
check  "28 converged NELM carried into scf"       jobs/B/02_scf/INCAR "NELM"

# 09 — pure-Python structure tools
run 09_supercell "$CMD" cases/A --supercell 2x2x2 --vacancy 1 --ase-output build/sc --build-only
check "09 supercell+vacancy counts (Al7 O8)"      build/sc/POSCAR "7  8"
run 10_substitute "$CMD" cases/A --substitute 2=Mg --ase-output build/sub --build-only
check "10 substitution introduced Mg"             build/sub/POSCAR "Mg"

# 11 — KPOINTS modes
run 11_kpath "$CMD" cases/A --kpath fcc --dry-run
check "11 line-mode k-path generated"             logs/11_kpath.log "Line-mode"
run 12_kspacing "$CMD" cases/A --kspacing 0.5 --dry-run
check "12 density-based mesh (4 A cube -> 4x4x4)" logs/12_kspacing.log "4 4 4"

# 13 — convergence scan: ENCUT then NELM then KPOINTS
run 13_convergence "$CMD" cases/B --converge-encut 300,350 --converge-scf \
    --nelm-values 40,60 --kpoints-values 2,3
check  "13 convergence selection printed"         logs/13_convergence.log "Selected"
check  "13 report includes ENCUT stage"           jobs/B/scf_convergence/scf_convergence_report.md "ENCUT"
exists "13 step CSV written"                      jobs/B/scf_convergence/scf_convergence_steps.csv

# 14 — scheduler submission (fake sbatch)
run 14_scheduler "$CMD" cases/A --scheduler slurm
exists "14 submit.sh written"                     jobs/A/submit.sh
check  "14 job id captured"                       logs/14_scheduler.log "4242"

# 15 — TSS/NEB preparation with interpolation
run 15_tss "$CMD" tss_demo --prepare --neb-images 3
exists "15 intermediate image interpolated"       jobs/tss_demo/02/POSCAR
check  "15 IMAGES tag written"                    jobs/tss_demo/INCAR "IMAGES = 3"

# 16 — per-case config override
run 16_local_config "$CMD" cases/C --dry-run
check "16 case config.yaml overrides neb_images"  logs/16_local_config.log "NEB images: 9"

# 17 — ASE builders (skipped when ASE is not installed in venv)
if "$PYTHON" -c "import ase" 2>/dev/null; then
  run 17_slab "$CMD" --ase-build-slab Al --ase-layers 3 --ase-vacuum 10 --ase-output build/slab --build-only
  exists "17 slab POSCAR built"                   build/slab/POSCAR
  run 18_molecule "$CMD" --ase-build-molecule H2O --ase-output build/h2o --build-only
  exists "18 molecule POSCAR built"               build/h2o/POSCAR
  run 26_crystal "$CMD" --ase-build-crystal "Na Cl" --ase-spacegroup 225 \
      --ase-basis "0,0,0;0.5,0.5,0.5" --ase-a 5.64 --ase-output build/nacl --build-only
  check "26 space-group crystal built (Cl4 Na4)"  build/nacl/POSCAR "4   4"
  run 27_nanotube "$CMD" --ase-build-nanotube C --ase-nt-n 5 --ase-nt-m 5 \
      --ase-nt-length 2 --ase-output build/cnt --build-only
  exists "27 nanotube POSCAR built"               build/cnt/POSCAR
else
  note SKIP "17/18/26/27 ASE builders (ASE not installed)"
fi

# 19 — parse-only regenerates the summary
run 19_parse_only "$CMD" cases/B --parse-only
check "19 parse-only writes Excel"                logs/19_parse_only.log "Wrote Excel"

# 22 — prototype crystals + supercell matching + stacking (pass 7/8)
run 22_prototype "$CMD" --build-prototype "graphene:vacuum=18" --ase-output build/graphene --build-only
check "22 graphene prototype built"               build/graphene/POSCAR "graphene"
run 23_match "$CMD" build/graphene --match-cells cases/A --match-gamma-tol 35 --build-only
check "23 match-cells prints a supercell table"   logs/23_match.log "strain a"
run 24_combine "$CMD" build/graphene --combine cases/A --combine-gap 3 --ase-output build/stack --build-only
check "24 combined stack contains both materials" build/stack/POSCAR "Al"

# 25 — read-only analysis command on the finished fake jobs
run 25_ads "$CMD" --adsorption-energy "jobs/cases/A,jobs/cases/B,jobs/cases/C"
check "25 adsorption energy assembled"            logs/25_ads.log "E_ads"

# 29 — Quantum ESPRESSO engine: dry-run preview writes a pw.in, nothing else
run 29_qe_dry "$CMD" cases/A --engine qe --pseudo-dir pseudo --calc-type scf \
  --kpoints-mode gamma --kmesh 4x4x4 --dry-run
check "29 QE dry-run shows pw.in"                 logs/29_qe_dry.log "calculation = 'scf'"
check "29 QE dry-run lists pseudopotential"       logs/29_qe_dry.log "Al.pbe-n-kjpaw"
[ ! -e jobs/A/pw.in ] && PASS=$((PASS+1)) && note PASS "29 QE dry-run wrote nothing" \
  || { FAIL=$((FAIL+1)); note FAIL "29 QE dry-run wrote files"; }

# 30 — full QE run with the fake pw.x (pw.in prepared, pw.out parsed to Excel)
run 30_qe_run "$CMD" cases/A --engine qe --pseudo-dir pseudo --calc-type relax --kmesh 2x2x2
exists "30 QE pw.in prepared"                     jobs/A/pw.in
exists "30 QE pseudopotential staged"             jobs/A/pseudo/Al.pbe-n-kjpaw_psl.1.0.0.UPF
exists "30 QE pw.out produced"                    jobs/A/pw.out
check  "30 QE engine marker written"              jobs/A/.engine "qe"
okcmd "30 QE energy parsed into Excel" "$PYTHON" -c "
import pandas
df = pandas.read_excel('jobs/A/A.xlsx')
assert df['engine'][0] == 'qe', df['engine'][0]
assert df['converged'][0]
assert df['energy_eV'][0] < 0
"

# 20 — web UI API answers and can read a structure
okcmd "20 UI server API responds" "$PYTHON" -c "
import json, threading, urllib.request
from vasp_auto_ui.server import create_server
server = create_server(port=0)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'
meta = json.load(urllib.request.urlopen(base + '/api/meta'))
assert 'scf' in meta['calc_types']
struct = json.load(urllib.request.urlopen(base + '/api/structure?path=$PWD/cases/A'))
assert struct['natoms'] == 2
browse = json.load(urllib.request.urlopen(base + '/api/browse?path=$PWD/cases'))
assert any(d['name'] == 'A' for d in browse['dirs'])
server.shutdown()
"

# 21 — unit test suite
okcmd "21 unit tests pass (pytest)" "$PYTHON" -m pytest -q "$REPO_ROOT/tests"

echo
echo "Result: $PASS passed, $FAIL failed  (logs in selfcheck/logs/)"
[ "$FAIL" -eq 0 ]
