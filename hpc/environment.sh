#!/bin/bash
# Source before starting Python. All generated caches and temporary files
# belong to this project; never repurpose HOME or the shared Conda prefix.
PROJECT="${GS_OJCS_PROJECT:-/home/tariq.qayyum/hpc/GapSlice-OJCS}"
mkdir -p "$PROJECT/.cache/pip" "$PROJECT/.cache/matplotlib" "$PROJECT/.cache/pycache" \
  "$PROJECT/.tools/installers" "$PROJECT/.config" "$PROJECT/.local/share" \
  "$PROJECT/.cache/uv" "$PROJECT/.cache/python-downloads" "$PROJECT/tmp/${SLURM_JOB_ID:-local}"
export TMPDIR="$PROJECT/tmp/${SLURM_JOB_ID:-local}"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PROJECT/.cache"
export XDG_CONFIG_HOME="$PROJECT/.config" XDG_DATA_HOME="$PROJECT/.local/share"
export XDG_STATE_HOME="$PROJECT/.local/state"
export MPLCONFIGDIR="$PROJECT/.cache/matplotlib" MPLBACKEND=Agg
export PIP_CACHE_DIR="$PROJECT/.cache/pip" PIP_REQUIRE_VIRTUALENV=true
export PYTHONPYCACHEPREFIX="$PROJECT/.cache/pycache" PYTHONNOUSERSITE=1
unset PYTHONHOME PYTHONPATH
export UV_CACHE_DIR="$PROJECT/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$PROJECT/.python"
export UV_PYTHON_CACHE_DIR="$PROJECT/.cache/python-downloads"
export UV_PYTHON_BIN_DIR="$PROJECT/.tools/python-bin"
export UV_TOOL_DIR="$PROJECT/.tools/uv-tools" UV_TOOL_BIN_DIR="$PROJECT/.tools/uv-tool-bin"
export UV_PROJECT_ENVIRONMENT="$PROJECT/.venv" UV_NO_CONFIG=1 UV_NO_MODIFY_PATH=1
export UV_PYTHON_INSTALL_BIN=0
if [ "$(uname -m)" = x86_64 ]; then export UV_PYTHON_ARCH=x86_64; fi
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export GAPSLICE_ROOT="$PROJECT" GAPSLICE_RESULTS="$PROJECT/results"
export GAPSLICE_OUTPUT="$PROJECT/outputs/legacy-generated"
