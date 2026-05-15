#!/usr/bin/env bash
set -euo pipefail

DEFAULT_AOSP_ROOT="/Users/jeremias/clawdroid/.work/aosp"
AOSP_ROOT="${1:-${DEFAULT_AOSP_ROOT}}"
MIN_FREE_GIB="${HANSOS_MIN_FREE_GIB:-250}"
JOBS="${JOBS:-2}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORK_DIR="${REPO_ROOT}/.work"
BIN_DIR="${WORK_DIR}/bin"
AOSP_PARENT="$(dirname "${AOSP_ROOT}")"
TMPDIR="${HANSOS_TMPDIR:-${REPO_ROOT}/.work/tmp}"
export TMPDIR

mkdir -p "${AOSP_PARENT}" "${BIN_DIR}" "${TMPDIR}"

STORAGE_CHECK_PATH="${AOSP_PARENT}"
if [[ -e "${AOSP_ROOT}" ]]; then
  STORAGE_CHECK_PATH="${AOSP_ROOT}"
fi

free_kib="$(df -k "${STORAGE_CHECK_PATH}" | awk 'NR == 2 { print $4 }')"
free_gib="$((free_kib / 1024 / 1024))"

if (( free_gib < MIN_FREE_GIB )); then
  cat >&2 <<EOF
Not enough free disk for AOSP.
  path: ${STORAGE_CHECK_PATH}
  free: ${free_gib} GiB
  required: ${MIN_FREE_GIB} GiB minimum
  recommended: 350-500 GiB for source + out/
EOF
  exit 1
fi

if command -v repo >/dev/null 2>&1; then
  REPO_BIN="$(command -v repo)"
else
  REPO_BIN="${BIN_DIR}/repo"
  if [[ ! -x "${REPO_BIN}" ]]; then
    curl -L https://storage.googleapis.com/git-repo-downloads/repo -o "${REPO_BIN}"
    chmod +x "${REPO_BIN}"
  fi
fi

mkdir -p "${AOSP_ROOT}"
cd "${AOSP_ROOT}"

if [[ ! -d ".repo" ]]; then
  "${REPO_BIN}" init \
    --partial-clone \
    --no-use-superproject \
    -u https://android.googlesource.com/platform/manifest \
    -b android-latest-release
fi

"${REPO_BIN}" sync -c --no-tags -j"${JOBS}"
"${SCRIPT_DIR}/integrate-aosp.sh" "${AOSP_ROOT}"
