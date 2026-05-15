#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'USAGE'
usage: watch-mp01-autoflash.sh --image /path/to/system.img [options]

Watch Mac and DGX USB paths for a Minimal Phone MP01. When exactly one MP01 is
visible over adb or bootloader fastboot / fastbootd, flash the provided HansOS
system.img and run the MP01 smoke test.

Options:
  --image PATH             Local Mac system.img to flash from Mac.
  --serial SERIAL          Restrict to a known MP01 serial.
  --timeout SECONDS        Watch timeout. Default: 1800.
  --interval SECONDS       Poll interval. Default: 10.
  --no-smoke               Flash only; do not run smoke-mp01.sh.
  --dgx-host HOST          SSH host for DGX fallback. Default: yearemias@gx10-1.
  --remote-image PATH      DGX system.img. Default: current HansOS MP01 path.
  --remote-fastboot PATH   DGX fastboot binary. Default: AOSP host fastboot.

This script does not pass --unlock. The current MP01 bring-up state is already
unlocked/orange; rerun unlock only after a fresh preflight proves it is locked.
USAGE
}

LOCAL_IMAGE=""
SERIAL_FILTER="${HANSOS_MP01_SERIAL:-${ANDROID_SERIAL:-}}"
TIMEOUT_SECONDS="${HANSOS_MP01_WATCH_TIMEOUT_SECONDS:-1800}"
INTERVAL_SECONDS="${HANSOS_MP01_WATCH_INTERVAL_SECONDS:-10}"
RUN_SMOKE=true
DGX_HOST="${HANSOS_DGX_HOST:-yearemias@gx10-1}"
REMOTE_IMAGE="${HANSOS_MP01_REMOTE_IMAGE:-/home/yearemias/hansos-work/out/los22-hansos/target/product/tdgsi_arm64_ab/system.img}"
REMOTE_FASTBOOT="${HANSOS_MP01_REMOTE_FASTBOOT:-/home/yearemias/hansos-work/out/aosp-android14/host/linux-arm64/bin/fastboot}"
LOG_DIR="${HANSOS_MP01_AUTOFLASH_LOG_DIR:-${REPO_ROOT}/logs/mp01-autoflash-$(date +%Y%m%d-%H%M%S)}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      LOCAL_IMAGE="$2"
      shift 2
      ;;
    --serial)
      SERIAL_FILTER="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --interval)
      INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --no-smoke)
      RUN_SMOKE=false
      shift
      ;;
    --dgx-host)
      DGX_HOST="$2"
      shift 2
      ;;
    --remote-image)
      REMOTE_IMAGE="$2"
      shift 2
      ;;
    --remote-fastboot)
      REMOTE_FASTBOOT="$2"
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

if [[ -z "${LOCAL_IMAGE}" || ! -f "${LOCAL_IMAGE}" ]]; then
  echo "Missing local system image. Pass --image /path/to/system.img." >&2
  exit 2
fi

mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/watch.log"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "${LOG}"
}

serial_allowed() {
  local serial="$1"
  [[ -z "${SERIAL_FILTER}" || "${serial}" == "${SERIAL_FILTER}" ]]
}

parse_fastboot_product() {
  sed -nE 's/^\(bootloader\)[[:space:]]*product:[[:space:]]*(.*)$/\1/p; s/^product:[[:space:]]*(.*)$/\1/p' | tail -1 | tr -d '\r'
}

is_mp01_fastboot_product() {
  local product="$1"
  [[ "${product}" == "MP01" || "${product}" == "Z10" ]]
}

find_mac_adb_mp01() {
  adb devices | awk 'NR > 1 && $2 == "device" {print $1}' | while read -r serial; do
    [[ -z "${serial}" ]] && continue
    serial_allowed "${serial}" || continue
    local model
    local device
    model="$(adb -s "${serial}" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
    device="$(adb -s "${serial}" shell getprop ro.product.device 2>/dev/null | tr -d '\r' || true)"
    if [[ "${model}" == "MP01" && "${device}" == "MP01" ]]; then
      echo "${serial}"
      return 0
    fi
  done
}

