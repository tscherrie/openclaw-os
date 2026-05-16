#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

host_tag() {
  case "$(uname -s)-$(uname -m)" in
    Linux-aarch64|Linux-arm64)
      echo "linux-arm64"
      ;;
    Linux-x86_64)
      echo "linux-x86"
      ;;
    Darwin-*)
      echo "darwin-x86"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

resolve_adb() {
  if [[ -n "${ADB:-}" ]]; then
    if [[ -x "${ADB}" ]]; then
      echo "${ADB}"
      return 0
    fi
    local resolved
    resolved="$(command -v "${ADB}" 2>/dev/null || true)"
    if [[ -n "${resolved}" ]]; then
      echo "${resolved}"
      return 0
    fi
    echo "Configured ADB not found: ${ADB}" >&2
    return 1
  fi

  local tag
  tag="$(host_tag)"
  local aosp_name
  aosp_name="$(basename "${AOSP_ROOT:-aosp}")"
  local out_base="${OUT_DIR_COMMON_BASE:-}"
  if [[ -z "${out_base}" && -n "${HANSOS_EXTERNAL_ROOT:-}" ]]; then
    out_base="${HANSOS_EXTERNAL_ROOT}/out"
  fi

  local candidates=(
    "${ANDROID_HOST_OUT:-}/bin/adb"
    "${out_base}/${aosp_name}/host/${tag}/bin/adb"
    "${out_base}/host/${tag}/bin/adb"
    "${REPO_ROOT}/.work/out/${aosp_name}/host/${tag}/bin/adb"
    "${REPO_ROOT}/.work/aosp/out/host/${tag}/bin/adb"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  local resolved
  resolved="$(command -v adb 2>/dev/null || true)"
  if [[ -n "${resolved}" ]]; then
    echo "${resolved}"
    return 0
  fi

  echo "adb not found. Build host tools first or set ADB=/path/to/adb." >&2
  return 1
}

ADB="$(resolve_adb)"
SERIAL="${HANSOS_ADB_SERIAL:-${ANDROID_SERIAL:-}}"
CONNECT_SERIAL="${HANSOS_ADB_CONNECT:-}"
ITERATIONS="${HANSOS_SMOKE_ITERATIONS:-1}"
INCLUDE_DEGRADED="${HANSOS_SMOKE_INCLUDE_DEGRADED:-false}"
INCLUDE_CANVAS_BRIDGE="${HANSOS_SMOKE_INCLUDE_CANVAS_BRIDGE:-true}"
VERBOSE="${HANSOS_SMOKE_VERBOSE:-false}"
ADB_CALL_TIMEOUT="${HANSOS_ADB_TIMEOUT_SECONDS:-25}"
ADB_WAIT_TIMEOUT="${HANSOS_ADB_WAIT_TIMEOUT_SECONDS:-90}"
INPUT_BRIDGE="${HANSOS_INPUT_BRIDGE:-${SCRIPT_DIR}/hans-input-bridge.sh}"

usage() {
  cat <<'USAGE'
usage: smoke-cuttlefish.sh [--serial SERIAL] [--connect SERIAL] [--iterations N]
                           [--include-degraded|--skip-degraded]
                           [--include-canvas-bridge|--skip-canvas-bridge]
                           [--verbose]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial)
      SERIAL="$2"
      shift 2
      ;;
    --connect)
      CONNECT_SERIAL="$2"
      SERIAL="${SERIAL:-$2}"
      shift 2
      ;;
    --iterations)
      ITERATIONS="$2"
      shift 2
      ;;
    --include-degraded)
      INCLUDE_DEGRADED=true
      shift
      ;;
    --skip-degraded)
      INCLUDE_DEGRADED=false
      shift
      ;;
    --include-canvas-bridge)
      INCLUDE_CANVAS_BRIDGE=true
      shift
      ;;
    --skip-canvas-bridge)
      INCLUDE_CANVAS_BRIDGE=false
      shift
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

