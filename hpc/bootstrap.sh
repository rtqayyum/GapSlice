#!/bin/bash
set -euo pipefail
PROJECT="${GS_OJCS_PROJECT:-/home/tariq.qayyum/hpc/GapSlice-OJCS}"
source "$PROJECT/hpc/environment.sh"
cd "$PROJECT"
source "$PROJECT/hpc/python_runtime.sh"
gs_prepare_python_runtime "$PROJECT"
PY="$GS_PROJECT_PYTHON"
"$PY" -c 'import sys; from pathlib import Path; assert Path(sys.prefix).resolve() == Path(".venv").resolve(), "Wrong project environment"'
mkdir -p "$PROJECT/outputs/setup"
"$PY" -c 'import json,platform,sys; from pathlib import Path; Path("outputs/setup/runtime.json").write_text(json.dumps(dict(executable=sys.executable,python=sys.version,base_prefix=sys.base_prefix,platform=platform.platform(),machine=platform.machine(),libc=platform.libc_ver()),indent=2)+"\n")'
HASH="$($PY -c 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("requirements-hpc.txt").read_bytes()).hexdigest())')"
MARKER="$PROJECT/.venv/.requirements.sha256"
if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER")" != "$HASH" ]; then
  "$PY" -m pip install --disable-pip-version-check --only-binary=:all: -r "$PROJECT/requirements-hpc.txt"
  printf '%s\n' "$HASH" > "$MARKER"
fi
"$PY" -m pip check
"$PY" -c 'import numpy, scipy, cvxpy, clarabel; print("Project environment:", numpy.__version__, scipy.__version__, cvxpy.__version__, clarabel.__version__)'
"$PY" -m pip freeze > "$PROJECT/outputs/setup/environment.txt"