find_mac_fastboot_mp01() {
  fastboot devices 2>/dev/null | awk 'NF {print $1}' | while read -r serial; do
    [[ -z "${serial}" ]] && continue
    serial_allowed "${serial}" || continue
    local product
    product="$(fastboot -s "${serial}" getvar product 2>&1 | parse_fastboot_product)"
    if is_mp01_fastboot_product "${product}"; then
      echo "${serial}"
      return 0
    fi
  done
}

find_dgx_adb_mp01() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${DGX_HOST}" '
    filter="'"${SERIAL_FILTER}"'"
    /usr/bin/adb devices | awk '\''NR > 1 && $2 == "device" {print $1}'\'' | while read -r serial; do
      [ -z "$serial" ] && continue
      if [ -n "$filter" ] && [ "$serial" != "$filter" ]; then
        continue
      fi
      model="$(/usr/bin/adb -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d "\r" || true)"
      device="$(/usr/bin/adb -s "$serial" shell getprop ro.product.device 2>/dev/null | tr -d "\r" || true)"
      if [ "$model" = "MP01" ] && [ "$device" = "MP01" ]; then
        echo "$serial"
        exit 0
      fi
    done
  ' 2>/dev/null | head -1
}

find_dgx_fastboot_mp01() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${DGX_HOST}" '
    filter="'"${SERIAL_FILTER}"'"
    fb="'"${REMOTE_FASTBOOT}"'"
    "$fb" devices 2>/dev/null | awk '\''NF {print $1}'\'' | while read -r serial; do
      [ -z "$serial" ] && continue
      if [ -n "$filter" ] && [ "$serial" != "$filter" ]; then
        continue
      fi
      product="$("$fb" -s "$serial" getvar product 2>&1 | sed -nE '\''s/^\(bootloader\)[[:space:]]*product:[[:space:]]*(.*)$/\1/p; s/^product:[[:space:]]*(.*)$/\1/p'\'' | tail -1 | tr -d "\r")"
      if [ "$product" = "MP01" ] || [ "$product" = "Z10" ]; then
        echo "$serial"
        exit 0
      fi
    done
  ' 2>/dev/null | head -1
}

find_mac_usb_hint() {
  if command -v system_profiler >/dev/null 2>&1; then
    system_profiler SPUSBDataType 2>/dev/null \
      | grep -Ei "MP01|Android|Fastboot|ADB|MediaTek|Minimal|ALONG|Google|MTP|MT[0-9]|Vendor ID: 0x0e8d|Vendor ID: 0x18d1|Vendor ID: 0x3725" -A8 -B5 \
      || true
  fi
}

find_dgx_usb_hint() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${DGX_HOST}" '
    if command -v lsusb >/dev/null 2>&1; then
      lsusb | grep -Ei "MP01|Android|MediaTek|Google|ALONG|0e8d|18d1|3725|8220|fastboot" || true
    fi
  ' 2>/dev/null || true
}

run_mac_flash_and_smoke() {
  local serial="$1"
  local from="$2"
  log "MP01 on Mac via ${from}: ${serial}"
  set +e
  if [[ "${from}" == "fastboot" ]]; then
    "${SCRIPT_DIR}/flash-mp01-system.sh" --serial "${serial}" --from-fastboot --image "${LOCAL_IMAGE}" 2>&1 | tee -a "${LOG}"
  else
    "${SCRIPT_DIR}/flash-mp01-system.sh" --serial "${serial}" --image "${LOCAL_IMAGE}" 2>&1 | tee -a "${LOG}"
  fi
  local ec=$?
  set -e
  log "flash_exit=${ec}"
  [[ "${ec}" -eq 0 ]] || return "${ec}"
  if [[ "${RUN_SMOKE}" == "true" ]]; then
    log "Waiting for MP01 first boot on Mac ADB"
    set +e
    adb -s "${serial}" wait-for-device 2>&1 | tee -a "${LOG}"
    "${SCRIPT_DIR}/smoke-mp01.sh" --serial "${serial}" --boot-timeout 900 --include-degraded --verbose 2>&1 | tee -a "${LOG}"
    ec=$?
    set -e
    log "smoke_exit=${ec}"
    return "${ec}"
  fi
}

