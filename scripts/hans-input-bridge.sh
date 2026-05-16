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
ADB_CALL_TIMEOUT="${HANSOS_ADB_TIMEOUT_SECONDS:-25}"
CANVAS_COMPONENT="ai.hansos.canvas/.HansCanvasActivity"
ACTION_SUBMIT="ai.hansos.canvas.action.SUBMIT"
ACTION_QUICK="ai.hansos.canvas.action.QUICK"
ACTION_STOP="ai.hansos.canvas.action.STOP"
ACTION_RETRY="ai.hansos.canvas.action.RETRY"
EXTRA_PROMPT="ai.hansos.canvas.extra.PROMPT"
EXTRA_QUICK="ai.hansos.canvas.extra.QUICK"

usage() {
  cat <<'USAGE'
usage: hans-input-bridge.sh [--serial SERIAL] [--connect SERIAL] <command> [args...]

Developer-only input bridge for a view-only HansOS WebRTC session.

commands:
  submit <text>            Send text to Canvas through the developer intent path
  quick focus|morning|settings
                           Run one of the Canvas quick actions
  stop                     Trigger Emergency Stop
  retry                    Retry the last Canvas prompt
  voice                    Run a headless Voice Session smoke through dumpsys
  ptt-sim <keycode>        Record a synthetic PTT diagnostic in dumpsys hans voice
  tap-desc <description>   Tap a UI node by content description
  tap-text <text>          Tap a UI node by visible text
  tap <x> <y>              Raw coordinate tap
  text <text>              Raw adb input text
  key <keycode>            Raw adb keyevent
  dump                     Print current UI hierarchy XML
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
    -h|--help)
      usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

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
}

start_canvas() {
  adb_cmd shell am start -n "${CANVAS_COMPONENT}" >/dev/null
  sleep 1
}

start_canvas_action() {
  local action="$1"
  shift
  adb_cmd shell am start -W -n "${CANVAS_COMPONENT}" -a "${action}" "$@" >/dev/null
}

shell_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

developer_submit() {
  local quoted_prompt
  quoted_prompt="$(shell_quote "$*")"
  adb_cmd shell "am start -W -n ${CANVAS_COMPONENT} -a ${ACTION_SUBMIT} --es ${EXTRA_PROMPT} ${quoted_prompt}" >/dev/null
}

developer_quick() {
  start_canvas_action "${ACTION_QUICK}" --es "${EXTRA_QUICK}" "$1"
}

developer_stop() {
  start_canvas_action "${ACTION_STOP}"
}

developer_retry() {
  start_canvas_action "${ACTION_RETRY}"
}

developer_voice_smoke() {
  adb_cmd shell dumpsys hans voice | tr -d '\r'
}

developer_ptt_sim() {
  adb_cmd shell dumpsys hans input "$1" 0 true | tr -d '\r'
  adb_cmd shell dumpsys hans input "$1" 1 true | tr -d '\r'
}

dump_ui() {
  adb_cmd shell uiautomator dump /sdcard/hans-window.xml >/dev/null
  adb_cmd shell cat /sdcard/hans-window.xml | tr '>' '>\n' | tr -d '\r'
}

find_node() {
  local attr="$1"
  local value="$2"
  dump_ui | grep -F "${attr}=\"${value}\"" | head -1 || true
}

tap_node() {
  local attr="$1"
  local value="$2"
  local node
  node="$(find_node "${attr}" "${value}")"
  if [[ -z "${node}" ]]; then
    echo "Could not find UI node with ${attr}=${value}" >&2
    exit 1
  fi

  local bounds
  bounds="$(printf "%s\n" "${node}" | sed -E 's/.*bounds="\[([0-9]+),([0-9]+)\]\[([0-9]+),([0-9]+)\]".*/\1 \2 \3 \4/')"
  if [[ "${bounds}" == "${node}" ]]; then
    echo "Could not parse UI bounds for ${attr}=${value}" >&2
    exit 1
  fi

  local x1 y1 x2 y2
  read -r x1 y1 x2 y2 <<<"${bounds}"
  adb_cmd shell input tap "$(((x1 + x2) / 2))" "$(((y1 + y2) / 2))"
}

escape_input_text() {
  printf "%s" "$1" \
    | tr '\n' ' ' \
    | sed -e 's/%/%25/g' -e 's/ /%s/g' -e 's/&/\\&/g' -e 's/</\\</g' -e 's/>/\\>/g'
}

input_text() {
  local escaped
  escaped="$(escape_input_text "$1")"
  adb_cmd shell input text "${escaped}"
}

ensure_device
command="$1"
shift

case "${command}" in
  submit)
    if [[ $# -lt 1 ]]; then
      echo "submit requires text" >&2
      exit 2
    fi
    developer_submit "$*"
    ;;
  quick)
    if [[ $# -ne 1 ]]; then
      echo "quick requires focus, morning, or settings" >&2
      exit 2
    fi
    start_canvas
    case "$1" in
      focus)
        developer_quick "focus"
        ;;
      morning)
        developer_quick "morning"
        ;;
      settings)
        developer_quick "settings"
        ;;
      *)
        echo "Unknown quick action: $1" >&2
        exit 2
        ;;
    esac
    ;;
  stop)
    developer_stop
    ;;
  retry)
    developer_retry
    ;;
  voice)
    developer_voice_smoke
    ;;
  ptt-sim)
    if [[ $# -ne 1 ]]; then
      echo "ptt-sim requires keycode" >&2
      exit 2
    fi
    developer_ptt_sim "$1"
    ;;
  tap-desc)
    if [[ $# -lt 1 ]]; then
      echo "tap-desc requires content description" >&2
      exit 2
    fi
    tap_node "content-desc" "$*"
    ;;
  tap-text)
    if [[ $# -lt 1 ]]; then
      echo "tap-text requires text" >&2
      exit 2
    fi
    tap_node "text" "$*"
    ;;
  tap)
    if [[ $# -ne 2 ]]; then
      echo "tap requires x y" >&2
      exit 2
    fi
    adb_cmd shell input tap "$1" "$2"
    ;;
  text)
    if [[ $# -lt 1 ]]; then
      echo "text requires input text" >&2
      exit 2
    fi
    input_text "$*"
    ;;
  key)
    if [[ $# -ne 1 ]]; then
      echo "key requires keycode" >&2
      exit 2
    fi
    adb_cmd shell input keyevent "$1"
    ;;
  dump)
    dump_ui
    ;;
  *)
    echo "Unknown command: ${command}" >&2
    usage >&2
    exit 2
    ;;
esac
