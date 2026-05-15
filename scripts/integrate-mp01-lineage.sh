#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/integrate-mp01-lineage.sh /path/to/los22

Copies HansOS modules into a LineageOS/TrebleDroid MP01 checkout and applies
the deep SystemServer integration:
  - HansManagerService in frameworks/base
  - SystemServer startup hook for the "hans" Binder service
  - services.core.unboosted dependency on hansos-agent-protocol
  - system service_contexts/service.te label for hans_service
  - HansCanvas/HansRuntime/HansProtocol/HansFakes product packages
  - Lineage WebView ARM64 LFS prebuilt materialized when only a pointer exists
USAGE
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

LINEAGE_ROOT="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -f "${LINEAGE_ROOT}/build/envsetup.sh" ]]; then
  echo "Not a Lineage/Android checkout: ${LINEAGE_ROOT}" >&2
  exit 1
fi

copy_dir() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "${dst}")"
  rsync -a --delete "${src}/" "${dst}/"
}

ensure_linux_arm64_go() {
  local arch
  arch="$(uname -m)"
  if [[ "${arch}" != "aarch64" && "${arch}" != "arm64" ]]; then
    return
  fi

  local x86_version_file="${LINEAGE_ROOT}/prebuilts/go/linux-x86/VERSION"
  local arm64_root="${LINEAGE_ROOT}/prebuilts/go/linux-arm64"
  if [[ ! -f "${x86_version_file}" ]]; then
    return
  fi

  local target_version
  target_version="$(head -n1 "${x86_version_file}")"
  if [[ -x "${arm64_root}/bin/go" ]] &&
      "${arm64_root}/bin/go" version 2>/dev/null | grep -q "${target_version} linux/arm64"; then
    if [[ ! -f "${arm64_root}/pkg/linux_arm64/runtime.a" ]]; then
      echo "Installing ${target_version} linux/arm64 Go standard-library archives"
      GOROOT="${arm64_root}" \
        GODEBUG=installgoroot=all \
        GOOS=linux \
        GOARCH=arm64 \
        "${arm64_root}/bin/go" install std
    fi
    return
  fi

  local tmpdir archive
  tmpdir="$(mktemp -d)"
  archive="${tmpdir}/${target_version}.linux-arm64.tar.gz"
  echo "Provisioning ${target_version} linux/arm64 Go toolchain for ARM64 host builds"
  curl -L -o "${archive}" "https://go.dev/dl/${target_version}.linux-arm64.tar.gz"
  rm -rf "${tmpdir}/go" "${arm64_root}"
  tar -C "${tmpdir}" -xzf "${archive}"
  mkdir -p "$(dirname "${arm64_root}")"
  mv "${tmpdir}/go" "${arm64_root}"
  rm -rf "${tmpdir}"

  "${arm64_root}/bin/go" version | grep -q "${target_version} linux/arm64"
  echo "Installing ${target_version} linux/arm64 Go standard-library archives"
  GOROOT="${arm64_root}" \
    GODEBUG=installgoroot=all \
    GOOS=linux \
    GOARCH=arm64 \
    "${arm64_root}/bin/go" install std
}

ensure_linux_musl_arm64_build_tools() {
  local arch
  arch="$(uname -m)"
  if [[ "${arch}" != "aarch64" && "${arch}" != "arm64" ]]; then
    return
  fi

  local arm64_root="${LINEAGE_ROOT}/prebuilts/build-tools/linux_musl-arm64"
  if [[ -x "${arm64_root}/bin/ckati" && -x "${arm64_root}/bin/ninja" ]]; then
    return
  fi

  local candidates=()
  if [[ -n "${HANSOS_AOSP_ROOT:-}" ]]; then
    candidates+=("${HANSOS_AOSP_ROOT}/prebuilts/build-tools/linux_musl-arm64")
  fi
  candidates+=(
    "/home/yearemias/aosp-android14/prebuilts/build-tools/linux_musl-arm64"
    "${REPO_ROOT}/.work/aosp/prebuilts/build-tools/linux_musl-arm64"
  )

  local src=""
  for candidate in "${candidates[@]}"; do
    if [[ -x "${candidate}/bin/ckati" && -x "${candidate}/bin/ninja" ]]; then
      src="${candidate}"
      break
    fi
  done

  if [[ -z "${src}" ]]; then
    echo "Missing native linux_musl-arm64 ckati/ninja build tools for ARM64 host builds" >&2
    echo "Set HANSOS_AOSP_ROOT to an AOSP checkout that contains prebuilts/build-tools/linux_musl-arm64." >&2
    exit 1
  fi

  echo "Provisioning native ARM64 ckati/ninja from ${src}"
  mkdir -p "$(dirname "${arm64_root}")"
  rsync -a --delete "${src}/" "${arm64_root}/"
}

