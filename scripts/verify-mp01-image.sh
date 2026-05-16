#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
usage: verify-mp01-image.sh --product-out /path/to/target/product/tdgsi_arm64_ab

Checks that a built Lineage/TrebleDroid MP01 product tree contains the HansOS
system image artifacts required before the first physical flash.
USAGE
}

PRODUCT_OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --product-out)
      PRODUCT_OUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${PRODUCT_OUT}" || ! -d "${PRODUCT_OUT}" ]]; then
  echo "Missing product output directory. Pass --product-out /path/to/product." >&2
  exit 2
fi

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "Missing ${label}: ${path}" >&2
    exit 1
  fi
  echo "  - ${label}: ${path}"
}

require_absent_path() {
  local path="$1"
  local label="$2"
  if [[ -e "${path}" ]]; then
    echo "Unexpected ${label}: ${path}" >&2
    exit 1
  fi
  echo "  - ${label} absent: ${path}"
}

require_zip_entry() {
  local zip="$1"
  local entry="$2"
  local label="$3"
  local tmp_list

  tmp_list="$(mktemp)"
  if command -v zipinfo >/dev/null 2>&1; then
    zipinfo -1 "${zip}" > "${tmp_list}"
    grep -qx "${entry}" "${tmp_list}" || {
      rm -f "${tmp_list}"
      echo "Missing ${label} in ${zip}: ${entry}" >&2
      exit 1
    }
  elif command -v jar >/dev/null 2>&1; then
    jar tf "${zip}" > "${tmp_list}"
    grep -qx "${entry}" "${tmp_list}" || {
      rm -f "${tmp_list}"
      echo "Missing ${label} in ${zip}: ${entry}" >&2
      exit 1
    }
  else
    rm -f "${tmp_list}"
    echo "Neither zipinfo nor jar is available to inspect ${zip}" >&2
    exit 1
  fi
  rm -f "${tmp_list}"
  echo "  - ${label}: ${entry}"
}

require_zip_dex_marker() {
  local zip="$1"
  local marker="$2"
  local label="$3"
  local tmp_dir
  local entry
  local found=0

  if ! command -v zipinfo >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1; then
    echo "Skipping ${label}; zipinfo or unzip is unavailable" >&2
    return 0
  fi

  tmp_dir="$(mktemp -d)"
  while IFS= read -r entry; do
    unzip -p "${zip}" "${entry}" > "${tmp_dir}/classes.dex"
    if grep -a -q "${marker}" "${tmp_dir}/classes.dex"; then
      found=1
      break
    fi
  done < <(zipinfo -1 "${zip}" | grep -E '^classes[0-9]*\.dex$')
  rm -rf "${tmp_dir}"

  if [[ "${found}" != "1" ]]; then
    echo "Missing ${label} in ${zip}: ${marker}" >&2
    exit 1
  fi
  echo "  - ${label}: ${marker}"
}

require_text_marker() {
  local file="$1"
  local marker="$2"
  local label="$3"
  if ! grep -q "${marker}" "${file}"; then
    echo "Missing ${label} in ${file}: ${marker}" >&2
    exit 1
  fi
  echo "  - ${label}: ${marker}"
}

SYSTEM_IMG="${PRODUCT_OUT}/system.img"
SYSTEM_DIR="${PRODUCT_OUT}/system"
SERVICES_JAR="${SYSTEM_DIR}/framework/services.jar"

require_file "${SYSTEM_IMG}" "flashable system.img"
require_file "${SYSTEM_DIR}/priv-app/HansCanvasSystem/HansCanvasSystem.apk" "HansCanvas system APK"
require_file "${SYSTEM_DIR}/priv-app/HansRuntimeServiceSystem/HansRuntimeServiceSystem.apk" "HansRuntime system APK"
require_file "${SYSTEM_DIR}/etc/permissions/privapp-permissions-ai.hansos.canvas.system.xml" "HansCanvas privapp permissions"
require_file "${SYSTEM_DIR}/etc/permissions/privapp-permissions-ai.hansos.runtime.system.xml" "HansRuntime privapp permissions"
require_file "${SERVICES_JAR}" "services.jar"
require_absent_path "${PRODUCT_OUT}/system_ext/priv-app/LineageSetupWizard" "LineageSetupWizard HOME blocker"
require_absent_path "${PRODUCT_OUT}/system_ext/priv-app/Provision" "Provision HOME blocker"

require_zip_entry "${SERVICES_JAR}" "classes.dex" "services dex payload"
require_zip_dex_marker "${SERVICES_JAR}" "Lai/hansos/server/HansManagerService;" "HansManagerService dex marker"
require_zip_dex_marker "${SERVICES_JAR}" "StartHansManagerService" "SystemServer Hans startup trace marker"
require_zip_dex_marker "${SERVICES_JAR}" "last_input_keycode" "PTT diagnostics dex marker"
require_zip_dex_marker "${SYSTEM_DIR}/priv-app/HansRuntimeServiceSystem/HansRuntimeServiceSystem.apk" \
  "Lai/hansos/runtime/SystemPhoneProvider;" "SystemPhoneProvider dex marker"
require_zip_dex_marker "${SYSTEM_DIR}/priv-app/HansRuntimeServiceSystem/HansRuntimeServiceSystem.apk" \
  "HansAppPilotAccessibilityService" "App Pilot accessibility dex marker"
require_zip_dex_marker "${SYSTEM_DIR}/priv-app/HansRuntimeServiceSystem/HansRuntimeServiceSystem.apk" \
  "HansNotificationListenerService" "notification listener dex marker"
require_zip_dex_marker "${SYSTEM_DIR}/priv-app/HansRuntimeServiceSystem/HansRuntimeServiceSystem.apk" \
  "audio/transcriptions" "OpenAI transcription dex marker"
require_zip_dex_marker "${SYSTEM_DIR}/priv-app/HansCanvasSystem/HansCanvasSystem.apk" \
  "Hans live phrase" "voice-first Canvas dex marker"
require_zip_dex_marker "${SYSTEM_DIR}/priv-app/HansCanvasSystem/HansCanvasSystem.apk" \
  "hansos_ptt_keycode" "Canvas PTT setting dex marker"
require_text_marker "${SYSTEM_DIR}/etc/permissions/privapp-permissions-ai.hansos.runtime.system.xml" \
  "WRITE_SECURE_SETTINGS" "runtime secure-settings permission"
require_text_marker "${SYSTEM_DIR}/etc/permissions/privapp-permissions-ai.hansos.runtime.system.xml" \
  "READ_PHONE_STATE" "runtime phone-state permission"
require_text_marker "${SYSTEM_DIR}/etc/permissions/privapp-permissions-ai.hansos.canvas.system.xml" \
  "RECORD_AUDIO" "canvas record-audio permission"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${SYSTEM_IMG}" > "${PRODUCT_OUT}/system.img.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "${SYSTEM_IMG}" > "${PRODUCT_OUT}/system.img.sha256"
else
  echo "Skipping checksum; no sha256 tool available" >&2
fi

echo "HansOS MP01 image verification passed."
