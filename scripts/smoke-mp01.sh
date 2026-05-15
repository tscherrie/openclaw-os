#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

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

  local resolved
  resolved="$(command -v adb 2>/dev/null || true)"
  if [[ -n "${resolved}" ]]; then
    echo "${resolved}"
    return 0
  fi

  echo "adb not found. Install Android platform-tools or set ADB=/path/to/adb." >&2
  return 1
}

usage() {
  cat <<'USAGE'
usage: smoke-mp01.sh [--serial SERIAL] [--boot-timeout SECONDS]
                    [--include-degraded] [--require-baked-home] [--verbose]

Post-flash HansOS smoke test for the Minimal Phone MP01.
It expects the device to be booted and authorized over adb.
USAGE
}

ADB="$(resolve_adb)"
SERIAL="${HANSOS_ADB_SERIAL:-${ANDROID_SERIAL:-}}"
ADB_CALL_TIMEOUT="${HANSOS_ADB_TIMEOUT_SECONDS:-25}"
ADB_WAIT_TIMEOUT="${HANSOS_ADB_WAIT_TIMEOUT_SECONDS:-180}"
BOOT_TIMEOUT="${HANSOS_MP01_BOOT_TIMEOUT_SECONDS:-600}"
INCLUDE_DEGRADED="${HANSOS_SMOKE_INCLUDE_DEGRADED:-false}"
REQUIRE_BAKED_HOME="${HANSOS_MP01_REQUIRE_BAKED_HOME:-false}"
VERBOSE="${HANSOS_SMOKE_VERBOSE:-false}"
RUNTIME_DISABLED=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial)
      SERIAL="$2"
      shift 2
      ;;
    --include-degraded)
      INCLUDE_DEGRADED=true
      shift
      ;;
    --require-baked-home)
      REQUIRE_BAKED_HOME=true
      shift
      ;;
    --boot-timeout)
      BOOT_TIMEOUT="$2"
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

restore_runtime() {
  if [[ "${RUNTIME_DISABLED}" == "true" ]]; then
    adb_cmd shell pm enable ai.hansos.runtime >/dev/null 2>&1 || true
    adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null 2>&1 || true
  fi
}
trap restore_runtime EXIT

ensure_device() {
  if [[ -z "${SERIAL}" ]]; then
    local devices
    devices="$(run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" devices | awk 'NR > 1 && $2 == "device" {print $1}')"
    local mp01_candidates=""
    local serial
    while IFS= read -r serial; do
      [[ -z "${serial}" ]] && continue
      local model
      model="$(run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" -s "${serial}" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
      if [[ "${model}" == "MP01" ]]; then
        mp01_candidates+="${serial}"$'\n'
      fi
    done <<< "${devices}"
    local count
    count="$(printf "%s\n" "${mp01_candidates}" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [[ "${count}" == "1" ]]; then
      SERIAL="$(printf "%s\n" "${mp01_candidates}" | sed '/^$/d' | head -1)"
    elif [[ "${count}" == "0" ]]; then
      echo "No authorized MP01 adb device found. Set --serial explicitly if needed." >&2
      run_with_timeout "${ADB_CALL_TIMEOUT}" "${ADB}" devices >&2
      exit 1
    else
      echo "Multiple MP01 devices found. Set --serial explicitly." >&2
      printf "%s\n" "${mp01_candidates}" >&2
      exit 1
    fi
  fi

  run_with_timeout "${ADB_WAIT_TIMEOUT}" "${ADB}" -s "${SERIAL}" wait-for-device
}

