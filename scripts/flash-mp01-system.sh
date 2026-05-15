#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'USAGE'
usage: flash-mp01-system.sh --image /path/to/system.img [--serial SERIAL]
                            [--from-adb|--from-fastboot]
                            [--direct-bootloader]
                            [--sparse-size SIZE]
                            [--unlock] [--skip-capture] [--no-wipe]

Flashes a HansOS/Treble system.img to the Minimal Phone MP01.

The script can start from an authorized adb device or from an MP01 already in
bootloader fastboot / fastbootd. Unlocking still requires the phone-side
confirmation screen when the bootloader asks for it.

By default the script erases userdata and metadata after flashing system. The
public MP01 GSI flow requires this cleanup, and skipping it can leave the phone
in a repeat boot loop after a valid system flash.

Use --direct-bootloader when the MP01 bootloader accepts direct GSI system
flashing but adb reboot fastboot / fastbootd falls back to Android.

Use --sparse-size 64M or HANSOS_MP01_FASTBOOT_SPARSE_SIZE=64M when macOS
Fastboot loses the USB connection while sending a large system image.
USAGE
}

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
    "${HOME}/hansos-work/out/aosp-android14/host/linux-arm64/bin/${name}"
    "${HOME}/hansos-work/out/los22-hansos/host/linux-arm64/bin/${name}"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  local resolved
  resolved="$(command -v "${name}" 2>/dev/null || true)"
  if [[ -n "${resolved}" ]]; then
    echo "${resolved}"
    return 0
  fi

  echo "${name} not found. Set ${env_name}=/path/to/${name}." >&2
  return 1
}

ADB="$(resolve_tool adb ADB)"
FASTBOOT="$(resolve_tool fastboot FASTBOOT)"
SERIAL="${HANSOS_MP01_SERIAL:-${ANDROID_SERIAL:-}}"
IMAGE=""
START_MODE="auto"
START_TRANSPORT=""
UNLOCK=false
SKIP_CAPTURE=false
WIPE_AFTER_FLASH=true
DIRECT_BOOTLOADER_REQUESTED=false
FASTBOOT_SPARSE_SIZE="${HANSOS_MP01_FASTBOOT_SPARSE_SIZE:-}"
FLASH_LOG_DIR="${HANSOS_MP01_FLASH_LOG_DIR:-${REPO_ROOT}/logs/mp01-flash-$(date +%Y%m%d-%H%M%S)}"
CAPTURE_FASTBOOT_GETVAR_ALL="${HANSOS_MP01_CAPTURE_FASTBOOT_GETVAR_ALL:-false}"
FASTBOOT_REBOOT_TIMEOUT_SECONDS="${HANSOS_MP01_FASTBOOT_REBOOT_TIMEOUT_SECONDS:-45}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      IMAGE="$2"
      shift 2
      ;;
    --serial)
      SERIAL="$2"
      shift 2
      ;;
    --from-adb)
      START_MODE="adb"
      shift
      ;;
    --from-fastboot)
      START_MODE="fastboot"
      shift
      ;;
    --direct-bootloader)
      DIRECT_BOOTLOADER_REQUESTED=true
      shift
      ;;
    --sparse-size)
      FASTBOOT_SPARSE_SIZE="$2"
      shift 2
      ;;
    --unlock)
      UNLOCK=true
      shift
      ;;
    --skip-capture)
      SKIP_CAPTURE=true
      shift
      ;;
    --no-wipe)
      WIPE_AFTER_FLASH=false
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

if [[ -z "${IMAGE}" || ! -f "${IMAGE}" ]]; then
  echo "Missing system image. Pass --image /path/to/system.img." >&2
  exit 2
fi

adb_cmd() {
  if [[ -n "${SERIAL}" ]]; then
    "${ADB}" -s "${SERIAL}" "$@"
  else
    "${ADB}" "$@"
  fi
}

fastboot_cmd() {
  if [[ -n "${SERIAL}" ]]; then
    "${FASTBOOT}" -s "${SERIAL}" "$@"
  else
    "${FASTBOOT}" "$@"
  fi
}

fastboot_cmd_with_alarm() {
  local timeout="$1"
  shift
  if [[ -n "${SERIAL}" ]]; then
    perl -e 'my $timeout = shift; alarm $timeout; exec @ARGV' "${timeout}" "${FASTBOOT}" -s "${SERIAL}" "$@"
  else
    perl -e 'my $timeout = shift; alarm $timeout; exec @ARGV' "${timeout}" "${FASTBOOT}" "$@"
  fi
}

adb_state_for_serial() {
  "${ADB}" -s "$1" get-state 2>/dev/null | tr -d '\r' || true
}

adb_prop_for_serial() {
  local serial="$1"
  local prop="$2"
  "${ADB}" -s "${serial}" shell getprop "${prop}" 2>/dev/null | tr -d '\r' || true
}

fastboot_raw() {
  local serial="$1"
  shift
  if [[ -n "${serial}" ]]; then
    "${FASTBOOT}" -s "${serial}" "$@"
  else
    "${FASTBOOT}" "$@"
  fi
}

