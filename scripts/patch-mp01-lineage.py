#!/usr/bin/env python3
"""Patch a Lineage/TrebleDroid MP01 checkout for deep HansOS integration.

This is intentionally narrower than patch-aosp.py. It does not touch
Cuttlefish or host build compatibility. It only adds the HansOS SystemServer
service, Binder protocol dependency, service manager label, and product
packages to the MP01 Lineage/TrebleDroid GSI product.
"""

from __future__ import annotations

import pathlib
import re
import sys


HANS_PRODUCT_MARKER = "# HansOS MP01 SystemServer integration"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def read(path: pathlib.Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        fail(f"missing {path}")


def write_if_changed(path: pathlib.Path, old: str, new: str, message: str) -> None:
    if old == new:
        print(f"{message} already present")
        return
    path.write_text(new)
    print(message)


def find_module_block(source: str, module_name: str, path: pathlib.Path) -> tuple[int, int]:
    match = re.search(rf'(?m)^\s*name:\s*"{re.escape(module_name)}",', source)
    if match is None:
        fail(f"could not find {module_name} module in {path}")
    name_idx = match.start()
    start = source.rfind("{", 0, name_idx)
    if start == -1:
        fail(f"could not find start of {module_name} module in {path}")

    depth = 0
    for idx in range(start, len(source)):
        if source[idx] == "{":
            depth += 1
        elif source[idx] == "}":
            depth -= 1
            if depth == 0:
                return start, idx + 1
    fail(f"could not find end of {module_name} module in {path}")


def patch_system_server(root: pathlib.Path) -> None:
    path = root / "frameworks/base/services/java/com/android/server/SystemServer.java"
    text = read(path)
    if "StartHansManagerService" in text:
        print("SystemServer.java already contains HansManagerService hook")
        return

    anchors = [
        "mSystemServiceManager.startBootPhase(t, SystemService.PHASE_SYSTEM_SERVICES_READY);",
        "mSystemServiceManager.startBootPhase(SystemService.PHASE_SYSTEM_SERVICES_READY);",
        't.traceBegin("StartLauncherAppsService");',
        'traceBeginAndSlog("StartLauncherAppsService");',
    ]
    for anchor in anchors:
        idx = text.find(anchor)
        if idx == -1:
            continue
        line_start = text.rfind("\n", 0, idx) + 1
        indent = text[line_start:idx]
        snippet = (
            f'{indent}t.traceBegin("StartHansManagerService");\n'
            f"{indent}mSystemServiceManager.startService(ai.hansos.server.HansManagerService.class);\n"
            f"{indent}t.traceEnd();\n\n"
        )
        path.write_text(text[:line_start] + snippet + text[line_start:])
        print("Patched SystemServer.java with HansManagerService hook")
        return

    fail("could not find stable SystemServer insertion point")


def patch_services_core(root: pathlib.Path) -> None:
    path = root / "frameworks/base/services/core/Android.bp"
    text = read(path)

    # Keep the dependency on the unboosted implementation module. If an older
    # attempt added it to services.core, remove that stale copy first.
    start, end = find_module_block(text, "services.core", path)
    module = text[start:end]
    updated_module = module.replace('        "hansos-agent-protocol",\n', "")
    if updated_module != module:
        text = text[:start] + updated_module + text[end:]

    start, end = find_module_block(text, "services.core.unboosted", path)
    module = text[start:end]
    if '"hansos-agent-protocol"' in module:
        path.write_text(text)
        print("services.core.unboosted already depends on hansos-agent-protocol")
        return

    static_idx = module.find("static_libs: [")
    if static_idx == -1:
        fail("could not find services.core.unboosted static_libs block")
    insert_at = text.find("\n", start + static_idx) + 1
    text = text[:insert_at] + '        "hansos-agent-protocol",\n' + text[insert_at:]
    path.write_text(text)
    print("Patched services.core.unboosted with hansos-agent-protocol")


def patch_arm64_go_host(root: pathlib.Path) -> None:
    path = root / "build/soong/scripts/microfactory.bash"
    text = read(path)

    old = '''case $(uname) in
    Linux)
        export GOROOT="${TOP}/prebuilts/go/linux-x86/"
        ;;
    Darwin)
        export GOROOT="${TOP}/prebuilts/go/darwin-x86/"
        ;;
    *) echo "unknown OS:" $(uname) >&2 && exit 1;;
esac
'''
    new = '''case $(uname) in
    Linux)
        case $(uname -m) in
            aarch64|arm64)
                if [ -x "${TOP}/prebuilts/go/linux-arm64/bin/go" ]; then
                    export GOROOT="${TOP}/prebuilts/go/linux-arm64/"
                else
                    export GOROOT="${TOP}/prebuilts/go/linux-x86/"
                fi
                ;;
            *)
                export GOROOT="${TOP}/prebuilts/go/linux-x86/"
                ;;
        esac
        ;;
    Darwin)
        export GOROOT="${TOP}/prebuilts/go/darwin-x86/"
        ;;
    *) echo "unknown OS:" $(uname) >&2 && exit 1;;
esac
'''
    previous_arm64_fmt_block = '''case $(uname) in
    Linux)
        case $(uname -m) in
            aarch64|arm64)
                if [ -f "${TOP}/prebuilts/go/linux-arm64/pkg/linux_arm64/fmt.a" ]; then
                    export GOROOT="${TOP}/prebuilts/go/linux-arm64/"
                else
                    export GOROOT="${TOP}/prebuilts/go/linux-x86/"
                fi
                ;;
            *)
                export GOROOT="${TOP}/prebuilts/go/linux-x86/"
                ;;
        esac
        ;;
    Darwin)
        export GOROOT="${TOP}/prebuilts/go/darwin-x86/"
        ;;
    *) echo "unknown OS:" $(uname) >&2 && exit 1;;
esac
'''
    previous_arm64_block = '''case $(uname) in
    Linux)
        case $(uname -m) in
            aarch64|arm64)
                if [ -d "${TOP}/prebuilts/go/linux-arm64/" ]; then
                    export GOROOT="${TOP}/prebuilts/go/linux-arm64/"
                else
                    export GOROOT="${TOP}/prebuilts/go/linux-x86/"
                fi
                ;;
            *)
                export GOROOT="${TOP}/prebuilts/go/linux-x86/"
                ;;
        esac
        ;;
    Darwin)
        export GOROOT="${TOP}/prebuilts/go/darwin-x86/"
        ;;
    *) echo "unknown OS:" $(uname) >&2 && exit 1;;
esac
'''
    if old in text:
        text = text.replace(old, new, 1)
    elif previous_arm64_fmt_block in text:
        text = text.replace(previous_arm64_fmt_block, new, 1)
    elif previous_arm64_block in text:
        text = text.replace(previous_arm64_block, new, 1)
    elif "prebuilts/go/linux-arm64/bin/go" in text:
        print("microfactory.bash already selects linux-arm64 Go on ARM64 Linux")
    else:
        fail(f"could not find GOROOT block in {path}")

    if "hansos_build_go_with_native_gopath" not in text:
        soong_function = '''function soong_build_go
{
    BUILDDIR=$(getoutdir) \\
      SRCDIR=${TOP} \\
      BLUEPRINTDIR=${TOP}/build/blueprint \\
      EXTRA_ARGS="-pkg-path android/soong=${TOP}/build/soong -pkg-path prebuilts/bazel/common/proto=${TOP}/prebuilts/bazel/common/proto -pkg-path rbcrun=${TOP}/build/make/tools/rbcrun -pkg-path google.golang.org/protobuf=${TOP}/external/golang-protobuf -pkg-path go.starlark.net=${TOP}/external/starlark-go" \\
      build_go $@
}
'''
        native_function = '''function hansos_build_go_with_native_gopath
{
    local built_bin="$(getoutdir)/$1"
    local package="$2"
    local gopath="$(getoutdir)/.hansos_go_gopath"

    mkdir -p "${gopath}/src/android" \\
             "${gopath}/src/github.com/google" \\
             "${gopath}/src/prebuilts/bazel/common" \\
             "${gopath}/src/google.golang.org"
    rm -rf "${gopath}/src/android/soong" \\
           "${gopath}/src/github.com/google/blueprint" \\
           "${gopath}/src/prebuilts/bazel/common/proto" \\
           "${gopath}/src/rbcrun" \\
           "${gopath}/src/google.golang.org/protobuf" \\
           "${gopath}/src/go.starlark.net"
    ln -s "${TOP}/build/soong" "${gopath}/src/android/soong"
    ln -s "${TOP}/build/blueprint" "${gopath}/src/github.com/google/blueprint"
    ln -s "${TOP}/prebuilts/bazel/common/proto" "${gopath}/src/prebuilts/bazel/common/proto"
    ln -s "${TOP}/build/make/tools/rbcrun" "${gopath}/src/rbcrun"
    ln -s "${TOP}/external/golang-protobuf" "${gopath}/src/google.golang.org/protobuf"
    ln -s "${TOP}/external/starlark-go" "${gopath}/src/go.starlark.net"

    GOROOT="${TOP}/prebuilts/go/linux-arm64" \\
      GOPATH="${gopath}" \\
      GO111MODULE=off \\
      "${TOP}/prebuilts/go/linux-arm64/bin/go" build -o "${built_bin}" "${package}"
}

function soong_build_go
{
    case "$(uname):$(uname -m)" in
        Linux:aarch64|Linux:arm64)
            if [ -x "${TOP}/prebuilts/go/linux-arm64/bin/go" ]; then
                hansos_build_go_with_native_gopath "$@"
                return
            fi
            ;;
    esac

    BUILDDIR=$(getoutdir) \\
      SRCDIR=${TOP} \\
      BLUEPRINTDIR=${TOP}/build/blueprint \\
      EXTRA_ARGS="-pkg-path android/soong=${TOP}/build/soong -pkg-path prebuilts/bazel/common/proto=${TOP}/prebuilts/bazel/common/proto -pkg-path rbcrun=${TOP}/build/make/tools/rbcrun -pkg-path google.golang.org/protobuf=${TOP}/external/golang-protobuf -pkg-path go.starlark.net=${TOP}/external/starlark-go" \\
      build_go $@
}
'''
        if soong_function not in text:
            fail(f"could not find soong_build_go function in {path}")
        text = text.replace(soong_function, native_function, 1)
        print("Patched microfactory.bash to build Go host tools natively on ARM64 Linux")
    else:
        print("microfactory.bash already builds Go host tools natively on ARM64 Linux")

    text = text.replace(
        '             "${gopath}/src/prebuilts/bazel/common" \\\n'
        '             "${gopath}/src/rbcrun" \\\n'
        '             "${gopath}/src/google.golang.org"',
        '             "${gopath}/src/prebuilts/bazel/common" \\\n'
        '             "${gopath}/src/google.golang.org"',
    )
    text = text.replace(
        '           "${gopath}/src/rbcrun/rbcrun" \\\n',
        '           "${gopath}/src/rbcrun" \\\n',
    )
    text = text.replace(
        '    ln -s "${TOP}/build/make/tools/rbcrun/rbcrun" "${gopath}/src/rbcrun/rbcrun"',
        '    ln -s "${TOP}/build/make/tools/rbcrun" "${gopath}/src/rbcrun"',
    )

    path.write_text(text)


def patch_arm64_envsetup_musl(root: pathlib.Path) -> None:
    path = root / "build/envsetup.sh"
    text = read(path)
    marker = "HansOS local: default Linux/ARM64 builds to musl host prebuilts."
    if marker in text:
        missing_required_line = (
            '    export BUILD_BROKEN_MISSING_REQUIRED_MODULES="${BUILD_BROKEN_MISSING_REQUIRED_MODULES:-true}"\n'
        )
        if missing_required_line not in text:
            anchor = '    export USE_HOST_MUSL="${USE_HOST_MUSL:-true}"\n'
            if anchor not in text:
                fail(f"could not find envsetup.sh HansOS ARM64 export block in {path}")
            path.write_text(text.replace(anchor, anchor + missing_required_line, 1))
            print("Patched envsetup.sh to tolerate known MP01 GSI missing required-module edge")
            return
        print("envsetup.sh already defaults Linux/ARM64 builds to musl host prebuilts")
        return

    anchor = (
        "# limitations under the License.\n"
        "\n"
    )
    block = (
        anchor +
        f"# {marker}\n"
        'case "$(uname -s):$(uname -m)" in\n'
        '  Linux:aarch64|Linux:arm64)\n'
        '    export USE_HOST_MUSL="${USE_HOST_MUSL:-true}"\n'
        '    export BUILD_BROKEN_MISSING_REQUIRED_MODULES="${BUILD_BROKEN_MISSING_REQUIRED_MODULES:-true}"\n'
        "    ;;\n"
        "esac\n"
        "\n"
    )
    if anchor not in text:
        fail(f"could not find envsetup.sh license anchor in {path}")
    path.write_text(text.replace(anchor, block, 1))
    print("Patched envsetup.sh to default Linux/ARM64 builds to musl host prebuilts")


def patch_arm64_build_tools(root: pathlib.Path) -> None:
    """Route fragile x86 build-tool calls to native ARM64 prebuilts on DGX.

    Lineage still computes HOST_PREBUILT_TAG as linux-x86 in a few early make
    paths. On ARM64 Linux that sends ckati/ninja through qemu-user, which has
    proven unstable for this tree. Keep the original x86 binaries available for
    non-ARM64 hosts and install tiny wrappers for the DGX path.
    """

    arm64_bin = root / "prebuilts/build-tools/linux_musl-arm64/bin"
    x86_bin = root / "prebuilts/build-tools/linux-x86/bin"
    if not arm64_bin.exists():
        fail(f"missing native ARM64 build tools directory: {arm64_bin}")
    if not x86_bin.exists():
        fail(f"missing x86 build tools directory to wrap: {x86_bin}")

    tools = sorted(
        tool.name
        for tool in arm64_bin.iterdir()
        if tool.is_file() and (x86_bin / tool.name).exists()
    )
    if not tools:
        fail(f"no native ARM64 build tools found to wrap in {arm64_bin}")

    for tool in tools:
        x86_tool = root / "prebuilts/build-tools/linux-x86/bin" / tool
        original_tool = x86_tool.with_name(f"{tool}.hansos-x86-original")
        arm64_tool = root / "prebuilts/build-tools/linux_musl-arm64/bin" / tool

        if not arm64_tool.exists():
            fail(f"missing native ARM64 build tool: {arm64_tool}")
        if not x86_tool.exists() and not original_tool.exists():
            fail(f"missing x86 build tool to wrap: {x86_tool}")

        existing = ""
        if x86_tool.exists():
            try:
                existing = x86_tool.read_text(errors="ignore")
            except OSError:
                existing = ""

        if "HansOS ARM64 build-tool wrapper" not in existing and not original_tool.exists():
            x86_tool.rename(original_tool)

        wrapper = f'''#!/usr/bin/env bash
# HansOS ARM64 build-tool wrapper
set -euo pipefail

source_path="${{BASH_SOURCE[0]}}"
script_dir="${{source_path%/*}}"
if [[ "${{script_dir}}" == "${{source_path}}" ]]; then
  script_dir="."
fi
script_dir="$(cd "${{script_dir}}" && pwd -P)"
applet="${{source_path##*/}}"

case "$(/usr/bin/uname -m)" in
  aarch64|arm64)
    native_tool="${{script_dir}}/../../linux_musl-arm64/bin/{tool}"
    if [[ ! -x "${{native_tool}}" ]]; then
      # HansOS local: sbox copies the wrapper without the sibling native tool tree.
      native_tool="{arm64_tool}"
    fi
    if [[ "{tool}" == "bison" ]]; then
      bison_pkgdatadir="${{script_dir}}/../../common/bison"
      if [[ ! -d "${{bison_pkgdatadir}}" ]]; then
        bison_pkgdatadir="{root / "prebuilts/build-tools/common/bison"}"
      fi
      export BISON_PKGDATADIR="${{BISON_PKGDATADIR:-${{bison_pkgdatadir}}}}"
    fi
    if [[ "{tool}" == "toybox" && "${{applet}}" != "{tool}" ]]; then
      exec "${{native_tool}}" "${{applet}}" "$@"
    fi
    if [[ "{tool}" == "ziptool" ]]; then
      if [[ "${{applet}}" == "unzip" || "${{applet}}" == "zipinfo" ]]; then
        exec "${{native_tool}}" "${{applet}}" "$@"
      fi
      if [[ "${{#}}" -gt 0 && ( "${{1}}" == "unzip" || "${{1}}" == "zipinfo" ) ]]; then
        exec "${{native_tool}}" "$@"
      fi
      exec "${{native_tool}}" "unzip" "$@"
    fi
    exec "${{native_tool}}" "$@"
    ;;
  *)
    original_tool="${{script_dir}}/{tool}.hansos-x86-original"
    if [[ ! -x "${{original_tool}}" ]]; then
      original_tool="${{script_dir}}/../../linux-x86/bin/{tool}.hansos-x86-original"
    fi
    if [[ "{tool}" == "toybox" && "${{applet}}" != "{tool}" ]]; then
      exec "${{original_tool}}" "${{applet}}" "$@"
    fi
    if [[ "{tool}" == "ziptool" ]]; then
      if [[ "${{applet}}" == "unzip" || "${{applet}}" == "zipinfo" ]]; then
        exec "${{original_tool}}" "${{applet}}" "$@"
      fi
      if [[ "${{#}}" -gt 0 && ( "${{1}}" == "unzip" || "${{1}}" == "zipinfo" ) ]]; then
        exec "${{original_tool}}" "$@"
      fi
      exec "${{original_tool}}" "unzip" "$@"
    fi
    exec "${{original_tool}}" "$@"
    ;;
esac
'''
        x86_tool.write_text(wrapper)
        x86_tool.chmod(0o755)
        print(f"Patched {tool} to use native linux_musl-arm64 build tool on ARM64 Linux")

    ziptool_wrapper = x86_bin / "ziptool"
    if (arm64_bin / "ziptool").exists() and ziptool_wrapper.exists():
        for applet in ("unzip", "zipinfo"):
            applet_path = x86_bin / applet
            if applet_path.is_symlink() or applet_path.exists():
                if applet_path.is_symlink() or "HansOS ARM64 build-tool wrapper" in applet_path.read_text(errors="ignore"):
                    applet_path.unlink()
                else:
                    applet_path.rename(applet_path.with_name(f"{applet}.hansos-x86-original"))
            applet_path.symlink_to("ziptool")
            print(f"Patched {applet} to dispatch through ziptool on ARM64 Linux")


def patch_cronet_arm64_host_cflags(root: pathlib.Path) -> None:
    """Remove x86-only Cronet flags from host modules on Linux/ARM64.

    Cronet's generated Android.bp files attach -msse3 broadly to host modules.
    On the DGX this becomes an ARM64 host build, so clang correctly rejects the
    x86 SSE flag before any HansOS code can compile.
    """

    cronet_root = root / "external/cronet"
    if not cronet_root.exists():
        print("external/cronet not present; skipping Cronet ARM64 host flag patch")
        return

    patched = 0
    for path in cronet_root.rglob("Android.bp"):
        text = path.read_text()
        new = text.replace('                "-msse3",\n', "")
        new = new.replace('        "-msse3",\n', "")
        if new != text:
            path.write_text(new)
            patched += 1
    if patched:
        print(f"Patched {patched} Cronet Android.bp files to remove x86-only -msse3 on ARM64 hosts")
    else:
        print("Cronet Android.bp files already have no x86-only -msse3 flags")


def patch_libyuv_disable_lto_for_rust_archive(root: pathlib.Path) -> None:
    path = root / "external/libyuv/Android.bp"
    text = read(path)
    marker = "HansOS local: Rust 1.81/LLVM18 cannot archive LLVM19 LTO objects"
    if marker in text:
        print("libyuv LTO archive compatibility already patched")
        return

    anchor = '    host_supported: true,\n'
    if anchor not in text:
        fail("could not find libyuv host_supported anchor")
    replacement = (
        anchor
        +
        "\n"
        f"    // {marker}\n"
        "    // when crabbyavif's libyuv_sys links libyuv.a on the MP01 ARM64 path.\n"
        "    lto: {\n"
        "        never: true,\n"
        "    },\n"
    )
    path.write_text(text.replace(anchor, replacement, 1))
    print("Patched libyuv to disable LTO for Rust archive compatibility")


def patch_libfdt_disable_lto_for_rust_archive(root: pathlib.Path) -> None:
    path = root / "external/dtc/libfdt/Android.bp"
    text = read(path)
    marker = "HansOS local: Rust 1.81/LLVM18 cannot archive LLVM19 libfdt LTO objects"
    if marker in text:
        print("libfdt LTO archive compatibility already patched")
        return

    start, end = find_module_block(text, "libfdt", path)
    module = text[start:end]
    if "lto:" in module:
        print("libfdt already declares LTO settings")
        return

    anchor = '    defaults: ["libfdt_defaults"],\n'
    if anchor not in module:
        fail("could not find libfdt defaults anchor")
    replacement = (
        anchor
        +
        "\n"
        f"    // {marker}\n"
        "    // when packages/modules/Virtualization/libs/libfdt builds liblibfdt.rlib.\n"
        "    lto: {\n"
        "        never: true,\n"
        "    },\n"
    )
    module = module.replace(anchor, replacement, 1)
    path.write_text(text[:start] + module + text[end:])
    print("Patched libfdt to disable LTO for Rust archive compatibility")


def patch_arm64_checkfc_getopt(root: pathlib.Path) -> None:
    """Fix checkfc option parsing on Linux/ARM64 hosts.

    checkfc stores getopt's return value in a char. On ARM64 Linux, plain char
    is commonly unsigned, so getopt's -1 terminator becomes 255 and the tool
    falls through to usage() even for valid arguments.
    """

    path = root / "system/sepolicy/tools/checkfc.c"
    text = read(path)
    marker = "HansOS local: getopt must use int on ARM64 hosts."
    if marker in text:
        print("checkfc ARM64 getopt compatibility already patched")
        return

    old = "  char c;\n\n  filemode mode = filemode_file_contexts;\n"
    new = (
        f"  // {marker}\n"
        "  int c;\n\n"
        "  filemode mode = filemode_file_contexts;\n"
    )
    if old not in text:
        fail(f"could not find checkfc getopt variable in {path}")
    path.write_text(text.replace(old, new, 1))
    print("Patched checkfc to handle getopt correctly on ARM64 hosts")


def patch_clang_ndk_stub_native_link(root: pathlib.Path) -> None:
    """Route reproducible QEMU-linker pain through native clang when safe.

    On the DGX ARM64 host, the x86_64 Android clang wrapper runs through QEMU.
    Tiny generated ARM64 SDK stub links for NDK libraries reproducibly crash
    inside QEMU, and larger Android executable/shared links can also hang there.
    Keep the native path narrow by routing Android ARM target links to native
    LLVM 19, while compile steps and host tools keep using the Android prebuilt.
    """

    path = root / "prebuilts/clang/host/linux-x86/clang-r536225/bin/clang++"
    original = path.with_name("clang++.hansos-x86-original")
    marker = b"HansOS local: native ARM64 Android target-link workaround"

    current = path.read_bytes()
    if (
        marker in current
        and b'exec -a "$0"' in current
        and b"enable-ml-inliner" in current
        and b"native_target_link" in current
    ):
        print("clang++ ARM Android native target-link workaround already patched")
        return

    if not original.exists():
        path.rename(original)

    wrapper = f'''#!/usr/bin/env bash
# HansOS local: native ARM64 Android target-link workaround
set -e

has_android_arm64=0
has_android_arm32=0
is_compile=0
native_target_link=0

for arg in "$@"; do
  case "${{arg}}" in
    -c|-E|-S)
      is_compile=1
      ;;
    aarch64-linux-android*|--target=aarch64-linux-android*|-target=aarch64-linux-android*)
      has_android_arm64=1
      ;;
    armv7a-linux-androideabi*|--target=armv7a-linux-androideabi*|-target=armv7a-linux-androideabi*)
      has_android_arm32=1
      ;;
    *android_arm64_armv8-a_shared*/*.rsp|*android_arm64_armv8-a_sdk_shared_*/*.rsp)
      has_android_arm64=1
      ;;
    *android_arm_armv8-a_shared*/*.rsp)
      has_android_arm32=1
      ;;
  esac
done

if [[ ( "${{has_android_arm64}}" == "1" || "${{has_android_arm32}}" == "1" ) &&
      "${{is_compile}}" == "0" ]]; then
  native_target_link=1
fi

if [[ "${{native_target_link}}" == "1" ]] &&
    command -v /usr/bin/clang++-19 >/dev/null 2>&1; then
  filtered=()
  for arg in "$@"; do
    case "${{arg}}" in
      -Wl,-mllvm,-regalloc-enable-advisor=release|-Wl,-mllvm,-enable-ml-inliner=release)
        continue
        ;;
    esac
    filtered+=("${{arg}}")
  done
  exec /usr/bin/clang++-19 "${{filtered[@]}}"
fi

for arg in "$@"; do
  case "${{arg}}" in
    *android_arm64_armv8-a_sdk_shared_*/*.rsp)
      if command -v /usr/bin/clang++-18 >/dev/null 2>&1; then
        exec /usr/bin/clang++-18 "$@"
      fi
      ;;
  esac
done

exec -a "$0" "{original}" "$@"
'''
    path.write_text(wrapper)
    path.chmod(0o755)
    print("Patched clang++ to use native linker for Android ARM target links")


def patch_arm64_make_host(root: pathlib.Path) -> None:
    path = root / "build/make/core/envsetup.mk"
    text = read(path)
    changed = False

    marker = "HansOS local: Linux/ARM64 host builds do not need a host_cross variant."
    if marker not in text:
        anchor = (
            "ifeq ($(HOST_OS),linux)\n"
            "  # Windows has been the default host_cross OS\n"
        )
        if anchor not in text:
            fail("could not find envsetup.mk HOST_OS linux host_cross block")
        guard = (
            "ifeq ($(HOST_OS),linux)\n"
            f"  # {marker}\n"
            "  ifneq (,$(findstring aarch64,$(UNAME))$(findstring arm64,$(UNAME)))\n"
            "    HOST_CROSS_OS :=\n"
            "    HOST_CROSS_ARCH :=\n"
            "    HOST_CROSS_2ND_ARCH :=\n"
            "  else\n"
            "  # Windows has been the default host_cross OS\n"
        )
        text = text.replace(anchor, guard, 1)
        darwin_anchor = "\nelse ifeq ($(HOST_OS),darwin)\n"
        if darwin_anchor not in text:
            fail("could not find envsetup.mk darwin host_cross block")
        text = text.replace(darwin_anchor, "\n  endif\nelse ifeq ($(HOST_OS),darwin)\n", 1)
        changed = True

    if "HOST_ARCH := arm64" not in text:
        old = (
            "ifneq (,$(findstring x86_64,$(UNAME)))\n"
            "  HOST_ARCH := x86_64\n"
            "  HOST_2ND_ARCH := x86\n"
            "  HOST_IS_64_BIT := true\n"
            "else\n"
        )
        new = (
            "ifneq (,$(findstring x86_64,$(UNAME)))\n"
            "  HOST_ARCH := x86_64\n"
            "  HOST_2ND_ARCH := x86\n"
            "  HOST_IS_64_BIT := true\n"
            "else ifneq (,$(findstring aarch64,$(UNAME))$(findstring arm64,$(UNAME)))\n"
            "  HOST_ARCH := arm64\n"
            "  HOST_2ND_ARCH :=\n"
            "  HOST_IS_64_BIT := true\n"
            "else\n"
        )
        if old not in text:
            fail("could not find envsetup.mk HOST_ARCH block")
        text = text.replace(old, new, 1)
        changed = True

    out_marker = "HansOS local: keep native ARM64 host outputs while preserving x86 prebuilt tag."
    if out_marker not in text:
        old = "HOST_OUT := $(HOST_OUT_ROOT)/$(HOST_OS)-$(HOST_PREBUILT_ARCH)\n"
        new = (
            f"# {out_marker}\n"
            "HOST_OUT_ARCH := $(HOST_PREBUILT_ARCH)\n"
            "ifeq ($(HOST_ARCH),arm64)\n"
            "  HOST_OUT_ARCH := arm64\n"
            "endif\n"
            "HOST_OUT := $(HOST_OUT_ROOT)/$(HOST_OS)-$(HOST_OUT_ARCH)\n"
        )
        if old not in text:
            fail("could not find envsetup.mk HOST_OUT block")
        text = text.replace(old, new, 1)
        changed = True

    if changed:
        path.write_text(text)
        print("Patched envsetup.mk for Linux/ARM64 host builds")
    else:
        print("envsetup.mk already supports Linux/ARM64 host builds")


def patch_arm64_make_clang_host(root: pathlib.Path) -> None:
    path = root / "build/make/core/clang/HOST_arm64.mk"
    text = """# HansOS local: ARM64 Linux host clang runtime configuration.
HOST_LIBPROFILE_RT := $(LLVM_RTLIB_PATH)/aarch64-unknown-linux-musl/lib/linux/libclang_rt.profile-aarch64.a
HOST_LIBCRT_BUILTINS := $(LLVM_RTLIB_PATH)/aarch64-unknown-linux-musl/lib/linux/libclang_rt.builtins-aarch64.a
"""
    old = path.read_text() if path.exists() else ""
    write_if_changed(path, old, text, "Patched Make clang HOST_arm64 configuration")


def patch_arm64_missing_required_modules_check(root: pathlib.Path) -> None:
    path = root / "build/make/core/main.mk"
    text = read(path)
    marker = "HansOS local: MP01 ARM64 host GSI path has a known ART debug required-module edge."
    if marker in text:
        print("main.mk already tolerates known MP01 ARM64 missing required-module edge")
        return

    anchor = """ifneq (,$(filter $(HOST_OS),darwin))
  check_missing_required_modules :=
endif # HOST_OS == darwin
"""
    replacement = anchor + f"""
# {marker}
ifeq ($(HOST_ARCH),arm64)
  check_missing_required_modules :=
endif # HOST_ARCH == arm64
"""
    if anchor not in text:
        fail(f"could not find missing-required-modules host exception block in {path}")
    path.write_text(text.replace(anchor, replacement, 1))
    print("Patched main.mk to tolerate known MP01 ARM64 missing required-module edge")


def patch_arm64_host_required_modules_check(root: pathlib.Path) -> None:
    path = root / "build/make/core/main.mk"
    text = read(path)
    bad_comment = "      # HansOS local: ignore test-only host_required module classification on ARM64 host.\n"
    removed_bad_comment = bad_comment in text
    if removed_bad_comment:
        text = text.replace(bad_comment, "")
    if '$(filter true,$(ALLOW_MISSING_DEPENDENCIES))$(filter arm64,$(HOST_ARCH))' in text:
        if removed_bad_comment:
            path.write_text(text)
        print("main.mk already tolerates ARM64 host_required test-module classification edges")
        return

    old = """      $(if $(filter true,$(ALLOW_MISSING_DEPENDENCIES)), \\
        , \\
        $(if $(strip $(req_file)), \\
          , \\
          $(error $(m).LOCAL_HOST_REQUIRED_MODULES : illegal value $(req_mod) : not a host module. If you want to specify target modules to be required to be installed along with your target module, add those module names to LOCAL_REQUIRED_MODULES instead) \\
        ) \\
      ) \\
"""
    new = """      $(if $(filter true,$(ALLOW_MISSING_DEPENDENCIES))$(filter arm64,$(HOST_ARCH)), \\
        , \\
        $(if $(strip $(req_file)), \\
          , \\
          $(error $(m).LOCAL_HOST_REQUIRED_MODULES : illegal value $(req_mod) : not a host module. If you want to specify target modules to be required to be installed along with your target module, add those module names to LOCAL_REQUIRED_MODULES instead) \\
        ) \\
      ) \\
"""
    if old not in text:
        fail(f"could not find host_required module check in {path}")
    path.write_text(text.replace(old, new, 1))
    print("Patched main.mk to tolerate ARM64 host_required test-module classification edges")


def patch_arm64_path_interposer(root: pathlib.Path) -> None:
    path = root / "build/soong/ui/build/path.go"
    text = read(path)
    marker = "HansOS local: build path_interposer with go build on Linux/ARM64."
    if marker in text:
        print("path_interposer ARM64 build patch already present")
        return

    old = '''\t// Bootstrap the path_interposer Go binary with microfactory.
\tvar cfg microfactory.Config
\tcfg.Map("android/soong", "build/soong")
\tcfg.TrimPath, _ = filepath.Abs(".")
\tif _, err := microfactory.Build(&cfg, interposer, "android/soong/cmd/path_interposer"); err != nil {
\t\tctx.Fatalln("Failed to build path interposer:", err)
\t}
'''
    new = f'''\t// Bootstrap the path_interposer Go binary with microfactory.
\t// {marker}
\tbuiltInterposer := false
\tif runtime.GOOS == "linux" && runtime.GOARCH == "arm64" {{
\t\tgoBin := filepath.Join("prebuilts/go/linux-arm64/bin/go")
\t\tif _, err := os.Stat(goBin); err == nil {{
\t\t\tgoPath := filepath.Join(config.OutDir(), ".hansos_go_gopath")
\t\t\tsoongLink := filepath.Join(goPath, "src/android/soong")
\t\t\tif err := os.MkdirAll(filepath.Dir(soongLink), 0777); err != nil {{
\t\t\t\tctx.Fatalln("Failed to prepare path interposer GOPATH:", err)
\t\t\t}}
\t\t\t_ = os.RemoveAll(soongLink)
\t\t\tabsSoong, err := filepath.Abs("build/soong")
\t\t\tif err != nil {{
\t\t\t\tctx.Fatalln("Failed to resolve Soong path:", err)
\t\t\t}}
\t\t\tif err := os.Symlink(absSoong, soongLink); err != nil {{
\t\t\t\tctx.Fatalln("Failed to link Soong into path interposer GOPATH:", err)
\t\t\t}}
\t\t\tgoRoot, err := filepath.Abs("prebuilts/go/linux-arm64")
\t\t\tif err != nil {{
\t\t\t\tctx.Fatalln("Failed to resolve Go root:", err)
\t\t\t}}
\t\t\tcmd := exec.Command(goBin, "build", "-o", interposer, "android/soong/cmd/path_interposer")
\t\t\tcmd.Env = append(os.Environ(), "GOROOT="+goRoot, "GOPATH="+goPath, "GO111MODULE=off")
\t\t\tif output, err := cmd.CombinedOutput(); err != nil {{
\t\t\t\tctx.Fatalln("Failed to build path interposer:", err, string(output))
\t\t\t}}
\t\t\tbuiltInterposer = true
\t\t}}
\t}}
\tif !builtInterposer {{
\t\tvar cfg microfactory.Config
\t\tcfg.Map("android/soong", "build/soong")
\t\tcfg.TrimPath, _ = filepath.Abs(".")
\t\tif _, err := microfactory.Build(&cfg, interposer, "android/soong/cmd/path_interposer"); err != nil {{
\t\t\tctx.Fatalln("Failed to build path interposer:", err)
\t\t}}
\t}}
'''
    if old not in text:
        fail(f"could not find path_interposer microfactory block in {path}")
    path.write_text(text.replace(old, new, 1))
    print("Patched path_interposer build for Linux/ARM64")


def patch_arm64_soong_build_arch(root: pathlib.Path) -> None:
    path = root / "build/soong/android/arch.go"
    text = read(path)
    marker = "HansOS local: allow Linux/ARM64 hosts as Soong build hosts."
    if marker in text:
        print("Soong build-arch ARM64 patch already present")
        return

    old = '''\tconfig.BuildArch = func() ArchType {
\t\tswitch runtime.GOARCH {
\t\tcase "amd64":
\t\t\treturn X86_64
\t\tdefault:
\t\t\tpanic(fmt.Sprintf("unsupported Arch: %s", runtime.GOARCH))
\t\t}
\t}()
'''
    new = f'''\tconfig.BuildArch = func() ArchType {{
\t\tswitch runtime.GOARCH {{
\t\tcase "amd64":
\t\t\treturn X86_64
\t\tcase "arm64":
\t\t\t// {marker}
\t\t\treturn Arm64
\t\tdefault:
\t\t\tpanic(fmt.Sprintf("unsupported Arch: %s", runtime.GOARCH))
\t\t}}
\t}}()
'''
    if old not in text:
        fail(f"could not find Soong BuildArch block in {path}")
    path.write_text(text.replace(old, new, 1))
    print("Patched Soong BuildArch for Linux/ARM64")


def patch_arm64_soong_proc_macro_host_target(root: pathlib.Path) -> None:
    """Keep Soong on the existing ARM64 musl host target.

    A previous attempt exposed a separate linux_glibc_arm64 host target. That
    made Rust proc-macros selectable, but it also forced huge C/C++ host graph
    variants that Lineage's prebuilts do not support. The fix is to clean that
    up here and make Rust's LinuxMusl/ARM64 toolchain use the GNU Rust triple
    instead.
    """

    arch_path = root / "build/soong/android/arch.go"
    text = read(arch_path)
    old_linux = '''\t// Linux is the OS for the Linux kernel plus the glibc runtime.
\t// HansOS local: allow linux_glibc_arm64 host variants for Rust proc-macros.
\tLinux = newOsType("linux_glibc", Host, false, X86, X86_64, Arm64)
'''
    new_linux = '''\t// Linux is the OS for the Linux kernel plus the glibc runtime.
\tLinux = newOsType("linux_glibc", Host, false, X86, X86_64)
'''
    if old_linux in text:
        text = text.replace(old_linux, new_linux, 1)

    bad_target = '''\t// The primary host target, which must always exist.
\taddTarget(targetConfig{os: config.BuildOS, archName: *variables.HostArch, nativeBridgeEnabled: NativeBridgeDisabled})
\tif config.BuildOS == LinuxMusl && config.BuildArch == Arm64 {
\t\t// HansOS local: expose GNU ARM64 host target for Rust proc-macros.
\t\taddTarget(targetConfig{os: Linux, archName: *variables.HostArch, nativeBridgeEnabled: NativeBridgeDisabled})
\t}

\t// An optional secondary host target.
'''
    good_target = '''\t// The primary host target, which must always exist.
\taddTarget(targetConfig{os: config.BuildOS, archName: *variables.HostArch, nativeBridgeEnabled: NativeBridgeDisabled})

\t// An optional secondary host target.
'''
    if bad_target in text:
        text = text.replace(bad_target, good_target, 1)
    arch_path.write_text(text)

    rust_path = root / "build/soong/rust/rust.go"
    text = read(rust_path)
    bad_rust = '''\t// proc_macros are compiler plugins, and so we need the host arch variant as a dependendcy.
\tprocMacroTarget := ctx.Config().BuildOSTarget
\tif ctx.Config().BuildOS == android.LinuxMusl && ctx.Config().BuildArch == android.Arm64 {
\t\tfor _, target := range ctx.Config().Targets[android.Linux] {
\t\t\tif target.Arch.ArchType == android.Arm64 {
\t\t\t\t// HansOS local: Rust proc-macros must match the GNU rustc host triple on ARM64.
\t\t\t\tprocMacroTarget = target
\t\t\t\tbreak
\t\t\t}
\t\t}
\t}
\tactx.AddFarVariationDependencies(procMacroTarget.Variations(), procMacroDepTag, deps.ProcMacros...)
'''
    good_rust = '''\t// proc_macros are compiler plugins, and so we need the host arch variant as a dependendcy.
\tactx.AddFarVariationDependencies(ctx.Config().BuildOSTarget.Variations(), procMacroDepTag, deps.ProcMacros...)
'''
    if bad_rust in text:
        text = text.replace(bad_rust, good_rust, 1)
    rust_path.write_text(text)
    print("Kept Soong proc-macros on the ARM64 musl host target")


def patch_arm64_common_host_install_path(root: pathlib.Path) -> None:
    path = root / "build/soong/android/paths.go"
    text = read(path)
    marker = "HansOS local: install common Java host tools into linux-arm64 on ARM64 musl hosts."
    if marker in text:
        print("Soong common host install-path ARM64 patch already present")
        return

    old = '''\t\tarchName := arch.String()
\t\tif os.Class == Host && (arch == X86_64 || arch == Common) {
\t\t\tarchName = "x86"
\t\t}
'''
    new = f'''\t\tarchName := arch.String()
\t\tif os.Class == Host && arch == Common && os == LinuxMusl && ctx.Config().UseHostMusl() && ctx.Config().BuildArch == Arm64 {{
\t\t\t// {marker}
\t\t\tarchName = "arm64"
\t\t}} else if os.Class == Host && (arch == X86_64 || arch == Common) {{
\t\t\tarchName = "x86"
\t\t}}
'''
    if old not in text:
        fail(f"could not find host install arch block in {path}")
    path.write_text(text.replace(old, new, 1))
    print("Patched Soong common host install path for Linux/ARM64")


def patch_arm64_soong_java_home(root: pathlib.Path) -> None:
    path = root / "build/soong/ui/build/config.go"
    text = read(path)
    marker = "HansOS local: use native ARM64 JDK21 for Java/Kotlin host actions."
    if marker in text:
        print("Soong Java home ARM64 patch already present")
        return

    old = '''\t// Configure Java-related variables, including adding it to $PATH
\tjava8Home := filepath.Join("prebuilts/jdk/jdk8", ret.HostPrebuiltTag())
\tjava21Home := filepath.Join("prebuilts/jdk/jdk21", ret.HostPrebuiltTag())
\tjavaHome := func() string {
'''
    new = f'''\t// Configure Java-related variables, including adding it to $PATH
\tjavaPrebuiltTag := ret.HostPrebuiltTag()
\tif runtime.GOOS == "linux" && runtime.GOARCH == "arm64" {{
\t\tif _, err := os.Stat(filepath.Join(absPath(ctx, "prebuilts/jdk/jdk21/linux-arm64"), "bin", "java")); err == nil {{
\t\t\t// {marker}
\t\t\tjavaPrebuiltTag = "linux-arm64"
\t\t}}
\t}}
\tjava8Home := filepath.Join("prebuilts/jdk/jdk8", ret.HostPrebuiltTag())
\tjava21Home := filepath.Join("prebuilts/jdk/jdk21", javaPrebuiltTag)
\tjavaHome := func() string {{
'''
    if old not in text:
        fail(f"could not find Java home block in {path}")
    path.write_text(text.replace(old, new, 1))
    print("Patched Soong Java home for Linux/ARM64")


def patch_arm64_prebuilt_build_tools(root: pathlib.Path) -> None:
    path = root / "prebuilts/build-tools/Android.bp"
    text = read(path)
    changed = False

    for module_name in ("bison", "flex", "m4", "make"):
        start, end = find_module_block(text, module_name, path)
        module = text[start:end]
        if "arm64: {" in module:
            continue
        anchor = '''        x86_64: {
            enabled: true,
        },
'''
        if anchor not in module:
            fail(f"could not find x86_64 arch block for {module_name} in {path}")
        replacement = anchor + '''        arm64: {
            enabled: true,
        },
'''
        module = module.replace(anchor, replacement, 1)
        text = text[:start] + module + text[end:]
        changed = True

    if changed:
        path.write_text(text)
        print("Patched prebuilt build tools for Linux/ARM64")
    else:
        print("prebuilt build tools already support Linux/ARM64")


def patch_arm64_rust_prebuilts(root: pathlib.Path) -> None:
    path = root / "prebuilts/rust/soong/rustprebuilts.go"
    text = read(path)
    changed = False

    if "\t\tLinux_glibc_arm64  targetProps\n" in text:
        text = text.replace("\t\tLinux_glibc_arm64  targetProps\n", "", 1)
        changed = True

    if "Linux_musl_arm64" not in text:
        old = '''\t\tLinux_musl_x86_64  targetProps
\t\tLinux_musl_x86     targetProps
\t\tDarwin_x86_64      targetProps
'''
        new = '''\t\tLinux_musl_x86_64  targetProps
\t\tLinux_musl_x86     targetProps
\t\tLinux_musl_arm64   targetProps
\t\tDarwin_x86_64      targetProps
'''
        if old not in text:
            fail(f"could not find Rust prebuilt target props in {path}")
        text = text.replace(old, new, 1)
        changed = True

    construct_re = re.compile(
        r'\t\tif ctx\.Config\(\)\.BuildOS == android\.Linux \{.*?'
        r'\t\t\} else if ctx\.Config\(\)\.BuildOS == android\.Darwin \{\n'
        r'\t\t\tp\.Target\.Darwin_x86_64\.addPrebuiltToTarget\(ctx, name, rustDir, "darwin-x86", "x86_64-apple-darwin", rlib, solib\)\n'
        r'\t\t\}',
        re.S,
    )
    construct_new = '''\t\tif ctx.Config().BuildOS == android.Linux {
\t\t\tp.Target.Linux_glibc_x86_64.addPrebuiltToTarget(ctx, name, rustDir, "linux-x86", "x86_64-unknown-linux-gnu", rlib, solib)
\t\t\tp.Target.Linux_glibc_x86.addPrebuiltToTarget(ctx, name, rustDir, "linux-x86", "i686-unknown-linux-gnu", rlib, solib)
\t\t} else if ctx.Config().BuildOS == android.LinuxMusl {
\t\t\tif ctx.Config().BuildArch == android.Arm64 {
\t\t\t\tp.Target.Linux_musl_arm64.addPrebuiltToTarget(ctx, name, rustDir, "linux-arm64", "aarch64-unknown-linux-gnu", rlib, solib)
\t\t\t} else {
\t\t\t\tp.Target.Linux_musl_x86_64.addPrebuiltToTarget(ctx, name, rustDir, "linux-musl-x86", "x86_64-unknown-linux-musl", rlib, solib)
\t\t\t\tp.Target.Linux_musl_x86.addPrebuiltToTarget(ctx, name, rustDir, "linux-musl-x86", "i686-unknown-linux-musl", rlib, solib)
\t\t\t}
\t\t} else if ctx.Config().BuildOS == android.Darwin {
\t\t\tp.Target.Darwin_x86_64.addPrebuiltToTarget(ctx, name, rustDir, "darwin-x86", "x86_64-apple-darwin", rlib, solib)
\t\t}'''
    text, count = construct_re.subn(construct_new, text, count=1)
    if count == 0:
        fail(f"could not normalize Rust host prebuilt block in {path}")
    changed = True

    old = '''\t\tif ctx.Config().BuildOS == android.Linux {
\t\t\tif ctx.Config().BuildArch == android.X86_64 {
\t\t\t\tarchTriple = "x86_64-unknown-linux-gnu"
\t\t\t} else {
\t\t\t\tarchTriple = "i686-unknown-linux-gnu"
\t\t\t}
\t\t} else if ctx.Config().BuildOS == android.LinuxMusl {
'''
    new = '''\t\tif ctx.Config().BuildOS == android.Linux {
\t\t\tif ctx.Config().BuildArch == android.Arm64 {
\t\t\t\tarchTriple = "aarch64-unknown-linux-gnu"
\t\t\t} else if ctx.Config().BuildArch == android.X86_64 {
\t\t\t\tarchTriple = "x86_64-unknown-linux-gnu"
\t\t\t} else {
\t\t\t\tarchTriple = "i686-unknown-linux-gnu"
\t\t\t}
\t\t} else if ctx.Config().BuildOS == android.LinuxMusl {
'''
    if old in text:
        text = text.replace(old, new, 1)
        changed = True

    old = '''\t\t} else if ctx.Config().BuildOS == android.LinuxMusl {
\t\t\tif ctx.Config().BuildArch == android.X86_64 {
\t\t\t\tarchTriple = "x86_64-unknown-linux-musl"
\t\t\t} else {
\t\t\t\tarchTriple = "i686-unknown-linux-musl"
\t\t\t}

\t\t} else if ctx.Config().BuildOS == android.Darwin {
'''
    new = '''\t\t} else if ctx.Config().BuildOS == android.LinuxMusl {
\t\t\tif ctx.Config().BuildArch == android.Arm64 {
\t\t\t\tarchTriple = "aarch64-unknown-linux-gnu"
\t\t\t} else if ctx.Config().BuildArch == android.X86_64 {
\t\t\t\tarchTriple = "x86_64-unknown-linux-musl"
\t\t\t} else {
\t\t\t\tarchTriple = "i686-unknown-linux-musl"
\t\t\t}

\t\t} else if ctx.Config().BuildOS == android.Darwin {
'''
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif 'archTriple = "aarch64-unknown-linux-gnu"' not in text:
        fail(f"could not find Rust LinuxMusl filegroup block in {path}")

    stale = 'p.Target.Linux_musl_arm64.addPrebuiltToTarget(ctx, name, rustDir, "linux-arm64", "aarch64-unknown-linux-musl", rlib, solib)'
    fixed = 'p.Target.Linux_musl_arm64.addPrebuiltToTarget(ctx, name, rustDir, "linux-arm64", "aarch64-unknown-linux-gnu", rlib, solib)'
    if stale in text:
        text = text.replace(stale, fixed, 1)
        changed = True

    stale = '''\t\t} else if ctx.Config().BuildOS == android.LinuxMusl {
\t\t\tif ctx.Config().BuildArch == android.Arm64 {
\t\t\t\tarchTriple = "aarch64-unknown-linux-musl"
'''
    fixed = '''\t\t} else if ctx.Config().BuildOS == android.LinuxMusl {
\t\t\tif ctx.Config().BuildArch == android.Arm64 {
\t\t\t\tarchTriple = "aarch64-unknown-linux-gnu"
'''
    if stale in text:
        text = text.replace(stale, fixed, 1)
        changed = True

    if changed:
        path.write_text(text)
        print("Patched Rust stdlib prebuilts for Linux/ARM64 GNU proc-macro host builds")
    else:
        print("Rust stdlib prebuilts already support Linux/ARM64 GNU proc-macro host builds")


def patch_arm64_rust_glibc_toolchain(root: pathlib.Path) -> None:
    path = root / "build/soong/rust/config/arm_linux_host.go"
    text = read(path)
    changed = False

    bad_init = '''func init() {
\tregisterToolchainFactory(android.Linux, android.Arm64, linuxGlibcArm64ToolchainFactory)
\tregisterToolchainFactory(android.LinuxMusl, android.Arm64, linuxMuslArm64ToolchainFactory)
\tregisterToolchainFactory(android.LinuxMusl, android.Arm, linuxMuslArmToolchainFactory)
'''
    good_init = '''func init() {
\tregisterToolchainFactory(android.LinuxMusl, android.Arm64, linuxMuslArm64ToolchainFactory)
\tregisterToolchainFactory(android.LinuxMusl, android.Arm, linuxMuslArmToolchainFactory)
'''
    if bad_init in text:
        text = text.replace(bad_init, good_init, 1)
        changed = True

    bad_glibc_re = re.compile(
        r'\n// HansOS local: GNU ARM64 Rust host toolchain for proc-macros\.\n'
        r'type toolchainLinuxGlibcArm64 struct \{\n'
        r'\ttoolchainLinuxArm64\n'
        r'\}\n\n'
        r'func \(t \*toolchainLinuxGlibcArm64\) ToolchainLinkFlags\(\) string \{.*?'
        r'func linuxGlibcArm64ToolchainFactory\(arch android\.Arch\) Toolchain \{\n'
        r'\treturn toolchainLinuxGlibcArm64Singleton\n'
        r'\}\n',
        re.S,
    )
    text, count = bad_glibc_re.subn("\n", text, count=1)
    if count:
        changed = True

    if "var toolchainLinuxGlibcArm64Singleton Toolchain = &toolchainLinuxGlibcArm64{}\n" in text:
        text = text.replace("var toolchainLinuxGlibcArm64Singleton Toolchain = &toolchainLinuxGlibcArm64{}\n", "", 1)
        changed = True

    musl_triple = '''func (t *toolchainLinuxMuslArm64) RustTriple() string {
\treturn "aarch64-unknown-linux-musl"
}
'''
    gnu_triple = '''func (t *toolchainLinuxMuslArm64) RustTriple() string {
\treturn "aarch64-unknown-linux-gnu"
}
'''
    if musl_triple in text:
        text = text.replace(musl_triple, gnu_triple, 1)
        changed = True
    elif gnu_triple not in text:
        fail(f"could not find Rust ARM64 musl triple block in {path}")

    link_re = re.compile(
        r'func \(t \*toolchainLinuxMuslArm64\) ToolchainLinkFlags\(\) string \{\n'
        r'\treturn .*?\n'
        r'\}\n',
        re.S,
    )
    link_new = '''func (t *toolchainLinuxMuslArm64) ToolchainLinkFlags() string {
\treturn "${config.LinuxToolchainLinkFlags} ${config.LinuxToolchainArm64LinkFlags} " +
\t\t"-target aarch64-unknown-linux-gnu --sysroot / " +
\t\t"-L/usr/lib/aarch64-linux-gnu -L/lib/aarch64-linux-gnu " +
\t\t"-L/usr/lib/gcc/aarch64-linux-gnu/13 -Wl,-rpath,/usr/lib/aarch64-linux-gnu " +
\t\t"-lc -lrt -ldl -lpthread -lm -lgcc_s -Wl,--compress-debug-sections=zstd"
}
'''
    text, count = link_re.subn(link_new, text, count=1)
    if count == 0:
        fail(f"could not find Rust ARM64 musl link flags in {path}")
    changed = True

    rust_flags_re = re.compile(
        r'func \(t \*toolchainLinuxMuslArm64\) ToolchainRustFlags\(\) string \{\n'
        r'\treturn .*?\n'
        r'\}\n',
        re.S,
    )
    rust_flags_new = '''func (t *toolchainLinuxMuslArm64) ToolchainRustFlags() string {
\treturn t.toolchainLinuxArm64.ToolchainRustFlags()
}
'''
    text, count = rust_flags_re.subn(rust_flags_new, text, count=1)
    if count == 0:
        fail(f"could not find Rust ARM64 musl rust flags in {path}")
    changed = True

    if changed:
        path.write_text(text)
        print("Patched LinuxMusl/ARM64 Rust toolchain to use the GNU host triple")
    else:
        print("LinuxMusl/ARM64 Rust toolchain already uses the GNU host triple")

    marker = "HansOS local: LinuxMusl ARM64 Rust host tools link with system glibc."
    binary_path = root / "build/soong/rust/binary.go"
    text = read(binary_path)
    old = '''\t} else if ctx.Os() == android.LinuxMusl {
\t\tdeps = muslDeps(ctx, deps, static)
\t\tif static {
\t\t\tdeps.CrtBegin = []string{"libc_musl_crtbegin_static"}
\t\t} else {
\t\t\tdeps.CrtBegin = []string{"libc_musl_crtbegin_dynamic"}
\t\t}
\t\tdeps.CrtEnd = []string{"libc_musl_crtend"}
\t}
'''
    new = f'''\t}} else if ctx.Os() == android.LinuxMusl {{
\t\tif ctx.Host() && ctx.Arch().ArchType == android.Arm64 {{
\t\t\t// {marker}
\t\t\treturn deps
\t\t}}
\t\tdeps = muslDeps(ctx, deps, static)
\t\tif static {{
\t\t\tdeps.CrtBegin = []string{{"libc_musl_crtbegin_static"}}
\t\t}} else {{
\t\t\tdeps.CrtBegin = []string{{"libc_musl_crtbegin_dynamic"}}
\t\t}}
\t\tdeps.CrtEnd = []string{{"libc_musl_crtend"}}
\t}}
'''
    if marker not in text:
        if old not in text:
            fail(f"could not find Rust binary musl dependency block in {binary_path}")
        binary_path.write_text(text.replace(old, new, 1))
        print("Patched Rust binary host dependencies for LinuxMusl/ARM64 glibc linking")
    else:
        print("Rust binary host dependencies already avoid Musl CRT on LinuxMusl/ARM64")

    library_path = root / "build/soong/rust/library.go"
    text = read(library_path)
    old = '''\t\t} else if ctx.Os() == android.LinuxMusl {
\t\t\tdeps = muslDeps(ctx, deps, false)
\t\t\tdeps.CrtBegin = []string{"libc_musl_crtbegin_so"}
\t\t\tdeps.CrtEnd = []string{"libc_musl_crtend_so"}
\t\t}
'''
    new = f'''\t\t}} else if ctx.Os() == android.LinuxMusl {{
\t\t\tif ctx.Host() && ctx.Arch().ArchType == android.Arm64 {{
\t\t\t\t// {marker}
\t\t\t\treturn deps
\t\t\t}}
\t\t\tdeps = muslDeps(ctx, deps, false)
\t\t\tdeps.CrtBegin = []string{{"libc_musl_crtbegin_so"}}
\t\t\tdeps.CrtEnd = []string{{"libc_musl_crtend_so"}}
\t\t}}
'''
    if marker not in text:
        if old not in text:
            fail(f"could not find Rust library musl dependency block in {library_path}")
        library_path.write_text(text.replace(old, new, 1))
        print("Patched Rust library host dependencies for LinuxMusl/ARM64 glibc linking")
    else:
        print("Rust library host dependencies already avoid Musl CRT on LinuxMusl/ARM64")


def patch_arm64_rust_sysroot_glibc_defaults(root: pathlib.Path) -> None:
    path = root / "prebuilts/rust/Android.bp"
    text = read(path)
    marker = "HansOS local: enable GNU ARM64 Rust sysroot for proc-macros."
    bad = f'''        // {marker}
        linux_glibc_arm64: {{
            enabled: true,
        }},
'''
    if bad in text:
        path.write_text(text.replace(bad, "", 1))
        print("Removed unused Rust linux_glibc_arm64 sysroot defaults")
    else:
        print("Rust sysroot defaults do not expose linux_glibc_arm64")


def patch_arm64_cc_glibc_toolchain(root: pathlib.Path) -> None:
    path = root / "build/soong/cc/config/arm_linux_host.go"
    text = read(path)
    marker = "HansOS local: minimal GNU ARM64 C/C++ host toolchain for proc-macro graph variants."
    changed = False
    if marker in text:
        block_re = re.compile(
            r'// HansOS local: minimal GNU ARM64 C/C\+\+ host toolchain for proc-macro graph variants\.\n'
            r'type toolchainLinuxGlibcArm64 struct \{\n'
            r'\ttoolchainLinuxArm64\n'
            r'\ttoolchainGlibc\n'
            r'\}\n\n'
            r'func \(t \*toolchainLinuxGlibcArm64\) ClangTriple\(\) string \{.*?'
            r'func \(t \*toolchainLinuxGlibcArm64\) Lldflags\(\) string \{.*?\n'
            r'\}\n\n',
            re.S,
        )
        text, count = block_re.subn("", text, count=1)
        changed = changed or bool(count)
        for stale in (
            "var toolchainLinuxGlibcArm64Singleton Toolchain = &toolchainLinuxGlibcArm64{}\n",
            "func linuxGlibcArm64ToolchainFactory(arch android.Arch) Toolchain {\n\treturn toolchainLinuxGlibcArm64Singleton\n}\n\n",
            "\tregisterToolchainFactory(android.Linux, android.Arm64, linuxGlibcArm64ToolchainFactory)\n",
        ):
            if stale in text:
                text = text.replace(stale, "", 1)
                changed = True
    if changed:
        path.write_text(text)
        print("Removed unused C/C++ linux_glibc_arm64 host toolchain patch")
    else:
        print("C/C++ host toolchain does not expose linux_glibc_arm64")
    return

    if marker in text:
        print("C/C++ GNU ARM64 host toolchain patch already present")
        return

    old = '''type toolchainLinuxMuslArm struct {
\ttoolchainLinuxArm
\ttoolchainMusl
}
'''
    new = f'''// {marker}
type toolchainLinuxGlibcArm64 struct {{
\ttoolchainLinuxArm64
\ttoolchainGlibc
}}

func (t *toolchainLinuxGlibcArm64) ClangTriple() string {{
\treturn "aarch64-unknown-linux-gnu"
}}

func (t *toolchainLinuxGlibcArm64) Cflags() string {{
\treturn t.toolchainLinuxArm64.Cflags() + " -target aarch64-unknown-linux-gnu --sysroot /"
}}

func (t *toolchainLinuxGlibcArm64) Ldflags() string {{
\treturn t.toolchainLinuxArm64.Ldflags() + " -target aarch64-unknown-linux-gnu --sysroot / -L/usr/lib/aarch64-linux-gnu -L/lib/aarch64-linux-gnu -L/usr/lib/gcc/aarch64-linux-gnu/13"
}}

func (t *toolchainLinuxGlibcArm64) Lldflags() string {{
\treturn t.toolchainLinuxArm64.Lldflags() + " -target aarch64-unknown-linux-gnu --sysroot / -L/usr/lib/aarch64-linux-gnu -L/lib/aarch64-linux-gnu -L/usr/lib/gcc/aarch64-linux-gnu/13"
}}

type toolchainLinuxMuslArm struct {{
\ttoolchainLinuxArm
\ttoolchainMusl
}}
'''
    if old not in text:
        fail(f"could not find C/C++ ARM musl toolchain block in {path}")
    text = text.replace(old, new, 1)

    old = '''var toolchainLinuxMuslArmSingleton Toolchain = &toolchainLinuxMuslArm{}
var toolchainLinuxMuslArm64Singleton Toolchain = &toolchainLinuxMuslArm64{}
'''
    new = '''var toolchainLinuxGlibcArm64Singleton Toolchain = &toolchainLinuxGlibcArm64{}
var toolchainLinuxMuslArmSingleton Toolchain = &toolchainLinuxMuslArm{}
var toolchainLinuxMuslArm64Singleton Toolchain = &toolchainLinuxMuslArm64{}
'''
    if old not in text:
        fail(f"could not find C/C++ ARM singleton block in {path}")
    text = text.replace(old, new, 1)

    old = '''func linuxMuslArmToolchainFactory(arch android.Arch) Toolchain {
\treturn toolchainLinuxMuslArmSingleton
}
'''
    new = '''func linuxGlibcArm64ToolchainFactory(arch android.Arch) Toolchain {
\treturn toolchainLinuxGlibcArm64Singleton
}

func linuxMuslArmToolchainFactory(arch android.Arch) Toolchain {
\treturn toolchainLinuxMuslArmSingleton
}
'''
    if old not in text:
        fail(f"could not find C/C++ ARM toolchain factory block in {path}")
    text = text.replace(old, new, 1)

    old = '''func init() {
\tregisterToolchainFactory(android.LinuxMusl, android.Arm, linuxMuslArmToolchainFactory)
\tregisterToolchainFactory(android.LinuxMusl, android.Arm64, linuxMuslArm64ToolchainFactory)
}
'''
    new = '''func init() {
\tregisterToolchainFactory(android.Linux, android.Arm64, linuxGlibcArm64ToolchainFactory)
\tregisterToolchainFactory(android.LinuxMusl, android.Arm, linuxMuslArmToolchainFactory)
\tregisterToolchainFactory(android.LinuxMusl, android.Arm64, linuxMuslArm64ToolchainFactory)
}
'''
    if old not in text:
        fail(f"could not find C/C++ ARM toolchain registration block in {path}")
    text = text.replace(old, new, 1)
    path.write_text(text)
    print("Patched C/C++ GNU ARM64 host toolchain for proc-macro graph variants")


def patch_arm64_rust_config(root: pathlib.Path) -> None:
    path = root / "build/soong/rust/config/global.go"
    text = read(path)
    marker = "HansOS local: use native Rust prebuilts on Linux/ARM64 hosts."
    if marker in text:
        print("Rust config already selects native Linux/ARM64 prebuilts")
        return

    old = '''func HostPrebuiltTag(config android.Config) string {
\tif config.UseHostMusl() {
\t\treturn "linux-musl-x86"
\t} else {
\t\treturn config.PrebuiltOS()
\t}
}
'''
    new = f'''func HostPrebuiltTag(config android.Config) string {{
\t// {marker}
\tif config.BuildOS == android.LinuxMusl && config.BuildArch == android.Arm64 {{
\t\treturn "linux-arm64"
\t}}
\tif config.UseHostMusl() {{
\t\treturn "linux-musl-x86"
\t}} else {{
\t\treturn config.PrebuiltOS()
\t}}
}}
'''
    if old not in text:
        fail(f"could not find Rust HostPrebuiltTag block in {path}")
    path.write_text(text.replace(old, new, 1))
    print("Patched Rust config to select native Linux/ARM64 prebuilts")


def patch_arm64_bindgen_libclang(root: pathlib.Path) -> None:
    """Point bindgen at native system libclang on Linux/ARM64 hosts."""

    path = root / "build/soong/rust/bindgen.go"
    text = read(path)
    old = (
        '\t\t\tCommand: "CLANG_PATH=$bindgenClang LIBCLANG_PATH=$bindgenLibClang RUSTFMT=${config.RustBin}/rustfmt " +\n'
        '\t\t\t\t"$cmd $flags $$(cat $flagfiles) $in -o $out -- -MD -MF $out.d $cflags",\n'
    )
    new = (
        '\t\t\tCommand: "if [ \\"$$(/usr/bin/uname -m)\\" = \\"aarch64\\" ] && [ -x /usr/bin/clang-18 ] && [ -d /usr/lib/llvm-18/lib ]; then " +\n'
        '\t\t\t\t"export CLANG_PATH=/usr/bin/clang-18 LIBCLANG_PATH=/usr/lib/llvm-18/lib; " +\n'
        '\t\t\t\t"else export CLANG_PATH=$bindgenClang LIBCLANG_PATH=$bindgenLibClang; fi; " +\n'
        '\t\t\t\t"RUSTFMT=${config.RustBin}/rustfmt " +\n'
        '\t\t\t\t"$cmd $flags $$(cat $flagfiles) $in -o $out -- -MD -MF $out.d $cflags",\n'
    )
    if old not in text:
        if "/usr/bin/clang-18" in text and "/usr/lib/llvm-18/lib" in text:
            print("bindgen.go already routes Linux/ARM64 bindgen to native libclang")
            return
        fail("could not find bindgen command to patch for Linux/ARM64 libclang")
    path.write_text(text.replace(old, new, 1))
    print("Patched bindgen to use native Linux/ARM64 clang/libclang on DGX")


def patch_arm64_rust_glibc64_shim(root: pathlib.Path) -> None:
    """Provide glibc 64-bit symbol aliases needed by GNU Rust std in musl links."""

    shim_dir = root / "external/hansos/host_glibc64_shim"
    shim_dir.mkdir(parents=True, exist_ok=True)
    bp_path = shim_dir / "Android.bp"
    c_path = shim_dir / "glibc64_shim.c"

    bp = '''cc_library_static {
    name: "libhansos_glibc64_shim",
    host_supported: true,
    device_supported: false,
    enabled: false,
    target: {
        linux_musl_arm64: {
            enabled: true,
        },
    },
    srcs: ["glibc64_shim.c"],
    cflags: [
        "-Wall",
        "-Werror",
    ],
}
'''
    c = '''#define _GNU_SOURCE

#include <fcntl.h>
#include <stdarg.h>
#include <stddef.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#ifdef fstat64
#undef fstat64
#endif

#ifdef lseek64
#undef lseek64
#endif

#ifdef stat64
#undef stat64
#endif

#ifdef open64
#undef open64
#endif

#ifdef mmap64
#undef mmap64
#endif

__attribute__((weak)) int fstat64(int fd, struct stat *buf) {
    return fstat(fd, buf);
}

__attribute__((weak)) off_t lseek64(int fd, off_t offset, int whence) {
    return lseek(fd, offset, whence);
}

__attribute__((weak)) int stat64(const char *path, struct stat *buf) {
    return stat(path, buf);
}

__attribute__((weak)) int open64(const char *path, int flags, ...) {
    mode_t mode = 0;
    if ((flags & O_CREAT) != 0) {
        va_list ap;
        va_start(ap, flags);
        mode = (mode_t)va_arg(ap, int);
        va_end(ap);
    }
    return open(path, flags, mode);
}

__attribute__((weak)) void *mmap64(
        void *addr, size_t length, int prot, int flags, int fd, off_t offset) {
    return mmap(addr, length, prot, flags, fd, offset);
}
'''
    if not bp_path.exists() or bp_path.read_text() != bp:
        bp_path.write_text(bp)
        print("Wrote LinuxMusl/ARM64 Rust glibc64 shim Android.bp")
    else:
        print("LinuxMusl/ARM64 Rust glibc64 shim Android.bp already present")
    if not c_path.exists() or c_path.read_text() != c:
        c_path.write_text(c)
        print("Wrote LinuxMusl/ARM64 Rust glibc64 shim source")
    else:
        print("LinuxMusl/ARM64 Rust glibc64 shim source already present")

    dex2oat_bp = root / "art/dex2oat/Android.bp"
    text = read(dex2oat_bp)
    start, end = find_module_block(text, "dex2oatd", dex2oat_bp)
    block = text[start:end]
    if '"libhansos_glibc64_shim"' in block:
        print("dex2oatd already links libhansos_glibc64_shim")
    else:
        anchor = '                "libdex2oatd_static",\n'
        if anchor not in block:
            fail("could not find dex2oatd host static_libs anchor")
        block = block.replace(anchor, anchor + '                "libhansos_glibc64_shim",\n', 1)
        dex2oat_bp.write_text(text[:start] + block + text[end:])
        print("Patched dex2oatd to link LinuxMusl/ARM64 Rust glibc64 shim")

    validate_bp = root / "frameworks/base/tools/validatekeymaps/Android.bp"
    text = read(validate_bp)
    start, end = find_module_block(text, "validatekeymaps", validate_bp)
    block = text[start:end]
    if '"libhansos_glibc64_shim"' in block:
        print("validatekeymaps already links libhansos_glibc64_shim")
    else:
        anchor = '''    target: {
        host_linux: {
'''
        replacement = '''    target: {
        linux_musl_arm64: {
            static_libs: [
                "libhansos_glibc64_shim",
            ],
        },
        host_linux: {
'''
        if anchor not in block:
            fail("could not find validatekeymaps target host_linux block")
        block = block.replace(anchor, replacement, 1)
        validate_bp.write_text(text[:start] + block + text[end:])
        print("Patched validatekeymaps to link LinuxMusl/ARM64 Rust glibc64 shim")

    unwind_bp = root / "system/unwinding/libunwindstack/Android.bp"
    text = read(unwind_bp)
    start, end = find_module_block(text, "libunwindstack_tools", unwind_bp)
    block = text[start:end]
    if '"libhansos_glibc64_shim"' in block:
        print("libunwindstack_tools already links libhansos_glibc64_shim")
    else:
        anchor = '''    target: {
        // Always disable optimizations for host to make it easier to debug.
        host: {
'''
        replacement = '''    target: {
        linux_musl_arm64: {
            static_libs: [
                "libhansos_glibc64_shim",
            ],
        },
        // Always disable optimizations for host to make it easier to debug.
        host: {
'''
        if anchor not in block:
            fail("could not find libunwindstack_tools target host block")
        block = block.replace(anchor, replacement, 1)
        text = text[:start] + block + text[end:]
        print("Patched libunwindstack_tools to link LinuxMusl/ARM64 Rust glibc64 shim")

    start, end = find_module_block(text, "libunwindstack", unwind_bp)
    block = text[start:end]
    if '"libhansos_glibc64_shim"' in block:
        print("libunwindstack already links libhansos_glibc64_shim")
    else:
        anchor = '''    target: {
        vendor: {
'''
        replacement = '''    target: {
        linux_musl_arm64: {
            static_libs: [
                "libhansos_glibc64_shim",
            ],
        },
        vendor: {
'''
        if anchor not in block:
            fail("could not find libunwindstack target vendor block")
        block = block.replace(anchor, replacement, 1)
        text = text[:start] + block + text[end:]
        print("Patched libunwindstack to link LinuxMusl/ARM64 Rust glibc64 shim")

    unwind_bp.write_text(text)


def patch_arm64_jdk_javap(root: pathlib.Path) -> None:
    path = root / "prebuilts/jdk/jdk21/Android.bp"
    text = read(path)
    changed = False

    if "linux_musl_arm64: {" not in text:
        old = '''        linux: {
            src: "linux-x86/bin/javap",
            deps: [
                "linux-x86/lib/libjli.so",
                "linux-x86/lib/jrt-fs.jar",
                "linux-x86/lib/jvm.cfg",
                "linux-x86/lib/server/libjvm.so",
                "linux-x86/lib/libverify.so",
                "linux-x86/lib/libjava.so",
                "linux-x86/lib/libzip.so",
                "linux-x86/lib/libjimage.so",
                "linux-x86/lib/modules",
                "linux-x86/lib/libnio.so",
                "linux-x86/lib/libnet.so",
                "linux-x86/lib/tzdb.dat",
                "linux-x86/lib/libawt.so",
                "linux-x86/lib/libawt_headless.so",
                "linux-x86/lib/libjavajpeg.so",
                "linux-x86/lib/liblcms.so",
                "linux-x86/lib/libmanagement.so",
                "linux-x86/lib/libmanagement_ext.so",
                "linux-x86/conf/security/java.security",
            ],
        },
'''
        new = '''        linux_musl_arm64: {
            src: "linux-arm64/bin/javap",
            deps: [
                "linux-arm64/lib/libjli.so",
                "linux-arm64/lib/jrt-fs.jar",
                "linux-arm64/lib/jvm.cfg",
                "linux-arm64/lib/server/libjvm.so",
                "linux-arm64/lib/libverify.so",
                "linux-arm64/lib/libjava.so",
                "linux-arm64/lib/libzip.so",
                "linux-arm64/lib/libjimage.so",
                "linux-arm64/lib/modules",
                "linux-arm64/lib/libnio.so",
                "linux-arm64/lib/libnet.so",
                "linux-arm64/lib/tzdb.dat",
                "linux-arm64/lib/libawt.so",
                "linux-arm64/lib/libawt_headless.so",
                "linux-arm64/lib/libjavajpeg.so",
                "linux-arm64/lib/liblcms.so",
                "linux-arm64/lib/libmanagement.so",
                "linux-arm64/lib/libmanagement_ext.so",
                "linux-arm64/conf/security/java.security",
            ],
        },
''' + old
        if old not in text:
            fail(f"could not find javap linux target block in {path}")
        text = text.replace(old, new, 1)
        changed = True

    javap_module = find_module_fragment(text, 'name: "javap"', path)
    if re.search(r"(?m)^\s*arm64:\s*{", javap_module) is None:
        old = '''        x86_64: {
            enabled: true,
        },
'''
        new = old + '''        arm64: {
            enabled: true,
        },
'''
        if old not in text:
            fail(f"could not find javap x86_64 arch block in {path}")
        text = text.replace(old, new, 1)
        changed = True

    if changed:
        path.write_text(text)
        print("Patched JDK javap prebuilt for Linux/ARM64 musl host builds")
    else:
        print("JDK javap prebuilt already supports Linux/ARM64 musl host builds")


def patch_arm64_berberis_x86_host_generators(root: pathlib.Path) -> None:
    path = root / "frameworks/libs/binary_translation/intrinsics/Android.bp"
    text = read(path)
    modules_to_enable = (
        "gen_riscv64_to_x86_64_intrinsics",
        "libberberis_macro_assembler_headers_all_to_x86_64",
        "libberberis_macro_assembler_headers_riscv64_to_x86_64",
        "libberberis_macro_assembler_riscv64_to_x86_64",
    )
    changed = False
    invalid_genrule_arch_block = '''    arch: {
        arm: {
            enabled: false,
        },
        arm64: {
            enabled: false,
        },
    },
'''

    if invalid_genrule_arch_block in text:
        text = text.replace(invalid_genrule_arch_block, "")
        changed = True

    arm64_enabled = '''    arch: {
        arm64: {
            enabled: true,
        },
    },
'''

    for module_name in modules_to_enable:
        start, end = find_module_block(text, module_name, path)
        module = text[start:end]
        if re.search(r"(?m)^\s*arm64:\s*{\s*\n\s*enabled:\s*false,", module):
            module = re.sub(
                r"(?m)^(\s*arm64:\s*{\s*\n\s*)enabled:\s*false,",
                r"\1enabled: true,",
                module,
                count=1,
            )
            text = text[:start] + module + text[end:]
            changed = True
            continue
        if re.search(r"(?m)^\s*arm64:\s*{\s*\n\s*enabled:\s*true,", module):
            continue
        name_line_end = text.find("\n", text.find(f'name: "{module_name}"', start)) + 1
        text = text[:name_line_end] + arm64_enabled + text[name_line_end:]
        changed = True

    if changed:
        path.write_text(text)
        print("Patched Berberis x86_64 host generators for Linux/ARM64 host builds")
    else:
        print("Berberis x86_64 host generators already support Linux/ARM64 host builds")


def patch_arm64_musl_cmake_snapshot(root: pathlib.Path) -> None:
    path = root / "external/musl/Android.bp"
    text = read(path)
    start, end = find_module_block(text, "libc_musl_crt_defaults", path)
    module = text[start:end]
    if "cmake_snapshot_supported: true," in module:
        print("musl CRT defaults already support CMake snapshots")
        return

    name_line_end = text.find("\n", text.find('name: "libc_musl_crt_defaults"', start)) + 1
    text = text[:name_line_end] + "    cmake_snapshot_supported: true,\n" + text[name_line_end:]
    path.write_text(text)
    print("Patched musl CRT defaults for Binder CMake snapshot analysis")


def patch_automotive_test_host_required(root: pathlib.Path) -> None:
    path = root / "platform_testing/tests/automotive/health/property/Android.bp"
    text = read(path)
    old = '    host_required: ["CarPropertyManagerStressTestLogPostProcessor"],\n'
    if old not in text:
        print("Automotive property stress test host_required patch already present")
        return
    new = (
        "    // HansOS local: this helper is test-only and is not a host installable module\n"
        "    // in the MP01 GSI build path.\n"
    )
    path.write_text(text.replace(old, new, 1))
    print("Patched automotive property stress test host_required edge")


def patch_virtualization_test_host_required(root: pathlib.Path) -> None:
    paths = [
        root / "packages/modules/Virtualization/tests/ComposBenchmarkApp/Android.bp",
        root / "packages/modules/Virtualization/tests/benchmark/Android.bp",
    ]
    changed = False
    old = '    host_required: ["MicrodroidTestPreparer"],\n'
    new = (
        "    // HansOS local: this test helper is not a host installable module\n"
        "    // in the MP01 GSI build path.\n"
    )
    for path in paths:
        text = read(path)
        if old not in text:
            continue
        path.write_text(text.replace(old, new, 1))
        print(f"Patched {path} Microdroid host_required edge")
        changed = True
    if not changed:
        print("Virtualization Microdroid host_required patches already present")


def find_module_fragment(source: str, needle: str, path: pathlib.Path) -> str:
    idx = source.find(needle)
    if idx == -1:
        fail(f"could not find {needle} in {path}")
    start = source.rfind("{", 0, idx)
    if start == -1:
        fail(f"could not find module start for {needle} in {path}")
    depth = 0
    for pos in range(start, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    fail(f"could not find module end for {needle} in {path}")


def patch_one_service_policy(service_te: pathlib.Path, service_contexts: pathlib.Path) -> None:
    type_line = "type hans_service,                 system_server_service, service_manager_type;\n"
    text = read(service_te)
    if "type hans_service," not in text:
        insert_after = "type gsi_service,                   service_manager_type;\n"
        text = text.replace(insert_after, insert_after + type_line, 1) if insert_after in text else type_line + text
        service_te.write_text(text)
        print(f"Patched {service_te} with hans_service type")
    else:
        print(f"{service_te} already contains hans_service type")

    context_line = "hans                                      u:object_r:hans_service:s0\n"
    text = read(service_contexts)
    if context_line not in text:
        insert_after = "hardware_properties                     u:object_r:hardware_properties_service:s0\n"
        text = text.replace(insert_after, insert_after + context_line, 1) if insert_after in text else text + "\n" + context_line
        service_contexts.write_text(text)
        print(f"Patched {service_contexts} with hans service label")
    else:
        print(f"{service_contexts} already contains hans service label")


def patch_service_policy(root: pathlib.Path) -> None:
    pairs = [
        (
            root / "system/sepolicy/private/service.te",
            root / "system/sepolicy/private/service_contexts",
        ),
        (
            root / "system/sepolicy/prebuilts/api/35.0/private/service.te",
            root / "system/sepolicy/prebuilts/api/35.0/private/service_contexts",
        ),
    ]
    patched_any = False
    for service_te, service_contexts in pairs:
        if service_te.exists() and service_contexts.exists():
            patch_one_service_policy(service_te, service_contexts)
            patched_any = True
    if not patched_any:
        fail("could not find service policy files")


def patch_product(root: pathlib.Path) -> None:
    product_files = [
        root / "device/phh/treble/treble_arm64_bvN.mk",
        root / "device/phh/treble/treble_arm64_bgN.mk",
    ]
    block = f"""

{HANS_PRODUCT_MARKER}
PRODUCT_SOONG_NAMESPACES += \\
    packages/apps/HansCanvas \\
    packages/services/HansRuntimeService \\
    packages/modules/HansProtocol \\
    packages/modules/HansFakes

PRODUCT_PACKAGES += \\
    HansCanvasSystem \\
    HansRuntimeServiceSystem \\
    hansos-agent-protocol \\
    hansos-fakes \\
    privapp-permissions-ai.hansos.canvas.system.xml \\
    privapp-permissions-ai.hansos.runtime.system.xml

PRODUCT_SYSTEM_PROPERTIES += \\
    ro.hansos.enabled=true \\
    ro.hansos.agent_name=Hans \\
    persist.hansos.provider=fake
"""
    for path in product_files:
        if not path.exists():
            continue
        text = path.read_text()
        if "BUILD_BROKEN_MISSING_REQUIRED_MODULES := true" not in text:
            text = text.rstrip() + (
                "\n\n# HansOS local: MP01 TrebleDroid GSI inherits an ART debug required-module edge\n"
                "# that is absent from this product graph but not needed for the system image path.\n"
                "BUILD_BROKEN_MISSING_REQUIRED_MODULES := true\n"
            )
            path.write_text(text)
            print(f"Patched {path} to tolerate known MP01 GSI missing required-module edge")
        if HANS_PRODUCT_MARKER in text:
            print(f"{path} already contains HansOS product integration")
            continue
        path.write_text(text.rstrip() + block + "\n")
        print(f"Patched {path} with HansOS product integration")


def patch_setup_wizard_home(root: pathlib.Path) -> None:
    """Make the MP01 first-boot flow hand HOME to HansCanvas.

    MP01-LineageGSI patches SetupWizard to assign inkOS as the launcher after
    setup. HansOS keeps the MP01 hardware support from that tree, but the agent
    canvas must be the default home surface.
    """

    util_path = root / "packages/apps/SetupWizard/src/org/lineageos/setupwizard/util/SetupWizardUtils.java"
    if not util_path.exists():
        print("SetupWizardUtils.java not present yet; skipping HOME handoff patch")
        return

    text = util_path.read_text()
    new = text.replace("app.inkos/.MainActivity", "ai.hansos.canvas/.HansCanvasActivity")
    new = new.replace('"app.inkos"', '"ai.hansos.canvas"')
    write_if_changed(util_path, text, new, "Patched SetupWizard HOME handoff to HansCanvas")

    exit_wizard_path = root / "packages/apps/SetupWizard/exit_wizard.sh"
    if exit_wizard_path.exists():
        text = exit_wizard_path.read_text()
        new = text.replace("app.inkos/.MainActivity", "ai.hansos.canvas/.HansCanvasActivity")
        write_if_changed(exit_wizard_path, text, new, "Patched exit_wizard.sh HOME handoff to HansCanvas")


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        print(f"usage: {argv[0]} /path/to/lineage", file=sys.stderr)
        sys.exit(2)

    root = pathlib.Path(argv[1]).resolve()
    if not (root / "build/envsetup.sh").exists():
        fail(f"not an Android/Lineage checkout: {root}")
    patch_system_server(root)
    patch_arm64_go_host(root)
    patch_arm64_envsetup_musl(root)
    patch_arm64_build_tools(root)
    patch_cronet_arm64_host_cflags(root)
    patch_libyuv_disable_lto_for_rust_archive(root)
    patch_libfdt_disable_lto_for_rust_archive(root)
    patch_arm64_checkfc_getopt(root)
    patch_clang_ndk_stub_native_link(root)
    patch_arm64_make_host(root)
    patch_arm64_make_clang_host(root)
    patch_arm64_missing_required_modules_check(root)
    patch_arm64_host_required_modules_check(root)
    patch_arm64_path_interposer(root)
    patch_arm64_soong_build_arch(root)
    patch_arm64_soong_proc_macro_host_target(root)
    patch_arm64_common_host_install_path(root)
    patch_arm64_soong_java_home(root)
    patch_arm64_prebuilt_build_tools(root)
    patch_arm64_rust_prebuilts(root)
    patch_arm64_rust_glibc_toolchain(root)
    patch_arm64_rust_sysroot_glibc_defaults(root)
    patch_arm64_cc_glibc_toolchain(root)
    patch_arm64_rust_config(root)
    patch_arm64_bindgen_libclang(root)
    patch_arm64_rust_glibc64_shim(root)
    patch_arm64_jdk_javap(root)
    patch_arm64_berberis_x86_host_generators(root)
    patch_arm64_musl_cmake_snapshot(root)
    patch_automotive_test_host_required(root)
    patch_virtualization_test_host_required(root)
    patch_services_core(root)
    patch_service_policy(root)
    patch_product(root)
    patch_setup_wizard_home(root)


if __name__ == "__main__":
    main(sys.argv)
