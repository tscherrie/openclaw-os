#!/usr/bin/env bash

if [[ -z "${REPO_ROOT:-}" ]]; then
  HANSOS_ENV_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="$(cd "${HANSOS_ENV_SCRIPT_DIR}/.." && pwd)"
fi

HANSOS_EXTERNAL_ROOT="${HANSOS_EXTERNAL_ROOT:-/Volumes/HansOSBuild/hansos-run2}"
HANSOS_TOOLS_DIR="${HANSOS_TOOLS_DIR:-${REPO_ROOT}/.work/bin}"

if [[ ! -d "${HANSOS_EXTERNAL_ROOT}" ]]; then
  echo "HansOS external workspace is not mounted: ${HANSOS_EXTERNAL_ROOT}" >&2
  return 1 2>/dev/null || exit 1
fi

PYTHON3_BIN="$(command -v python3 || true)"
if [[ -z "${PYTHON3_BIN}" ]]; then
  echo "python3 is required for the HansOS AOSP build" >&2
  return 1 2>/dev/null || exit 1
fi

mkdir -p "${HANSOS_TOOLS_DIR}"
ln -sf "${PYTHON3_BIN}" "${HANSOS_TOOLS_DIR}/python"

export PATH="${HANSOS_TOOLS_DIR}:${PATH}"
export OUT_DIR_COMMON_BASE="${HANSOS_EXTERNAL_ROOT}/out"
export TMPDIR="${HANSOS_EXTERNAL_ROOT}/tmp"
export CCACHE_DIR="${HANSOS_EXTERNAL_ROOT}/ccache"

if [[ "$(uname -s)" == "Darwin" ]]; then
  export LLVM_BINDGEN_PREBUILTS_VERSION="${LLVM_BINDGEN_PREBUILTS_VERSION:-clang-r563880c}"
fi

if [[ "$(uname -s)" == "Linux" && "$(uname -m)" == "aarch64" ]]; then
  export FORCE_BUILD_LLVM_COMPONENTS="${FORCE_BUILD_LLVM_COMPONENTS:-true}"
fi

mkdir -p "${OUT_DIR_COMMON_BASE}" "${TMPDIR}" "${CCACHE_DIR}"

echo "HansOS AOSP build environment:"
echo "  source: ${AOSP_ROOT:-${REPO_ROOT}/.work/aosp}"
echo "  out:    ${OUT_DIR_COMMON_BASE}"
echo "  tmp:    ${TMPDIR}"
echo "  ccache: ${CCACHE_DIR}"
if [[ -n "${LLVM_BINDGEN_PREBUILTS_VERSION:-}" ]]; then
  echo "  bindgen clang: ${LLVM_BINDGEN_PREBUILTS_VERSION}"
fi
if [[ -n "${FORCE_BUILD_LLVM_COMPONENTS:-}" ]]; then
  echo "  force LLVM components: ${FORCE_BUILD_LLVM_COMPONENTS}"
fi