fastboot_has_serial() {
  local serial="$1"
  "${FASTBOOT}" devices 2>/dev/null | awk '{print $1}' | grep -qx "${serial}"
}

fastboot_getvar_for_serial() {
  local serial="$1"
  local var="$2"
  fastboot_raw "${serial}" getvar "${var}" 2>&1 | sed -nE "s/^\\(bootloader\\)[[:space:]]*${var}:[[:space:]]*(.*)$/\\1/p; s/^${var}:[[:space:]]*(.*)$/\\1/p" | tail -1 | tr -d '\r'
}

is_mp01_fastboot_product() {
  local product="$1"
  # The MP01 bootloader reports the platform alias Z10, while fastbootd reports MP01.
  [[ "${product}" == "MP01" || "${product}" == "Z10" ]]
}

fastboot_is_userspace() {
  local value
  value="$(fastboot_getvar_for_serial "${SERIAL}" "is-userspace" || true)"
  [[ "${value}" == "yes" ]]
}

verify_fastboot_mp01() {
  local serial="$1"
  local product
  product="$(fastboot_getvar_for_serial "${serial}" "product" || true)"
  if ! is_mp01_fastboot_product "${product}"; then
    echo "Connected fastboot device is product=${product:-unknown}, expected MP01/Z10." >&2
    return 1
  fi
}

choose_mp01_serial() {
  if [[ -n "${SERIAL}" ]]; then
    if [[ "${START_MODE}" != "fastboot" && "$(adb_state_for_serial "${SERIAL}")" == "device" ]]; then
      local model
      local device
      model="$(adb_prop_for_serial "${SERIAL}" ro.product.model)"
      device="$(adb_prop_for_serial "${SERIAL}" ro.product.device)"
      if [[ "${model}" == "MP01" && "${device}" == "MP01" ]]; then
        START_TRANSPORT="adb"
        return 0
      fi
      if [[ "${START_MODE}" == "adb" ]]; then
        echo "Connected adb device is model=${model} device=${device}, expected MP01." >&2
        exit 1
      fi
    fi

    if [[ "${START_MODE}" != "adb" ]] && fastboot_has_serial "${SERIAL}"; then
      verify_fastboot_mp01 "${SERIAL}" || exit 1
      START_TRANSPORT="fastboot"
      return 0
    fi

    echo "MP01 serial ${SERIAL} is not available over ${START_MODE}." >&2
    "${ADB}" devices -l >&2 || true
    "${FASTBOOT}" devices -l >&2 || true
    exit 1
  fi

  local devices
  local candidates=()
  if [[ "${START_MODE}" != "fastboot" ]]; then
    devices="$("${ADB}" devices | awk 'NR > 1 && $2 == "device" {print $1}')"
    local serial
    while IFS= read -r serial; do
      [[ -z "${serial}" ]] && continue
      local model
      model="$(adb_prop_for_serial "${serial}" ro.product.model)"
      if [[ "${model}" == "MP01" ]]; then
        candidates+=("${serial}")
      fi
    done <<< "${devices}"
    if [[ "${#candidates[@]}" -eq 1 ]]; then
      SERIAL="${candidates[0]}"
      START_TRANSPORT="adb"
      return 0
    fi
    if [[ "${START_MODE}" == "adb" ]]; then
      echo "Expected exactly one authorized MP01 over adb; found ${#candidates[@]}." >&2
      "${ADB}" devices -l >&2
      exit 1
    fi
  fi

  candidates=()
  if [[ "${START_MODE}" != "adb" ]]; then
    devices="$("${FASTBOOT}" devices 2>/dev/null | awk 'NF {print $1}')"
    local serial
    while IFS= read -r serial; do
      [[ -z "${serial}" ]] && continue
      if verify_fastboot_mp01 "${serial}" >/dev/null 2>&1; then
        candidates+=("${serial}")
      fi
    done <<< "${devices}"
  fi
  if [[ "${#candidates[@]}" -ne 1 ]]; then
    echo "Expected exactly one MP01 over adb or fastboot; found ${#candidates[@]} fastboot candidate(s)." >&2
    "${ADB}" devices -l >&2 || true
    "${FASTBOOT}" devices -l >&2 || true
    exit 1
  fi
  SERIAL="${candidates[0]}"
  START_TRANSPORT="fastboot"
}

wait_fastboot_status() {
  local timeout="${1:-90}"
  local elapsed=0
  while [[ "${elapsed}" -lt "${timeout}" ]]; do
    if fastboot_cmd devices | awk '{print $1}' | grep -qx "${SERIAL}"; then
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  return 1
}

wait_fastboot() {
  local timeout="${1:-90}"
  if wait_fastboot_status "${timeout}"; then
    return 0
  fi
  echo "Timed out waiting for MP01 in fastboot: ${SERIAL}" >&2
  exit 1
}

sha256_image() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${IMAGE}" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${IMAGE}" | awk '{print $1}'
  else
    echo "sha256-tool-missing"
  fi
}