run_dgx_flash_and_smoke() {
  local serial="$1"
  local from="$2"
  log "MP01 on DGX via ${from}: ${serial}"
  set +e
  if [[ "${from}" == "fastboot" ]]; then
    ssh "${DGX_HOST}" "cd /home/yearemias/hansos-overlay && ADB=/usr/bin/adb FASTBOOT=${REMOTE_FASTBOOT} scripts/flash-mp01-system.sh --serial '${serial}' --from-fastboot --image '${REMOTE_IMAGE}'" 2>&1 | tee -a "${LOG}"
  else
    ssh "${DGX_HOST}" "cd /home/yearemias/hansos-overlay && ADB=/usr/bin/adb FASTBOOT=${REMOTE_FASTBOOT} scripts/flash-mp01-system.sh --serial '${serial}' --image '${REMOTE_IMAGE}'" 2>&1 | tee -a "${LOG}"
  fi
  local ec=$?
  set -e
  log "remote_flash_exit=${ec}"
  [[ "${ec}" -eq 0 ]] || return "${ec}"
  if [[ "${RUN_SMOKE}" == "true" ]]; then
    log "Waiting for MP01 first boot on DGX ADB"
    set +e
    ssh "${DGX_HOST}" "cd /home/yearemias/hansos-overlay && ADB=/usr/bin/adb scripts/smoke-mp01.sh --serial '${serial}' --boot-timeout 900 --include-degraded --verbose" 2>&1 | tee -a "${LOG}"
    ec=$?
    set -e
    log "remote_smoke_exit=${ec}"
    return "${ec}"
  fi
}

log "MP01 autoflash watcher started. log=${LOG}"
log "image=${LOCAL_IMAGE}"
log "timeout=${TIMEOUT_SECONDS}s interval=${INTERVAL_SECONDS}s serial=${SERIAL_FILTER:-auto}"

deadline=$(( $(date +%s) + TIMEOUT_SECONDS ))
last_status=0
last_usb_hint=""
while [[ "$(date +%s)" -lt "${deadline}" ]]; do
  serial="$(find_mac_adb_mp01 || true)"
  if [[ -n "${serial}" ]]; then
    run_mac_flash_and_smoke "${serial}" "adb"
    exit $?
  fi

  serial="$(find_mac_fastboot_mp01 || true)"
  if [[ -n "${serial}" ]]; then
    run_mac_flash_and_smoke "${serial}" "fastboot"
    exit $?
  fi

  serial="$(find_dgx_adb_mp01 || true)"
  if [[ -n "${serial}" ]]; then
    run_dgx_flash_and_smoke "${serial}" "adb"
    exit $?
  fi

  serial="$(find_dgx_fastboot_mp01 || true)"
  if [[ -n "${serial}" ]]; then
    run_dgx_flash_and_smoke "${serial}" "fastboot"
    exit $?
  fi

  now="$(date +%s)"
  if [[ "$((now - last_status))" -ge 60 ]]; then
    usb_hint="$( { find_mac_usb_hint; find_dgx_usb_hint; } | sed '/^$/d' | head -20 )"
    if [[ -n "${usb_hint}" ]]; then
      if [[ "${usb_hint}" != "${last_usb_hint}" ]]; then
        log "USB-level Android/MP01-like hint seen, but adb/fastboot is not ready yet:"
        while IFS= read -r line; do
          log "  ${line}"
        done <<< "${usb_hint}"
        last_usb_hint="${usb_hint}"
      else
        log "USB-level hint still present, but adb/fastboot is not ready yet."
      fi
    else
      log "No MP01 visible on Mac or DGX yet; no Android-like USB device is electrically visible either."
    fi
    last_status="${now}"
  fi
  sleep "${INTERVAL_SECONDS}"
done

log "Timed out waiting for MP01 USB visibility."
exit 124
