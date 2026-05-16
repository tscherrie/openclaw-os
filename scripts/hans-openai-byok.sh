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

usage() {
  cat <<'USAGE'
usage: hans-openai-byok.sh [--serial SERIAL] [--connect SERIAL]
                           [--model MODEL] [--prompt TEXT] [--base-url URL]
                           [--transcription-model MODEL]
                           <configure|clear|test>

commands:
  configure   Read an OpenAI key from stdin and configure BYOK chunks on device.
  clear       Switch back to the fake provider and ignore all key chunks.
  test        Submit a small "ask openai ..." prompt through HansRuntimeService.

The key is intentionally read from stdin so it does not appear in shell history
or process arguments.
USAGE
}

ADB="$(resolve_adb)"
SERIAL="${HANSOS_ADB_SERIAL:-${ANDROID_SERIAL:-}}"
CONNECT_SERIAL="${HANSOS_ADB_CONNECT:-}"
ADB_CALL_TIMEOUT="${HANSOS_ADB_TIMEOUT_SECONDS:-30}"
MODEL="${HANSOS_OPENAI_MODEL:-gpt-5.4-mini}"
TRANSCRIPTION_MODEL="${HANSOS_OPENAI_TRANSCRIPTION_MODEL:-gpt-4o-mini-transcribe}"
BASE_URL="${HANSOS_OPENAI_BASE_URL:-}"
PROMPT="${HANSOS_OPENAI_TEST_PROMPT:-HansOS OpenAI BYOK smoke. Answer with one short sentence.}"
COMMAND=""
CHUNK_SIZE=80
MAX_PARTS=8

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
    --model)
      MODEL="$2"
      shift 2
      ;;
    --transcription-model)
      TRANSCRIPTION_MODEL="$2"
      shift 2
      ;;
    --prompt)
      PROMPT="$2"
      shift 2
      ;;
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    configure|clear|test)
      COMMAND="$1"
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

if [[ -z "${COMMAND}" ]]; then
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

adb_shell_setprop() {
  local prop="$1"
  local value="$2"
  if [[ -n "${SERIAL}" ]]; then
    printf "%s\n" "${value}" | run_with_timeout "${ADB_CALL_TIMEOUT}" \
      "${ADB}" -s "${SERIAL}" shell "IFS= read -r hans_value; setprop ${prop} \"\$hans_value\""
  else
    printf "%s\n" "${value}" | run_with_timeout "${ADB_CALL_TIMEOUT}" \
      "${ADB}" shell "IFS= read -r hans_value; setprop ${prop} \"\$hans_value\""
  fi
}

prop_to_setting() {
  case "$1" in
    persist.hansos.provider)
      echo "hansos_provider"
      ;;
    persist.hansos.openai_key)
      echo "hansos_openai_key"
      ;;
    persist.hansos.openai_key_parts)
      echo "hansos_openai_key_parts"
      ;;
    persist.hansos.openai_key_part*)
      echo "hansos_openai_key_part${1#persist.hansos.openai_key_part}"
      ;;
    persist.hansos.openai_key_file)
      echo "hansos_openai_key_file"
      ;;
    persist.hansos.openai_model)
      echo "hansos_openai_model"
      ;;
    persist.hansos.openai_transcription_model)
      echo "hansos_openai_transcription_model"
      ;;
    persist.hansos.openai_base_url)
      echo "hansos_openai_base_url"
      ;;
    *)
      return 1
      ;;
  esac
}

adb_shell_settings_put() {
  local setting="$1"
  local value="$2"
  if [[ -n "${SERIAL}" ]]; then
    printf "%s\n" "${value}" | run_with_timeout "${ADB_CALL_TIMEOUT}" \
      "${ADB}" -s "${SERIAL}" shell "IFS= read -r hans_value; settings put global ${setting} \"\$hans_value\""
  else
    printf "%s\n" "${value}" | run_with_timeout "${ADB_CALL_TIMEOUT}" \
      "${ADB}" shell "IFS= read -r hans_value; settings put global ${setting} \"\$hans_value\""
  fi
}

set_hans_config() {
  local prop="$1"
  local value="$2"
  if adb_shell_setprop "${prop}" "${value}" >/dev/null 2>&1; then
    return 0
  fi
  local setting
  setting="$(prop_to_setting "${prop}" 2>/dev/null || true)"
  if [[ -z "${setting}" ]]; then
    echo "Could not set ${prop}; no Settings.Global fallback exists" >&2
    return 1
  fi
  adb_shell_settings_put "${setting}" "${value}"
}