if ! [[ "${ITERATIONS}" =~ ^[0-9]+$ ]] || [[ "${ITERATIONS}" -lt 1 ]]; then
  echo "--iterations must be a positive integer" >&2
  exit 2
fi

restore_runtime() {
  if [[ "${RUNTIME_DISABLED:-false}" == "true" ]]; then
    adb_cmd shell pm enable ai.hansos.runtime >/dev/null 2>&1 || true
    adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null 2>&1 || true
  fi
}
trap restore_runtime EXIT

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

bridge_cmd() {
  if command -v timeout >/dev/null 2>&1; then
    ADB="${ADB}" timeout --foreground "${ADB_CALL_TIMEOUT}" \
      "${INPUT_BRIDGE}" --serial "${SERIAL}" "$@"
  else
    ADB="${ADB}" "${INPUT_BRIDGE}" --serial "${SERIAL}" "$@"
  fi
}

ensure_device() {
  if [[ -n "${CONNECT_SERIAL}" ]]; then
    run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" connect "${CONNECT_SERIAL}" >/dev/null || true
  elif [[ -n "${SERIAL}" && "${SERIAL}" == *":"* ]]; then
    run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" connect "${SERIAL}" >/dev/null || true
  fi

  if [[ -z "${SERIAL}" ]]; then
    local devices
    devices="$(run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" devices | awk 'NR > 1 && $2 == "device" {print $1}')"
    local count
    count="$(printf "%s\n" "${devices}" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [[ "${count}" == "1" ]]; then
      SERIAL="$(printf "%s\n" "${devices}" | sed '/^$/d' | head -1)"
    elif [[ "${count}" == "0" ]]; then
      echo "No adb device connected. Set --connect 0.0.0.0:6520 or HANSOS_ADB_SERIAL." >&2
      exit 1
    else
      echo "Multiple adb devices connected. Set --serial explicitly." >&2
      run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" devices >&2
      exit 1
    fi
  fi

  if [[ -n "${SERIAL}" ]]; then
    run_with_timeout "${ADB_WAIT_TIMEOUT}" "${ADB}" -s "${SERIAL}" wait-for-device
  else
    run_with_timeout "${ADB_WAIT_TIMEOUT}" "${ADB}" wait-for-device
  fi
}

wait_prop() {
  local prop="$1"
  local expected="$2"
  local timeout="${3:-120}"
  local elapsed=0
  while [[ "${elapsed}" -lt "${timeout}" ]]; do
    local value
    value="$(adb_cmd shell getprop "${prop}" 2>/dev/null | tr -d '\r')"
    if [[ "${value}" == "${expected}" ]]; then
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  echo "Timed out waiting for ${prop}=${expected}" >&2
  return 1
}

ensure_device
wait_prop sys.boot_completed 1 180

manager_boot_state="$(adb_cmd shell dumpsys hans 2>/dev/null | tr -d '\r' || true)"
if [[ "${manager_boot_state}" != *"HansManagerService"* ]]; then
  echo "Binder service 'hans' not reachable over dumpsys" >&2
  exit 1
fi

adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null
adb_cmd shell am start -n ai.hansos.canvas/.HansCanvasActivity >/dev/null
adb_cmd shell setprop persist.hansos.context_provider fake >/dev/null 2>&1 || true

wait_runtime() {
  local timeout="${1:-30}"
  local elapsed=0
  while [[ "${elapsed}" -lt "${timeout}" ]]; do
    local output
    output="$(adb_cmd shell dumpsys hans 2>/dev/null | tr -d '\r')"
    if [[ "${output}" == *"runtime=true"* ]]; then
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  echo "Hans runtime did not register with manager" >&2
  adb_cmd shell dumpsys hans >&2 || true
  return 1
}

