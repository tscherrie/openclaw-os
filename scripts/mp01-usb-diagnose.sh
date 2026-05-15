#!/usr/bin/env bash
set -euo pipefail

SERIAL_FILTER="${HANSOS_MP01_SERIAL:-${ANDROID_SERIAL:-}}"
DGX_HOST="${HANSOS_DGX_HOST:-yearemias@gx10-1}"
REMOTE_FASTBOOT="${HANSOS_MP01_REMOTE_FASTBOOT:-/home/yearemias/hansos-work/out/aosp-android14/host/linux-arm64/bin/fastboot}"
VERBOSE=false

usage() {
  cat <<'USAGE'
usage: mp01-usb-diagnose.sh [--serial SERIAL] [--dgx-host HOST] [--verbose]

Non-destructive MP01 USB visibility diagnostic across the Mac and the DGX host.
It checks adb, fastboot, and lower-level USB enumeration so bring-up can tell a
tool issue from a physical cable or device-mode issue.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial)
      SERIAL_FILTER="$2"
      shift 2
      ;;
    --dgx-host)
      DGX_HOST="$2"
      shift 2
      ;;
    --verbose)
      VERBOSE=true
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

section() {
  printf "\n== %s ==\n" "$1"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

serial_allowed() {
  local serial="$1"
  [[ -z "${SERIAL_FILTER}" || "${serial}" == "${SERIAL_FILTER}" ]]
}

parse_fastboot_product() {
  sed -nE 's/^\(bootloader\)[[:space:]]*product:[[:space:]]*(.*)$/\1/p; s/^product:[[:space:]]*(.*)$/\1/p' | tail -1 | tr -d '\r'
}

MAC_READY=false
DGX_READY=false
MAC_USB_HINT=false
DGX_USB_HINT=false

section "Mac adb"
if have adb; then
  adb devices -l || true
  while IFS= read -r serial; do
    [[ -z "${serial}" ]] && continue
    serial_allowed "${serial}" || continue
    model="$(adb -s "${serial}" shell getprop ro.product.model 2>/dev/null | tr -d "\r" || true)"
    device="$(adb -s "${serial}" shell getprop ro.product.device 2>/dev/null | tr -d "\r" || true)"
    if [[ "${model}" == "MP01" && "${device}" == "MP01" ]]; then
      echo "Mac adb MP01: ${serial}"
      MAC_READY=true
    fi
  done < <(adb devices | awk 'NR > 1 && $2 == "device" {print $1}')
else
  echo "adb not found on Mac PATH"
fi

section "Mac fastboot"
if have fastboot; then
  fastboot devices -l 2>/dev/null || true
  while IFS= read -r serial; do
    [[ -z "${serial}" ]] && continue
    serial_allowed "${serial}" || continue
    product="$(fastboot -s "${serial}" getvar product 2>&1 | parse_fastboot_product || true)"
    if [[ "${product}" == "MP01" || "${product}" == "Z10" ]]; then
      echo "Mac fastboot MP01: ${serial}"
      MAC_READY=true
    fi
  done < <(fastboot devices 2>/dev/null | awk 'NF {print $1}')
else
  echo "fastboot not found on Mac PATH"
fi

section "Mac USB"
if have system_profiler; then
  mac_usb="$(system_profiler SPUSBDataType 2>/dev/null | grep -Ei "MP01|Android|Fastboot|ADB|MediaTek|Minimal|ALONG|Google|MTP|MT[0-9]|Vendor ID: 0x0e8d|Vendor ID: 0x18d1|Vendor ID: 0x3725" -A8 -B5 || true)"
  if [[ -n "${mac_usb}" ]]; then
    MAC_USB_HINT=true
    printf "%s\n" "${mac_usb}"
  else
    echo "No MP01/Android/Fastboot-like USB device in system_profiler."
  fi
else
  echo "system_profiler unavailable"
fi

if [[ "${VERBOSE}" == "true" ]] && have ioreg; then
  echo
  echo "-- ioreg USB hints --"
  ioreg -p IOUSB -l -w 0 2>/dev/null | grep -Ei "MP01|Android|Fastboot|MediaTek|ALONG|Minimal|idVendor|idProduct|USB Product Name|USB Vendor Name" -A3 -B3 | head -240 || true
fi

section "DGX adb/fastboot/USB"
dgx_output="$(ssh -o BatchMode=yes -o ConnectTimeout=10 "${DGX_HOST}" "REMOTE_FASTBOOT='${REMOTE_FASTBOOT}' bash -s" 2>/dev/null <<'REMOTE' || true
set +e
echo --adb--
/usr/bin/adb devices -l
echo --adb-mp01--
/usr/bin/adb devices | awk 'NR > 1 && $2 == "device" {print $1}' | while read -r serial; do
  [ -z "$serial" ] && continue
  model="$(/usr/bin/adb -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d "\r" || true)"
  device="$(/usr/bin/adb -s "$serial" shell getprop ro.product.device 2>/dev/null | tr -d "\r" || true)"
  if [ "$model" = MP01 ] && [ "$device" = MP01 ]; then echo "$serial"; fi
done
echo --fastboot--
fb="${REMOTE_FASTBOOT}"
if [ -x "$fb" ]; then
  "$fb" devices -l 2>/dev/null || true
  echo --fastboot-mp01--
  "$fb" devices 2>/dev/null | awk 'NF {print $1}' | while read -r serial; do
    [ -z "$serial" ] && continue
    product="$("$fb" -s "$serial" getvar product 2>&1 | sed -nE 's/^\(bootloader\)[[:space:]]*product:[[:space:]]*(.*)$/\1/p; s/^product:[[:space:]]*(.*)$/\1/p' | tail -1 | tr -d "\r")"
    if [ "$product" = MP01 ] || [ "$product" = Z10 ]; then echo "$serial"; fi
  done
else
  echo "fastboot not found: $fb"
  echo --fastboot-mp01--
fi
echo --lsusb--
if command -v lsusb >/dev/null 2>&1; then
  lsusb | grep -Ei "MP01|Android|MediaTek|Google|ALONG|0e8d|18d1|3725" || true
else
  echo lsusb not found
fi
REMOTE
)"
printf "%s\n" "${dgx_output}"

