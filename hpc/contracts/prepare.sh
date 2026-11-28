#!/bin/bash -l
# Isolated contract environment; existing certified .venv is read only.
set -euo pipefail
PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS
cd "$PROJECT"
mkdir -p "$PROJECT/logs" "$PROJECT/results" "$PROJECT/outputs" "$PROJECT/figures" "$PROJECT/tmp"
export GS_OJCS_PROJECT="$PROJECT"
source "$PROJECT/hpc/environment.sh"
type module >/dev/null 2>&1 && module load anaconda3
BASE_PY="$PROJECT/.venv/bin/python"
PY="$PROJECT/.venv-contract/bin/python"
test -x "$BASE_PY" || { echo 'Existing project Python .venv/bin/python is required.' >&2; exit 2; }
test ! -L "$PROJECT/.venv-contract" || { echo 'Refusing a symlinked contract environment.' >&2; exit 2; }
if [ ! -x "$PY" ]; then "$BASE_PY" -m venv --without-pip "$PROJECT/.venv-contract"; fi
"$PY" -c 'import pathlib,sys; assert sys.version_info >= (3,11); assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(sys.argv[1]).resolve()' "$PROJECT/.venv-contract"
"$BASE_PY" -m pip --python "$PY" install --require-virtualenv -r "$PROJECT/requirements-contract.txt"
"$BASE_PY" -m pip --python "$PY" check
"$PY" -m compileall -q "$PROJECT/contractlab"
for script in "$PROJECT/BatchContracts" "$PROJECT/hpc/contracts/prepare.sh"; do
  bash -n "$script"
done
"$PY" -m pytest "$PROJECT/tests/test_contract_core.py" "$PROJECT/tests/test_contract_runtime.py" -q -p no:cacheprovider
"$PY" -m contractlab.hpc dependencies
printf 'Prepared isolated runtime: %s\n' "$PY"
