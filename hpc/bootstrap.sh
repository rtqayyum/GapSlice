#!/bin/bash
set -euo pipefail
PROJECT="${GS_OJCS_PROJECT:-/home/tariq.qayyum/hpc/GapSlice-OJCS}"
source "$PROJECT/hpc/environment.sh"
cd "$PROJECT"
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Load a Python >=3.11 module before creating the project environment"'
if [ ! -x "$PROJECT/.venv/bin/python" ]; then
  python3 -m venv --copies "$PROJECT/.venv"
fi
PY="$PROJECT/.venv/bin/python"
"$PY" -c 'import sys; from pathlib import Path; assert Path(sys.prefix).resolve() == Path(".venv").resolve(), "Wrong project environment"'
HASH="$($PY -c 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("requirements-hpc.txt").read_bytes()).hexdigest())')"
MARKER="$PROJECT/.venv/.requirements.sha256"
if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER")" != "$HASH" ]; then
  "$PY" -m pip install --disable-pip-version-check -r "$PROJECT/requirements-hpc.txt"
  printf '%s\n' "$HASH" > "$MARKER"
fi
"$PY" -m pip check
"$PY" -c 'import numpy, scipy, cvxpy, clarabel; print("Project environment:", numpy.__version__, scipy.__version__, cvxpy.__version__, clarabel.__version__)'
