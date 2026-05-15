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

find_host_bin() {
  local binary="$1"
  local tag
  tag="$(host_tag)"
  local aosp_name
  aosp_name="$(basename "${AOSP_ROOT:-aosp}")"
  local out_base="${OUT_DIR_COMMON_BASE:-}"
  if [[ -z "${out_base}" && -n "${HANSOS_EXTERNAL_ROOT:-}" ]]; then
    out_base="${HANSOS_EXTERNAL_ROOT}/out"
  fi

  local candidates=(
    "${ANDROID_HOST_OUT:-}/bin/${binary}"
    "${out_base}/${aosp_name}/host/${tag}/bin/${binary}"
    "${out_base}/host/${tag}/bin/${binary}"
    "${REPO_ROOT}/.work/out/${aosp_name}/host/${tag}/bin/${binary}"
    "${REPO_ROOT}/.work/aosp/out/host/${tag}/bin/${binary}"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  local resolved
  resolved="$(command -v "${binary}" 2>/dev/null || true)"
  if [[ -n "${resolved}" ]]; then
    echo "${resolved}"
    return 0
  fi

  return 1
}

find_product_out() {
  if [[ -n "${PRODUCT_OUT:-}" && -d "${PRODUCT_OUT}" ]]; then
    echo "${PRODUCT_OUT}"
    return 0
  fi

  local aosp_name
  aosp_name="$(basename "${AOSP_ROOT:-aosp}")"
  local out_base="${OUT_DIR_COMMON_BASE:-}"
  if [[ -z "${out_base}" && -n "${HANSOS_EXTERNAL_ROOT:-}" ]]; then
    out_base="${HANSOS_EXTERNAL_ROOT}/out"
  fi

  local candidates=(
    "${out_base}/${aosp_name}/target/product/vsoc_arm64_only"
    "${REPO_ROOT}/.work/out/${aosp_name}/target/product/vsoc_arm64_only"
    "${REPO_ROOT}/.work/aosp/out/target/product/vsoc_arm64_only"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}/system.img" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  if [[ -n "${out_base}" && -d "${out_base}/${aosp_name}/target/product" ]]; then
    candidate="$(
      find "${out_base}/${aosp_name}/target/product" -maxdepth 2 -name system.img -print -quit 2>/dev/null || true
    )"
    if [[ -n "${candidate}" ]]; then
      dirname "${candidate}"
      return 0
    fi
  fi

  return 1
}

ensure_kvm_access() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    return 0
  fi

  if [[ ! -e /dev/kvm ]]; then
    echo "/dev/kvm not found. Enable KVM on the Linux host before launching Cuttlefish." >&2
    exit 1
  fi

  if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
    echo "/dev/kvm is present but not accessible by $(id -un)." >&2
    echo "Grant KVM access, for example: sudo usermod -aG kvm $(id -un)" >&2
    echo "For the current session, an ACL such as sudo setfacl -m u:$(id -un):rw /dev/kvm may also be needed." >&2
    exit 1
  fi
}

LAUNCHER_MODE=""
LAUNCHER_BIN="${LAUNCH_CVD:-}"
if [[ -n "${LAUNCHER_BIN}" ]]; then
  LAUNCHER_MODE="launch_cvd"
fi
if [[ -z "${LAUNCHER_BIN}" ]]; then
  LAUNCHER_BIN="$(find_host_bin cvd || true)"
  if [[ -n "${LAUNCHER_BIN}" ]]; then
    LAUNCHER_MODE="cvd"
  fi
fi
if [[ -z "${LAUNCHER_BIN}" ]]; then
  LAUNCHER_BIN="$(find_host_bin launch_cvd || true)"
  if [[ -n "${LAUNCHER_BIN}" ]]; then
    LAUNCHER_MODE="launch_cvd"
  fi
fi
if [[ -z "${LAUNCHER_BIN}" ]]; then
  LAUNCHER_BIN="$(find_host_bin cvd_internal_start || true)"
  if [[ -n "${LAUNCHER_BIN}" ]]; then
    LAUNCHER_MODE="cvd_internal_start"
  fi
fi
if [[ -z "${LAUNCHER_BIN}" ]]; then
  echo "No Cuttlefish launcher found. Build host tools first." >&2
  exit 1
fi

PRODUCT_OUT="$(find_product_out || true)"
if [[ -z "${PRODUCT_OUT}" ]]; then
  echo "PRODUCT_OUT not found. Build images first or set PRODUCT_OUT=/path/to/target/product/..." >&2
  exit 1
fi

HOST_OUT="$(cd "$(dirname "${LAUNCHER_BIN}")/.." && pwd)"
CVD_HOME="${HANSOS_CVD_HOME:-${HANSOS_EXTERNAL_ROOT:-${REPO_ROOT}/.work}/cvd-home}"
mkdir -p "${CVD_HOME}"

ensure_kvm_access

export ANDROID_HOST_OUT="${ANDROID_HOST_OUT:-${HOST_OUT}}"
export ANDROID_SOONG_HOST_OUT="${ANDROID_SOONG_HOST_OUT:-${HOST_OUT}}"
export CVD_ACQUIRE_FILE_LOCK="${CVD_ACQUIRE_FILE_LOCK:-false}"

