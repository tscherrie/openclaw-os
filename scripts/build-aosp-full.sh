#!/usr/bin/env bash
set -eo pipefail

DEFAULT_AOSP_ROOT="/Users/jeremias/clawdroid/.work/aosp"
AOSP_ROOT="${AOSP_ROOT:-${DEFAULT_AOSP_ROOT}}"
LUNCH_TARGET="${LUNCH_TARGET:-hansos_cf_arm64-trunk_staging-userdebug}"
JOBS="${JOBS:-4}"
DEFAULT_TARGET="${DEFAULT_TARGET:-droidcore-unbundled}"
SKIP_SOONG_TESTS="${SKIP_SOONG_TESTS:-true}"
SKIP_ABI_CHECKS="${SKIP_ABI_CHECKS:-true}"
THINLTO_USE_MLGO="${THINLTO_USE_MLGO:-false}"

export SKIP_ABI_CHECKS
export THINLTO_USE_MLGO

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -f "${AOSP_ROOT}/build/envsetup.sh" ]]; then
  echo "Not an AOSP checkout: ${AOSP_ROOT}" >&2
  exit 1
fi

source "${REPO_ROOT}/scripts/aosp-build-env.sh"
cd "${AOSP_ROOT}"
source build/envsetup.sh
lunch "${LUNCH_TARGET}"

if [[ "${SKIP_SOONG_TESTS}" == "true" ]]; then
  if [[ "$#" -eq 0 ]]; then
    m --skip-soong-tests -j"${JOBS}" "${DEFAULT_TARGET}"
  else
    m --skip-soong-tests -j"${JOBS}" "$@"
  fi
else
  if [[ "$#" -eq 0 ]]; then
    m -j"${JOBS}" "${DEFAULT_TARGET}"
  else
    m -j"${JOBS}" "$@"
  fi
fi