ensure_linux_arm64_rust() {
  local arch
  arch="$(uname -m)"
  if [[ "${arch}" != "aarch64" && "${arch}" != "arm64" ]]; then
    return
  fi

  local version="1.81.0"
  local config_file="${LINEAGE_ROOT}/build/soong/rust/config/global.go"
  if [[ -f "${config_file}" ]]; then
    local configured
    configured="$(sed -n 's/.*RustDefaultVersion = "\([^"]*\)".*/\1/p' "${config_file}" | head -n1)"
    if [[ -n "${configured}" ]]; then
      version="${configured}"
    fi
  fi

  local rustup_bin="${RUSTUP:-${HOME}/.cargo/bin/rustup}"
  if [[ ! -x "${rustup_bin}" ]]; then
    echo "Missing rustup at ${rustup_bin}; needed to provision Rust ${version} for ARM64 host builds" >&2
    exit 1
  fi

  local toolchain="${version}-aarch64-unknown-linux-gnu"
  local rust_path
  rust_path="$(dirname "${rustup_bin}"):/usr/bin:/bin:${PATH}"

  echo "Provisioning Rust ${version} linux/arm64 toolchain for ARM64 host builds"
  PATH="${rust_path}" "${rustup_bin}" toolchain install "${toolchain}"
  PATH="${rust_path}" "${rustup_bin}" target add aarch64-unknown-linux-musl --toolchain "${toolchain}"
  PATH="${rust_path}" "${rustup_bin}" component add rustfmt rust-analyzer --toolchain "${toolchain}"

  local sysroot
  sysroot="$(PATH="${rust_path}" "${rustup_bin}" run "${toolchain}" rustc --print sysroot)"
  if [[ ! -x "${sysroot}/bin/rustc" ]]; then
    echo "Rust sysroot is missing rustc: ${sysroot}" >&2
    exit 1
  fi
  if ! ls "${sysroot}/lib/rustlib/aarch64-unknown-linux-musl/lib/libstd-"*.rlib >/dev/null 2>&1; then
    echo "Rust sysroot is missing aarch64-unknown-linux-musl stdlib: ${sysroot}" >&2
    exit 1
  fi

  local arm64_root="${LINEAGE_ROOT}/prebuilts/rust/linux-arm64"
  local arm64_version_root="${arm64_root}/${version}"
  mkdir -p "${arm64_root}/stable"
  rm -rf "${arm64_root:?}/${version}"
  mkdir -p "${arm64_version_root}/bin"
  ln -s "${sysroot}/lib" "${arm64_version_root}/lib"
  if [[ -d "${sysroot}/share" ]]; then
    ln -s "${sysroot}/share" "${arm64_version_root}/share"
  fi

  local bin_tool
  for bin_tool in "${sysroot}/bin/"*; do
    [[ -e "${bin_tool}" ]] || continue
    local name
    name="$(basename "${bin_tool}")"
    if [[ "${name}" == "rustc" || "${name}" == "rustdoc" || "${name}" == "clippy-driver" ]]; then
      cat >"${arm64_version_root}/bin/${name}" <<EOF
#!/usr/bin/env bash
export RUSTC_BOOTSTRAP=1
exec "${sysroot}/bin/${name}" "\$@"
EOF
      chmod +x "${arm64_version_root}/bin/${name}"
    else
      ln -s "${bin_tool}" "${arm64_version_root}/bin/${name}"
    fi
  done

  local tool
  for tool in rustfmt rust-analyzer; do
    if [[ -x "${arm64_version_root}/bin/${tool}" ]]; then
      ln -sf "../${version}/bin/${tool}" "${arm64_root}/stable/${tool}"
    fi
  done
}

ensure_linux_arm64_jdk21() {
  local arch
  arch="$(uname -m)"
  if [[ "${arch}" != "aarch64" && "${arch}" != "arm64" ]]; then
    return
  fi

  local arm64_root="${LINEAGE_ROOT}/prebuilts/jdk/jdk21/linux-arm64"
  if [[ -x "${arm64_root}/bin/javap" ]]; then
    return
  fi

  local candidates=(
    "/usr/lib/jvm/java-21-openjdk-arm64"
    "/usr/lib/jvm/java-21-openjdk-aarch64"
    "/usr/lib/jvm/openjdk-21"
  )

  local src=""
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "${candidate}/bin/javap" ]]; then
      src="${candidate}"
      break
    fi
  done

  if [[ -z "${src}" ]] && sudo -n true 2>/dev/null; then
    echo "Installing OpenJDK 21 for native ARM64 javap"
    sudo -n apt-get update
    sudo -n apt-get install -y openjdk-21-jdk-headless
    if [[ -x "/usr/lib/jvm/java-21-openjdk-arm64/bin/javap" ]]; then
      src="/usr/lib/jvm/java-21-openjdk-arm64"
    fi
  fi

  if [[ -z "${src}" ]]; then
    echo "Missing native OpenJDK 21 javap for ARM64 host builds" >&2
    echo "Install openjdk-21-jdk-headless or place a JDK at prebuilts/jdk/jdk21/linux-arm64." >&2
    exit 1
  fi

  echo "Provisioning native ARM64 JDK 21 javap from ${src}"
  mkdir -p "$(dirname "${arm64_root}")"
  rsync -a --delete "${src}/" "${arm64_root}/"
}

