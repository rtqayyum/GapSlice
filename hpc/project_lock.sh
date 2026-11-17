#!/bin/bash
# Source this helper. mkdir gives an atomic project guard without requiring
# flock support on the shared filesystem. Existing guards are never reclaimed
# automatically: a killed owner must first be checked in Slurm accounting.

gs_acquire_project_lock() {
  local project="${1:?Absolute project directory required}"
  local parent error owner_tmp owner_pid
  case "$project" in
    /*) ;;
    *) printf 'ERROR: project lock requires an absolute project path.\n' >&2; return 73 ;;
  esac
  if [ "${GS_PROJECT_LOCK_OWNED:-0}" = 1 ]; then
    printf 'ERROR: this shell already owns a project guard.\n' >&2
    return 75
  fi
  parent="$project/outputs/ojcs"
  if error="$(mkdir -p "$parent" 2>&1)"; then
    :
  else
    printf 'ERROR: cannot create project guard parent %s: %s\n' "$parent" "$error" >&2
    return 73
  fi
  GS_PROJECT_LOCK_DIR="$parent/.campaign.guard"
  owner_pid="${BASHPID:-$$}"
  GS_PROJECT_LOCK_TOKEN="${SLURM_JOB_ID:-local}-${owner_pid}-${RANDOM}-${RANDOM}"
  GS_PROJECT_LOCK_OWNED=0
  if error="$(mkdir -m 700 "$GS_PROJECT_LOCK_DIR" 2>&1)"; then
    owner_tmp="$GS_PROJECT_LOCK_DIR/owner-$GS_PROJECT_LOCK_TOKEN.tmp"
    if (
      umask 077
      printf 'job_id=%s\nhost=%s\npid=%s\ntoken=%s\ncreated_utc=%s\n' \
        "${SLURM_JOB_ID:-local}" "${HOSTNAME:-unknown}" "$owner_pid" \
        "$GS_PROJECT_LOCK_TOKEN" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$owner_tmp"
    ) && mv "$owner_tmp" "$GS_PROJECT_LOCK_DIR/owner"; then
      GS_PROJECT_LOCK_OWNED=1
      return 0
    fi
    printf 'ERROR: created project guard but could not write owner metadata: %s\n' "$GS_PROJECT_LOCK_DIR" >&2
    printf 'No campaign started; inspect the filesystem and this guard before retrying.\n' >&2
    return 73
  fi
  if [ -d "$GS_PROJECT_LOCK_DIR" ]; then
    printf 'ERROR: project guard already exists: %s\n' "$GS_PROJECT_LOCK_DIR" >&2
    if [ -f "$GS_PROJECT_LOCK_DIR/owner" ]; then
      printf 'Recorded owner (this does not establish whether it is still active):\n' >&2
      cat "$GS_PROJECT_LOCK_DIR/owner" >&2
    else
      printf 'Owner metadata is unavailable; another startup may be writing it or an earlier startup was interrupted.\n' >&2
    fi
    printf 'Check the recorded job in squeue/sacct. An interrupted guard requires explicit recovery; it is never removed automatically.\n' >&2
    return 75
  fi
  printf 'ERROR: cannot create project guard %s: %s\n' "$GS_PROJECT_LOCK_DIR" "$error" >&2
  return 73
}

gs_release_project_lock() {
  local key value recorded_token=''
  if [ "${GS_PROJECT_LOCK_OWNED:-0}" != 1 ]; then
    return 0
  fi
  if [ -f "$GS_PROJECT_LOCK_DIR/owner" ]; then
    while IFS='=' read -r key value; do
      if [ "$key" = token ]; then recorded_token="$value"; fi
    done < "$GS_PROJECT_LOCK_DIR/owner"
  fi
  if [ "$recorded_token" != "$GS_PROJECT_LOCK_TOKEN" ]; then
    printf 'ERROR: refusing to release a guard whose ownership metadata changed: %s\n' "$GS_PROJECT_LOCK_DIR" >&2
    return 74
  fi
  # Remove only this owner's metadata and an empty guard, never other files.
  if rm "$GS_PROJECT_LOCK_DIR/owner" && rmdir "$GS_PROJECT_LOCK_DIR"; then
    GS_PROJECT_LOCK_OWNED=0
    return 0
  fi
  printf 'ERROR: could not release project guard: %s\n' "$GS_PROJECT_LOCK_DIR" >&2
  return 74
}