assert_contains() {
  local output="$1"
  local expected="$2"
  local label="$3"
  if [[ "${output}" != *"${expected}"* ]]; then
    echo "Expected ${label} to contain: ${expected}" >&2
    echo "${output}" >&2
    exit 1
  fi
}

test_canvas_bridge() {
  echo "HansOS Canvas developer bridge:"
  if [[ ! -x "${INPUT_BRIDGE}" ]]; then
    echo "Input bridge not executable: ${INPUT_BRIDGE}" >&2
    exit 1
  fi

  adb_cmd shell am start -n ai.hansos.canvas/.HansCanvasActivity >/dev/null
  sleep 1

  local ui
  ui="$(bridge_cmd dump 2>/dev/null | tr -d '\r')"
  assert_contains "${ui}" "Hans live phrase" "Canvas UI"
  assert_contains "${ui}" "Hans voice status" "Canvas UI"
  assert_contains "${ui}" "Seitentaste halten" "Canvas UI"

  bridge_cmd quick focus >/dev/null
  sleep 2
  local memory
  memory="$(adb_cmd shell dumpsys hans memory 2>/dev/null | tr -d '\r')"
  assert_contains "${memory}" "turn on focus mode" "Canvas quick focus"
  assert_contains "${memory}" "focus_mode enabled; undo available" "Canvas quick focus"

  bridge_cmd submit "canvas bridge smoke" >/dev/null
  sleep 2
  memory="$(adb_cmd shell dumpsys hans memory 2>/dev/null | tr -d '\r')"
  assert_contains "${memory}" "canvas bridge smoke" "Canvas submit"

  local voice
  voice="$(bridge_cmd voice 2>/dev/null | tr -d '\r')"
  assert_contains "${voice}" "listening_started" "Canvas voice smoke"
  assert_contains "${voice}" "speaking_started" "Canvas voice smoke"
  assert_contains "${voice}" "Voice turn abgeschlossen" "Canvas voice smoke"

  bridge_cmd quick morning >/dev/null
  sleep 2
  memory="$(adb_cmd shell dumpsys hans memory 2>/dev/null | tr -d '\r')"
  assert_contains "${memory}" "morning brief generated from fake providers" "Canvas quick morning"

  bridge_cmd quick settings >/dev/null
  sleep 2
  memory="$(adb_cmd shell dumpsys hans memory 2>/dev/null | tr -d '\r')"
  assert_contains "${memory}" "app_control settings fixture inspected" "Canvas quick settings"

  bridge_cmd stop >/dev/null
  sleep 1
  local state
  state="$(adb_cmd shell dumpsys hans 2>/dev/null | tr -d '\r')"
  assert_contains "${state}" "state=7" "Canvas emergency stop"
  echo "  - UI hierarchy exposes the voice-first live phrase surface"
  echo "  - developer intents drive Canvas quick actions and submit"
  echo "  - developer bridge validates a headless Voice Session"
  echo "  - Canvas emergency stop reaches STOPPED"
}

run_flow() {
  local label="$1"
  local prompt="$2"
  shift 2
  local output
  output="$(adb_cmd shell dumpsys hans submit "${prompt}" 2>/dev/null | tr -d '\r')"
  assert_contains "${output}" "requestId=" "${label}"
  for expected in "$@"; do
    assert_contains "${output}" "${expected}" "${label}"
  done
  if [[ "${VERBOSE}" == "true" ]]; then
    echo "${output}"
  fi
  echo "  - ${label}"
}

