#!/bin/bash
# Source after environment.sh. Prefer a usable project venv, then compatible
# installed Python; otherwise install an isolated, pinned managed interpreter.
# No conda environment, shared package directory or shell profile is changed.

gs_python_compatible() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

gs_project_venv_compatible() {
  "$1/bin/python" -c 'import os,sys; sys.exit(0 if sys.version_info >= (3, 11) and os.path.realpath(sys.prefix) == os.path.realpath(sys.argv[1]) else 1)' "$1" >/dev/null 2>&1
}

gs_file_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    printf 'ERROR: sha256sum or shasum is required to verify the runtime installer.\n' >&2
    return 2
  fi
}

gs_prepare_python_runtime() {
  local project="${1:?Absolute project directory required}"
  local candidate base='' installer part actual backup uv_version uv_expected python_target uv
  case "$project" in /*) ;; *) printf 'ERROR: absolute project path required.\n' >&2; return 2 ;; esac
  GS_PROJECT_PYTHON="$project/.venv/bin/python"
  if [ -L "$project/.venv" ]; then
    printf 'ERROR: .venv is a symlink; refusing to change an environment outside this project.\n' >&2
    return 2
  fi
  if gs_project_venv_compatible "$project/.venv"; then
    printf 'Reusing project environment: %s\n' "$GS_PROJECT_PYTHON"
    return 0
  fi
  if [ -e "$project/.venv" ]; then
    backup="$project/.venv.incompatible-$(date -u '+%Y%m%dT%H%M%SZ')-$$-$RANDOM"
    mv "$project/.venv" "$backup" || return $?
    printf 'Preserved incompatible/incomplete project environment: %s\n' "$backup"
  fi
  if [ "${GS_OJCS_MANAGED_PYTHON:-0}" != 1 ]; then
    for candidate in python3.13 python3.12 python3.11 python3 python; do
      if command -v "$candidate" >/dev/null 2>&1 && gs_python_compatible "$candidate"; then
        base="$(command -v "$candidate")"
        break
      fi
    done
  fi
  if [ -n "$base" ]; then
    printf 'Creating project environment with compatible interpreter: %s\n' "$base"
    "$base" -m venv --copies "$project/.venv" || return $?
  else
    uv_version=0.13.8
    python_target=3.13.9
    uv_expected=4d8fa56e00f16b66feecacbd943773c61d61ab768b13856de350d86fd8740e2f
    uv="$project/.tools/uv-$uv_version/uv"
    installer="$project/.tools/installers/uv-$uv_version.sh"
    printf 'No usable installed Python selected; preparing project-local CPython %s.\n' "$python_target"
    if [ ! -x "$uv" ]; then
      command -v curl >/dev/null 2>&1 || { printf 'ERROR: curl is required to download the project runtime.\n' >&2; return 2; }
      mkdir -p "$project/.tools/installers" || return $?
      if [ ! -f "$installer" ]; then
        part="$installer.part-$$"
        curl --fail --location --retry 3 --connect-timeout 15 --max-time 120 \
          "https://astral.sh/uv/$uv_version/install.sh" -o "$part" || return $?
        actual="$(gs_file_sha256 "$part")" || return $?
        if [ "$actual" != "$uv_expected" ]; then
          printf 'ERROR: runtime installer checksum mismatch; not executing it. Expected %s, got %s.\n' "$uv_expected" "$actual" >&2
          return 2
        fi
        mv "$part" "$installer" || return $?
      fi
      actual="$(gs_file_sha256 "$installer")" || return $?
      if [ "$actual" != "$uv_expected" ]; then
        printf 'ERROR: cached runtime installer checksum mismatch; not executing it.\n' >&2
        return 2
      fi
      UV_UNMANAGED_INSTALL="$project/.tools/uv-$uv_version" UV_NO_MODIFY_PATH=1 \
        sh "$installer" || return $?
    fi
    "$uv" --version || return $?
    "$uv" python install "$python_target" || return $?
    "$uv" venv --seed --managed-python --python "$python_target" "$project/.venv" || return $?
  fi
  if ! gs_project_venv_compatible "$project/.venv"; then
    printf 'ERROR: project runtime creation did not produce an isolated Python >=3.11.\n' >&2
    return 2
  fi
  "$GS_PROJECT_PYTHON" --version
}