ensure_linux_arm64_llvm19() {
  local arch
  arch="$(uname -m)"
  if [[ "${arch}" != "aarch64" && "${arch}" != "arm64" ]]; then
    return
  fi

  if command -v /usr/bin/clang++-19 >/dev/null 2>&1 &&
      command -v /usr/bin/ld.lld-19 >/dev/null 2>&1; then
    return
  fi

  if sudo -n true 2>/dev/null; then
    echo "Installing LLVM 19 for native ARM64 Android link probes"
    sudo -n apt-get update
    sudo -n apt-get install -y clang-19 lld-19
    return
  fi

  echo "Missing native clang++-19/lld-19; ARM64 Android links may fall back to slow x86 emulation" >&2
}

ensure_lineage_webview_arm64_lfs() {
  local apk="${LINEAGE_ROOT}/external/chromium-webview/prebuilt/arm64/webview.apk"
  [[ -f "${apk}" ]] || return

  if file "${apk}" | grep -q "Android package"; then
    return
  fi
  if ! grep -q "git-lfs.github.com/spec" "${apk}"; then
    return
  fi

  echo "Materializing Lineage ARM64 WebView LFS prebuilt"
  python3 - "${apk}" <<'PY'
import hashlib
import json
import pathlib
import sys
import urllib.request

apk = pathlib.Path(sys.argv[1])
pointer = apk.read_text()
oid = None
size = None
for line in pointer.splitlines():
    if line.startswith("oid sha256:"):
        oid = line.split(":", 1)[1].strip()
    elif line.startswith("size "):
        size = int(line.split()[1])
if not oid or not size:
    raise SystemExit(f"could not parse Git LFS pointer: {apk}")

url = "https://review.lineageos.org/LineageOS/android_external_chromium-webview_prebuilt_arm64.git/info/lfs/objects/batch"
payload = {
    "operation": "download",
    "transfers": ["basic"],
    "objects": [{"oid": oid, "size": size}],
}
request = urllib.request.Request(
    url,
    data=json.dumps(payload).encode(),
    headers={
        "Accept": "application/vnd.git-lfs+json",
        "Content-Type": "application/vnd.git-lfs+json",
    },
)
with urllib.request.urlopen(request, timeout=60) as response:
    data = json.load(response)
obj = data["objects"][0]
if "error" in obj:
    raise SystemExit(f"Git LFS server error: {obj['error']}")
href = obj["actions"]["download"]["href"]

tmp = apk.with_suffix(".apk.download")
hasher = hashlib.sha256()
total = 0
with urllib.request.urlopen(href, timeout=120) as response, tmp.open("wb") as fh:
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        fh.write(chunk)
        hasher.update(chunk)
        total += len(chunk)
if total != size:
    raise SystemExit(f"WebView LFS size mismatch: got {total}, expected {size}")
actual = hasher.hexdigest()
if actual != oid:
    raise SystemExit(f"WebView LFS sha256 mismatch: got {actual}, expected {oid}")
tmp.replace(apk)
print(f"Materialized {apk} ({total} bytes)")
PY
}

ensure_linux_arm64_go
ensure_linux_musl_arm64_build_tools
ensure_linux_arm64_rust
ensure_linux_arm64_jdk21
ensure_linux_arm64_llvm19
ensure_lineage_webview_arm64_lfs

copy_dir "${REPO_ROOT}/aosp/frameworks/base/services/core/java/ai/hansos" \
  "${LINEAGE_ROOT}/frameworks/base/services/core/java/ai/hansos"
copy_dir "${REPO_ROOT}/aosp/packages/apps/HansCanvas" \
  "${LINEAGE_ROOT}/packages/apps/HansCanvas"
copy_dir "${REPO_ROOT}/runtime/HansRuntimeService" \
  "${LINEAGE_ROOT}/packages/services/HansRuntimeService"
copy_dir "${REPO_ROOT}/protocol" \
  "${LINEAGE_ROOT}/packages/modules/HansProtocol"
copy_dir "${REPO_ROOT}/fakes" \
  "${LINEAGE_ROOT}/packages/modules/HansFakes"

"${SCRIPT_DIR}/patch-mp01-lineage.py" "${LINEAGE_ROOT}"

cat <<EOF
HansOS MP01 Lineage overlay integrated into:
  ${LINEAGE_ROOT}

Next:
  cd ${LINEAGE_ROOT}
  source build/envsetup.sh
  lunch treble_arm64_bvN-bp1a-userdebug
  m HansCanvasSystem HansRuntimeServiceSystem services systemimage
EOF