shell_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
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

  adb_cmd wait-for-device >/dev/null
}

read_key_from_stdin() {
  local key
  if [[ -t 0 ]]; then
    printf "OpenAI API key: " >&2
    IFS= read -r -s key
    printf "\n" >&2
  else
    key="$(cat | tr -d '\r\n')"
  fi
  if [[ -z "${key}" ]]; then
    echo "OpenAI key input is empty" >&2
    return 2
  fi
  printf "%s" "${key}"
}

configure_byok() {
  local key="$1"
  if [[ -z "${key}" ]]; then
    echo "OpenAI key input is empty" >&2
    return 2
  fi
  local parts=()
  local offset=0
  local length=${#key}
  while [[ "${offset}" -lt "${length}" ]]; do
    parts+=("${key:${offset}:${CHUNK_SIZE}}")
    offset=$((offset + CHUNK_SIZE))
  done
  if [[ "${#parts[@]}" -gt "${MAX_PARTS}" ]]; then
    echo "OpenAI key needs ${#parts[@]} property chunks; max is ${MAX_PARTS}" >&2
    exit 2
  fi

  set_hans_config persist.hansos.openai_key ""
  set_hans_config persist.hansos.openai_key_parts "${#parts[@]}"
  local index=1
  local part
  for part in "${parts[@]}"; do
    set_hans_config "persist.hansos.openai_key_part${index}" "${part}"
    index=$((index + 1))
  done
  while [[ "${index}" -le "${MAX_PARTS}" ]]; do
    set_hans_config "persist.hansos.openai_key_part${index}" ""
    index=$((index + 1))
  done
  set_hans_config persist.hansos.openai_model "${MODEL}"
  set_hans_config persist.hansos.openai_transcription_model "${TRANSCRIPTION_MODEL}"
  if [[ -n "${BASE_URL}" ]]; then
    set_hans_config persist.hansos.openai_base_url "${BASE_URL}"
  fi
  set_hans_config persist.hansos.provider openai
  adb_cmd shell pm enable ai.hansos.runtime >/dev/null 2>&1 || true
  adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null
  echo "OpenAI BYOK configured on ${SERIAL} with ${#parts[@]} chunk(s); key not printed."
}

clear_byok() {
  set_hans_config persist.hansos.provider fake
  set_hans_config persist.hansos.openai_key ""
  set_hans_config persist.hansos.openai_key_parts 0
  set_hans_config persist.hansos.openai_transcription_model ""
  set_hans_config persist.hansos.openai_base_url ""
  local index=1
  while [[ "${index}" -le "${MAX_PARTS}" ]]; do
    set_hans_config "persist.hansos.openai_key_part${index}" ""
    index=$((index + 1))
  done
  adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null 2>&1 || true
  echo "OpenAI BYOK cleared on ${SERIAL}; provider is fake."
}

test_byok() {
  local quoted_prompt
  quoted_prompt="$(shell_quote "ask openai ${PROMPT}")"
  adb_cmd shell am startservice -n ai.hansos.runtime/.HansRuntimeService >/dev/null
  local output
  output="$(adb_cmd shell "dumpsys hans submit ${quoted_prompt}" 2>/dev/null | tr -d '\r')"
  if [[ "${output}" != *"requestId="* ]]; then
    echo "Hans submit did not return a requestId" >&2
    echo "${output}" >&2
    exit 1
  fi
  if [[ "${output}" == *"\"type\":\"error\""* ]]; then
    echo "OpenAI BYOK test returned an error" >&2
    echo "${output}" >&2
    exit 1
  fi
  if [[ "${output}" != *"OpenAI"* && "${output}" != *"\"type\":\"speech\""* ]]; then
    echo "OpenAI BYOK test did not show OpenAI/speech events" >&2
    echo "${output}" >&2
    exit 1
  fi
  echo "OpenAI BYOK test passed on ${SERIAL}."
}

ensure_device

case "${COMMAND}" in
  configure)
    key="$(read_key_from_stdin)" || exit $?
    configure_byok "${key}"
    ;;
  clear)
    clear_byok
    ;;
  test)
    test_byok
    ;;
esac
