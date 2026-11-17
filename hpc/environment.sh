#!/bin/bash
# Source before starting Python. All generated caches and temporary files
# belong to this project; never repurpose HOME or the shared Conda prefix.
PROJECT="${GS_OJCS_PROJECT:-/home/tariq.qayyum/hpc/GapSlice-OJCS}"
mkdir -p "$PROJECT/.cache/pip" "$PROJECT/.cache/matplotlib" "$PROJECT/.cache/pycache" \
  "$PROJECT/tmp/${SLURM_JOB_ID:-local}"
export TMPDIR="$PROJECT/tmp/${SLURM_JOB_ID:-local}"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PROJECT/.cache"
export MPLCONFIGDIR="$PROJECT/.cache/matplotlib" MPLBACKEND=Agg
export PIP_CACHE_DIR="$PROJECT/.cache/pip" PIP_REQUIRE_VIRTUALENV=true
export PYTHONPYCACHEPREFIX="$PROJECT/.cache/pycache" PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export GAPSLICE_ROOT="$PROJECT" GAPSLICE_RESULTS="$PROJECT/results"
export GAPSLICE_OUTPUT="$PROJECT/outputs/legacy-generated"