test_fake_flows_once() {
  local iteration="$1"
  echo "HansOS fake-flow iteration ${iteration}/${ITERATIONS}:"
  adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null
  wait_runtime 45

  run_flow "Command -> Action flow" \
    "turn on focus mode" \
    "\"type\":\"action_completed\"" \
    "fake_device_state.focus_mode=true" \
    "\"type\":\"done\""

  run_flow "Morning Agent flow" \
    "morgen briefing" \
    "\"type\":\"speech\"" \
    "Guten Morgen" \
    "\"type\":\"done\""

  run_flow "App Control flow" \
    "open settings network" \
    "\"type\":\"app_control_completed\"" \
    "fake_settings.network" \
    "\"type\":\"done\""

  memory="$(adb_cmd shell dumpsys hans memory 2>/dev/null | tr -d '\r')"
  assert_contains "${memory}" "runtime_audit" "manager memory"

  adb_cmd shell dumpsys hans stop >/dev/null
  state="$(adb_cmd shell dumpsys hans 2>/dev/null | tr -d '\r')"
  assert_contains "${state}" "state=7" "emergency stop state"
  echo "  - emergency stop reaches STOPPED"

  local voice
  voice="$(adb_cmd shell dumpsys hans voice 2>/dev/null | tr -d '\r')"
  assert_contains "${voice}" "listening_started" "voice smoke"
  assert_contains "${voice}" "speaking_started" "voice smoke"
  assert_contains "${voice}" "Voice turn abgeschlossen" "voice smoke"
  echo "  - voice session smoke passes"
}

test_degraded_runtime_missing() {
  echo "HansOS degraded-runtime path:"
  adb_cmd root >/dev/null 2>&1 || true
  sleep 3
  ensure_device

  adb_cmd shell pm enable ai.hansos.runtime >/dev/null || true
  adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null || true
  wait_runtime 45

  adb_cmd shell am stopservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null || true
  adb_cmd shell am force-stop ai.hansos.runtime >/dev/null || true
  adb_cmd shell pm disable-user --user 0 ai.hansos.runtime >/dev/null || true
  RUNTIME_DISABLED=true

  local elapsed=0
  while [[ "${elapsed}" -lt 20 ]]; do
    local manager_state
    manager_state="$(adb_cmd shell dumpsys hans 2>/dev/null | tr -d '\r')"
    if [[ "${manager_state}" == *"runtime=false"* ]]; then
      break
    fi
    local pid
    pid="$(adb_cmd shell pidof ai.hansos.runtime 2>/dev/null | tr -d '\r' || true)"
    if [[ -n "${pid}" ]]; then
      adb_cmd shell kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  local degraded
  degraded="$(adb_cmd shell dumpsys hans submit "runtime missing degraded test" 2>/dev/null | tr -d '\r')"
  assert_contains "${degraded}" "Hans is running without runtime" "degraded runtime"
  assert_contains "${degraded}" "Use degraded local fake response" "degraded runtime"
  assert_contains "${degraded}" "Runtime missing. Core Binder path is alive." "degraded runtime"
  if [[ "${VERBOSE}" == "true" ]]; then
    echo "${degraded}"
  fi

  adb_cmd shell pm enable ai.hansos.runtime >/dev/null
  RUNTIME_DISABLED=false
  adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null
  wait_runtime 45
  echo "  - runtime missing returns degraded response"
  echo "  - runtime restored"
}

for iteration in $(seq 1 "${ITERATIONS}"); do
  if [[ "${iteration}" == "1" && "${INCLUDE_CANVAS_BRIDGE}" == "true" ]]; then
    test_canvas_bridge
  fi
  test_fake_flows_once "${iteration}"
done

if [[ "${INCLUDE_DEGRADED}" == "true" ]]; then
  test_degraded_runtime_missing
fi

echo "HansOS Cuttlefish smoke passed:"
echo "  - serial ${SERIAL}"
echo "  - boot completed"
echo "  - binder service hans present"
echo "  - runtime registered"
echo "  - canvas activity launched"
if [[ "${INCLUDE_CANVAS_BRIDGE}" == "true" ]]; then
  echo "  - Canvas developer bridge passed"
fi
echo "  - ${ITERATIONS} fake-flow iteration(s) passed"
if [[ "${INCLUDE_DEGRADED}" == "true" ]]; then
  echo "  - degraded runtime-missing behavior passed"
fi
