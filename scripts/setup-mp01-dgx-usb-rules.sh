#!/usr/bin/env bash
set -euo pipefail

RULES_PATH="${HANSOS_MP01_UDEV_RULES_PATH:-/etc/udev/rules.d/51-hansos-mp01.rules}"
DRY_RUN=false

usage() {
  cat <<'USAGE'
usage: setup-mp01-dgx-usb-rules.sh [--dry-run]

Install Linux udev rules for the Minimal Phone MP01 bring-up path.
The rules cover:
  - ALONG/Minimal Phone MP01 normal USB: 0e8d:201c
  - MediaTek boot/preloader style USB: 0e8d
  - Google/Android fastboot style USB: 18d1

This does not flash or unlock the phone. It only prevents Linux permissions from
being the next blocker after the phone is electrically visible.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
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

rules_content() {
  cat <<'RULES'
# HansOS Minimal Phone MP01 bring-up USB rules.
# Normal MP01 USB, observed on macOS as decimal 3725:8220.
# Linux udev reports USB IDs in hexadecimal: 0e8d:201c.
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="201c", MODE="0666", GROUP="plugdev", TAG+="uaccess"

# MediaTek boot/preloader and Android/fastboot fallback IDs seen on many MP01-class flows.
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev", TAG+="uaccess"
RULES
}

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "Would install ${RULES_PATH}:"
  rules_content
  exit 0
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo not found; rerun as root or install manually:" >&2
  rules_content >&2
  exit 1
fi

tmp="$(mktemp)"
rules_content > "${tmp}"
sudo install -m 0644 -o root -g root "${tmp}" "${RULES_PATH}"
rm -f "${tmp}"

if command -v udevadm >/dev/null 2>&1; then
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=usb || true
fi

echo "Installed MP01 USB rules at ${RULES_PATH}"
