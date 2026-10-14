#!/usr/bin/env bash
# Reproduce every result, figure and table of the paper from scratch.
# Run from the repository root:   bash scripts/run_all.sh
# About 3.5 hours on two CPU cores. The two table builders use both cores;
# the experiments run one at a time.
#
# By default the stored files in results/, figures/ and tables/ are
# overwritten. To keep them and write elsewhere, set GAPSLICE_OUTPUT:
#   GAPSLICE_OUTPUT=/tmp/rerun bash scripts/run_all.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

if [ -n "${GAPSLICE_OUTPUT:-}" ]; then
  LOG="$GAPSLICE_OUTPUT/results"
  # later steps read the tables written by the first steps
  export GAPSLICE_RESULTS="$LOG"
else
  LOG="results"
fi
mkdir -p "$LOG"
run() { local name=$1; shift; echo "[$name]"; python3 -m gapslice run "$@" | tee "$LOG/$name.log"; }

echo "[checks] model and channel consistency"
python3 -m pytest -q tests/test_model_consistency.py tests/test_channel.py

run tail_table   type-b-table          # per-event risk table (type B, loan guard)
run descriptor   type-a-table          # certified gain curves (type A)
run feas         feasibility
run e1           e1
run e2           e2
run e5           e5
run e5_joint     e5b
run e6           e6
run sens         sensitivity
run e3_A         e3 A
run e3_B         e3 B
run e4_A         e4 A
run e4_B         e4 B
run e7_A         e7 A
run e7_B         e7 B
run e8_A         e8 A
run e8_B         e8 B
run e9_A         e9 A
run e9_B         e9 B

echo "[reports] figures and tables"
python3 -m gapslice figures
python3 -m gapslice tables
echo "Done."