wait_prop() {
  local prop="$1"
  local expected="$2"
  local timeout="${3:-180}"
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

wait_runtime() {
  local timeout="${1:-45}"
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

set_optional_fake_provider() {
  if adb_cmd shell setprop persist.hansos.provider fake >/dev/null 2>&1; then
    return 0
  fi
  echo "  - persist.hansos.provider could not be set; continuing with built-in/default fake provider"
}

ensure_canvas_home() {
  adb_cmd shell settings put global device_provisioned 1 >/dev/null 2>&1 || true
  adb_cmd shell settings put secure user_setup_complete 1 >/dev/null 2>&1 || true
  adb_cmd shell cmd package set-home-activity "ai.hansos.canvas/.HansCanvasActivity" >/dev/null 2>&1 || true

  local home_activity
  local needed_setupwizard_disable=false
  home_activity="$(adb_cmd shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME 2>/dev/null | tr -d '\r' || true)"
  if [[ "${home_activity}" != *"ai.hansos.canvas"* && "${home_activity}" == *"org.lineageos.setupwizard"* ]]; then
    needed_setupwizard_disable=true
    if [[ "${REQUIRE_BAKED_HOME}" == "true" ]]; then
      echo "Baked HOME check failed: SetupWizard is still the HOME resolver." >&2
      echo "${home_activity}" >&2
      exit 1
    fi
    adb_cmd shell pm disable-user --user 0 org.lineageos.setupwizard >/dev/null 2>&1 || true
    adb_cmd shell cmd package set-home-activity "ai.hansos.canvas/.HansCanvasActivity" >/dev/null 2>&1 || true
    adb_cmd shell am force-stop org.lineageos.setupwizard >/dev/null 2>&1 || true
    adb_cmd shell am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1 || true
    sleep 2
    home_activity="$(adb_cmd shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME 2>/dev/null | tr -d '\r' || true)"
  fi

  assert_contains "${home_activity}" "ai.hansos.canvas" "HOME activity"
  if [[ "${needed_setupwizard_disable}" == "true" ]]; then
    echo "  - Canvas HOME required runtime SetupWizard disable fallback"
  else
    echo "  - Canvas HOME baked/provisioned without SetupWizard fallback"
  fi
}

run_flow() {
  local label="$1"
  local prompt="$2"
  shift 2
  local output
  output="$(adb_cmd shell dumpsys hans submit "${prompt}" 2>/dev/null | tr -d '\r')"
  assert_contains "${output}" "requestId=" "${label}"
  local expected
  for expected in "$@"; do
    assert_contains "${output}" "${expected}" "${label}"
  done
  if [[ "${VERBOSE}" == "true" ]]; then
    echo "${output}"
  fi
  echo "  - ${label}"
}

test_degraded_runtime_missing() {
  echo "HansOS MP01 degraded-runtime path:"
  adb_cmd root >/dev/null 2>&1 || true
  sleep 3
  adb_cmd shell pm enable ai.hansos.runtime >/dev/null || true
  adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null || true
  wait_runtime 45
  adb_cmd shell am stopservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null || true
  adb_cmd shell am force-stop ai.hansos.runtime >/dev/null || true
  adb_cmd shell pm disable-user --user 0 ai.hansos.runtime >/dev/null || true
  RUNTIME_DISABLED=true

  local degraded
  degraded="$(adb_cmd shell dumpsys hans submit "runtime missing degraded test" 2>/dev/null | tr -d '\r')"
  assert_contains "${degraded}" "Hans is running without runtime" "degraded runtime"
  assert_contains "${degraded}" "Runtime missing. Core Binder path is alive." "degraded runtime"
  adb_cmd shell pm enable ai.hansos.runtime >/dev/null
  RUNTIME_DISABLED=false
  adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null
  wait_runtime 45
  echo "  - runtime missing returns degraded response"
}

ensure_device
wait_prop sys.boot_completed 1 "${BOOT_TIMEOUT}"

model="$(adb_cmd shell getprop ro.product.model 2>/dev/null | tr -d '\r')"
if [[ "${model}" != "MP01" ]]; then
  echo "Connected device is ${model}, expected MP01" >&2
  exit 1
fi

manager_boot_state="$(adb_cmd shell dumpsys hans 2>/dev/null | tr -d '\r' || true)"
if [[ "${manager_boot_state}" != *"HansManagerService"* ]]; then
  echo "Binder service 'hans' not reachable over dumpsys" >&2
  exit 1
fi

set_optional_fake_provider
adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null
adb_cmd shell am start -n ai.hansos.canvas/.HansCanvasActivity >/dev/null
wait_runtime 45

ensure_canvas_home

echo "HansOS MP01 fake flows:"
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
assert_contains "${state}" "state=5" "emergency stop state"
echo "  - emergency stop reaches STOPPED"

if [[ "${INCLUDE_DEGRADED}" == "true" ]]; then
  test_degraded_runtime_missing
fi

echo "HansOS MP01 smoke passed:"
echo "  - serial ${SERIAL}"
echo "  - boot completed"
echo "  - binder service hans present"
echo "  - runtime registered"
echo "  - canvas is HOME"
echo "  - fake alpha flows passed"