CROSVM_ARGS=()
if [[ ! -x "${ANDROID_HOST_OUT}/bin/crosvm" && -x "${ANDROID_HOST_OUT}/bin/aarch64-linux-gnu/crosvm" ]]; then
  CROSVM_ARGS=("--crosvm_binary=${ANDROID_HOST_OUT}/bin/aarch64-linux-gnu/crosvm")
fi
NETSIM_ARGS=("--netsim=false" "--netsim_bt=false" "--netsim_uwb=false")
START_WEBRTC="${HANSOS_START_WEBRTC:-false}"
START_WEBRTC_SIG_SERVER="${HANSOS_START_WEBRTC_SIG_SERVER:-${START_WEBRTC}}"
DISPLAY0="${HANSOS_DISPLAY0:-width=390,height=844,dpi=420,refresh_rate_hz=60}"
HWCOMPOSER="${HANSOS_HWCOMPOSER:-none}"
ENABLE_WIFI="${HANSOS_ENABLE_WIFI:-false}"
if [[ "${START_WEBRTC}" == "true" && -z "${HANSOS_CVD_VIEW_ONLY_WEBRTC+x}" ]]; then
  export HANSOS_CVD_VIEW_ONLY_WEBRTC=true
fi
ALPHA_BOOT_ARGS=(
  "--resume=false"
  "--data_policy=always_create"
  "--blank_data_image_mb=8192"
)
ALPHA_HOST_ARGS=(
  "--enable_audio=false"
  "--enable_wifi=${ENABLE_WIFI}"
  "--gpu_mode=guest_swiftshader"
  "--gpu_vhost_user_mode=off"
  "--hwcomposer=${HWCOMPOSER}"
  "--enable_host_bluetooth=false"
  "--enable_host_nfc=false"
  "--enable_host_uwb=false"
  "--rootcanal_instance_num=1"
  "--casimir_instance_num=1"
  "--pica_instance_num=1"
  "--display0=${DISPLAY0}"
  "--start_webrtc=${START_WEBRTC}"
  "--start_webrtc_sig_server=${START_WEBRTC_SIG_SERVER}"
  "--vhost_user_vsock=false"
)

echo "Starting Cuttlefish:"
echo "  launcher: ${LAUNCHER_BIN} (${LAUNCHER_MODE})"
echo "  product:  ${PRODUCT_OUT}"
echo "  home:     ${CVD_HOME}"

if [[ "${LAUNCHER_MODE}" == "cvd" ]]; then
  HOME="${CVD_HOME}" \
  ANDROID_HOST_OUT="${ANDROID_HOST_OUT}" \
  ANDROID_SOONG_HOST_OUT="${ANDROID_SOONG_HOST_OUT}" \
  ANDROID_PRODUCT_OUT="${PRODUCT_OUT}" \
  CVD_ACQUIRE_FILE_LOCK="${CVD_ACQUIRE_FILE_LOCK}" \
  "${LAUNCHER_BIN}" start \
    --system_image_dir="${PRODUCT_OUT}" \
    --report_anonymous_usage_stats=n \
    "${CROSVM_ARGS[@]}" \
    "${NETSIM_ARGS[@]}" \
    "${ALPHA_BOOT_ARGS[@]}" \
    "${ALPHA_HOST_ARGS[@]}" \
    "$@"
else
  LEGACY_CROSVM_ARGS=()
  if [[ "${#CROSVM_ARGS[@]}" -gt 0 ]]; then
    LEGACY_CROSVM_ARGS=("-crosvm_binary=${ANDROID_HOST_OUT}/bin/aarch64-linux-gnu/crosvm")
  fi
  LEGACY_NETSIM_ARGS=("-netsim=false" "-netsim_bt=false" "-netsim_uwb=false")
  LEGACY_ALPHA_BOOT_ARGS=(
    "-resume=false"
    "-data_policy=always_create"
    "-blank_data_image_mb=8192"
  )
  LEGACY_ALPHA_HOST_ARGS=(
    "-enable_audio=false"
    "-enable_wifi=${ENABLE_WIFI}"
    "-gpu_mode=guest_swiftshader"
    "-gpu_vhost_user_mode=off"
    "-hwcomposer=${HWCOMPOSER}"
    "-enable_host_bluetooth=false"
    "-enable_host_nfc=false"
    "-enable_host_uwb=false"
    "-rootcanal_instance_num=1"
    "-casimir_instance_num=1"
    "-pica_instance_num=1"
    "-display0=${DISPLAY0}"
    "-start_webrtc=${START_WEBRTC}"
    "-start_webrtc_sig_server=${START_WEBRTC_SIG_SERVER}"
    "-vhost_user_vsock=false"
  )

  HOME="${CVD_HOME}" \
  ANDROID_HOST_OUT="${ANDROID_HOST_OUT}" \
  ANDROID_SOONG_HOST_OUT="${ANDROID_SOONG_HOST_OUT}" \
  ANDROID_PRODUCT_OUT="${PRODUCT_OUT}" \
  CVD_ACQUIRE_FILE_LOCK="${CVD_ACQUIRE_FILE_LOCK}" \
  "${LAUNCHER_BIN}" \
    -system_image_dir="${PRODUCT_OUT}" \
    -report_anonymous_usage_stats=n \
    "${LEGACY_CROSVM_ARGS[@]}" \
    "${LEGACY_NETSIM_ARGS[@]}" \
    "${LEGACY_ALPHA_BOOT_ARGS[@]}" \
    "${LEGACY_ALPHA_HOST_ARGS[@]}" \
    "$@"
fi
