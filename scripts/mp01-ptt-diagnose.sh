#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

resolve_adb() {
  if [[ -n "${ADB:-}" ]]; then
    command -v "${ADB}" >/dev/null 2>&1 && command -v "${ADB}" && return 0
    [[ -x "${ADB}" ]] && echo "${ADB}" && return 0
  fi
  local candidates=(
    "${ANDROID_HOME:-}/platform-tools/adb"
    "${ANDROID_SDK_ROOT:-}/platform-tools/adb"
    "${HOME}/Library/Android/sdk/platform-tools/adb"
    "${REPO_ROOT}/.work/aosp/out/host/darwin-x86/bin/adb"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  command -v adb
}

usage() {
  cat <<'USAGE'
usage: mp01-ptt-diagnose.sh [--serial SERIAL] [--duration SECONDS]

Captures MP01 hardware key evidence for the HansOS push-to-talk button.
While it runs, hold and release the middle side button once or twice.
USAGE
}

ADB="$(resolve_adb)"
SERIAL="${HANSOS_ADB_SERIAL:-${ANDROID_SERIAL:-}}"
DURATION="${HANSOS_PTT_DIAGNOSE_SECONDS:-20}"
ADB_CALL_TIMEOUT="${HANSOS_ADB_TIMEOUT_SECONDS:-30}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial)
      SERIAL="$2"
      shift 2
      ;;
    --duration)
      DURATION="$2"
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

run_with_timeout() {
  local seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout --foreground "${seconds}" "$@"
  else
    "$@"
  fi
}

adb_cmd() {
  if [[ -n "${SERIAL}" ]]; then
    run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" -s "${SERIAL}" "$@"
  else
    run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" "$@"
  fi
}

ensure_device() {
  if [[ -z "${SERIAL}" ]]; then
    local devices
    devices="$(run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" devices | awk 'NR > 1 && $2 == "device" {print $1}')"
    local count
    count="$(printf "%s\n" "${devices}" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [[ "${count}" == "1" ]]; then
      SERIAL="$(printf "%s\n" "${devices}" | sed '/^$/d' | head -1)"
    else
      echo "Set --serial; found ${count} adb devices." >&2
      run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" devices >&2
      exit 1
    fi
  fi
  run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" -s "${SERIAL}" wait-for-device
}

ensure_device

echo "HansOS MP01 PTT diagnose on ${SERIAL}"
echo "1. Press and hold the middle side button."
echo "2. Release it."
echo "3. Repeat once if possible."
echo
echo "Input devices:"
adb_cmd shell 'for f in /dev/input/event*; do getevent -i "$f" 2>/dev/null | sed -n "1,10p"; done' | tr -d '\r'
echo
echo "Current keylayout hints:"
adb_cmd shell 'cat /system/usr/keylayout/aw9523b-key.kl /system/usr/keylayout/Generic.kl 2>/dev/null | grep -E "key +(249|250|251|252|582|583|115|114|116)" || true' | tr -d '\r'
echo
echo "Capturing getevent for ${DURATION}s..."
adb_cmd shell "timeout ${DURATION} getevent -l -t 2>/dev/null" | tr -d '\r' || true
echo
echo "Hans diagnostics after capture:"
adb_cmd shell dumpsys hans voice | tr -d '\r' || true
