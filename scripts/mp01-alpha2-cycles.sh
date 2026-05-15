#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'USAGE'
usage: mp01-alpha2-cycles.sh --image /path/to/system.img [options]

Run repeatable MP01 Alpha 2 validation cycles on the active USB host.
Each cycle flashes system.img, wipes userdata/metadata, boots, runs the full
MP01 smoke with baked-HOME enforcement, reboots once, and checks persistence.

Options:
  --image PATH             system.img to flash.
  --serial SERIAL          MP01 serial. Default: HANSOS_MP01_SERIAL/ANDROID_SERIAL.
  --cycles N               Number of cycles. Default: 3.
  --fastboot PATH          fastboot binary. Default: FASTBOOT or PATH lookup.
  --adb PATH               adb binary. Default: ADB or PATH lookup.
  --log-dir PATH           Log directory. Default: logs/mp01-alpha2-<timestamp>.
  --no-reboot-check        Skip post-smoke reboot persistence check.
USAGE
}

IMAGE=""
SERIAL="${HANSOS_MP01_SERIAL:-${ANDROID_SERIAL:-MP0125031802636}}"
CYCLES="${HANSOS_MP01_ALPHA2_CYCLES:-3}"
LOG_DIR="${HANSOS_MP01_ALPHA2_LOG_DIR:-${REPO_ROOT}/logs/mp01-alpha2-$(date +%Y%m%d-%H%M%S)}"
RUN_REBOOT_CHECK=true

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
    --cycles)
      CYCLES="$2"
      shift 2
      ;;
    --fastboot)
      export FASTBOOT="$2"
      shift 2
      ;;
    --adb)
      export ADB="$2"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="$2"
      shift 2
      ;;
    --no-reboot-check)
      RUN_REBOOT_CHECK=false
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

mkdir -p "${LOG_DIR}"

run_logged() {
  local log="$1"
  shift
  set +e
  "$@" 2>&1 | tee "${log}"
  local ec=${PIPESTATUS[0]}
  set -e
  echo "exit=${ec}" | tee -a "${log}"
  return "${ec}"
}

adb_tool() {
  if [[ -n "${ADB:-}" ]]; then
    echo "${ADB}"
  elif command -v adb >/dev/null 2>&1; then
    command -v adb
  else
    echo "adb"
  fi
}

check_post_reboot() {
  local cycle_dir="$1"
  local adb_bin
  adb_bin="$(adb_tool)"
  "${adb_bin}" -s "${SERIAL}" reboot
  "${adb_bin}" -s "${SERIAL}" wait-for-device
  local deadline=$(( $(date +%s) + 600 ))
  while [[ "$(date +%s)" -lt "${deadline}" ]]; do
    if [[ "$("${adb_bin}" -s "${SERIAL}" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; then
      break
    fi
    sleep 2
  done
  {
    echo "adb:"
    "${adb_bin}" devices -l
    echo "boot:"
    "${adb_bin}" -s "${SERIAL}" shell 'getprop sys.boot_completed; getprop dev.bootcomplete; getprop ro.build.fingerprint'
    echo "home:"
    "${adb_bin}" -s "${SERIAL}" shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME
    echo "hans:"
    "${adb_bin}" -s "${SERIAL}" shell 'service list | grep -i hans; dumpsys hans | head -20'
  } > "${cycle_dir}/post-reboot.txt" 2>&1
  grep -q "ai.hansos.canvas/.HansCanvasActivity" "${cycle_dir}/post-reboot.txt"
  grep -q "runtime=true" "${cycle_dir}/post-reboot.txt"
}

echo "MP01 Alpha 2 cycles"
echo "  serial: ${SERIAL}"
echo "  image:  ${IMAGE}"
echo "  cycles: ${CYCLES}"
echo "  logs:   ${LOG_DIR}"

for cycle in $(seq 1 "${CYCLES}"); do
  cycle_dir="${LOG_DIR}/cycle-${cycle}"
  mkdir -p "${cycle_dir}"
  echo "=== cycle ${cycle}/${CYCLES}: flash ==="
  run_logged "${cycle_dir}/flash.log" \
    "${SCRIPT_DIR}/flash-mp01-system.sh" \
      --serial "${SERIAL}" \
      --image "${IMAGE}"

  echo "=== cycle ${cycle}/${CYCLES}: smoke ==="
  run_logged "${cycle_dir}/smoke.log" \
    "${SCRIPT_DIR}/smoke-mp01.sh" \
      --serial "${SERIAL}" \
      --boot-timeout 900 \
      --include-degraded \
      --require-baked-home \
      --verbose

  if [[ "${RUN_REBOOT_CHECK}" == "true" ]]; then
    echo "=== cycle ${cycle}/${CYCLES}: post-reboot check ==="
    check_post_reboot "${cycle_dir}"
  fi
done

echo "MP01 Alpha 2 cycles passed: ${CYCLES}"
echo "log_dir=${LOG_DIR}"
