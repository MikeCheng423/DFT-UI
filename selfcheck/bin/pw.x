#!/usr/bin/env bash
# Fake Quantum ESPRESSO pw.x for the selfcheck: reads -in pw.in and prints a
# plausible converged SCF output to stdout (the runner captures it as pw.out).
# No real QE needed.
infile=""
while [ $# -gt 0 ]; do
  case "$1" in
    -in|-inp|-i) infile="$2"; shift 2 ;;
    *) shift ;;
  esac
done

cat <<'EOF'
     Program PWSCF v.7.2 starts (fake pw.x for vasp_auto selfcheck)
     Reading input from pw.in
     Self-consistent Calculation
     convergence has been achieved in   9 iterations
!    total energy              =     -22.79430000 Ry
     Total force =     0.000500     Total SCF correction =     0.000002
     number of bfgs steps      =      2
     JOB DONE.
EOF
exit 0
