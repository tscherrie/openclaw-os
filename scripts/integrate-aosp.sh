#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/integrate-aosp.sh /path/to/aosp

Copies the HansOS overlay into an AOSP checkout and applies required framework
patches:
  - device/hansos/cuttlefish
  - device/hansos/gsi
  - frameworks/base/services/core/java/ai/hansos/server/HansManagerService.java
  - packages/apps/HansCanvas
  - packages/services/HansRuntimeService
  - packages/modules/HansProtocol
  - packages/modules/HansFakes
  - SystemServer startup hook
  - services.core.unboosted dependency on hansos-agent-protocol
USAGE
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

AOSP_ROOT="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -f "${AOSP_ROOT}/build/envsetup.sh" ]]; then
  echo "Not an AOSP checkout: ${AOSP_ROOT}" >&2
  exit 1
fi

copy_dir() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "${dst}")"
  rsync -a --delete "${src}/" "${dst}/"
}

copy_dir "${REPO_ROOT}/aosp/device/hansos" "${AOSP_ROOT}/device/hansos"
copy_dir "${REPO_ROOT}/aosp/frameworks/base/services/core/java/ai/hansos" \
  "${AOSP_ROOT}/frameworks/base/services/core/java/ai/hansos"
copy_dir "${REPO_ROOT}/aosp/packages/apps/HansCanvas" \
  "${AOSP_ROOT}/packages/apps/HansCanvas"
copy_dir "${REPO_ROOT}/runtime/HansRuntimeService" \
  "${AOSP_ROOT}/packages/services/HansRuntimeService"
copy_dir "${REPO_ROOT}/protocol" \
  "${AOSP_ROOT}/packages/modules/HansProtocol"
copy_dir "${REPO_ROOT}/fakes" \
  "${AOSP_ROOT}/packages/modules/HansFakes"

"${SCRIPT_DIR}/patch-aosp.py" "${AOSP_ROOT}"

cat <<EOF
HansOS overlay integrated into:
  ${AOSP_ROOT}

Next:
  cd ${AOSP_ROOT}
  source build/envsetup.sh
  lunch hansos_cf_arm64-trunk_staging-userdebug
  m HansCanvas HansRuntimeService hansos-agent-protocol hansos-fakes

For MP01/GSI image work:
  lunch hansos_gsi_arm64-trunk_staging-userdebug
  m systemimage
EOF
