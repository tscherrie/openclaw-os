#!/usr/bin/env bash
set -eo pipefail

DEFAULT_AOSP_ROOT="/Users/jeremias/clawdroid/.work/aosp"
AOSP_ROOT="${AOSP_ROOT:-${DEFAULT_AOSP_ROOT}}"
LUNCH_TARGET="${LUNCH_TARGET:-hansos_cf_arm64-trunk_staging-userdebug}"
JOBS="${JOBS:-4}"
SKIP_SOONG_TESTS="${SKIP_SOONG_TESTS:-true}"
SKIP_ABI_CHECKS="${SKIP_ABI_CHECKS:-true}"
THINLTO_USE_MLGO="${THINLTO_USE_MLGO:-false}"

export SKIP_ABI_CHECKS
export THINLTO_USE_MLGO

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REQUESTED_TARGETS=("$@")
if [[ ${#REQUESTED_TARGETS[@]} -eq 0 ]]; then
  if [[ "${LUNCH_TARGET}" == hansos_gsi_* ]]; then
    REQUESTED_TARGETS=(HansCanvasSystem HansRuntimeServiceSystem)
  else
    REQUESTED_TARGETS=(HansCanvas HansRuntimeService)
  fi
fi

if [[ ! -f "${AOSP_ROOT}/build/envsetup.sh" ]]; then
  echo "Not an AOSP checkout: ${AOSP_ROOT}" >&2
  exit 1
fi

source "${REPO_ROOT}/scripts/aosp-build-env.sh"
cd "${AOSP_ROOT}"
source build/envsetup.sh
lunch "${LUNCH_TARGET}"

PRODUCT_OUT="$(get_build_var PRODUCT_OUT)"
if [[ -z "${PRODUCT_OUT}" ]]; then
  echo "Could not resolve PRODUCT_OUT for ${LUNCH_TARGET}" >&2
  exit 1
fi
TARGETS=()

add_target() {
  local target="$1"
  local existing
  for existing in "${TARGETS[@]}"; do
    if [[ "${existing}" == "${target}" ]]; then
      return
    fi
  done
  TARGETS+=("${target}")
}

for target in "${REQUESTED_TARGETS[@]}"; do
  case "${target}" in
    HansCanvas)
      if [[ "${LUNCH_TARGET}" == hansos_gsi_* ]]; then
        add_target "${PRODUCT_OUT}/system/priv-app/HansCanvasSystem/HansCanvasSystem.apk"
      else
        add_target "${PRODUCT_OUT}/system_ext/priv-app/HansCanvas/HansCanvas.apk"
      fi
      ;;
    HansCanvasSystem)
      add_target "${PRODUCT_OUT}/system/priv-app/HansCanvasSystem/HansCanvasSystem.apk"
      ;;
    HansRuntimeService)
      if [[ "${LUNCH_TARGET}" == hansos_gsi_* ]]; then
        add_target "${PRODUCT_OUT}/system/priv-app/HansRuntimeServiceSystem/HansRuntimeServiceSystem.apk"
      else
        add_target "${PRODUCT_OUT}/system_ext/priv-app/HansRuntimeService/HansRuntimeService.apk"
      fi
      ;;
    HansRuntimeServiceSystem)
      add_target "${PRODUCT_OUT}/system/priv-app/HansRuntimeServiceSystem/HansRuntimeServiceSystem.apk"
      ;;
    hansos-agent-protocol)
      if [[ "${LUNCH_TARGET}" == hansos_gsi_* ]]; then
        add_target "${PRODUCT_OUT}/system/priv-app/HansCanvasSystem/HansCanvasSystem.apk"
      else
        add_target "${PRODUCT_OUT}/system_ext/priv-app/HansCanvas/HansCanvas.apk"
      fi
      ;;
    hansos-fakes)
      if [[ "${LUNCH_TARGET}" == hansos_gsi_* ]]; then
        add_target "${PRODUCT_OUT}/system/priv-app/HansRuntimeServiceSystem/HansRuntimeServiceSystem.apk"
      else
        add_target "${PRODUCT_OUT}/system_ext/priv-app/HansRuntimeService/HansRuntimeService.apk"
      fi
      ;;
    privapp-permissions-ai.hansos.canvas.xml)
      if [[ "${LUNCH_TARGET}" == hansos_gsi_* ]]; then
        add_target "${PRODUCT_OUT}/system/etc/permissions/privapp-permissions-ai.hansos.canvas.xml"
      else
        add_target "${PRODUCT_OUT}/system_ext/etc/permissions/privapp-permissions-ai.hansos.canvas.xml"
      fi
      ;;
    privapp-permissions-ai.hansos.canvas.system.xml)
      add_target "${PRODUCT_OUT}/system/etc/permissions/privapp-permissions-ai.hansos.canvas.xml"
      ;;
    privapp-permissions-ai.hansos.runtime.xml)
      if [[ "${LUNCH_TARGET}" == hansos_gsi_* ]]; then
        add_target "${PRODUCT_OUT}/system/etc/permissions/privapp-permissions-ai.hansos.runtime.xml"
      else
        add_target "${PRODUCT_OUT}/system_ext/etc/permissions/privapp-permissions-ai.hansos.runtime.xml"
      fi
      ;;
    privapp-permissions-ai.hansos.runtime.system.xml)
      add_target "${PRODUCT_OUT}/system/etc/permissions/privapp-permissions-ai.hansos.runtime.xml"
      ;;
    images|cuttlefish-images)
      add_target systemimage
      add_target systemextimage
      add_target productimage
      add_target vendorimage
      add_target superimage
      add_target vbmetaimage
      add_target vbmetasystemimage
      ;;
    gsi-image|mp01-image)
      add_target systemimage
      ;;
    *)
      add_target "${target}"
      ;;
  esac
done

echo "Resolved build targets:"
printf '  %s\n' "${TARGETS[@]}"

if [[ "${SKIP_SOONG_TESTS}" == "true" ]]; then
  m --skip-soong-tests -j"${JOBS}" "${TARGETS[@]}"
else
  m -j"${JOBS}" "${TARGETS[@]}"
fi
