#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

resolve_tool() {
  local name="$1"
  local env_name="$2"
  local configured="${!env_name:-}"
  if [[ -n "${configured}" ]]; then
    if [[ -x "${configured}" ]]; then
      echo "${configured}"
      return 0
    fi
    local resolved
    resolved="$(command -v "${configured}" 2>/dev/null || true)"
    if [[ -n "${resolved}" ]]; then
      echo "${resolved}"
      return 0
    fi
    echo "Configured ${env_name} not found: ${configured}" >&2
    return 1
  fi

  local candidates=(
    "${ANDROID_HOME:-}/platform-tools/${name}"
    "${ANDROID_SDK_ROOT:-}/platform-tools/${name}"
    "${HOME}/Library/Android/sdk/platform-tools/${name}"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  command -v "${name}" 2>/dev/null || true
}

ADB="$(resolve_tool adb ADB)"
FASTBOOT="$(resolve_tool fastboot FASTBOOT)"
SERIAL="${HANSOS_ADB_SERIAL:-${ANDROID_SERIAL:-}}"
OUT_DIR="${HANSOS_MP01_STATE_DIR:-${REPO_ROOT}/logs/mp01-state-$(date +%Y%m%d-%H%M%S)}"
INCLUDE_FASTBOOT=false

usage() {
  cat <<'USAGE'
usage: mp01-capture-state.sh [--serial SERIAL] [--fastboot]

Capture stock/bring-up state for the Minimal Phone MP01 before and after
unlock/flash steps. By default this is adb-only and non-destructive.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial)
      SERIAL="$2"
      shift 2
      ;;
    --fastboot)
      INCLUDE_FASTBOOT=true
      shift
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

if [[ ! -x "${ADB}" ]]; then
  echo "adb not found: ${ADB}" >&2
  exit 1
fi

if [[ "${INCLUDE_FASTBOOT}" == "true" && ( -z "${FASTBOOT}" || ! -x "${FASTBOOT}" ) ]]; then
  echo "fastboot not found: ${FASTBOOT}" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

run_adb() {
  if [[ -n "${SERIAL}" ]]; then
    "${ADB}" -s "${SERIAL}" "$@"
  else
    "${ADB}" "$@"
  fi
}

select_mp01() {
  if [[ -n "${SERIAL}" ]]; then
    return
  fi
  local devices
  devices="$("${ADB}" devices | awk 'NR > 1 && $2 == "device" {print $1}')"
  local candidates=""
  local serial
  while IFS= read -r serial; do
    [[ -z "${serial}" ]] && continue
    local model
    model="$("${ADB}" -s "${serial}" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
    if [[ "${model}" == "MP01" ]]; then
      candidates+="${serial}"$'\n'
    fi
  done <<< "${devices}"
  local count
  count="$(printf "%s\n" "${candidates}" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "${count}" != "1" ]]; then
    echo "Expected exactly one authorized MP01 device; found ${count}" >&2
    "${ADB}" devices -l >&2
    exit 1
  fi
  SERIAL="$(printf "%s\n" "${candidates}" | sed '/^$/d' | head -1)"
}

capture_adb() {
  run_adb wait-for-device
  run_adb devices -l > "${OUT_DIR}/adb-devices.txt"
  run_adb shell getprop > "${OUT_DIR}/getprop.txt"
  run_adb shell getprop ro.product.model > "${OUT_DIR}/model.txt"
  run_adb shell getprop ro.build.fingerprint > "${OUT_DIR}/fingerprint.txt"
  run_adb shell getprop ro.build.description > "${OUT_DIR}/build-description.txt"
  run_adb shell getprop ro.boot.verifiedbootstate > "${OUT_DIR}/verifiedbootstate.txt"
  run_adb shell getprop ro.boot.flash.locked > "${OUT_DIR}/flash-locked.txt"
  run_adb shell getprop ro.boot.vbmeta.device_state > "${OUT_DIR}/vbmeta-device-state.txt"
  run_adb shell getprop ro.boot.slot_suffix > "${OUT_DIR}/slot-suffix.txt"
  run_adb shell getprop ro.treble.enabled > "${OUT_DIR}/treble.txt"
  run_adb shell getprop ro.boot.dynamic_partitions > "${OUT_DIR}/dynamic-partitions.txt"
  run_adb shell df -h > "${OUT_DIR}/df-h.txt"
  run_adb shell mount > "${OUT_DIR}/mount.txt"
  run_adb shell uname -a > "${OUT_DIR}/uname.txt"
  run_adb shell 'ls -la /dev/block/by-name 2>/dev/null || true' > "${OUT_DIR}/by-name.txt"
  run_adb shell 'lpdump 2>/dev/null || true' > "${OUT_DIR}/lpdump.txt"
  run_adb shell 'cat /proc/partitions 2>/dev/null || true' > "${OUT_DIR}/proc-partitions.txt"
}

capture_fastboot() {
  "${FASTBOOT}" devices -l > "${OUT_DIR}/fastboot-devices.txt" 2>&1 || true
  "${FASTBOOT}" getvar all > "${OUT_DIR}/fastboot-getvar-all.txt" 2>&1 || true
}

select_mp01
capture_adb
if [[ "${INCLUDE_FASTBOOT}" == "true" ]]; then
  capture_fastboot
fi

cat > "${OUT_DIR}/summary.txt" <<EOF
MP01 state captured.
serial=${SERIAL}
adb=$("${ADB}" version | head -1)
fastboot=$([[ -n "${FASTBOOT}" ]] && "${FASTBOOT}" --version 2>/dev/null | head -1 || true)
fastboot_included=${INCLUDE_FASTBOOT}
EOF

echo "MP01 state captured in ${OUT_DIR}"