if printf "%s\n" "${dgx_output}" | awk '/--adb-mp01--/ {capture=1; next} /--fastboot--/ {capture=0} capture && NF {found=1} END {exit found ? 0 : 1}'; then
  DGX_READY=true
fi
if printf "%s\n" "${dgx_output}" | awk '/--fastboot-mp01--/ {capture=1; next} /--lsusb--/ {capture=0} capture && NF {found=1} END {exit found ? 0 : 1}'; then
  DGX_READY=true
fi
if printf "%s\n" "${dgx_output}" | awk '/--lsusb--/ {capture=1; next} capture && NF {found=1} END {exit found ? 0 : 1}'; then
  DGX_USB_HINT=true
fi

section "Summary"
if [[ "${MAC_READY}" == "true" ]]; then
  echo "Mac: MP01 is ready for flash/smoke automation."
elif [[ "${MAC_USB_HINT}" == "true" ]]; then
  echo "Mac: Android-like USB is electrically visible, but adb/fastboot is not ready."
else
  echo "Mac: no MP01/Android/Fastboot USB visibility."
fi

if [[ "${DGX_READY}" == "true" ]]; then
  echo "DGX: MP01 is ready for flash/smoke automation."
elif [[ "${DGX_USB_HINT}" == "true" ]]; then
  echo "DGX: Android-like USB is electrically visible, but adb/fastboot is not ready."
else
  echo "DGX: no MP01/Android/Fastboot USB visibility."
fi

if [[ "${MAC_READY}" == "true" || "${DGX_READY}" == "true" ]]; then
  exit 0
fi

echo "Not ready: make the MP01 visible over USB on Mac or DGX, then rerun this diagnostic."
exit 1