capture_fastboot_state() {
  local label="$1"
  mkdir -p "${FLASH_LOG_DIR}"
  fastboot_cmd devices -l > "${FLASH_LOG_DIR}/${label}-devices.txt" 2>&1 || true
  if [[ "${CAPTURE_FASTBOOT_GETVAR_ALL}" == "true" ]]; then
    fastboot_cmd getvar all > "${FLASH_LOG_DIR}/${label}-getvar-all.txt" 2>&1 || true
  fi
}

choose_mp01_serial

mkdir -p "${FLASH_LOG_DIR}"
sha256_image > "${FLASH_LOG_DIR}/system-img-sha256.txt"

if [[ "${START_TRANSPORT}" == "adb" ]]; then
  "${ADB}" -s "${SERIAL}" wait-for-device
  model="$(adb_cmd shell getprop ro.product.model 2>/dev/null | tr -d '\r')"
  device="$(adb_cmd shell getprop ro.product.device 2>/dev/null | tr -d '\r')"
  if [[ "${model}" != "MP01" || "${device}" != "MP01" ]]; then
    echo "Connected adb device is model=${model} device=${device}, expected MP01." >&2
    exit 1
  fi
  adb_cmd shell getprop > "${FLASH_LOG_DIR}/adb-preflash-getprop.txt" || true
elif [[ "${START_TRANSPORT}" == "fastboot" ]]; then
  verify_fastboot_mp01 "${SERIAL}" || exit 1
else
  echo "Internal error: no MP01 transport selected." >&2
  exit 1
fi

echo "MP01 flash preflight:"
echo "  serial:    ${SERIAL}"
echo "  transport: ${START_TRANSPORT}"
echo "  image:     ${IMAGE}"
echo "  sha256:    $(sha256_image)"
echo "  logdir:    ${FLASH_LOG_DIR}"

if [[ "${START_TRANSPORT}" == "adb" ]]; then
  if [[ "${SKIP_CAPTURE}" != "true" ]]; then
    ADB="${ADB}" FASTBOOT="${FASTBOOT}" "${SCRIPT_DIR}/mp01-capture-state.sh" --serial "${SERIAL}" >/dev/null
  fi
  adb_cmd reboot bootloader
  wait_fastboot 120
  capture_fastboot_state "before-unlock"
else
  capture_fastboot_state "initial-fastboot"
fi

if [[ "${UNLOCK}" == "true" ]]; then
  if fastboot_is_userspace; then
    echo "Rebooting from fastbootd to bootloader before unlock."
    fastboot_cmd reboot bootloader
    wait_fastboot 120
  fi
  echo "Requesting bootloader unlock. Confirm on the MP01 if prompted."
  fastboot_cmd flashing unlock || {
    echo "Unlock command did not complete. If the phone is asking, confirm on-device and rerun the flash step." >&2
    exit 1
  }
  wait_fastboot 120
  capture_fastboot_state "after-unlock"
fi

DIRECT_BOOTLOADER_FLASH=false
if [[ "${DIRECT_BOOTLOADER_REQUESTED}" == "true" ]]; then
  echo "Using direct bootloader fastboot system flashing."
  DIRECT_BOOTLOADER_FLASH=true
elif fastboot_is_userspace; then
  echo "MP01 is already in fastbootd."
else
  echo "Switching to fastbootd for dynamic partition flashing."
  set +e
  fastboot_cmd_with_alarm "${FASTBOOT_REBOOT_TIMEOUT_SECONDS}" reboot fastboot
  reboot_fastboot_ec=$?
  set -e
  if [[ "${reboot_fastboot_ec}" -ne 0 ]]; then
    echo "fastboot reboot fastboot did not complete cleanly (exit ${reboot_fastboot_ec})."
  fi

  if wait_fastboot_status 120 && fastboot_is_userspace; then
    echo "MP01 entered fastbootd."
  else
    echo "MP01 did not enter fastbootd; falling back to bootloader fastboot system flashing."
    if [[ "$(adb_state_for_serial "${SERIAL}")" == "device" ]]; then
      adb_cmd reboot bootloader
    fi
    wait_fastboot 120
    verify_fastboot_mp01 "${SERIAL}" || exit 1
    DIRECT_BOOTLOADER_FLASH=true
  fi
fi
if [[ "${DIRECT_BOOTLOADER_FLASH}" == "true" ]]; then
  capture_fastboot_state "bootloader-before-flash"
else
  capture_fastboot_state "fastbootd-before-flash"
fi

echo "Flashing system image to MP01."
if [[ -n "${FASTBOOT_SPARSE_SIZE}" ]]; then
  echo "Using fastboot sparse transfer size: ${FASTBOOT_SPARSE_SIZE}"
  fastboot_cmd -S "${FASTBOOT_SPARSE_SIZE}" flash system "${IMAGE}"
else
  fastboot_cmd flash system "${IMAGE}"
fi

if [[ "${WIPE_AFTER_FLASH}" == "true" ]]; then
  echo "Erasing userdata and metadata for a clean MP01 GSI first boot."
  fastboot_cmd erase userdata
  fastboot_cmd erase metadata
fi

echo "Rebooting MP01."
fastboot_cmd reboot
echo "MP01 flash command sequence finished; first boot can take several minutes."
