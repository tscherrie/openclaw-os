#!/usr/bin/env python3
"""Patch an AOSP checkout for HansOS.

This script is intentionally idempotent. It inserts:
  - HansManagerService startup into SystemServer.java
  - hansos-agent-protocol into services.core Android.bp
  - local build compatibility patches for android-latest-release on macOS
"""

from __future__ import annotations

import pathlib
import platform
import re
import sys


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def patch_system_server(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/base/services/java/com/android/server/SystemServer.java"
    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text()
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
        if idx != -1:
            line_start = text.rfind("\n", 0, idx) + 1
            indent = text[line_start:idx]
            snippet = (
                f'{indent}t.traceBegin("StartHansManagerService");\n'
                f"{indent}mSystemServiceManager.startService(ai.hansos.server.HansManagerService.class);\n"
                f"{indent}t.traceEnd();\n\n"
            )
            text = text[:line_start] + snippet + text[line_start:]
            path.write_text(text)
            print("Patched SystemServer.java with HansManagerService hook")
            return

    fail(
        "could not find a stable SystemServer insertion point; "
        "add the StartHansManagerService snippet manually in startOtherServices()"
    )


def patch_services_core_bp(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/base/services/core/Android.bp"
    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text()

    def find_module_block(source: str, module_name: str) -> tuple[int, int]:
        name_idx = source.find(f'name: "{module_name}"')
        if name_idx == -1:
            fail(f"could not find {module_name} module in frameworks/base/services/core/Android.bp")
        start = source.rfind("{", 0, name_idx)
        if start == -1:
            fail(f"could not find start of {module_name} module")

        depth = 0
        for idx in range(start, len(source)):
            if source[idx] == "{":
                depth += 1
            elif source[idx] == "}":
                depth -= 1
                if depth == 0:
                    return start, idx + 1
        fail(f"could not find end of {module_name} module")

    def remove_static_lib(source: str, module_name: str, lib_name: str) -> tuple[str, bool]:
        start, end = find_module_block(source, module_name)
        block = source[start:end]
        updated = block.replace(f'        "{lib_name}",\n', "")
        if updated == block:
            return source, False
        return source[:start] + updated + source[end:], True

    text, removed_stale_entry = remove_static_lib(
        text,
        "services.core",
        "hansos-agent-protocol",
    )

    module_start, module_end = find_module_block(text, "services.core.unboosted")
    module = text[module_start:module_end]
    if '"hansos-agent-protocol"' in module:
        if removed_stale_entry:
            path.write_text(text)
            print("Removed stale services.core hansos-agent-protocol dependency")
        else:
            print("services.core.unboosted already depends on hansos-agent-protocol")
        return

    static_idx = module.find("static_libs: [")
    if static_idx == -1:
        fail("could not find services.core.unboosted static_libs block")

    insert_at = text.find("\n", module_start + static_idx) + 1
    text = (
        text[:insert_at]
        + '        "hansos-agent-protocol",\n'
        + text[insert_at:]
    )
    path.write_text(text)
    print("Patched services.core.unboosted with hansos-agent-protocol")


def patch_hans_service_sepolicy(aosp_root: pathlib.Path) -> None:
    service_te = aosp_root / "system/sepolicy/private/service.te"
    service_contexts = aosp_root / "system/sepolicy/private/service_contexts"
    if not service_te.exists() or not service_contexts.exists():
        fail("missing system/sepolicy private service policy files")

    type_line = "type hans_service,                 system_server_service, service_manager_type;\n"
    text = service_te.read_text()
    if "type hans_service," in text:
        print("Hans service SELinux type already present")
    else:
        insert_after = "type gsi_service,                   service_manager_type;\n"
        if insert_after in text:
            text = text.replace(insert_after, insert_after + type_line, 1)
        else:
            text = type_line + text
        service_te.write_text(text)
        print("Patched service.te with hans_service type")

    context_line = "hans                                      u:object_r:hans_service:s0\n"
    text = service_contexts.read_text()
    if context_line in text:
        print("Hans service_contexts entry already present")
    else:
        insert_after = "hardware_properties                     u:object_r:hardware_properties_service:s0\n"
        if insert_after in text:
            text = text.replace(insert_after, insert_after + context_line, 1)
        else:
            text += "\n" + context_line
        service_contexts.write_text(text)
        print("Patched service_contexts with hans service label")


def patch_crosvm_manager_view_only_webrtc(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/libs/vm_manager/crosvm_manager.cpp"
    if not path.exists():
        print("Skipping Cuttlefish view-only WebRTC patch; crosvm_manager.cpp not present")
        return

    text = path.read_text()
    marker = "HansOS local: allow view-only WebRTC on hosts where crosvm touch sockets fail."

    if "#include <cstdlib>\n" not in text:
        include_anchor = "#include <cassert>\n"
        if include_anchor not in text:
            fail("could not find crosvm_manager.cpp include insertion point")
        text = text.replace(include_anchor, "#include <cstdlib>\n" + include_anchor, 1)
    if "#include <string>\n" not in text:
        include_anchor = "#include <cstdlib>\n"
        if include_anchor not in text:
            fail("could not find crosvm_manager.cpp string include insertion point")
        text = text.replace(include_anchor, include_anchor + "#include <string>\n", 1)

    if marker in text:
        old_env = (
            "    const bool view_only_webrtc =\n"
            "        std::getenv(\"HANSOS_CVD_VIEW_ONLY_WEBRTC\") != nullptr;\n"
        )
        new_env = (
            "    const char* view_only_webrtc_env =\n"
            "        std::getenv(\"HANSOS_CVD_VIEW_ONLY_WEBRTC\");\n"
            "    const bool view_only_webrtc = view_only_webrtc_env != nullptr &&\n"
            "        std::string(view_only_webrtc_env) != \"0\" &&\n"
            "        std::string(view_only_webrtc_env) != \"false\";\n"
        )
        if old_env in text:
            text = text.replace(old_env, new_env, 1)
        old_display_touch = (
            "        crosvm_cmd.Cmd().AddParameter(\n"
            "            touch_type_parameter,\n"
            "            \"path=\", instance.touch_socket_path(touch_idx++),\n"
            "            \",width=\", display_config.width,\n"
            "            \",height=\", display_config.height);\n"
        )
        new_display_touch = (
            "        crosvm_cmd.Cmd().AddParameter(\n"
            "            touch_type_parameter,\n"
            "            instance.touch_socket_path(touch_idx++), \":\",\n"
            "            display_config.width, \":\", display_config.height);\n"
        )
        if old_display_touch in text:
            text = text.replace(old_display_touch, new_display_touch, 1)
        old_touchpad = (
            "        crosvm_cmd.Cmd().AddParameter(\n"
            "            touch_type_parameter,\n"
            "            \"path=\", instance.touch_socket_path(touch_idx++),\n"
            "            \",width=\", touchpad_config.width,\n"
            "            \",height=\", touchpad_config.height,\n"
            "            \",name=\", kTouchpadDefaultPrefix, i);\n"
        )
        new_touchpad = (
            "        crosvm_cmd.Cmd().AddParameter(\n"
            "            touch_type_parameter,\n"
            "            instance.touch_socket_path(touch_idx++), \":\",\n"
            "            touchpad_config.width, \":\", touchpad_config.height, \":\",\n"
            "            kTouchpadDefaultPrefix, i);\n"
        )
        if old_touchpad in text:
            text = text.replace(old_touchpad, new_touchpad, 1)
        if path.read_text() != text:
            path.write_text(text)
            print("Updated Cuttlefish view-only WebRTC/native input handling")
        else:
            print("Cuttlefish view-only WebRTC patch already present")
        return

    old = (
        "  if (instance.enable_webrtc()) {\n"
        "    bool is_chromeos =\n"
        "        instance.boot_flow() ==\n"
        "            CuttlefishConfig::InstanceSpecific::BootFlow::ChromeOs ||\n"
        "        instance.boot_flow() ==\n"
        "            CuttlefishConfig::InstanceSpecific::BootFlow::ChromeOsDisk;\n"
        "    auto touch_type_parameter =\n"
        "        is_chromeos ? \"--single-touch=\" : \"--multi-touch=\";\n"
        "\n"
        "    auto display_configs = instance.display_configs();\n"
        "    CF_EXPECT(display_configs.size() >= 1);\n"
        "\n"
        "    int touch_idx = 0;\n"
        "    for (auto& display_config : display_configs) {\n"
        "      crosvm_cmd.Cmd().AddParameter(\n"
        "          touch_type_parameter,\n"
        "          \"path=\", instance.touch_socket_path(touch_idx++),\n"
        "          \",width=\", display_config.width,\n"
        "          \",height=\", display_config.height);\n"
        "    }\n"
        "    auto touchpad_configs = instance.touchpad_configs();\n"
        "    for (int i = 0; i < touchpad_configs.size(); ++i) {\n"
        "      auto touchpad_config = touchpad_configs[i];\n"
        "      crosvm_cmd.Cmd().AddParameter(\n"
        "          touch_type_parameter,\n"
        "          \"path=\", instance.touch_socket_path(touch_idx++),\n"
        "          \",width=\", touchpad_config.width,\n"
        "          \",height=\", touchpad_config.height,\n"
        "          \",name=\", kTouchpadDefaultPrefix, i);\n"
        "    }\n"
        "    crosvm_cmd.Cmd().AddParameter(\"--rotary=\",\n"
        "                                  instance.rotary_socket_path());\n"
        "    crosvm_cmd.Cmd().AddParameter(\"--keyboard=\",\n"
        "                                  instance.keyboard_socket_path());\n"
        "    crosvm_cmd.Cmd().AddParameter(\"--switches=\",\n"
        "                                  instance.switches_socket_path());\n"
        "  }\n"
    )
    new = (
        "  if (instance.enable_webrtc()) {\n"
        "    const char* view_only_webrtc_env =\n"
        "        std::getenv(\"HANSOS_CVD_VIEW_ONLY_WEBRTC\");\n"
        "    const bool view_only_webrtc = view_only_webrtc_env != nullptr &&\n"
        "        std::string(view_only_webrtc_env) != \"0\" &&\n"
        "        std::string(view_only_webrtc_env) != \"false\";\n"
        "    if (view_only_webrtc) {\n"
        f"      // {marker}\n"
        "      LOG(INFO) << \"HansOS view-only WebRTC: skipping crosvm input sockets\";\n"
        "    } else {\n"
        "      bool is_chromeos =\n"
        "          instance.boot_flow() ==\n"
        "              CuttlefishConfig::InstanceSpecific::BootFlow::ChromeOs ||\n"
        "          instance.boot_flow() ==\n"
        "              CuttlefishConfig::InstanceSpecific::BootFlow::ChromeOsDisk;\n"
        "      auto touch_type_parameter =\n"
        "          is_chromeos ? \"--single-touch=\" : \"--multi-touch=\";\n"
        "\n"
        "      auto display_configs = instance.display_configs();\n"
        "      CF_EXPECT(display_configs.size() >= 1);\n"
        "\n"
        "      int touch_idx = 0;\n"
        "      for (auto& display_config : display_configs) {\n"
        "        crosvm_cmd.Cmd().AddParameter(\n"
        "            touch_type_parameter,\n"
        "            instance.touch_socket_path(touch_idx++), \":\",\n"
        "            display_config.width, \":\", display_config.height);\n"
        "      }\n"
        "      auto touchpad_configs = instance.touchpad_configs();\n"
        "      for (int i = 0; i < touchpad_configs.size(); ++i) {\n"
        "        auto touchpad_config = touchpad_configs[i];\n"
        "        crosvm_cmd.Cmd().AddParameter(\n"
        "            touch_type_parameter,\n"
        "            instance.touch_socket_path(touch_idx++), \":\",\n"
        "            touchpad_config.width, \":\", touchpad_config.height, \":\",\n"
        "            kTouchpadDefaultPrefix, i);\n"
        "      }\n"
        "      crosvm_cmd.Cmd().AddParameter(\"--rotary=\",\n"
        "                                    instance.rotary_socket_path());\n"
        "      crosvm_cmd.Cmd().AddParameter(\"--keyboard=\",\n"
        "                                    instance.keyboard_socket_path());\n"
        "      crosvm_cmd.Cmd().AddParameter(\"--switches=\",\n"
        "                                    instance.switches_socket_path());\n"
        "    }\n"
        "  }\n"
    )
    if old not in text:
        fail("could not find Cuttlefish crosvm WebRTC input block")

    path.write_text(text.replace(old, new, 1))
    print("Patched Cuttlefish crosvm manager with view-only WebRTC mode")


def patch_cuttlefish_external_webrtc_port(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/commands/assemble_cvd/flags.cc"
    if not path.exists():
        print("Skipping Cuttlefish external WebRTC port patch; flags.cc not present")
        return

    text = path.read_text()
    marker = "HansOS local: preserve explicit external WebRTC signaling server port."
    if marker in text:
        print("Cuttlefish external WebRTC port patch already present")
        return

    old = (
        "    } else {\n"
        "      auto port = 8443 + num - 1;\n"
        "      // Change the signaling server port for all instances\n"
        "      tmp_config_obj.set_sig_server_port(port);\n"
        "      // Either the signaling server or the proxy is started, never both\n"
        "      instance.set_start_webrtc_signaling_server(FLAGS_start_webrtc_sig_server);\n"
    )
    new = (
        "    } else {\n"
        "      // HansOS local: preserve explicit external WebRTC signaling server port.\n"
        "      auto port = FLAGS_start_webrtc_sig_server ? 8443 + num - 1\n"
        "                                           : FLAGS_webrtc_sig_server_port;\n"
        "      // Change the signaling server port for all instances\n"
        "      tmp_config_obj.set_sig_server_port(port);\n"
        "      // Either the signaling server or the proxy is started, never both\n"
        "      instance.set_start_webrtc_signaling_server(FLAGS_start_webrtc_sig_server);\n"
    )
    if old not in text:
        fail("could not find Cuttlefish WebRTC signaling server port block")

    path.write_text(text.replace(old, new, 1))
    print("Patched Cuttlefish external WebRTC signaling server port handling")


def patch_soong_darwin_sdk_versions(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/soong/cc/config/darwin_host.go"
    if not path.exists():
        print("Skipping Soong macOS SDK patch; darwin_host.go not present")
        return

    text = path.read_text()
    if '"26"' in text:
        print("Soong darwin_host.go already supports macOS SDK 26")
        return

    anchor = '\t\t"15",\n'
    if anchor not in text:
        fail("could not find darwinSupportedSdkVersions insertion point")

    text = text.replace(anchor, anchor + '\t\t"26",\n', 1)
    path.write_text(text)
    print("Patched Soong darwin_host.go with macOS SDK 26 support")


def patch_soong_darwin_skip_ccdeps(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/soong/cc/ccdeps.go"
    if not path.exists():
        print("Skipping Soong ccdeps Darwin patch; ccdeps.go not present")
        return

    text = path.read_text()
    marker = "HansOS local: avoid expensive ccdeps graph generation on Darwin host builds."
    if marker in text:
        print("Soong ccdeps Darwin skip already patched")
        return

    import_anchor = '\t"path"\n'
    if import_anchor not in text:
        fail("could not find ccdeps.go import insertion point")
    text = text.replace(import_anchor, import_anchor + '\t"runtime"\n', 1)

    old = (
        "func (c *ccdepsGeneratorSingleton) GenerateBuildActions(ctx android.SingletonContext) {\n"
        "\t// (b/204397180) Generate module_bp_cc_deps.json by default.\n"
    )
    new = (
        "func (c *ccdepsGeneratorSingleton) GenerateBuildActions(ctx android.SingletonContext) {\n"
        "\tif runtime.GOOS == \"darwin\" {\n"
        f"\t\t// {marker}\n"
        "\t\tccfpath := android.PathForOutput(ctx, ccdepsJsonFileName)\n"
        "\t\terr := createJsonFile(ccDeps{}, ccfpath)\n"
        "\t\tif err != nil {\n"
        "\t\t\tctx.Errorf(err.Error())\n"
        "\t\t}\n"
        "\t\tc.outputPath = ccfpath\n"
        "\t\tctx.Build(pctx, android.BuildParams{\n"
        "\t\t\tRule:   android.Touch,\n"
        "\t\t\tOutput: ccfpath,\n"
        "\t\t})\n"
        "\t\treturn\n"
        "\t}\n"
        "\n"
        "\t// (b/204397180) Generate module_bp_cc_deps.json by default.\n"
    )
    if old not in text:
        fail("could not find ccdeps GenerateBuildActions insertion point")

    path.write_text(text.replace(old, new, 1))
    print("Patched Soong ccdeps to skip expensive Darwin host metadata generation")


def patch_soong_build_darwin_memory_limit(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/soong/cmd/soong_build/main.go"
    if not path.exists():
        print("Skipping Soong Darwin memory limit patch; main.go not present")
        return

    text = path.read_text()
    marker = "HansOS local: keep translated Darwin soong_build below swap-heavy memory spikes."
    if marker in text:
        print("Soong Darwin memory limit already patched")
        return

    import_anchor = '\t"runtime"\n'
    if import_anchor not in text:
        fail("could not find soong_build runtime import")
    text = text.replace(import_anchor, import_anchor + '\t"runtime/debug"\n', 1)

    old = (
        "func main() {\n"
        "\tflag.Parse()\n"
    )
    new = (
        "func main() {\n"
        "\tif runtime.GOOS == \"darwin\" {\n"
        f"\t\t// {marker}\n"
        "\t\tdebug.SetGCPercent(35)\n"
        "\t\tdebug.SetMemoryLimit(14 << 30)\n"
        "\t}\n"
        "\n"
        "\tflag.Parse()\n"
    )
    if old not in text:
        fail("could not find soong_build main insertion point")

    path.write_text(text.replace(old, new, 1))
    print("Patched Soong build with Darwin memory limit")


def patch_soong_darwin_host_cc_shared_lib_path(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/soong/android/config.go"
    if not path.exists():
        print("Skipping Soong Darwin host C++ shared library path patch; config.go not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin host C++ shared libraries install as .dylib."
    if marker in text:
        print("Soong Darwin host C++ shared library path already patched")
        return

    old = (
        "func (c *config) HostCcSharedLibPath(ctx PathContext, lib string) Path {\n"
        "\tlibDir := \"lib\"\n"
        "\tif ctx.Config().BuildArch.Multilib == \"lib64\" {\n"
        "\t\tlibDir = \"lib64\"\n"
        "\t}\n"
        "\treturn pathForInstall(ctx, ctx.Config().BuildOS, ctx.Config().BuildArch, libDir, lib+\".so\")\n"
        "}\n"
    )
    new = (
        "func (c *config) HostCcSharedLibPath(ctx PathContext, lib string) Path {\n"
        "\tlibDir := \"lib\"\n"
        "\tif ctx.Config().BuildArch.Multilib == \"lib64\" {\n"
        "\t\tlibDir = \"lib64\"\n"
        "\t}\n"
        "\text := \".so\"\n"
        "\tif runtime.GOOS == \"darwin\" {\n"
        f"\t\t// {marker}\n"
        "\t\text = \".dylib\"\n"
        "\t}\n"
        "\treturn pathForInstall(ctx, ctx.Config().BuildOS, ctx.Config().BuildArch, libDir, lib+ext)\n"
        "}\n"
    )
    if old not in text:
        fail("could not find Soong HostCcSharedLibPath implementation")

    path.write_text(text.replace(old, new, 1))
    print("Patched Soong Darwin host C++ shared library path")


def patch_make_core_main_darwin_image_packaging(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/make/core/main.mk"
    if not path.exists():
        print("Skipping Make core Darwin image packaging patch; main.mk not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin image builds need the core packaging rules."
    if marker in text:
        print("Make core Darwin image packaging rules already patched")
        return

    old = (
        "ALL_DEFAULT_INSTALLED_MODULES := $(modules_to_install)\n"
        "ifeq ($(HOST_OS),linux)\n"
        "  include $(BUILD_SYSTEM)/Makefile\n"
        "endif\n"
        "modules_to_install := $(sort $(ALL_DEFAULT_INSTALLED_MODULES))\n"
    )
    new = (
        "ALL_DEFAULT_INSTALLED_MODULES := $(modules_to_install)\n"
        "ifneq (,$(filter linux darwin,$(HOST_OS)))\n"
        f"  # {marker}\n"
        "  include $(BUILD_SYSTEM)/Makefile\n"
        "endif\n"
        "modules_to_install := $(sort $(ALL_DEFAULT_INSTALLED_MODULES))\n"
    )
    if old not in text:
        fail("could not find Make core HOST_OS guard for image packaging patch")

    path.write_text(text.replace(old, new, 1))
    print("Patched Make core Darwin image packaging rules")


def patch_make_core_darwin_selinux_fc(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/make/core/Makefile"
    if not path.exists():
        print("Skipping Make core Darwin SELinux file_contexts patch; Makefile not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin image builds use Soong-generated file_contexts.bin."
    if marker in text:
        print("Make core Darwin SELinux file_contexts path already patched")
        return

    old = "SELINUX_FC := $(call intermediates-dir-for,ETC,file_contexts.bin)/file_contexts.bin\n"
    new = (
        "ifeq ($(HOST_OS),darwin)\n"
        f"# {marker}\n"
        "SELINUX_FC := $(SOONG_OUT_DIR)/.intermediates/system/sepolicy/file_contexts_bin_gen/android_common/gen/file_contexts.bin\n"
        "else\n"
        "SELINUX_FC := $(call intermediates-dir-for,ETC,file_contexts.bin)/file_contexts.bin\n"
        "endif\n"
    )
    if old not in text:
        fail("could not find Make core SELINUX_FC assignment")

    path.write_text(text.replace(old, new, 1))
    print("Patched Make core Darwin SELinux file_contexts path")


def patch_rootdir_darwin_init_environ_source(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/rootdir/create_root_structure.mk"
    if not path.exists():
        print("Skipping rootdir Darwin init.environ.rc patch; create_root_structure.mk not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin image builds use Soong-generated init.environ.rc."
    if marker in text:
        print("rootdir Darwin init.environ.rc source already patched")
        return

    old = (
        "init.environ.rc-soong := $(call intermediates-dir-for,ETC,init.environ.rc-soong)/init.environ.rc-soong\n"
        "$(eval $(call copy-one-file,$(init.environ.rc-soong),$(LOCAL_BUILT_MODULE)))\n"
        "init.environ.rc-soong :=\n"
    )
    new = (
        "ifeq ($(HOST_OS),darwin)\n"
        f"# {marker}\n"
        "init.environ.rc-soong := $(SOONG_OUT_DIR)/.intermediates/system/core/rootdir/init.environ.rc-soong/android_$(TARGET_ARCH)_$(TARGET_ARCH_VARIANT)_$(TARGET_CPU_VARIANT)/init.environ.rc\n"
        "else\n"
        "init.environ.rc-soong := $(call intermediates-dir-for,ETC,init.environ.rc-soong)/init.environ.rc-soong\n"
        "endif\n"
        "$(eval $(call copy-one-file,$(init.environ.rc-soong),$(LOCAL_BUILT_MODULE)))\n"
        "init.environ.rc-soong :=\n"
    )
    if old not in text:
        fail("could not find rootdir init.environ.rc-soong assignment")

    path.write_text(text.replace(old, new, 1))
    print("Patched rootdir Darwin init.environ.rc source")


def patch_make_tools_darwin_python3_shebang(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/make/tools/extract_kernel.py"
    if not path.exists():
        print("Skipping extract_kernel.py Python shebang patch; script not present")
        return

    text = path.read_text()
    marker = "HansOS local: macOS hosts do not provide /usr/bin/env python."
    if marker in text:
        print("extract_kernel.py Python 3 shebang already patched")
        return

    old = "#!/usr/bin/env python\n"
    new = f"#!/usr/bin/env python3\n# {marker}\n"
    if old not in text:
        fail("could not find extract_kernel.py Python shebang")

    path.write_text(text.replace(old, new, 1))
    print("Patched extract_kernel.py Python 3 shebang")


def patch_darwin_env_python_shebangs(aosp_root: pathlib.Path) -> None:
    marker = "HansOS local: macOS hosts do not provide /usr/bin/env python."
    old = "#!/usr/bin/env python\n"
    new = f"#!/usr/bin/env python3\n# {marker}\n"
    roots = [
        aosp_root / "build/soong/scripts",
        aosp_root / "build/make/tools",
        aosp_root / "packages/modules/Virtualization/build",
    ]

    patched = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text()
            if not text.startswith(old):
                continue
            path.write_text(new + text[len(old):])
            patched.append(str(path.relative_to(aosp_root)))

    if patched:
        print(f"Patched {len(patched)} build script Python shebangs to python3")
    else:
        print("Build script Python shebangs already use python3 where needed")


def patch_cronet_headers_copy_python3(aosp_root: pathlib.Path) -> None:
    paths = [
        aosp_root / "external/cronet/tot/Android.bp",
        aosp_root / "external/cronet/tot/components/cronet/gn2bp/gen_android_bp.py",
    ]
    old = "python $(location components/cronet/gn2bp/headers_copy.py) --gen-dir $(genDir) --headers"
    new = "python3 $(location components/cronet/gn2bp/headers_copy.py) --gen-dir $(genDir) --headers"
    changed = False

    for path in paths:
        if not path.exists():
            print(f"Skipping Cronet Python 3 patch; {path.relative_to(aosp_root)} not present")
            continue

        text = path.read_text()
        if old in text:
            count = text.count(old)
            path.write_text(text.replace(old, new))
            print(f"Patched {path.relative_to(aosp_root)} Cronet headers_copy invocations to python3 ({count})")
            changed = True
        elif new in text:
            print(f"{path.relative_to(aosp_root)} Cronet headers_copy invocations already use python3")
        else:
            fail(f"could not find Cronet headers_copy invocation in {path.relative_to(aosp_root)}")

    if not changed:
        print("Cronet headers_copy Python 3 patch already applied")


def patch_cronet_darwin_linker_flags(aosp_root: pathlib.Path) -> None:
    root = aosp_root / "external/cronet/tot"
    if not root.exists():
        print("Skipping Cronet Darwin linker flag patch; external/cronet/tot not present")
        return

    paths = list(root.rglob("Android.bp"))
    paths.append(root / "components/cronet/gn2bp/gen_android_bp.py")
    flags = [
        "-Wl,--as-needed",
        "-Wl,--gc-sections",
    ]
    changed_paths: list[str] = []

    for path in paths:
        if not path.exists():
            continue
        text = path.read_text()
        patched = text
        for flag in flags:
            patched = re.sub(rf'^[ \t]*"{re.escape(flag)}",\n', "", patched, flags=re.MULTILINE)
        if patched != text:
            path.write_text(patched)
            changed_paths.append(str(path.relative_to(aosp_root)))

    if changed_paths:
        for changed_path in changed_paths:
            print(f"Patched {changed_path} to drop GNU ld-only Cronet linker flags")
    else:
        print("Cronet GNU ld-only linker flags already removed")


def patch_cronet_darwin_host_linkage(aosp_root: pathlib.Path) -> None:
    bp_path = aosp_root / "external/cronet/tot/Android.bp"
    cxa_path = aosp_root / "external/cronet/tot/third_party/libc++abi/src/src/cxa_thread_atexit.cpp"

    if bp_path.exists():
        text = bp_path.read_text()
        marker = "HansOS local: Abseil cctz uses CoreFoundation on Darwin host builds."
        block_range = find_named_module_block(text, "cc_defaults", "tot_cronet_cc_defaults")
        if block_range is None:
            fail("could not find tot_cronet_cc_defaults in external/cronet/tot/Android.bp")
        start, end = block_range
        block = text[start:end]
        if marker in block:
            print("Cronet defaults already link CoreFoundation on Darwin")
        else:
            old = "    target: {\n        android: {\n"
            new = (
                "    target: {\n"
                "        darwin: {\n"
                f"            // {marker}\n"
                '            host_ldlibs: ["-framework CoreFoundation"],\n'
                "        },\n"
                "        android: {\n"
            )
            if old not in block:
                fail("could not find Cronet defaults target block")
            bp_path.write_text(text[:start] + block.replace(old, new, 1) + text[end:])
            print("Patched Cronet defaults to link CoreFoundation on Darwin")
    else:
        print("Skipping Cronet CoreFoundation patch; external/cronet/tot/Android.bp not present")

    if cxa_path.exists():
        text = cxa_path.read_text()
        marker = "HansOS local: ld64.lld needs weak_import for this optional Darwin libc symbol."
        if marker in text:
            print("Cronet libc++abi cxa_thread_atexit Darwin weak import already patched")
        else:
            old = (
                "#ifndef HAVE___CXA_THREAD_ATEXIT_IMPL\n"
                "  // A weak symbol is used to detect this function's presence in the C library\n"
                "  // at runtime, even if libc++ is built against an older libc\n"
                "  _LIBCXXABI_WEAK\n"
                "#endif\n"
                "  int __cxa_thread_atexit_impl(Dtor, void*, void*);\n"
            )
            new = (
                "#ifndef HAVE___CXA_THREAD_ATEXIT_IMPL\n"
                "  // A weak symbol is used to detect this function's presence in the C library\n"
                "  // at runtime, even if libc++ is built against an older libc\n"
                "#if defined(__APPLE__)\n"
                f"  // {marker}\n"
                "  __attribute__((weak_import))\n"
                "#else\n"
                "  _LIBCXXABI_WEAK\n"
                "#endif\n"
                "#endif\n"
                "  int __cxa_thread_atexit_impl(Dtor, void*, void*);\n"
            )
            if old not in text:
                fail("could not find Cronet libc++abi cxa_thread_atexit weak declaration")
            cxa_path.write_text(text.replace(old, new, 1))
            print("Patched Cronet libc++abi cxa_thread_atexit weak import for Darwin")

        text = cxa_path.read_text()
        fallback_marker = "HansOS local: ld64.lld still reports the optional weak import as undefined."
        old_start = (
            "#else\n"
            "    if (__cxa_thread_atexit_impl) {\n"
            "      return __cxa_thread_atexit_impl(dtor, obj, dso_symbol);\n"
            "    } else {\n"
        )
        new_start = (
            "#else\n"
            "#if defined(__APPLE__)\n"
            f"    // {fallback_marker}\n"
            "    (void)dso_symbol;\n"
            "    if (false) {\n"
            "#else\n"
            "    if (__cxa_thread_atexit_impl) {\n"
            "      return __cxa_thread_atexit_impl(dtor, obj, dso_symbol);\n"
            "#endif\n"
            "    } else {\n"
        )
        old_end = (
            "      return 0;\n"
            "    }\n"
            "#endif // HAVE___CXA_THREAD_ATEXIT_IMPL\n"
        )
        if fallback_marker in text:
            stale_start = (
                "#else\n"
                "#if defined(__APPLE__)\n"
                f"    // {fallback_marker}\n"
                "    (void)dso_symbol;\n"
                "    {\n"
                "#else\n"
                "    if (__cxa_thread_atexit_impl) {\n"
                "      return __cxa_thread_atexit_impl(dtor, obj, dso_symbol);\n"
                "    } else {\n"
            )
            stale_end = (
                "      return 0;\n"
                "    }\n"
                "#endif\n"
                "#endif // HAVE___CXA_THREAD_ATEXIT_IMPL\n"
            )
            changed = False
            if stale_start in text:
                text = text.replace(stale_start, new_start, 1)
                changed = True
            if stale_end in text:
                text = text.replace(stale_end, old_end, 1)
                changed = True
            if changed:
                cxa_path.write_text(text)
                print("Repaired Cronet libc++abi Darwin fallback preprocessor shape")
            else:
                print("Cronet libc++abi Darwin fallback path already avoids weak __cxa_thread_atexit_impl link")
        else:
            if old_start not in text:
                fail("could not find Cronet libc++abi cxa_thread_atexit runtime fallback start")
            if old_end not in text:
                fail("could not find Cronet libc++abi cxa_thread_atexit runtime fallback end")
            text = text.replace(old_start, new_start, 1)
            cxa_path.write_text(text)
            print("Patched Cronet libc++abi Darwin fallback to avoid weak __cxa_thread_atexit_impl link")
    else:
        print("Skipping Cronet libc++abi weak import patch; cxa_thread_atexit.cpp not present")


def find_named_module_block(text: str, module_type: str, module_name: str) -> tuple[int, int] | None:
    cursor = 0
    marker = f"{module_type} {{"
    while True:
        start = text.find(marker, cursor)
        if start == -1:
            return None

        depth = 0
        for idx in range(start, len(text)):
            char = text[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    block = text[start:end]
                    if f'name: "{module_name}"' in block:
                        return start, end
                    cursor = end
                    break
        else:
            fail(f"unterminated {module_type} block in prebuilts/rust/Android.bp")


def add_vendor_available_to_module(
    path: pathlib.Path,
    module_type: str,
    module_name: str,
    reason: str,
) -> bool:
    if not path.exists():
        print(f"Skipping {module_name} vendor variant patch; {path} not present")
        return False

    text = path.read_text()
    block_range = find_named_module_block(text, module_type, module_name)
    if block_range is None:
        print(f"Skipping {module_name} vendor variant patch; module not present")
        return False

    start, end = block_range
    block = text[start:end]
    if "vendor_available: true," in block:
        print(f"{module_name} already has vendor variants")
        return False

    name_idx = block.find(f'name: "{module_name}"')
    insert_at = start + block.find("\n", name_idx) + 1
    text = (
        text[:insert_at]
        + f"    // {reason}\n"
        + "    vendor_available: true,\n"
        + text[insert_at:]
    )
    path.write_text(text)
    print(f"Patched {module_name} with vendor variants")
    return True


def enable_named_module(
    path: pathlib.Path,
    module_type: str,
    module_name: str,
    reason: str,
) -> bool:
    if not path.exists():
        print(f"Skipping {module_name} enablement; {path} not present")
        return False

    text = path.read_text()
    block_range = find_named_module_block(text, module_type, module_name)
    if block_range is None:
        print(f"Skipping {module_name} enablement; module not present")
        return False

    start, end = block_range
    block = text[start:end]
    if "enabled: false," not in block:
        print(f"{module_name} is already enabled")
        return False

    updated = block.replace(
        "    enabled: false,\n",
        f"    // {reason}\n"
        "    enabled: true,\n",
        1,
    )
    path.write_text(text[:start] + updated + text[end:])
    print(f"Enabled {module_name}")
    return True


def patch_open_dice_baremetal_vendor_variants(aosp_root: pathlib.Path) -> None:
    reason = (
        "HansOS local: AOSP14 ARM64 Cuttlefish builds request a vendor variant "
        "through Virtualization no_std Rust bindings."
    )
    changed = False
    changed |= add_vendor_available_to_module(
        aosp_root / "external/open-dice/Android.bp",
        "cc_library_static",
        "libopen_dice_cbor_baremetal",
        reason,
    )
    changed |= add_vendor_available_to_module(
        aosp_root / "external/open-dice/Android.bp",
        "cc_library_static",
        "libopen_dice_android_baremetal",
        reason,
    )
    changed |= add_vendor_available_to_module(
        aosp_root / "external/boringssl/Android.bp",
        "cc_library_static",
        "libcrypto_baremetal",
        reason,
    )
    if not changed:
        print("OpenDice/BoringSSL baremetal vendor variants already patched or not needed")


def patch_cronet_aml_android_runtime_jni_headers(aosp_root: pathlib.Path) -> None:
    reason = (
        "HansOS local: Linux/ARM64 AOSP14 Cronet graph depends on these generated "
        "JNI headers."
    )
    path = aosp_root / "external/cronet/Android.bp"
    changed = False
    changed |= enable_named_module(
        path,
        "cc_genrule",
        "cronet_aml_base_android_runtime_jni_headers",
        reason,
    )
    changed |= enable_named_module(
        path,
        "cc_genrule",
        "cronet_aml_base_android_runtime_jni_headers__testing",
        reason,
    )
    if not changed:
        print("Cronet AML runtime JNI headers already enabled or not needed")


def patch_cronet_aml_testing_library_install_collision(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/cronet/Android.bp"
    if not path.exists():
        print("Skipping Cronet AML testing install patch; Android.bp not present")
        return

    text = path.read_text()
    module_name = "cronet_aml_components_cronet_android_cronet__testing"
    block_range = find_named_module_block(text, "cc_library_shared", module_name)
    if block_range is None:
        print("Skipping Cronet AML testing install patch; testing module not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: avoid duplicate system install with production Cronet."
    if marker in block:
        print("Cronet AML testing library install collision already patched")
        return

    anchor = f'    name: "{module_name}",\n'
    if anchor not in block:
        fail("could not find Cronet AML testing module name anchor")

    insertion = (
        anchor +
        f"    // {marker}\n"
        "    installable: false,\n"
    )
    block = block.replace(anchor, insertion, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Disabled install for Cronet AML testing shared library")


def patch_crosvm_linux_glibc_arm64_prebuilt_collision(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/crosvm/Android.bp"
    if not path.exists():
        print("Skipping crosvm Linux/ARM64 source cleanup; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "rust_binary", "crosvm")
    if block_range is None:
        print("Skipping crosvm Linux/ARM64 source cleanup; crosvm module not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: keep source crosvm away from the common_crosvm wrapper on Linux/ARM64 hosts."
    linux_arm64_patch = (
        "        linux_glibc_arm64: {\n"
        f"            // {marker}\n"
        '            relative_install_path: "source-linux-glibc-arm64",\n'
        "        },\n"
    )
    stale_patches = [
        (
            "        // HansOS local: match common_crosvm wrapper layout on Linux/ARM64 hosts.\n"
            "        linux_glibc_arm64: {\n"
            '            relative_install_path: "aarch64-linux-gnu",\n'
            "        },\n"
        ),
        (
            "        // HansOS local: use the Cuttlefish prebuilt crosvm on Linux/ARM64 hosts.\n"
            "        linux_glibc_arm64: {\n"
            "            enabled: false,\n"
            "        },\n"
        ),
    ]
    is_linux_arm64_host = sys.platform.startswith("linux") and platform.machine() in ("aarch64", "arm64")
    if not is_linux_arm64_host:
        stale_patches.append(linux_arm64_patch)

    updated = block
    for stale_patch in stale_patches:
        updated = updated.replace(stale_patch, "")

    if not is_linux_arm64_host:
        if updated == block:
            print("Skipping crosvm Linux/ARM64 source install path patch on this host")
            return
        path.write_text(text[:start] + updated + text[end:])
        print("Removed crosvm Linux/ARM64 source install path patch not needed on this host")
        return

    if marker not in updated:
        anchor = "        linux_bionic_arm64: {\n"
        if anchor not in updated:
            fail("could not find crosvm Linux/ARM64 target insertion point")
        updated = updated.replace(anchor, linux_arm64_patch + anchor, 1)

    if updated == block:
        print("crosvm source module ARM64 host install path already patched")
        return

    path.write_text(text[:start] + updated + text[end:])
    print("Patched crosvm source module to avoid ARM64 host wrapper collision")


def patch_cvd_host_package_arm64_prebuilt_crosvm(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/build/Android.bp"
    if not path.exists():
        print("Skipping cvd-host_package crosvm patch; Android.bp not present")
        return

    text = path.read_text()
    original = text
    marker = "HansOS local: ARM64 host package uses prebuilt crosvm, x86 keeps source crosvm."

    tools_anchor_name = "cvd_host_tools = ["
    tools_anchor = '    "crosvm",\n'
    tools_start = text.find(tools_anchor_name)
    if tools_start == -1:
        print("Skipping cvd-host_package crosvm patch; cvd_host_tools list not present")
        return

    tools_list_start = text.find("[", tools_start)
    tools_list_end = text.find("]", tools_list_start)
    if tools_list_start == -1 or tools_list_end == -1:
        fail("could not find cvd_host_tools list bounds")

    tools_block = text[tools_list_start : tools_list_end + 1]
    if tools_anchor in tools_block:
        tools_block = tools_block.replace(tools_anchor, "", 1)
        text = text[:tools_list_start] + tools_block + text[tools_list_end + 1 :]

    x86_anchor = "        x86_64: {\n            deps: cvd_host_x86_64,\n"
    x86_replacement = (
        "        x86_64: {\n"
        f"            // {marker}\n"
        '            deps: cvd_host_x86_64 + ["crosvm"],\n'
    )
    if x86_replacement in text:
        pass
    elif x86_anchor in text:
        text = text.replace(x86_anchor, x86_replacement, 1)
    else:
        fail("could not find cvd-host_package x86_64 dependency anchor")

    if text == original:
        print("cvd-host_package crosvm dependency already patched")
        return

    path.write_text(text)
    print("Moved source crosvm dependency to x86_64 Cuttlefish host package only")


def patch_cuttlefish_crosvm_linux_arm64_support_check(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/libs/vm_manager/crosvm_manager.cpp"
    if not path.exists():
        print("Skipping crosvm Linux/ARM64 support check patch; crosvm_manager.cpp not present")
        return

    text = path.read_text()
    marker = "HansOS local: Linux/ARM64 source check only needs accessible KVM for crosvm."
    if marker in text:
        print("crosvm Linux/ARM64 support check already patched")
        return

    include_anchor = "#include <sys/types.h>\n"
    if include_anchor not in text:
        fail("could not find crosvm_manager.cpp include insertion point")
    text = text.replace(include_anchor, include_anchor + "#include <unistd.h>\n", 1)

    old = (
        "bool CrosvmManager::IsSupported() {\n"
        "#ifdef __ANDROID__\n"
        "  return true;\n"
        "#else\n"
        "  return HostSupportsQemuCli();\n"
        "#endif\n"
        "}\n"
    )
    new = (
        "bool CrosvmManager::IsSupported() {\n"
        "#ifdef __ANDROID__\n"
        "  return true;\n"
        "#else\n"
        "#if defined(__linux__) && defined(__aarch64__)\n"
        f"  // {marker}\n"
        "  return access(\"/dev/kvm\", R_OK | W_OK) == 0;\n"
        "#else\n"
        "  return HostSupportsQemuCli();\n"
        "#endif\n"
        "#endif\n"
        "}\n"
    )
    if old not in text:
        fail("could not find crosvm IsSupported implementation")

    path.write_text(text.replace(old, new, 1))
    print("Patched crosvm Linux/ARM64 support check to use /dev/kvm access")


def patch_appcompat_current_host_out(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "art/tools/veridex/appcompat.sh"
    if not path.exists():
        print("Skipping appcompat host-out patch; appcompat.sh not present")
        return

    text = path.read_text()
    marker = "HansOS local: use the installed script host dir before linux-x86 fallback."
    if marker in text:
        print("appcompat host-out fallback already patched")
        return

    old = (
        'if [[ -z "${ANDROID_HOST_OUT}" ]]; then\n'
        '  ANDROID_HOST_OUT=${OUT}/host/linux-x86\n'
        "fi\n"
    )
    new = (
        'if [[ -z "${ANDROID_HOST_OUT}" ]]; then\n'
        f"  # {marker}\n"
        '  if [[ -x "${SCRIPT_DIR}/veridex" ]]; then\n'
        '    ANDROID_HOST_OUT="$(cd "${SCRIPT_DIR}/.." && pwd)"\n'
        "  else\n"
        '    ANDROID_HOST_OUT=${OUT}/host/linux-x86\n'
        "  fi\n"
        "fi\n"
    )
    if old not in text:
        fail("could not find appcompat ANDROID_HOST_OUT fallback")

    path.write_text(text.replace(old, new, 1))
    print("Patched appcompat.sh to use current host output directory")


def patch_fastboot_host_cross_collision(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/fastboot/Android.bp"
    if not path.exists():
        print("Skipping fastboot host_cross patch; system/core/fastboot/Android.bp not present")
        return

    text = path.read_text()
    fastboot_block_range = find_named_module_block(text, "cc_binary_host", "fastboot")
    if fastboot_block_range is not None:
        start, end = fastboot_block_range
        block = text[start:end]
        bad_patch = (
            "    // HansOS local: Linux/ARM64 host builds otherwise install duplicate "
            "glibc and musl fastboot test data.\n"
            "    host_cross_supported: false,\n"
        )
        if bad_patch in block:
            text = text[:start] + block.replace(bad_patch, "", 1) + text[end:]
            path.write_text(text)
            print("Removed unsupported fastboot host_cross_supported property")

    text = path.read_text()
    block_range = find_named_module_block(text, "python_test_host", "fastboot_integration_test")
    if block_range is None:
        print("Skipping fastboot integration test collision patch; module not present")
        return

    start, end = block_range
    block = text[start:end]
    bad_enabled_patch = (
        "    // HansOS local: Linux/ARM64 host builds install duplicate glibc and musl "
        "fastboot test data.\n"
        "    enabled: false,\n"
    )
    if bad_enabled_patch in block:
        block = block.replace(bad_enabled_patch, "", 1)
        text = text[:start] + block + text[end:]
        path.write_text(text)
        print("Removed unsupported fastboot_integration_test enabled property")

    text = path.read_text()
    block_range = find_named_module_block(text, "python_test_host", "fastboot_integration_test")
    if block_range is None:
        print("Skipping fastboot integration test data patch; module not present")
        return

    start, end = block_range
    block = text[start:end]
    if 'data: [":fastboot"],' not in block:
        print("fastboot_integration_test no longer installs fastboot test data")
        return

    reason = (
        "HansOS local: Linux/ARM64 host builds install duplicate glibc and musl "
        "fastboot test data."
    )
    updated = block.replace(
        '    data: [":fastboot"],\n',
        f"    // {reason}\n",
        1,
    )
    text = text[:start] + updated + text[end:]
    path.write_text(text)
    print("Removed fastboot_integration_test fastboot data to avoid Linux/ARM64 testcase collision")


def patch_linux_arm64_disable_host_cross(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/make/core/envsetup.mk"
    if not path.exists():
        print("Skipping Linux/ARM64 host_cross patch; envsetup.mk not present")
        return

    text = path.read_text()
    marker = "HansOS local: Linux/ARM64 host builds do not need a host_cross variant."
    if marker in text:
        print("Linux/ARM64 host_cross disable already patched")
        return

    new_guard = (
        "  # " + marker + "\n"
        "  ifneq (,$(findstring aarch64,$(UNAME))$(findstring arm64,$(UNAME)))\n"
        "    HOST_CROSS_OS :=\n"
        "    HOST_CROSS_ARCH :=\n"
        "    HOST_CROSS_2ND_ARCH :=\n"
        "  else\n"
    )

    stale_guard = (
        "  # On ARM64 hosts, disable cross-host builds entirely\n"
        "  ifeq ($(HOST_ARCH),arm64)\n"
        "    HOST_CROSS_OS :=\n"
        "    HOST_CROSS_ARCH :=\n"
        "    HOST_CROSS_2ND_ARCH :=\n"
        "  else\n"
    )
    if stale_guard in text:
        path.write_text(text.replace(stale_guard, new_guard, 1))
        print("Repaired Linux/ARM64 host_cross disable to use UNAME before HOST_ARCH exists")
        return

    anchor = (
        "ifeq ($(HOST_OS),linux)\n"
        "  # Windows has been the default host_cross OS\n"
    )
    if anchor not in text:
        fail("could not find envsetup.mk HOST_OS linux host_cross block")

    text = text.replace(
        anchor,
        "ifeq ($(HOST_OS),linux)\n"
        + new_guard
        + "  # Windows has been the default host_cross OS\n",
        1,
    )
    darwin_anchor = "\nelse ifeq ($(HOST_OS),darwin)\n"
    if darwin_anchor not in text:
        fail("could not find envsetup.mk darwin host_cross block")

    text = text.replace(darwin_anchor, "\n  endif\nelse ifeq ($(HOST_OS),darwin)\n", 1)
    path.write_text(text)
    print("Patched Linux/ARM64 host builds to disable host_cross variants")


def patch_linux_arm64_soong_config_host_cross(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/make/core/soong_config.mk"
    if not path.exists():
        print("Skipping Linux/ARM64 Soong host_cross patch; soong_config.mk not present")
        return

    text = path.read_text()
    marker = "HansOS local: Linux/ARM64 host builds pass no CrossHost to Soong."
    if marker in text:
        print("Linux/ARM64 Soong CrossHost disable already patched")
        return

    old = (
        "$(call add_json_str,  CrossHost,                         $(HOST_CROSS_OS))\n"
        "$(call add_json_str,  CrossHostArch,                     $(HOST_CROSS_ARCH))\n"
        "$(call add_json_str,  CrossHostSecondaryArch,            $(HOST_CROSS_2ND_ARCH))\n"
    )
    new = (
        "ifeq ($(HOST_ARCH),arm64)\n"
        f"# {marker}\n"
        "$(call add_json_str,  CrossHost,                         )\n"
        "$(call add_json_str,  CrossHostArch,                     )\n"
        "$(call add_json_str,  CrossHostSecondaryArch,            )\n"
        "else\n"
        "$(call add_json_str,  CrossHost,                         $(HOST_CROSS_OS))\n"
        "$(call add_json_str,  CrossHostArch,                     $(HOST_CROSS_ARCH))\n"
        "$(call add_json_str,  CrossHostSecondaryArch,            $(HOST_CROSS_2ND_ARCH))\n"
        "endif\n"
    )
    if old not in text:
        fail("could not find soong_config.mk CrossHost JSON block")

    path.write_text(text.replace(old, new, 1))
    print("Patched Soong config to omit CrossHost on Linux/ARM64 hosts")


def patch_base_system_ld_mc_host_package(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/make/target/product/base_system.mk"
    if not path.exists():
        print("Skipping ld.mc host package patch; base_system.mk not present")
        return

    text = path.read_text()
    marker = "HansOS local: ARM64 Linux hosts do not provide a usable ld.mc host package."
    if marker in text:
        print("base_system ld.mc host package already patched")
        return

    old = (
        "    incident_report \\\n"
        "    ld.mc \\\n"
        "    lpdump \\\n"
    )
    new = (
        "    incident_report \\\n"
        "    lpdump \\\n"
    )
    if old not in text:
        print("Skipping ld.mc host package patch; host package line not present")
        return

    comment_anchor = "# Host tools to install\n"
    if comment_anchor not in text:
        fail("could not find base_system host tools comment")

    text = text.replace(comment_anchor, comment_anchor + f"# {marker}\n", 1)
    text = text.replace(old, new, 1)
    path.write_text(text)
    print("Removed ld.mc from PRODUCT_HOST_PACKAGES")


def patch_rust_prebuilts_bp(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "prebuilts/rust/Android.bp"
    if not path.exists():
        print("Skipping prebuilts/rust patch; Android.bp not present")
        return

    print("Leaving prebuilts/rust/Android.bp unchanged; rust prebuilt module types are provided by prebuilts/rust/soong")


def patch_rust_linux_arm64_host_prebuilts(aosp_root: pathlib.Path) -> None:
    bp_path = aosp_root / "prebuilts/rust/Android.bp"
    soong_path = aosp_root / "prebuilts/rust/soong/rustprebuilts.go"
    if not bp_path.exists() or not soong_path.exists():
        print("Skipping Rust Linux/ARM64 prebuilt patch; prebuilts/rust files not present")
        return

    bp_text = bp_path.read_text()
    marker = "HansOS local: Linux/ARM64 host builds Rust sysroot from the local rustup-backed source tree."
    stale_disabled_marker = "        // HansOS local: Linux/ARM64 host uses prebuilt Rust sysroot; keep source glibc_arm64 disabled.\n"
    desired_source_variant = (
        f"        // {marker}\n"
        "        glibc_arm64: {\n"
        "            enabled: true,\n"
        "        },\n"
    )
    bare_source_variant = (
        "        glibc_arm64: {\n"
        "            enabled: true,\n"
        "        },\n"
    )
    changed_bp = False
    if stale_disabled_marker in bp_text:
        bp_text = bp_text.replace(stale_disabled_marker, "", 1)
        changed_bp = True

    if desired_source_variant not in bp_text:
        anchor = (
            "        glibc: {\n"
            "            enabled: false,\n"
            "        },\n"
        )
        if bare_source_variant in bp_text:
            bp_text = bp_text.replace(bare_source_variant, desired_source_variant, 1)
        elif anchor in bp_text:
            bp_text = bp_text.replace(anchor, anchor + desired_source_variant, 1)
        else:
            fail("could not find prebuilts/rust rust_sysroot_defaults glibc block")
        changed_bp = True

    libstd_marker = "HansOS local: Linux/ARM64 host uses prebuilt libstd while lower sysroot crates build from source."
    libstd_block_range = find_named_module_block(bp_text, "rust_toolchain_library", "libstd")
    if libstd_block_range is None:
        fail("could not find prebuilts/rust source libstd module")
    libstd_start, libstd_end = libstd_block_range
    libstd_block = bp_text[libstd_start:libstd_end]
    if libstd_marker not in libstd_block:
        target_anchor = "    target: {\n"
        if target_anchor not in libstd_block:
            fail("could not find prebuilts/rust source libstd target block")
        libstd_insert = (
            f"        // {libstd_marker}\n"
            "        glibc_arm64: {\n"
            "            enabled: false,\n"
            "        },\n"
        )
        libstd_block = libstd_block.replace(target_anchor, target_anchor + libstd_insert, 1)
        bp_text = bp_text[:libstd_start] + libstd_block + bp_text[libstd_end:]
        changed_bp = True

    if changed_bp:
        bp_path.write_text(bp_text)
        print("Patched Rust sysroot defaults for Linux/ARM64 source host use")
    else:
        print("Rust sysroot defaults already enable Linux/ARM64 source host use")

    soong_text = soong_path.read_text()
    changed_soong = False
    removals = [
        "\t\tLinux_musl_arm64   targetProps\n",
        "\t\t\t// Also populate musl arm64 prebuilts since HOST_CROSS_OS=linux_musl creates musl variants\n",
        '\t\t\tp.Target.Linux_musl_arm64.addPrebuiltToTarget(ctx, name, rustDir, "linux-arm64", "aarch64-unknown-linux-gnu", rlib, solib)\n',
    ]
    for stale in removals:
        while stale in soong_text:
            soong_text = soong_text.replace(stale, "", 1)
            changed_soong = True

    if "Linux_glibc_arm64" not in soong_text:
        old = (
            "\t\tLinux_glibc_x86_64 targetProps\n"
            "\t\tLinux_glibc_x86    targetProps\n"
            "\t\tLinux_musl_x86_64  targetProps\n"
        )
        new = (
            "\t\tLinux_glibc_x86_64 targetProps\n"
            "\t\tLinux_glibc_x86    targetProps\n"
            "\t\tLinux_glibc_arm64  targetProps\n"
            "\t\tLinux_musl_x86_64  targetProps\n"
        )
        if old not in soong_text:
            fail("could not find rustprebuilts.go Linux glibc target props")
        soong_text = soong_text.replace(old, new, 1)
        changed_soong = True

    linux_glibc_arm64_call = (
        '\t\t\tp.Target.Linux_glibc_arm64.addPrebuiltToTarget(ctx, name, rustDir, '
        '"linux-arm64", "aarch64-unknown-linux-gnu", rlib, solib)\n'
    )
    if linux_glibc_arm64_call not in soong_text:
        old = (
            '\t\t\tp.Target.Linux_glibc_x86_64.addPrebuiltToTarget(ctx, name, rustDir, "linux-x86", "x86_64-unknown-linux-gnu", rlib, solib)\n'
            '\t\t\tp.Target.Linux_glibc_x86.addPrebuiltToTarget(ctx, name, rustDir, "linux-x86", "i686-unknown-linux-gnu", rlib, solib)\n'
        )
        new = old + linux_glibc_arm64_call
        if old not in soong_text:
            fail("could not find rustprebuilts.go Linux glibc prebuilt calls")
        soong_text = soong_text.replace(old, new, 1)
        changed_soong = True

    if changed_soong:
        soong_path.write_text(soong_text)
        print("Patched Rust Linux/ARM64 host libstd prebuilt selection")
    else:
        print("Rust Linux/ARM64 host libstd prebuilt selection already patched")

    if platform.system() == "Linux" and platform.machine() in {"aarch64", "arm64"}:
        version = "1.75.0"
        link_path = aosp_root / "prebuilts/rust/linux-arm64" / version
        rustup_toolchain = pathlib.Path.home() / ".rustup" / "toolchains" / f"{version}-aarch64-unknown-linux-gnu"
        if not link_path.exists() and rustup_toolchain.exists():
            link_path.parent.mkdir(parents=True, exist_ok=True)
            link_path.symlink_to(rustup_toolchain, target_is_directory=True)
            print(f"Linked Rust Linux/ARM64 prebuilt toolchain to {rustup_toolchain}")
        elif link_path.exists():
            print("Rust Linux/ARM64 prebuilt toolchain path already exists")
        else:
            print("Rust Linux/ARM64 rustup toolchain not found; install rustup toolchain 1.75.0 before hosttools build")


def patch_streaming_proto_corefoundation(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/base/tools/streaming_proto/Android.bp"
    if not path.exists():
        print("Skipping streaming_proto CoreFoundation patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "cc_defaults", "protoc-gen-stream-defaults")
    if block_range is None:
        print("Skipping streaming_proto CoreFoundation patch; defaults module not present")
        return

    start, end = block_range
    block = text[start:end]
    if "CoreFoundation" in block:
        print("protoc-gen-stream-defaults already links CoreFoundation on Darwin")
        return

    anchor = '    static_libs: ["libprotoc"],\n'
    if anchor not in block:
        fail("could not find protoc-gen-stream-defaults static_libs anchor")

    target_patch = (
        "\n"
        "    // HansOS local: libprotoc pulls Abseil cctz, which calls CoreFoundation on Darwin.\n"
        "    target: {\n"
        "        darwin: {\n"
        "            host_ldlibs: [\n"
        '                "-framework CoreFoundation",\n'
        "            ],\n"
        "        },\n"
        "    },\n"
    )
    replacement = block.replace(anchor, target_patch + anchor, 1)
    path.write_text(text[:start] + replacement + text[end:])
    print("Patched streaming_proto host tools to link CoreFoundation on Darwin")


def patch_perfetto_proto_plugins_corefoundation(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/perfetto/Android.bp"
    if not path.exists():
        print("Skipping Perfetto CoreFoundation patch; Android.bp not present")
        return

    text = path.read_text()
    changed = False
    modules = (
        "ipc_plugin",
        "perfetto_src_protozero_protoc_plugin_cppgen_plugin",
        "protozero_plugin",
    )
    for module_name in modules:
        block_range = find_named_module_block(text, "cc_binary_host", module_name)
        if block_range is None:
            print(f"Skipping Perfetto CoreFoundation patch; {module_name} not present")
            continue

        start, end = block_range
        block = text[start:end]
        if "CoreFoundation" in block:
            print(f"Perfetto {module_name} already links CoreFoundation on Darwin")
            continue

        anchor = "    cflags: [\n"
        if anchor not in block:
            fail(f"could not find Perfetto {module_name} cflags anchor")

        target_patch = (
            "    // HansOS local: libprotoc pulls Abseil cctz, which calls CoreFoundation on Darwin.\n"
            "    target: {\n"
            "        darwin: {\n"
            "            host_ldlibs: [\n"
            '                "-framework CoreFoundation",\n'
            "            ],\n"
            "        },\n"
            "    },\n"
        )
        replacement = block.replace(anchor, target_patch + anchor, 1)
        text = text[:start] + replacement + text[end:]
        changed = True

    if changed:
        path.write_text(text)
        print("Patched Perfetto proto plugins to link CoreFoundation on Darwin")
    else:
        print("Perfetto proto plugins CoreFoundation patch already applied")


def patch_grpc_java_protoc_plugin_corefoundation(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/grpc-grpc-java/compiler/Android.bp"
    if not path.exists():
        print("Skipping gRPC Java protoc plugin CoreFoundation patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "cc_binary_host", "protoc-gen-grpc-java-plugin")
    if block_range is None:
        print("Skipping gRPC Java protoc plugin CoreFoundation patch; module not present")
        return

    start, end = block_range
    block = text[start:end]
    if "CoreFoundation" in block:
        print("gRPC Java protoc plugin already links CoreFoundation on Darwin")
        return

    insertion = (
        "\n"
        "    // HansOS local: libprotoc pulls Abseil cctz, which calls CoreFoundation on Darwin.\n"
        "    target: {\n"
        "        darwin: {\n"
        "            host_ldlibs: [\n"
        '                "-framework CoreFoundation",\n'
        "            ],\n"
        "        },\n"
        "    },\n"
    )
    replacement = block[:-1] + insertion + "}"
    path.write_text(text[:start] + replacement + text[end:])
    print("Patched gRPC Java protoc plugin to link CoreFoundation on Darwin")


def patch_libchrome_include_generator_python3(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/libchrome/libchrome_tools/include_generator.py"
    if not path.exists():
        print("Skipping libchrome include_generator Python 3 patch; script not present")
        return

    text = path.read_text()
    if text.startswith("#!/usr/bin/env python3\n"):
        print("libchrome include_generator already uses python3")
        return

    old_shebangs = (
        "#!/usr/bin/env python\n",
        "#!/usr/bin/python\n",
    )
    for shebang in old_shebangs:
        if text.startswith(shebang):
            path.write_text("#!/usr/bin/env python3\n" + text[len(shebang):])
            print("Patched libchrome include_generator shebang to python3")
            return

    fail("could not find libchrome include_generator python shebang")


def patch_libchrome_jni_registration_generator_embedded_python(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/libchrome/base/android/jni_generator/jni_registration_generator.py"
    if not path.exists():
        print("Skipping libchrome JNI registration generator patch; script not present")
        return

    text = path.read_text()
    marker = "HansOS local: embedded Soong Python on Darwin can have sys.executable unset."
    if marker in text:
        print("libchrome JNI registration generator already avoids embedded Python multiprocessing issue")
        return

    old = (
        "  # Without multiprocessing, script takes ~13 seconds for chrome_public_apk\n"
        "  # on a z620. With multiprocessing, takes ~2 seconds.\n"
        "  pool = multiprocessing.Pool()\n"
        "  paths = (p for p in java_file_paths if p not in args.no_register_java)\n"
        "  results = [d for d in pool.imap_unordered(_DictForPath, paths) if d]\n"
        "  pool.close()\n"
    )
    new = (
        "  # Without multiprocessing, script takes ~13 seconds for chrome_public_apk\n"
        "  # on a z620. With multiprocessing, takes ~2 seconds.\n"
        "  paths = [p for p in java_file_paths if p not in args.no_register_java]\n"
        f"  # {marker}\n"
        "  if sys.executable is None:\n"
        "    results = [d for d in map(_DictForPath, paths) if d]\n"
        "  else:\n"
        "    pool = multiprocessing.Pool()\n"
        "    results = [d for d in pool.imap_unordered(_DictForPath, paths) if d]\n"
        "    pool.close()\n"
    )
    if old not in text:
        fail("could not find libchrome JNI registration generator multiprocessing block")

    path.write_text(text.replace(old, new, 1))
    print("Patched libchrome JNI registration generator for embedded Python on Darwin")


def patch_crosvm_proc_macro_variants(aosp_root: pathlib.Path) -> None:
    specs = (
        ("external/crosvm/argh_helpers/Android.bp", "libargh_helpers"),
        ("external/crosvm/base/base_event_token_derive/Android.bp", "libbase_event_token_derive"),
        ("external/crosvm/bit_field/bit_field_derive/Android.bp", "libbit_field_derive"),
        ("external/crosvm/hypervisor/hypervisor_test_macro/Android.bp", "libhypervisor_test_macro"),
        ("external/crosvm/serde_keyvalue/serde_keyvalue_derive/Android.bp", "libserde_keyvalue_derive"),
    )

    changed = False
    for rel_path, module_name in specs:
        path = aosp_root / rel_path
        if not path.exists():
            print(f"Skipping crosvm proc macro patch; {rel_path} not present")
            continue

        text = path.read_text()
        block_range = find_named_module_block(text, "rust_proc_macro", module_name)
        if block_range is None:
            print(f"Skipping crosvm proc macro patch; {module_name} not present")
            continue

        start, end = block_range
        block = text[start:end]
        replacement = block
        snippets: list[str] = []

        if "darwin:" not in block:
            snippets.append(
                "    // HansOS local: crosvm_defaults disables Darwin, but Android Rust proc macros build on the host.\n"
                "    target: {\n"
                "        darwin: {\n"
                "            enabled: true,\n"
                "        },\n"
                "    },\n"
            )

        if 'apex_available: ["com.android.virt"]' not in block:
            snippets.append(
                "    // HansOS local: crosvm Rust APEX libs need matching proc macro variants.\n"
                '    apex_available: ["com.android.virt"],\n'
            )

        if snippets:
            close_idx = replacement.rfind("\n}")
            if close_idx == -1:
                fail(f"could not find crosvm {module_name} module terminator")

            replacement = replacement[:close_idx + 1] + "".join(snippets) + replacement[close_idx + 1:]
            text = text[:start] + replacement + text[end:]
            path.write_text(text)
            print(f"Patched crosvm proc macro variants for {module_name}")
            changed = True

    if not changed:
        print("crosvm proc macro Darwin/APEX variants already patched")


def patch_minijail_securebits_all_bits(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/minijail/system.c"
    if not path.exists():
        print("Skipping minijail securebits patch; system.c not present")
        return

    text = path.read_text()
    marker = "HansOS local: libcap securebits header may lag newer kernel secure bits."
    if marker in text:
        print("minijail securebits SECURE_ALL_BITS patch already applied")
        return

    old = (
        "#if defined(__ANDROID__)\n"
        "_Static_assert(SECURE_ALL_BITS == 0x555, \"SECURE_ALL_BITS == 0x555.\");\n"
        "#endif\n"
    )
    new = (
        "#if defined(__ANDROID__)\n"
        "#if SECURE_ALL_BITS != 0x555\n"
        f"// {marker}\n"
        "#undef SECURE_ALL_BITS\n"
        "#define SECURE_ALL_BITS \\\n"
        "\t(SECBIT_NOROOT | SECBIT_NO_SETUID_FIXUP | SECBIT_KEEP_CAPS | \\\n"
        "\t SECBIT_NO_CAP_AMBIENT_RAISE | SECBIT_EXEC_RESTRICT_FILE | \\\n"
        "\t SECBIT_EXEC_DENY_INTERACTIVE)\n"
        "#undef SECURE_ALL_LOCKS\n"
        "#define SECURE_ALL_LOCKS (SECURE_ALL_BITS << 1)\n"
        "#endif\n"
        "_Static_assert(SECURE_ALL_BITS == 0x555, \"SECURE_ALL_BITS == 0x555.\");\n"
        "#endif\n"
    )
    if old not in text:
        fail("could not find minijail SECURE_ALL_BITS static assertion")

    path.write_text(text.replace(old, new, 1))
    print("Patched minijail SECURE_ALL_BITS for newer securebits with older libcap headers")


def patch_aidl_rust_darwin_host_variants(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/tools/aidl/build/aidl_interface_backends.go"
    if not path.exists():
        print("Skipping AIDL Rust Darwin host patch; aidl_interface_backends.go not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin does not ship libbinder_rs for AIDL Rust host variants."
    if marker in text:
        print("AIDL Rust Darwin host variant patch already applied")
        return

    import_anchor = '\t"path/filepath"\n\t"strings"\n'
    if import_anchor not in text:
        fail("could not find aidl_interface_backends.go import anchor")
    text = text.replace(import_anchor, '\t"path/filepath"\n\t"runtime"\n\t"strings"\n', 1)

    setup_anchor = (
        "\tversionedRustName := fixRustName(i.versionedName(version))\n"
        "\trustCrateName := fixRustName(i.ModuleBase.Name())\n\n"
        "\tmctx.CreateModule(wrapLibraryFactory(aidlRustLibraryFactory), &rustProperties{\n"
    )
    replacement = (
        "\tversionedRustName := fixRustName(i.versionedName(version))\n"
        "\trustCrateName := fixRustName(i.ModuleBase.Name())\n\n"
        "\thostSupported := i.properties.Host_supported\n"
        "\tif runtime.GOOS == \"darwin\" {\n"
        f"\t\t// {marker}\n"
        "\t\thostSupported = nil\n"
        "\t}\n\n"
        "\tmctx.CreateModule(wrapLibraryFactory(aidlRustLibraryFactory), &rustProperties{\n"
    )
    if setup_anchor not in text:
        fail("could not find AIDL Rust library setup anchor")
    text = text.replace(setup_anchor, replacement, 1)

    host_anchor = "\t\tHost_supported:     i.properties.Host_supported,\n"
    if host_anchor not in text:
        fail("could not find AIDL Rust Host_supported assignment")
    text = text.replace(host_anchor, "\t\tHost_supported:     hostSupported,\n", 1)

    path.write_text(text)
    print("Patched AIDL Rust backend to skip Darwin host variants")


def patch_binder_ndk_rust_missing_bindings(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/binder/rust/sys/bindings.rs"
    if not path.exists():
        print("Skipping Binder NDK Rust bindings patch; static bindings.rs not present")
        return

    text = path.read_text()
    old_status_block = (
        "// Compatibility aliases for android::c_interface namespace types\n"
        "pub type android_c_interface_StatusCode = ::std::os::raw::c_int;\n"
        "pub const android_c_interface_StatusCode_OK: android_c_interface_StatusCode = 0;\n"
        "pub const android_c_interface_StatusCode_UNKNOWN_ERROR: android_c_interface_StatusCode = -2147483648;\n"
        "pub const android_c_interface_StatusCode_NO_MEMORY: android_c_interface_StatusCode = -12;\n"
        "pub const android_c_interface_StatusCode_INVALID_OPERATION: android_c_interface_StatusCode = -38;\n"
        "pub const android_c_interface_StatusCode_BAD_VALUE: android_c_interface_StatusCode = -22;\n"
        "pub const android_c_interface_StatusCode_BAD_TYPE: android_c_interface_StatusCode = -2147483647;\n"
        "pub const android_c_interface_StatusCode_NAME_NOT_FOUND: android_c_interface_StatusCode = -2;\n"
        "pub const android_c_interface_StatusCode_PERMISSION_DENIED: android_c_interface_StatusCode = -1;\n"
        "pub const android_c_interface_StatusCode_NO_INIT: android_c_interface_StatusCode = -19;\n"
        "pub const android_c_interface_StatusCode_ALREADY_EXISTS: android_c_interface_StatusCode = -17;\n"
        "pub const android_c_interface_StatusCode_DEAD_OBJECT: android_c_interface_StatusCode = -32;\n"
        "pub const android_c_interface_StatusCode_FAILED_TRANSACTION: android_c_interface_StatusCode = -2147483646;\n"
        "pub const android_c_interface_StatusCode_BAD_INDEX: android_c_interface_StatusCode = -75;\n"
        "pub const android_c_interface_StatusCode_NOT_ENOUGH_DATA: android_c_interface_StatusCode = -61;\n"
        "pub const android_c_interface_StatusCode_WOULD_BLOCK: android_c_interface_StatusCode = -11;\n"
        "pub const android_c_interface_StatusCode_TIMED_OUT: android_c_interface_StatusCode = -110;\n"
        "pub const android_c_interface_StatusCode_UNKNOWN_TRANSACTION: android_c_interface_StatusCode = -74;\n"
        "pub const android_c_interface_StatusCode_FDS_NOT_ALLOWED: android_c_interface_StatusCode = -2147483641;\n"
        "pub const android_c_interface_StatusCode_UNEXPECTED_NULL: android_c_interface_StatusCode = -2147483640;\n"
    )
    new_status_block = (
        "// Compatibility aliases for android::c_interface namespace types\n"
        "// HansOS local: AIDL Rust code expects StatusCode associated constants.\n"
        "#[allow(non_camel_case_types)]\n"
        "#[repr(i32)]\n"
        "#[derive(Debug, Copy, Clone, Hash, PartialEq, Eq)]\n"
        "pub enum android_c_interface_StatusCode {\n"
        "    OK = 0,\n"
        "    UNKNOWN_ERROR = -2147483647 - 1,\n"
        "    NO_MEMORY = -12,\n"
        "    INVALID_OPERATION = -38,\n"
        "    BAD_VALUE = -22,\n"
        "    BAD_TYPE = -2147483647,\n"
        "    NAME_NOT_FOUND = -2,\n"
        "    PERMISSION_DENIED = -1,\n"
        "    NO_INIT = -19,\n"
        "    ALREADY_EXISTS = -17,\n"
        "    DEAD_OBJECT = -32,\n"
        "    FAILED_TRANSACTION = -2147483646,\n"
        "    BAD_INDEX = -75,\n"
        "    NOT_ENOUGH_DATA = -61,\n"
        "    WOULD_BLOCK = -11,\n"
        "    TIMED_OUT = -110,\n"
        "    UNKNOWN_TRANSACTION = -74,\n"
        "    FDS_NOT_ALLOWED = -2147483641,\n"
        "    UNEXPECTED_NULL = -2147483640,\n"
        "}\n"
        "pub const android_c_interface_StatusCode_OK: android_c_interface_StatusCode = android_c_interface_StatusCode::OK;\n"
        "pub const android_c_interface_StatusCode_UNKNOWN_ERROR: android_c_interface_StatusCode = android_c_interface_StatusCode::UNKNOWN_ERROR;\n"
        "pub const android_c_interface_StatusCode_NO_MEMORY: android_c_interface_StatusCode = android_c_interface_StatusCode::NO_MEMORY;\n"
        "pub const android_c_interface_StatusCode_INVALID_OPERATION: android_c_interface_StatusCode = android_c_interface_StatusCode::INVALID_OPERATION;\n"
        "pub const android_c_interface_StatusCode_BAD_VALUE: android_c_interface_StatusCode = android_c_interface_StatusCode::BAD_VALUE;\n"
        "pub const android_c_interface_StatusCode_BAD_TYPE: android_c_interface_StatusCode = android_c_interface_StatusCode::BAD_TYPE;\n"
        "pub const android_c_interface_StatusCode_NAME_NOT_FOUND: android_c_interface_StatusCode = android_c_interface_StatusCode::NAME_NOT_FOUND;\n"
        "pub const android_c_interface_StatusCode_PERMISSION_DENIED: android_c_interface_StatusCode = android_c_interface_StatusCode::PERMISSION_DENIED;\n"
        "pub const android_c_interface_StatusCode_NO_INIT: android_c_interface_StatusCode = android_c_interface_StatusCode::NO_INIT;\n"
        "pub const android_c_interface_StatusCode_ALREADY_EXISTS: android_c_interface_StatusCode = android_c_interface_StatusCode::ALREADY_EXISTS;\n"
        "pub const android_c_interface_StatusCode_DEAD_OBJECT: android_c_interface_StatusCode = android_c_interface_StatusCode::DEAD_OBJECT;\n"
        "pub const android_c_interface_StatusCode_FAILED_TRANSACTION: android_c_interface_StatusCode = android_c_interface_StatusCode::FAILED_TRANSACTION;\n"
        "pub const android_c_interface_StatusCode_BAD_INDEX: android_c_interface_StatusCode = android_c_interface_StatusCode::BAD_INDEX;\n"
        "pub const android_c_interface_StatusCode_NOT_ENOUGH_DATA: android_c_interface_StatusCode = android_c_interface_StatusCode::NOT_ENOUGH_DATA;\n"
        "pub const android_c_interface_StatusCode_WOULD_BLOCK: android_c_interface_StatusCode = android_c_interface_StatusCode::WOULD_BLOCK;\n"
        "pub const android_c_interface_StatusCode_TIMED_OUT: android_c_interface_StatusCode = android_c_interface_StatusCode::TIMED_OUT;\n"
        "pub const android_c_interface_StatusCode_UNKNOWN_TRANSACTION: android_c_interface_StatusCode = android_c_interface_StatusCode::UNKNOWN_TRANSACTION;\n"
        "pub const android_c_interface_StatusCode_FDS_NOT_ALLOWED: android_c_interface_StatusCode = android_c_interface_StatusCode::FDS_NOT_ALLOWED;\n"
        "pub const android_c_interface_StatusCode_UNEXPECTED_NULL: android_c_interface_StatusCode = android_c_interface_StatusCode::UNEXPECTED_NULL;\n"
    )
    if old_status_block in text:
        text = text.replace(old_status_block, new_status_block, 1)
    elif "pub enum android_c_interface_StatusCode" in text:
        pass
    else:
        fail("could not find Binder NDK Rust StatusCode compatibility block")

    old_exception_block = (
        "pub type android_c_interface_ExceptionCode = ::std::os::raw::c_int;\n"
        "pub const android_c_interface_ExceptionCode_NONE: android_c_interface_ExceptionCode = 0;\n"
        "pub const android_c_interface_ExceptionCode_SECURITY: android_c_interface_ExceptionCode = -1;\n"
        "pub const android_c_interface_ExceptionCode_BAD_PARCELABLE: android_c_interface_ExceptionCode = -2;\n"
        "pub const android_c_interface_ExceptionCode_ILLEGAL_ARGUMENT: android_c_interface_ExceptionCode = -3;\n"
        "pub const android_c_interface_ExceptionCode_NULL_POINTER: android_c_interface_ExceptionCode = -4;\n"
        "pub const android_c_interface_ExceptionCode_ILLEGAL_STATE: android_c_interface_ExceptionCode = -5;\n"
        "pub const android_c_interface_ExceptionCode_NETWORK_MAIN_THREAD: android_c_interface_ExceptionCode = -6;\n"
        "pub const android_c_interface_ExceptionCode_UNSUPPORTED_OPERATION: android_c_interface_ExceptionCode = -7;\n"
        "pub const android_c_interface_ExceptionCode_SERVICE_SPECIFIC: android_c_interface_ExceptionCode = -8;\n"
        "pub const android_c_interface_ExceptionCode_PARCELABLE: android_c_interface_ExceptionCode = -9;\n"
        "pub const android_c_interface_ExceptionCode_TRANSACTION_FAILED: android_c_interface_ExceptionCode = -129;\n"
    )
    new_exception_block = (
        "// HansOS local: AOSP Rust callers expect ExceptionCode associated constants.\n"
        "#[allow(non_camel_case_types)]\n"
        "#[repr(i32)]\n"
        "#[derive(Debug, Copy, Clone, Hash, PartialEq, Eq)]\n"
        "pub enum android_c_interface_ExceptionCode {\n"
        "    NONE = 0,\n"
        "    SECURITY = -1,\n"
        "    BAD_PARCELABLE = -2,\n"
        "    ILLEGAL_ARGUMENT = -3,\n"
        "    NULL_POINTER = -4,\n"
        "    ILLEGAL_STATE = -5,\n"
        "    NETWORK_MAIN_THREAD = -6,\n"
        "    UNSUPPORTED_OPERATION = -7,\n"
        "    SERVICE_SPECIFIC = -8,\n"
        "    PARCELABLE = -9,\n"
        "    TRANSACTION_FAILED = -129,\n"
        "}\n"
        "pub const android_c_interface_ExceptionCode_NONE: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::NONE;\n"
        "pub const android_c_interface_ExceptionCode_SECURITY: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::SECURITY;\n"
        "pub const android_c_interface_ExceptionCode_BAD_PARCELABLE: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::BAD_PARCELABLE;\n"
        "pub const android_c_interface_ExceptionCode_ILLEGAL_ARGUMENT: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::ILLEGAL_ARGUMENT;\n"
        "pub const android_c_interface_ExceptionCode_NULL_POINTER: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::NULL_POINTER;\n"
        "pub const android_c_interface_ExceptionCode_ILLEGAL_STATE: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::ILLEGAL_STATE;\n"
        "pub const android_c_interface_ExceptionCode_NETWORK_MAIN_THREAD: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::NETWORK_MAIN_THREAD;\n"
        "pub const android_c_interface_ExceptionCode_UNSUPPORTED_OPERATION: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::UNSUPPORTED_OPERATION;\n"
        "pub const android_c_interface_ExceptionCode_SERVICE_SPECIFIC: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::SERVICE_SPECIFIC;\n"
        "pub const android_c_interface_ExceptionCode_PARCELABLE: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::PARCELABLE;\n"
        "pub const android_c_interface_ExceptionCode_TRANSACTION_FAILED: android_c_interface_ExceptionCode = android_c_interface_ExceptionCode::TRANSACTION_FAILED;\n"
    )
    if old_exception_block in text:
        text = text.replace(old_exception_block, new_exception_block, 1)
    elif "pub enum android_c_interface_ExceptionCode" in text:
        pass
    else:
        fail("could not find Binder NDK Rust ExceptionCode compatibility block")

    declarations = [
        ("AIBinder_markVintfStability", "    pub fn AIBinder_markVintfStability(binder: *mut AIBinder);\n"),
        ("AIBinder_markVendorStability", "    pub fn AIBinder_markVendorStability(binder: *mut AIBinder);\n"),
        ("AIBinder_markSystemStability", "    pub fn AIBinder_markSystemStability(binder: *mut AIBinder);\n"),
        ("AIBinder_setRequestingSid", "    pub fn AIBinder_setRequestingSid(binder: *mut AIBinder, requestingSid: bool);\n"),
        ("AIBinder_getCallingSid", "    pub fn AIBinder_getCallingSid() -> *const ::std::os::raw::c_char;\n"),
        ("AParcel_markSensitive", "    pub fn AParcel_markSensitive(parcel: *const AParcel);\n"),
        (
            "AServiceManager_addService",
            "    pub fn AServiceManager_addService(\n"
            "        binder: *mut AIBinder,\n"
            "        instance: *const ::std::os::raw::c_char,\n"
            "    ) -> binder_exception_t;\n",
        ),
        (
            "AServiceManager_getService",
            "    pub fn AServiceManager_getService(\n"
            "        instance: *const ::std::os::raw::c_char,\n"
            "    ) -> *mut AIBinder;\n",
        ),
        (
            "AServiceManager_waitForService",
            "    pub fn AServiceManager_waitForService(\n"
            "        instance: *const ::std::os::raw::c_char,\n"
            "    ) -> *mut AIBinder;\n",
        ),
        (
            "AServiceManager_registerLazyService",
            "    pub fn AServiceManager_registerLazyService(\n"
            "        binder: *mut AIBinder,\n"
            "        instance: *const ::std::os::raw::c_char,\n"
            "    ) -> binder_status_t;\n",
        ),
        (
            "AServiceManager_isDeclared",
            "    pub fn AServiceManager_isDeclared(\n"
            "        instance: *const ::std::os::raw::c_char,\n"
            "    ) -> bool;\n",
        ),
        (
            "AServiceManager_forEachDeclaredInstance",
            "    pub fn AServiceManager_forEachDeclaredInstance(\n"
            "        interface: *const ::std::os::raw::c_char,\n"
            "        context: *mut ::std::os::raw::c_void,\n"
            "        callback: ::std::option::Option<\n"
            "            unsafe extern \"C\" fn(\n"
            "                instance: *const ::std::os::raw::c_char,\n"
            "                context: *mut ::std::os::raw::c_void,\n"
            "            ),\n"
            "        >,\n"
            "    );\n",
        ),
        ("AServiceManager_forceLazyServicesPersist", "    pub fn AServiceManager_forceLazyServicesPersist(persist: bool);\n"),
        (
            "AIBinder_Class_setHandleShellCommand",
            "    pub fn AIBinder_Class_setHandleShellCommand(\n"
            "        clazz: *mut AIBinder_Class,\n"
            "        handleShellCommand: ::std::option::Option<\n"
            "            unsafe extern \"C\" fn(\n"
            "                binder: *mut AIBinder,\n"
            "                in_: ::std::os::raw::c_int,\n"
            "                out: ::std::os::raw::c_int,\n"
            "                err: ::std::os::raw::c_int,\n"
            "                argv: *mut *const ::std::os::raw::c_char,\n"
            "                argc: u32,\n"
            "            ) -> i32,\n"
            "        >,\n"
            "    );\n",
        ),
        ("ABinderProcess_startThreadPool", "    pub fn ABinderProcess_startThreadPool();\n"),
        (
            "ABinderProcess_setThreadPoolMaxThreadCount",
            "    pub fn ABinderProcess_setThreadPoolMaxThreadCount(numThreads: u32);\n",
        ),
        ("ABinderProcess_joinThreadPool", "    pub fn ABinderProcess_joinThreadPool();\n"),
    ]
    missing = [declaration for name, declaration in declarations if f"pub fn {name}" not in text]
    if not missing and text == path.read_text():
        print("Binder NDK Rust static bindings already contain required declarations")
    elif missing:
        marker = "HansOS local: complete missing Binder NDK Rust declarations for ARM64 Linux hosts."
        addition = "\n// " + marker + "\nextern \"C\" {\n" + "".join(missing) + "}\n"
        text = text.rstrip() + "\n" + addition

    if text != path.read_text():
        path.write_text(text)
        print(f"Patched Binder NDK Rust static bindings with {len(missing)} declarations")

    sys_lib_path = aosp_root / "frameworks/native/libs/binder/rust/sys/lib.rs"
    if not sys_lib_path.exists():
        print("Skipping Binder NDK sys StatusCode trait patch; lib.rs not present")
    else:
        sys_lib_text = sys_lib_path.read_text()
        trait_marker = "HansOS local: make StatusCode usable with anyhow::Context."
        if trait_marker in sys_lib_text:
            print("Binder NDK sys StatusCode traits already patched")
        else:
            if "use std::error::Error;\n" not in sys_lib_text:
                anchor = "//! Generated Rust bindings to libbinder_ndk\n\n"
                if anchor not in sys_lib_text:
                    fail("could not find Binder NDK sys import insertion point")
                sys_lib_text = sys_lib_text.replace(anchor, anchor + "use std::error::Error;\n", 1)
            if "use std::fmt;\n" not in sys_lib_text:
                import_anchor = "use std::error::Error;\n"
                sys_lib_text = sys_lib_text.replace(import_anchor, import_anchor + "use std::fmt;\n", 1)

            anchor = "pub use bindings::*;\n"
            if anchor not in sys_lib_text:
                fail("could not find Binder NDK sys bindings export")
            addition = (
                anchor
                + "\n"
                + f"// {trait_marker}\n"
                + "impl fmt::Display for android_c_interface_StatusCode {\n"
                + "    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n"
                + "        write!(f, \"{:?}\", self)\n"
                + "    }\n"
                + "}\n\n"
                + "impl Error for android_c_interface_StatusCode {}\n"
            )
            sys_lib_path.write_text(sys_lib_text.replace(anchor, addition, 1))
            print("Patched Binder NDK sys StatusCode Display/Error traits")

    lib_path = aosp_root / "frameworks/native/libs/binder/rust/src/lib.rs"
    if not lib_path.exists():
        print("Skipping Binder Rust sys visibility patch; lib.rs not present")
        return

    lib_text = lib_path.read_text()
    old = "use binder_ndk_sys as sys;\n"
    new = (
        "// HansOS local: exported AIDL helper macros reference binder::sys from generated crates.\n"
        "pub use binder_ndk_sys as sys;\n"
    )
    if new in lib_text:
        print("Binder Rust sys module already public for AIDL macros")
    elif old in lib_text:
        lib_path.write_text(lib_text.replace(old, new, 1))
        print("Patched Binder Rust sys module visibility for AIDL macros")
    else:
        fail("could not find Binder Rust sys import")

    error_path = aosp_root / "frameworks/native/libs/binder/rust/src/error.rs"
    if not error_path.exists():
        print("Skipping Binder Rust StatusCode conversion patch; error.rs not present")
        return

    error_text = error_path.read_text()
    conversion_marker = "HansOS local: AIDL generated crates pass StatusCode enum values directly."
    anchor = (
        "impl From<status_t> for Status {\n"
        "    fn from(status: status_t) -> Status {\n"
        "        // Safety: `AStatus_fromStatus` expects any `status_t` integer, so\n"
        "        // this is a safe FFI call. Unknown values will be coerced into\n"
        "        // UNKNOWN_ERROR.\n"
        "        let ptr = unsafe { sys::AStatus_fromStatus(status) };\n"
        "        Self(ptr::NonNull::new(ptr).expect(\"Unexpected null AStatus pointer\"))\n"
        "    }\n"
        "}\n"
    )
    if anchor not in error_text:
        fail("could not find Binder Rust Status From<status_t> block")

    if conversion_marker in error_text:
        print("Binder Rust StatusCode to Status conversion already patched")
    else:
        addition = (
            anchor
            + "\n"
            + f"// {conversion_marker}\n"
            + "impl From<StatusCode> for Status {\n"
            + "    fn from(status: StatusCode) -> Status {\n"
            + "        Status::from(status as status_t)\n"
            + "    }\n"
            + "}\n"
        )
        error_text = error_text.replace(anchor, addition, 1)
        print("Patched Binder Rust StatusCode to Status conversion")

    exception_conversion_marker = (
        "HansOS local: ExceptionCode enum values need explicit Status conversion."
    )
    if exception_conversion_marker in error_text:
        print("Binder Rust ExceptionCode to Status conversion already patched")
    else:
        status_impl = (
            f"// {conversion_marker}\n"
            "impl From<StatusCode> for Status {\n"
            "    fn from(status: StatusCode) -> Status {\n"
            "        Status::from(status as status_t)\n"
            "    }\n"
            "}\n"
        )
        exception_impl = (
            status_impl
            + "\n"
            + f"// {exception_conversion_marker}\n"
            + "impl From<ExceptionCode> for Status {\n"
            + "    fn from(exception: ExceptionCode) -> Status {\n"
            + "        let ptr = unsafe { sys::AStatus_fromExceptionCode(exception as i32) };\n"
            + "        Self(ptr::NonNull::new(ptr).expect(\"Unexpected null AStatus pointer\"))\n"
            + "    }\n"
            + "}\n"
        )
        if status_impl not in error_text:
            fail("could not find Binder Rust StatusCode conversion block")
        error_text = error_text.replace(status_impl, exception_impl, 1)
        print("Patched Binder Rust ExceptionCode to Status conversion")

    if error_text != error_path.read_text():
        error_path.write_text(error_text)


def patch_binder_tokio_missing_sys_import(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/binder/rust/binder_tokio/lib.rs"
    if not path.exists():
        print("Skipping Binder Tokio sys import patch; binder_tokio/lib.rs not present")
        return

    text = path.read_text()
    marker = "HansOS local: binder_tokio uses binder::sys status constants on Linux/ARM64."
    if "use binder::sys;" in text:
        print("Binder Tokio sys import already patched")
        return
    if "sys::" not in text:
        print("Binder Tokio no longer references sys constants")
        return

    anchor = "use binder::binder_impl::BinderAsyncRuntime;\n"
    if anchor not in text:
        fail("could not find Binder Tokio import anchor")

    text = text.replace(anchor, anchor + f"// {marker}\nuse binder::sys;\n", 1)
    path.write_text(text)
    print("Patched Binder Tokio missing binder::sys import")


def patch_binder_rpc_rust_missing_bindings(aosp_root: pathlib.Path) -> None:
    bp_path = aosp_root / "frameworks/native/libs/binder/rust/rpcbinder/Android.bp"
    session_path = aosp_root / "frameworks/native/libs/binder/rust/rpcbinder/src/session.rs"
    if not bp_path.exists():
        print("Skipping Binder RPC Rust bindings patch; rpcbinder Android.bp not present")
        return

    text = bp_path.read_text()
    block_range = find_named_module_block(text, "rust_bindgen", "libbinder_rpc_unstable_bindgen")
    if block_range is None:
        print("Skipping Binder RPC Rust bindings patch; libbinder_rpc_unstable_bindgen not present")
    else:
        start, end = block_range
        block = text[start:end]
        marker = "HansOS local: bindgen drops unstable RPC Binder declarations on Linux/ARM64."
        if marker in block:
            print("Binder RPC Rust bindgen declarations already patched")
        else:
            anchor = (
                '        "--raw-line",\n'
                '        "use binder_ndk_sys::AIBinder;",\n'
            )
            if anchor not in block:
                fail("could not find Binder RPC bindgen raw-line anchor")

            raw_lines = [
                "// " + marker,
                "#[allow(non_camel_case_types)]",
                "#[repr(i32)]",
                "#[derive(Debug, Copy, Clone, Hash, PartialEq, Eq)]",
                "pub enum ARpcSession_FileDescriptorTransportMode { None = 0, Unix = 1, Trusty = 2 }",
                "#[repr(C)]",
                "#[derive(Debug, Copy, Clone)]",
                "pub struct ARpcServer { _unused: [u8; 0] }",
                "#[repr(C)]",
                "#[derive(Debug, Copy, Clone)]",
                "pub struct ARpcSession { _unused: [u8; 0] }",
                'extern "C" {',
                "    pub fn ARpcServer_newVsock(service: *mut AIBinder, cid: ::std::os::raw::c_uint, port: ::std::os::raw::c_uint) -> *mut ARpcServer;",
                "    pub fn ARpcServer_newBoundSocket(service: *mut AIBinder, socketFd: ::std::os::raw::c_int) -> *mut ARpcServer;",
                "    pub fn ARpcServer_newUnixDomainBootstrap(service: *mut AIBinder, bootstrapFd: ::std::os::raw::c_int) -> *mut ARpcServer;",
                "    pub fn ARpcServer_newInet(service: *mut AIBinder, address: *const ::std::os::raw::c_char, port: ::std::os::raw::c_uint) -> *mut ARpcServer;",
                "    pub fn ARpcServer_setSupportedFileDescriptorTransportModes(handle: *mut ARpcServer, modes: *const ARpcSession_FileDescriptorTransportMode, modes_len: usize);",
                "    pub fn ARpcServer_start(server: *mut ARpcServer);",
                "    pub fn ARpcServer_join(server: *mut ARpcServer);",
                "    pub fn ARpcServer_shutdown(server: *mut ARpcServer) -> bool;",
                "    pub fn ARpcServer_free(server: *mut ARpcServer);",
                "    pub fn ARpcSession_new() -> *mut ARpcSession;",
                "    pub fn ARpcSession_setupVsockClient(session: *mut ARpcSession, cid: ::std::os::raw::c_uint, port: ::std::os::raw::c_uint) -> *mut AIBinder;",
                "    pub fn ARpcSession_setupUnixDomainClient(session: *mut ARpcSession, name: *const ::std::os::raw::c_char) -> *mut AIBinder;",
                "    pub fn ARpcSession_setupUnixDomainBootstrapClient(session: *mut ARpcSession, bootstrapFd: ::std::os::raw::c_int) -> *mut AIBinder;",
                "    pub fn ARpcSession_setupInet(session: *mut ARpcSession, address: *const ::std::os::raw::c_char, port: ::std::os::raw::c_uint) -> *mut AIBinder;",
                '    pub fn ARpcSession_setupPreconnectedClient(session: *mut ARpcSession, requestFd: ::std::option::Option<unsafe extern "C" fn(param: *mut ::std::os::raw::c_void) -> ::std::os::raw::c_int>, param: *mut ::std::os::raw::c_void) -> *mut AIBinder;',
                "    pub fn ARpcSession_setFileDescriptorTransportMode(session: *mut ARpcSession, mode: ARpcSession_FileDescriptorTransportMode);",
                "    pub fn ARpcSession_setMaxIncomingThreads(session: *mut ARpcSession, threads: usize);",
                "    pub fn ARpcSession_setMaxOutgoingConnections(session: *mut ARpcSession, connections: usize);",
                "    pub fn ARpcSession_free(session: *mut ARpcSession);",
                "}",
            ]
            insertion = "".join(
                f'        "--raw-line",\n        "{line.replace("\\", "\\\\").replace("\"", "\\\"")}",\n'
                for line in raw_lines
            )
            updated_block = block.replace(anchor, anchor + insertion, 1)
            bp_path.write_text(text[:start] + updated_block + text[end:])
            print("Patched Binder RPC Rust bindgen with missing declarations")

    if not session_path.exists():
        print("Skipping Binder RPC Rust sys import patch; session.rs not present")
        return

    session_text = session_path.read_text()
    old = "use binder::{FromIBinder, SpIBinder, StatusCode, Strong};\n"
    new = "use binder::{sys, FromIBinder, SpIBinder, StatusCode, Strong};\n"
    if new in session_text:
        print("Binder RPC Rust session already imports binder::sys")
    elif old in session_text:
        session_path.write_text(session_text.replace(old, new, 1))
        print("Patched Binder RPC Rust session with binder::sys import")
    else:
        fail("could not find Binder RPC session binder import")


def patch_apkmanifest_bindgen_missing_functions(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "packages/modules/Virtualization/libs/apkmanifest/Android.bp"
    if not path.exists():
        print("Skipping apkmanifest bindgen patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "rust_bindgen", "libapkmanifest_bindgen")
    if block_range is None:
        print("Skipping apkmanifest bindgen patch; libapkmanifest_bindgen not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: bindgen drops apkmanifest C ABI functions on Linux/ARM64."
    if marker in block:
        print("apkmanifest bindgen functions already patched")
        return

    anchor = "    bindgen_flags: [\n"
    if anchor not in block:
        fail("could not find apkmanifest bindgen_flags anchor")

    raw_lines = [
        "// " + marker,
        'extern "C" {',
        "    pub fn extractManifestInfo(manifest: *const ::std::os::raw::c_void, size: usize) -> *const ApkManifestInfo;",
        "    pub fn freeManifestInfo(info: *const ApkManifestInfo);",
        "    pub fn getPackageName(info: *const ApkManifestInfo) -> *const ::std::os::raw::c_char;",
        "    pub fn getVersionCode(info: *const ApkManifestInfo) -> u64;",
        "}",
    ]
    insertion = "".join(
        f'        "--raw-line",\n        "{line.replace("\\", "\\\\").replace("\"", "\\\"")}",\n'
        for line in raw_lines
    )
    block = block.replace(anchor, anchor + insertion, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Patched apkmanifest bindgen with missing C ABI functions")


def patch_keystore2_crypto_bindgen_missing_symbols(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/security/keystore2/src/crypto/Android.bp"
    if not path.exists():
        print("Skipping keystore2 crypto bindgen patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "rust_bindgen", "libkeystore2_crypto_bindgen")
    if block_range is None:
        print("Skipping keystore2 crypto bindgen patch; libkeystore2_crypto_bindgen not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: bindgen drops keystore2 crypto declarations on Linux/ARM64."
    if marker in block:
        print("keystore2 crypto bindgen declarations already patched")
        return

    anchor = "    bindgen_flags: [\n"
    if anchor not in block:
        fail("could not find keystore2 crypto bindgen_flags anchor")

    raw_lines = [
        "// " + marker,
        "#[allow(non_camel_case_types)]",
        "pub type km_id_t = u64;",
        "#[repr(C)]",
        "#[derive(Debug, Copy, Clone)]",
        "pub struct EC_KEY { _unused: [u8; 0] }",
        "#[repr(C)]",
        "#[derive(Debug, Copy, Clone)]",
        "pub struct EC_POINT { _unused: [u8; 0] }",
        "pub const EC_MAX_BYTES: usize = 32;",
        'extern "C" {',
        "    pub fn hmacSha256(key: *const u8, key_size: usize, msg: *const u8, msg_size: usize, out: *mut u8, out_size: usize) -> bool;",
        "    pub fn randomBytes(out: *mut u8, len: usize) -> bool;",
        "    pub fn AES_gcm_encrypt(input: *const u8, out: *mut u8, len: usize, key: *const u8, key_size: usize, iv: *const u8, tag: *mut u8) -> bool;",
        "    pub fn AES_gcm_decrypt(input: *const u8, out: *mut u8, len: usize, key: *const u8, key_size: usize, iv: *const u8, tag: *const u8) -> bool;",
        "    pub fn CreateKeyId(key_blob: *const u8, len: usize, out_id: *mut km_id_t) -> bool;",
        "    pub fn PBKDF2(key: *mut u8, key_len: usize, pw: *const ::std::os::raw::c_char, pw_len: usize, salt: *const u8);",
        "    pub fn HKDFExtract(out_key: *mut u8, out_len: *mut usize, secret: *const u8, secret_len: usize, salt: *const u8, salt_len: usize) -> bool;",
        "    pub fn HKDFExpand(out_key: *mut u8, out_len: usize, prk: *const u8, prk_len: usize, info: *const u8, info_len: usize) -> bool;",
        "    pub fn ECDHComputeKey(out: *mut ::std::os::raw::c_void, pub_key: *const EC_POINT, priv_key: *const EC_KEY) -> ::std::os::raw::c_int;",
        "    pub fn ECKEYGenerateKey() -> *mut EC_KEY;",
        "    pub fn ECKEYMarshalPrivateKey(priv_key: *const EC_KEY, buf: *mut u8, len: usize) -> usize;",
        "    pub fn ECKEYParsePrivateKey(buf: *const u8, len: usize) -> *mut EC_KEY;",
        "    pub fn ECPOINTPoint2Oct(point: *const EC_POINT, buf: *mut u8, len: usize) -> usize;",
        "    pub fn ECPOINTOct2Point(buf: *const u8, len: usize) -> *mut EC_POINT;",
        "    pub fn EC_KEY_free(key: *mut EC_KEY);",
        "    pub fn EC_KEY_get0_public_key(key: *const EC_KEY) -> *const EC_POINT;",
        "    pub fn EC_POINT_free(point: *mut EC_POINT);",
        "}",
    ]
    insertion = "".join(
        f'        "--raw-line",\n        "{line.replace("\\", "\\\\").replace("\"", "\\\"")}",\n'
        for line in raw_lines
    )
    block = block.replace(anchor, anchor + insertion, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Patched keystore2 crypto bindgen with missing declarations")


def patch_keystore2_aaid_bindgen_missing_symbols(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/security/keystore2/aaid/Android.bp"
    if not path.exists():
        print("Skipping keystore2 AAID bindgen patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "rust_bindgen", "libkeystore2_aaid_bindgen")
    if block_range is None:
        print("Skipping keystore2 AAID bindgen patch; libkeystore2_aaid_bindgen not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: bindgen drops keystore2 AAID C ABI functions on Linux/ARM64."
    if marker in block:
        print("keystore2 AAID bindgen declarations already patched")
        return

    anchor = "    bindgen_flags: [\n"
    if anchor not in block:
        fail("could not find keystore2 AAID bindgen_flags anchor")

    raw_lines = [
        "// " + marker,
        'extern "C" {',
        "    pub fn aaid_keystore_attestation_id(uid: u32, aaid: *mut u8, aaid_size: *mut usize) -> u32;",
        "}",
    ]
    insertion = "".join(
        f'        "--raw-line",\n        "{line.replace("\\", "\\\\").replace("\"", "\\\"")}",\n'
        for line in raw_lines
    )
    block = block.replace(anchor, anchor + insertion, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Patched keystore2 AAID bindgen with missing declarations")


def patch_keystore2_apc_compat_bindgen_missing_symbols(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/security/keystore2/apc_compat/Android.bp"
    if not path.exists():
        print("Skipping keystore2 APC compat bindgen patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(
        text,
        "rust_bindgen",
        "libkeystore2_apc_compat_bindgen",
    )
    if block_range is None:
        print("Skipping keystore2 APC compat bindgen patch; libkeystore2_apc_compat_bindgen not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: bindgen drops keystore2 APC compat declarations on Linux/ARM64."
    if marker in block:
        print("keystore2 APC compat bindgen declarations already patched")
        return

    anchor = "    bindgen_flags: [\n"
    if anchor not in block:
        fail("could not find keystore2 APC compat bindgen_flags anchor")

    raw_lines = [
        "// " + marker,
        "pub type ApcCompatServiceHandle = *mut ::std::os::raw::c_void;",
        "#[repr(C)]",
        "#[derive(Debug, Copy, Clone)]",
        "pub struct ApcCompatUiOptions {",
        "    pub inverted: bool,",
        "    pub magnified: bool,",
        "}",
        "#[repr(C)]",
        "#[derive(Debug, Copy, Clone)]",
        "pub struct ApcCompatCallback {",
        "    pub data: *mut ::std::os::raw::c_void,",
        "    pub result: ::std::option::Option<extern \"C\" fn(*mut ::std::os::raw::c_void, u32, *const u8, usize, *const u8, usize)>,",
        "}",
        'extern "C" {',
        "    pub static INVALID_SERVICE_HANDLE: ApcCompatServiceHandle;",
        "    pub fn tryGetUserConfirmationService() -> ApcCompatServiceHandle;",
        "    pub fn promptUserConfirmation(handle: ApcCompatServiceHandle, callback: ApcCompatCallback, prompt_text: *const ::std::os::raw::c_char, extra_data: *const u8, extra_data_size: usize, locale: *const ::std::os::raw::c_char, ui_options: ApcCompatUiOptions) -> u32;",
        "    pub fn abortUserConfirmation(handle: ApcCompatServiceHandle);",
        "    pub fn closeUserConfirmationService(handle: ApcCompatServiceHandle);",
        "}",
    ]
    insertion = "".join(
        f'        "--raw-line",\n        "{line.replace("\\", "\\\\").replace("\"", "\\\"")}",\n'
        for line in raw_lines
    )
    block = block.replace(anchor, anchor + insertion, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Patched keystore2 APC compat bindgen with missing declarations")


def patch_simpleperf_profcollect_bindgen_missing_functions(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/extras/simpleperf/Android.bp"
    if not path.exists():
        print("Skipping simpleperf profcollect bindgen patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(
        text,
        "rust_bindgen",
        "libsimpleperf_profcollect_bindgen",
    )
    if block_range is None:
        print("Skipping simpleperf profcollect bindgen patch; libsimpleperf_profcollect_bindgen not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: bindgen drops simpleperf profcollect C ABI functions on Linux/ARM64."
    if marker in block:
        print("simpleperf profcollect bindgen declarations already patched")
        return

    anchor = '    source_stem: "bindings",\n'
    if anchor not in block:
        fail("could not find simpleperf profcollect source_stem anchor")

    raw_lines = [
        "// " + marker,
        'extern "C" {',
        "    pub fn IsETMDriverAvailable() -> bool;",
        "    pub fn IsETMDeviceAvailable() -> bool;",
        "    pub fn IsLBRAvailable() -> bool;",
        "    pub fn RunRecordCmd(args: *mut *const ::std::os::raw::c_char, arg_count: ::std::os::raw::c_int) -> bool;",
        "    pub fn RunInjectCmd(args: *mut *const ::std::os::raw::c_char, arg_count: ::std::os::raw::c_int) -> bool;",
        "    pub fn SetLogFile(filename: *const ::std::os::raw::c_char);",
        "    pub fn ResetLogFile();",
        "}",
    ]
    raw_line_flags = "".join(
        f'        "--raw-line",\n        "{line.replace("\\", "\\\\").replace("\"", "\\\"")}",\n'
        for line in raw_lines
    )
    insertion = f"\n    bindgen_flags: [\n{raw_line_flags}    ],\n"
    block = block.replace(anchor, anchor + insertion, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Patched simpleperf profcollect bindgen with missing declarations")


def patch_mkuserimg_mke2fs_host_tool_lookup(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/extras/ext4_utils/mkuserimg_mke2fs.py"
    if not path.exists():
        print("Skipping mkuserimg_mke2fs host tool lookup patch; script not present")
        return

    text = path.read_text()
    marker = "HansOS local: Soong python wrappers may not live beside host tools on Linux/ARM64."
    if marker in text:
        print("mkuserimg_mke2fs host tool lookup already patched")
        return

    old = """def FindProgram(prog_name):
  \"\"\"Finds the path to prog_name.

  Args:
    prog_name: the program name to find.
  Returns:
    path to the progName if found. The program is searched in the same directory
    where this script is located at. If not found, progName is returned.
  \"\"\"
  exec_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
  prog_path = os.path.join(exec_dir, prog_name)
  if os.path.exists(prog_path):
    return prog_path
  else:
    return prog_name
"""
    new = f"""def FindProgram(prog_name):
  \"\"\"Finds the path to prog_name.

  Args:
    prog_name: the program name to find.
  Returns:
    path to the progName if found. The program is searched in the same directory
    where this script is located at. If not found, progName is returned.
  \"\"\"
  # {marker}
  candidate_dirs = [os.path.dirname(os.path.realpath(sys.argv[0]))]

  for env_name in ("ANDROID_HOST_OUT", "SOONG_HOST_OUT", "HOST_OUT"):
    host_out = os.environ.get(env_name)
    if host_out:
      candidate_dirs.extend([host_out, os.path.join(host_out, "bin")])

  out_dir = os.environ.get("OUT_DIR")
  if out_dir:
    candidate_dirs.extend([
        os.path.join(out_dir, "host", "linux-arm64", "bin"),
        os.path.join(out_dir, "host", "linux-x86", "bin"),
    ])

  for exec_dir in candidate_dirs:
    prog_path = os.path.join(exec_dir, prog_name)
    if os.path.exists(prog_path):
      return prog_path

  return prog_name
"""
    if old not in text:
        fail("could not find mkuserimg_mke2fs FindProgram block")

    path.write_text(text.replace(old, new, 1))
    print("Patched mkuserimg_mke2fs host tool lookup")


def patch_releasetools_build_image_host_tool_lookup(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/make/tools/releasetools/build_image.py"
    if not path.exists():
        print("Skipping releasetools build_image host tool lookup patch; script not present")
        return

    text = path.read_text()
    marker = "HansOS local: Soong python wrappers may not live beside host tools on Linux/ARM64."
    changed = False

    if marker not in text:
        anchor = "\n\nclass BuildImageError(Exception):\n"
        if anchor not in text:
            fail("could not find build_image.py BuildImageError anchor")

        helper = f"""

def FindHostTool(prog_name):
  # {marker}
  candidate_dirs = [os.path.dirname(os.path.realpath(sys.argv[0]))]

  for env_name in ("ANDROID_HOST_OUT", "SOONG_HOST_OUT", "HOST_OUT"):
    host_out = os.environ.get(env_name)
    if host_out:
      candidate_dirs.extend([host_out, os.path.join(host_out, "bin")])

  out_dir = os.environ.get("OUT_DIR")
  if out_dir:
    candidate_dirs.extend([
        os.path.join(out_dir, "host", "linux-arm64", "bin"),
        os.path.join(out_dir, "host", "linux-x86", "bin"),
    ])

  for candidate_dir in candidate_dirs:
    prog_path = os.path.join(candidate_dir, prog_name)
    if os.path.exists(prog_path):
      return prog_path

  return prog_name
"""
        text = text.replace(anchor, helper + anchor, 1)
        changed = True

    replacements = {
        'cmd = ["tune2fs", "-l", unsparse_image_path]':
            'cmd = [FindHostTool("tune2fs"), "-l", unsparse_image_path]',
        'cmd = ["fsck.f2fs", "-l", unsparse_image_path]':
            'cmd = [FindHostTool("fsck.f2fs"), "-l", unsparse_image_path]',
        'inflate_command = ["simg2img", sparse_image_path, unsparse_image_path]':
            'inflate_command = [FindHostTool("simg2img"), sparse_image_path, unsparse_image_path]',
        'convert_command = ["blk_alloc_to_base_fs", block_map_file, base_fs_file]':
            'convert_command = [FindHostTool("blk_alloc_to_base_fs"), block_map_file, base_fs_file]',
        'build_command = ["mkfs.erofs"]':
            'build_command = [FindHostTool("mkfs.erofs")]',
        'build_command = ["mkf2fsuserimg"]':
            'build_command = [FindHostTool("mkf2fsuserimg")]',
        'img2simg_argv = ["img2simg", out_file, temp_file]':
            'img2simg_argv = [FindHostTool("img2simg"), out_file, temp_file]',
        'e2fsck_command = ["e2fsck", "-f", "-n", unsparse_image]':
            'e2fsck_command = [FindHostTool("e2fsck"), "-f", "-n", unsparse_image]',
        'fsck_command = ["fsck.erofs", "--extract", out_file]':
            'fsck_command = [FindHostTool("fsck.erofs"), "--extract", out_file]',
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new, 1)
            changed = True
        elif new not in text:
            fail(f"could not find build_image.py command block: {old}")

    ext_old = '    build_command = [prop_dict["ext_mkuserimg"]]\n'
    ext_new = (
        '    ext_mkuserimg = prop_dict["ext_mkuserimg"]\n'
        '    if os.path.basename(ext_mkuserimg) == ext_mkuserimg:\n'
        '      ext_mkuserimg = FindHostTool(ext_mkuserimg)\n'
        "    build_command = [ext_mkuserimg]\n"
    )
    if ext_old in text:
        text = text.replace(ext_old, ext_new, 1)
        changed = True
    elif ext_new not in text:
        fail("could not find build_image.py ext_mkuserimg command block")

    if changed:
        path.write_text(text)
        print("Patched releasetools build_image host tool lookup")
    else:
        print("releasetools build_image host tool lookup already patched")


def patch_ota_from_raw_img_delta_generator_path(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/make/tools/releasetools/ota_from_raw_img.py"
    if not path.exists():
        print("Skipping ota_from_raw_img delta_generator path patch; script not present")
        return

    text = path.read_text()
    marker = "HansOS local: payload_signer invokes delta_generator by basename under Soong Python wrappers."
    changed = False

    if marker not in text:
        helper_anchor = "  return path\n\n\ndef main(argv):\n"
        if helper_anchor not in text:
            fail("could not find ota_from_raw_img ResolveBinaryPath anchor")

        helper = f"""  return path


def AddHostToolSearchPath(search_path):
  # {marker}
  if not search_path or not os.path.exists(search_path):
    return

  candidates = [os.path.join(search_path, "bin"), search_path]
  existing = os.environ.get("PATH", "").split(os.pathsep)
  prepend = [candidate for candidate in candidates
             if os.path.exists(candidate) and candidate not in existing]
  if prepend:
    os.environ["PATH"] = os.pathsep.join(prepend + existing)


def main(argv):
"""
        text = text.replace(helper_anchor, helper, 1)
        changed = True

    call_old = "  args = parser.parse_args(argv[1:])\n"
    call_new = (
        "  args = parser.parse_args(argv[1:])\n"
        "  AddHostToolSearchPath(args.search_path)\n"
    )
    if call_new not in text:
        if call_old not in text:
            fail("could not find ota_from_raw_img parse_args anchor")
        text = text.replace(call_old, call_new, 1)
        changed = True

    if changed:
        path.write_text(text)
        print("Patched ota_from_raw_img delta_generator host tool path")
    else:
        print("ota_from_raw_img delta_generator host tool path already patched")


def patch_dexpreopt_gen_product_packages_path(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "build/soong/dexpreopt/dexpreopt_gen/dexpreopt_gen.go"
    if not path.exists():
        print("Skipping dexpreopt_gen product_packages path patch; source not present")
        return

    text = path.read_text()
    marker = "HansOS local: Make passes product_packages as an absolute OUT_DIR path on Linux/ARM64."
    changed = False

    if marker not in text:
        anchor = (
            "func writeScripts(ctx android.BuilderContext, globalSoong *dexpreopt.GlobalSoongConfig,\n"
            "\tglobal *dexpreopt.GlobalConfig, module *dexpreopt.ModuleConfig, dexpreoptScriptPath string,\n"
            "\tproductPackagesPath string) {\n"
        )
        if anchor not in text:
            fail("could not find dexpreopt_gen writeScripts anchor")

        helper = f"""func productPackagesAsPath(ctx android.PathContext, productPackagesPath string) android.Path {{
\t// {marker}
\tif filepath.IsAbs(productPackagesPath) {{
\t\trel, err := filepath.Rel(ctx.Config().OutDir(), productPackagesPath)
\t\tif err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator)) && !filepath.IsAbs(rel) {{
\t\t\treturn android.PathForArbitraryOutput(ctx, rel)
\t\t}}
\t}}
\treturn android.PathForTesting(productPackagesPath)
}}

"""
        text = text.replace(anchor, helper + anchor, 1)
        changed = True

    old = (
        "\tdexpreoptRule, err := dexpreopt.GenerateDexpreoptRule(\n"
        "\t\tctx, globalSoong, global, module, android.PathForTesting(productPackagesPath))\n"
    )
    new = (
        "\tdexpreoptRule, err := dexpreopt.GenerateDexpreoptRule(\n"
        "\t\tctx, globalSoong, global, module, productPackagesAsPath(ctx, productPackagesPath))\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif new not in text:
        fail("could not find dexpreopt_gen productPackages PathForTesting call")

    if changed:
        path.write_text(text)
        print("Patched dexpreopt_gen product_packages host output path")
    else:
        print("dexpreopt_gen product_packages host output path already patched")


def patch_input_rust_missing_bindgen_constants(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/input/rust/input.rs"
    if not path.exists():
        print("Skipping input Rust bindgen constants patch; input.rs not present")
        return

    text = path.read_text()
    marker = "HansOS local: bindgen drops some android/input.h enum constants on Linux/ARM64."
    changed = False

    if marker not in text:
        anchor = "use std::fmt;\n"
        if anchor not in text:
            fail("could not find input.rs std::fmt import anchor")

        constants = f"""

#[allow(dead_code)]
mod hans_bindgen_constants {{
    // {marker}
    pub const AINPUT_SOURCE_CLASS_NONE: u32 = 0x00000000;
    pub const AINPUT_SOURCE_CLASS_BUTTON: u32 = 0x00000001;
    pub const AINPUT_SOURCE_CLASS_POINTER: u32 = 0x00000002;
    pub const AINPUT_SOURCE_CLASS_NAVIGATION: u32 = 0x00000004;
    pub const AINPUT_SOURCE_CLASS_POSITION: u32 = 0x00000008;
    pub const AINPUT_SOURCE_CLASS_JOYSTICK: u32 = 0x00000010;

    pub const AINPUT_SOURCE_UNKNOWN: u32 = 0x00000000;
    pub const AINPUT_SOURCE_KEYBOARD: u32 = 0x00000100 | AINPUT_SOURCE_CLASS_BUTTON;
    pub const AINPUT_SOURCE_DPAD: u32 = 0x00000200 | AINPUT_SOURCE_CLASS_BUTTON;
    pub const AINPUT_SOURCE_GAMEPAD: u32 = 0x00000400 | AINPUT_SOURCE_CLASS_BUTTON;
    pub const AINPUT_SOURCE_TOUCHSCREEN: u32 = 0x00001000 | AINPUT_SOURCE_CLASS_POINTER;
    pub const AINPUT_SOURCE_MOUSE: u32 = 0x00002000 | AINPUT_SOURCE_CLASS_POINTER;
    pub const AINPUT_SOURCE_STYLUS: u32 = 0x00004000 | AINPUT_SOURCE_CLASS_POINTER;
    pub const AINPUT_SOURCE_BLUETOOTH_STYLUS: u32 = 0x00008000 | AINPUT_SOURCE_STYLUS;
    pub const AINPUT_SOURCE_TRACKBALL: u32 = 0x00010000 | AINPUT_SOURCE_CLASS_NAVIGATION;
    pub const AINPUT_SOURCE_MOUSE_RELATIVE: u32 = 0x00020000 | AINPUT_SOURCE_CLASS_NAVIGATION;
    pub const AINPUT_SOURCE_TOUCHPAD: u32 = 0x00100000 | AINPUT_SOURCE_CLASS_POSITION;
    pub const AINPUT_SOURCE_TOUCH_NAVIGATION: u32 = 0x00200000 | AINPUT_SOURCE_CLASS_NONE;
    pub const AINPUT_SOURCE_JOYSTICK: u32 = 0x01000000 | AINPUT_SOURCE_CLASS_JOYSTICK;
    pub const AINPUT_SOURCE_HDMI: u32 = 0x02000000 | AINPUT_SOURCE_CLASS_BUTTON;
    pub const AINPUT_SOURCE_SENSOR: u32 = 0x04000000 | AINPUT_SOURCE_CLASS_NONE;
    pub const AINPUT_SOURCE_ROTARY_ENCODER: u32 = 0x00400000 | AINPUT_SOURCE_CLASS_NONE;

    pub const AMOTION_EVENT_ACTION_MASK: u32 = 0xff;
    pub const AMOTION_EVENT_ACTION_POINTER_INDEX_MASK: u32 = 0xff00;
    pub const AMOTION_EVENT_ACTION_POINTER_INDEX_SHIFT: u32 = 8;
    pub const AMOTION_EVENT_ACTION_DOWN: u32 = 0;
    pub const AMOTION_EVENT_ACTION_UP: u32 = 1;
    pub const AMOTION_EVENT_ACTION_MOVE: u32 = 2;
    pub const AMOTION_EVENT_ACTION_CANCEL: u32 = 3;
    pub const AMOTION_EVENT_ACTION_OUTSIDE: u32 = 4;
    pub const AMOTION_EVENT_ACTION_POINTER_DOWN: u32 = 5;
    pub const AMOTION_EVENT_ACTION_POINTER_UP: u32 = 6;
    pub const AMOTION_EVENT_ACTION_HOVER_MOVE: u32 = 7;
    pub const AMOTION_EVENT_ACTION_SCROLL: u32 = 8;
    pub const AMOTION_EVENT_ACTION_HOVER_ENTER: u32 = 9;
    pub const AMOTION_EVENT_ACTION_HOVER_EXIT: u32 = 10;
    pub const AMOTION_EVENT_ACTION_BUTTON_PRESS: u32 = 11;
    pub const AMOTION_EVENT_ACTION_BUTTON_RELEASE: u32 = 12;

    pub const AMOTION_EVENT_FLAG_WINDOW_IS_OBSCURED: u32 = 0x1;
}}
"""
        text = text.replace(anchor, anchor + constants, 1)
        changed = True

    names = [
        "AINPUT_SOURCE_CLASS_NONE",
        "AINPUT_SOURCE_CLASS_BUTTON",
        "AINPUT_SOURCE_CLASS_POINTER",
        "AINPUT_SOURCE_CLASS_NAVIGATION",
        "AINPUT_SOURCE_CLASS_POSITION",
        "AINPUT_SOURCE_CLASS_JOYSTICK",
        "AINPUT_SOURCE_UNKNOWN",
        "AINPUT_SOURCE_KEYBOARD",
        "AINPUT_SOURCE_DPAD",
        "AINPUT_SOURCE_GAMEPAD",
        "AINPUT_SOURCE_TOUCHSCREEN",
        "AINPUT_SOURCE_MOUSE",
        "AINPUT_SOURCE_STYLUS",
        "AINPUT_SOURCE_BLUETOOTH_STYLUS",
        "AINPUT_SOURCE_TRACKBALL",
        "AINPUT_SOURCE_MOUSE_RELATIVE",
        "AINPUT_SOURCE_TOUCHPAD",
        "AINPUT_SOURCE_TOUCH_NAVIGATION",
        "AINPUT_SOURCE_JOYSTICK",
        "AINPUT_SOURCE_HDMI",
        "AINPUT_SOURCE_SENSOR",
        "AINPUT_SOURCE_ROTARY_ENCODER",
        "AMOTION_EVENT_ACTION_MASK",
        "AMOTION_EVENT_ACTION_POINTER_INDEX_MASK",
        "AMOTION_EVENT_ACTION_POINTER_INDEX_SHIFT",
        "AMOTION_EVENT_ACTION_DOWN",
        "AMOTION_EVENT_ACTION_UP",
        "AMOTION_EVENT_ACTION_MOVE",
        "AMOTION_EVENT_ACTION_CANCEL",
        "AMOTION_EVENT_ACTION_OUTSIDE",
        "AMOTION_EVENT_ACTION_POINTER_DOWN",
        "AMOTION_EVENT_ACTION_POINTER_UP",
        "AMOTION_EVENT_ACTION_HOVER_ENTER",
        "AMOTION_EVENT_ACTION_HOVER_MOVE",
        "AMOTION_EVENT_ACTION_HOVER_EXIT",
        "AMOTION_EVENT_ACTION_SCROLL",
        "AMOTION_EVENT_ACTION_BUTTON_PRESS",
        "AMOTION_EVENT_ACTION_BUTTON_RELEASE",
        "AMOTION_EVENT_FLAG_WINDOW_IS_OBSCURED",
    ]
    for name in names:
        old = f"input_bindgen::{name}"
        new = f"hans_bindgen_constants::{name}"
        if old in text:
            text = text.replace(old, new)
            changed = True

    if changed:
        path.write_text(text)
        print("Patched input Rust missing bindgen constants")
    else:
        print("input Rust missing bindgen constants already patched")


def patch_nanopb_soong_plugin_detection(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/nanopb-c/generator/nanopb_generator.py"
    if not path.exists():
        print("Skipping Nanopb plugin detection patch; nanopb_generator.py not present")
        return

    text = path.read_text()
    marker = "HansOS local: Soong's Python launcher hides the protoc-gen-* argv name."
    if marker in text:
        print("Nanopb Soong plugin detection already patched")
        return

    old = (
        "if __name__ == '__main__':\n"
        "    # Check if we are running as a plugin under protoc\n"
        "    if 'protoc-gen-' in sys.argv[0] or '--protoc-plugin' in sys.argv:\n"
        "        main_plugin()\n"
        "    else:\n"
        "        main_cli()\n"
    )
    new = (
        "if __name__ == '__main__':\n"
        "    # Check if we are running as a plugin under protoc\n"
        "    soong_wrapped_plugin = (\n"
        "        os.path.basename(sys.argv[0]) == '__soong_entrypoint_redirector__.py'\n"
        "        and len(sys.argv) == 1\n"
        "        and not sys.stdin.isatty()\n"
        "    )\n"
        "    if (\n"
        "        'protoc-gen-' in sys.argv[0]\n"
        "        or '--protoc-plugin' in sys.argv\n"
        "        or soong_wrapped_plugin\n"
        "    ):\n"
        f"        # {marker}\n"
        "        main_plugin()\n"
        "    else:\n"
        "        main_cli()\n"
    )
    if old not in text:
        fail("could not find Nanopb generator plugin-mode detection block")

    path.write_text(text.replace(old, new, 1))
    print("Patched Nanopb generator to detect Soong-wrapped protoc plugin invocations")


def patch_input_bindgen_binder_headers(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/input/Android.bp"
    if not path.exists():
        print("Skipping input bindgen binder include patch; Android.bp not present")
        return

    text = path.read_text()
    headers_marker = (
        "HansOS local: expose generated AIDL C++ headers without linking libbinder on Darwin."
    )
    if headers_marker in text:
        print("inputconstants generated header export already patched")
    else:
        aidl_range = find_named_module_block(text, "aidl_interface", "inputconstants")
        if aidl_range is None:
            fail("could not find inputconstants aidl_interface")

        _, aidl_end = aidl_range
        headers_module = (
            "\n"
            "cc_library_headers {\n"
            '    name: "inputconstants-cpp-headers",\n'
            f"    // {headers_marker}\n"
            "    host_supported: true,\n"
            "    generated_headers: [\n"
            '        "inputconstants-cpp-source",\n'
            "    ],\n"
            "    export_generated_headers: [\n"
            '        "inputconstants-cpp-source",\n'
            "    ],\n"
            "}\n"
        )
        text = text[:aidl_end] + headers_module + text[aidl_end:]
        path.write_text(text)
        print("Patched inputconstants with generated header-only export")

    text = path.read_text()
    block_range = find_named_module_block(text, "rust_bindgen", "libinput_bindgen")
    if block_range is None:
        print("Skipping input bindgen binder include patch; libinput_bindgen not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: Darwin bindgen needs binder/Enums.h from libbinder headers."
    if marker in block:
        print("input bindgen binder include path already patched")
    else:
        anchor = "    bindgen_flags: [\n"
        if anchor not in block:
            fail("could not find libinput_bindgen bindgen_flags anchor")

        insertion = (
            f"    // {marker}\n"
            "    cflags: [\n"
            '        "-Iframeworks/native/libs/binder/include",\n'
            "    ],\n"
            "\n"
        )
        replacement = block.replace(anchor, insertion + anchor, 1)
        path.write_text(text[:start] + replacement + text[end:])
        print("Patched input bindgen with libbinder header include path")

    text = path.read_text()
    block_range = find_named_module_block(text, "rust_bindgen", "libinput_bindgen")
    if block_range is None:
        fail("could not re-read libinput_bindgen module after binder include patch")

    start, end = block_range
    block = text[start:end]
    changed = False
    if '        "inputconstants-cpp",\n' in block:
        block = block.replace('        "inputconstants-cpp",\n', "", 1)
        changed = True

    header_deps = [
        '        "inputconstants-cpp-headers",\n',
        '        "libbase_headers",\n',
        '        "libcutils_headers",\n',
        '        "liblog_headers",\n',
        '        "libutils_headers",\n',
    ]
    missing_header_deps = [dep for dep in header_deps if dep not in block]
    if missing_header_deps:
        header_anchor = "    header_libs: [\n"
        if header_anchor not in block:
            fail("could not find libinput_bindgen header_libs anchor")
        block = block.replace(header_anchor, header_anchor + "".join(missing_header_deps), 1)
        changed = True

    if changed:
        path.write_text(text[:start] + block + text[end:])
        print("Patched input bindgen to use inputconstants generated headers without Darwin libbinder link")
    else:
        print("input bindgen inputconstants header dependency already patched")

    wrapper_path = aosp_root / "frameworks/native/libs/input/InputWrapper.hpp"
    if not wrapper_path.exists():
        print("Skipping input bindgen wrapper patch; InputWrapper.hpp not present")
        return

    wrapper_text = wrapper_path.read_text()
    wrapper_marker = "HansOS local: Input.h references these generated enums on Darwin bindgen."
    if wrapper_marker in wrapper_text:
        print("input bindgen wrapper enum includes already patched")
        return

    wrapper_anchor = "#include <android/input.h>\n"
    wrapper_insertion = (
        "#if defined(__APPLE__)\n"
        f"// {wrapper_marker}\n"
        "#include <android/os/IInputConstants.h>\n"
        "#include <android/os/MotionEventFlag.h>\n"
        "#endif\n"
    )
    if wrapper_anchor not in wrapper_text:
        fail("could not find InputWrapper.hpp include anchor")

    wrapper_path.write_text(wrapper_text.replace(wrapper_anchor, wrapper_insertion + wrapper_anchor, 1))
    print("Patched input bindgen wrapper with Darwin generated enum includes")


def patch_inputflinger_aidl_static_darwin_variant(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/input/Android.bp"
    if not path.exists():
        print("Skipping inputflinger AIDL Darwin variant patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "cc_library_static", "iinputflinger_aidl_lib_static")
    if block_range is None:
        print("Skipping inputflinger AIDL Darwin variant patch; module not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: Darwin host builds lack libbinder/libgui host variants."
    if marker in block:
        print("inputflinger AIDL static Darwin host variant already disabled")
        return

    anchor = "    host_supported: true,\n"
    if anchor not in block:
        fail("could not find iinputflinger_aidl_lib_static host_supported anchor")

    insertion = (
        anchor +
        "    target: {\n"
        "        darwin: {\n"
        f"            // {marker}\n"
        "            enabled: false,\n"
        "        },\n"
        "    },\n"
    )
    block = block.replace(anchor, insertion, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Disabled inputflinger AIDL static Darwin host variant")


def patch_libinput_android_only_host_deps(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/input/Android.bp"
    if not path.exists():
        print("Skipping libinput host dependency patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "cc_library", "libinput")
    if block_range is None:
        print("Skipping libinput host dependency patch; libinput module not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: keep Android-only Binder/InputFlinger deps off host libinput variants."
    if marker in block:
        print("libinput Android-only host dependencies already patched")
        return

    shared_deps = (
        '        "libbinder",\n'
        '        "libbinder_ndk",\n'
    )
    if shared_deps not in block:
        fail("could not find libinput Binder shared_libs")

    inputflinger_dep = '        "iinputflinger_aidl_lib_static",\n'
    if inputflinger_dep not in block:
        fail("could not find libinput inputflinger whole_static_lib")

    android_anchor = (
        "        android: {\n"
        "            required: [\n"
    )
    if android_anchor not in block:
        fail("could not find libinput android target anchor")

    android_only_deps = (
        "        android: {\n"
        f"            // {marker}\n"
        "            shared_libs: [\n"
        '                "libbinder",\n'
        '                "libbinder_ndk",\n'
        "            ],\n"
        "            whole_static_libs: [\n"
        '                "iinputflinger_aidl_lib_static",\n'
        "            ],\n"
        "            required: [\n"
    )

    block = block.replace(shared_deps, "", 1)
    block = block.replace(inputflinger_dep, "", 1)
    block = block.replace(android_anchor, android_only_deps, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Moved libinput Binder/InputFlinger deps to Android target only")


def patch_libinput_inputconstants_android_only(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/input/Android.bp"
    if not path.exists():
        print("Skipping libinput inputconstants host patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "cc_library", "libinput")
    if block_range is None:
        print("Skipping libinput inputconstants host patch; libinput module not present")
        return

    start, end = block_range
    block = text[start:end]
    marker = "HansOS local: keep Binder-backed inputconstants-cpp off host libinput variants."
    dep = '        "inputconstants-cpp",\n'

    target_anchor = "\n    target: {\n"
    if target_anchor not in block:
        fail("could not find libinput target block")

    top_level, target_and_rest = block.split(target_anchor, 1)
    if dep not in top_level:
        if marker in block:
            print("libinput inputconstants-cpp Android-only dependency already patched")
            return
        print("Skipping libinput inputconstants host patch; inputconstants-cpp already absent from host static_libs")
        return

    android_static_anchor = (
        "            static_libs: [\n"
        '                "libstatslog_libinput",\n'
    )
    android_static_replacement = (
        "            static_libs: [\n"
        f"                // {marker}\n"
        '                "inputconstants-cpp",\n'
        '                "libstatslog_libinput",\n'
    )
    if android_static_replacement in target_and_rest:
        top_level = top_level.replace(dep, "", 1)
    elif android_static_anchor in target_and_rest:
        top_level = top_level.replace(dep, "", 1)
        target_and_rest = target_and_rest.replace(android_static_anchor, android_static_replacement, 1)
    else:
        fail("could not find libinput Android static_libs anchor")

    block = top_level + target_anchor + target_and_rest
    path.write_text(text[:start] + block + text[end:])
    print("Moved libinput inputconstants-cpp dependency to Android target only")


def patch_libinput_darwin_generated_input_headers(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/input/Android.bp"
    if not path.exists():
        print("Skipping libinput generated input header patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "cc_library", "libinput")
    if block_range is None:
        print("Skipping libinput generated input header patch; libinput module not present")
        return

    start, end = block_range
    block = text[start:end]
    dep = '        "inputconstants-cpp-headers",\n'
    if dep in block:
        print("libinput generated input headers already available to host build")
        return

    marker = "HansOS local: host libinput still needs generated input enum headers."
    anchor = "    header_libs: [\n"
    if anchor not in block:
        fail("could not find libinput header_libs anchor")

    block = block.replace(anchor, anchor + f"        // {marker}\n" + dep, 1)
    path.write_text(text[:start] + block + text[end:])
    print("Patched libinput with generated input enum headers for host build")


def patch_input_rust_darwin_inputconstants(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/native/libs/input/rust/input.rs"
    if not path.exists():
        print("Skipping input Rust Darwin constants patch; input.rs not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin host builds cannot link generated inputconstants Rust AIDL."
    if marker in text:
        print("input Rust Darwin inputconstants shim already patched")
        return

    anchor = "//! Common definitions of the Android Input Framework in rust.\n\n"
    if anchor not in text:
        fail("could not find input.rs module insertion anchor")

    shim = (
        "#[cfg(target_os = \"macos\")]\n"
        "#[allow(dead_code, missing_docs, non_snake_case)]\n"
        "mod inputconstants {\n"
        "    pub mod aidl {\n"
        "        pub mod android {\n"
        "            pub mod os {\n"
        "                pub mod IInputConstants {\n"
        f"                    // {marker}\n"
        "                    pub const DEVICE_CLASS_KEYBOARD: i32 = 0x00000001;\n"
        "                    pub const DEVICE_CLASS_ALPHAKEY: i32 = 0x00000002;\n"
        "                    pub const DEVICE_CLASS_TOUCH: i32 = 0x00000004;\n"
        "                    pub const DEVICE_CLASS_CURSOR: i32 = 0x00000008;\n"
        "                    pub const DEVICE_CLASS_TOUCH_MT: i32 = 0x00000010;\n"
        "                    pub const DEVICE_CLASS_DPAD: i32 = 0x00000020;\n"
        "                    pub const DEVICE_CLASS_GAMEPAD: i32 = 0x00000040;\n"
        "                    pub const DEVICE_CLASS_SWITCH: i32 = 0x00000080;\n"
        "                    pub const DEVICE_CLASS_JOYSTICK: i32 = 0x00000100;\n"
        "                    pub const DEVICE_CLASS_VIBRATOR: i32 = 0x00000200;\n"
        "                    pub const DEVICE_CLASS_MIC: i32 = 0x00000400;\n"
        "                    pub const DEVICE_CLASS_EXTERNAL_STYLUS: i32 = 0x00000800;\n"
        "                    pub const DEVICE_CLASS_ROTARY_ENCODER: i32 = 0x00001000;\n"
        "                    pub const DEVICE_CLASS_SENSOR: i32 = 0x00002000;\n"
        "                    pub const DEVICE_CLASS_BATTERY: i32 = 0x00004000;\n"
        "                    pub const DEVICE_CLASS_LIGHT: i32 = 0x00008000;\n"
        "                    pub const DEVICE_CLASS_TOUCHPAD: i32 = 0x00010000;\n"
        "                    pub const DEVICE_CLASS_VIRTUAL: i32 = 0x20000000;\n"
        "                    pub const DEVICE_CLASS_EXTERNAL: i32 = 0x40000000;\n"
        "                }\n"
        "\n"
        "                pub mod MotionEventFlag {\n"
        "                    #[derive(Clone, Copy, Debug, Eq, PartialEq)]\n"
        "                    pub struct MotionEventFlag(pub i32);\n"
        "\n"
        "                    impl MotionEventFlag {\n"
        "                        pub const WINDOW_IS_OBSCURED: Self = Self(0x1);\n"
        "                        pub const WINDOW_IS_PARTIALLY_OBSCURED: Self = Self(0x2);\n"
        "                        pub const HOVER_EXIT_PENDING: Self = Self(0x4);\n"
        "                        pub const IS_GENERATED_GESTURE: Self = Self(0x8);\n"
        "                        pub const CANCELED: Self = Self(0x20);\n"
        "                        pub const NO_FOCUS_CHANGE: Self = Self(0x40);\n"
        "                        pub const PRIVATE_FLAG_SUPPORTS_ORIENTATION: Self = Self(0x80);\n"
        "                        pub const PRIVATE_FLAG_SUPPORTS_DIRECTIONAL_ORIENTATION: Self = Self(0x100);\n"
        "                        pub const IS_ACCESSIBILITY_EVENT: Self = Self(0x800);\n"
        "                        pub const INJECTED_FROM_ACCESSIBILITY_TOOL: Self = Self(0x1000);\n"
        "                        pub const TAINTED: Self = Self(i32::MIN);\n"
        "                        pub const TARGET_ACCESSIBILITY_FOCUS: Self = Self(0x40000000);\n"
        "\n"
        "                        #[cfg(test)]\n"
        "                        pub fn enum_values() -> &'static [Self] {\n"
        "                            &[\n"
        "                                Self::WINDOW_IS_OBSCURED,\n"
        "                                Self::WINDOW_IS_PARTIALLY_OBSCURED,\n"
        "                                Self::HOVER_EXIT_PENDING,\n"
        "                                Self::IS_GENERATED_GESTURE,\n"
        "                                Self::CANCELED,\n"
        "                                Self::NO_FOCUS_CHANGE,\n"
        "                                Self::PRIVATE_FLAG_SUPPORTS_ORIENTATION,\n"
        "                                Self::PRIVATE_FLAG_SUPPORTS_DIRECTIONAL_ORIENTATION,\n"
        "                                Self::IS_ACCESSIBILITY_EVENT,\n"
        "                                Self::INJECTED_FROM_ACCESSIBILITY_TOOL,\n"
        "                                Self::TAINTED,\n"
        "                                Self::TARGET_ACCESSIBILITY_FOCUS,\n"
        "                            ]\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n\n"
    )

    path.write_text(text.replace(anchor, anchor + shim, 1))
    print("Patched input Rust with Darwin-only inputconstants constants shim")


def patch_gemmlowp_darwin_malloc_header(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/gemmlowp/internal/platform.h"
    if not path.exists():
        print("Skipping gemmlowp Darwin malloc patch; platform.h not present")
        return

    text = path.read_text()
    marker = "HansOS local: macOS host builds define ANDROID but do not provide malloc.h."
    if marker in text:
        print("gemmlowp Darwin malloc header already patched")
        return

    old = (
        "#if defined ANDROID || defined __ANDROID__\n"
        "#include <malloc.h>\n"
    )
    new = (
        f"// {marker}\n"
        "#if (defined ANDROID || defined __ANDROID__) && !defined(__APPLE__)\n"
        "#include <malloc.h>\n"
    )
    if old not in text:
        fail("could not find gemmlowp Android malloc.h guard")

    path.write_text(text.replace(old, new, 1))
    print("Patched gemmlowp malloc.h guard for Darwin host builds")


def patch_expresscatalog_codegen_int64_format(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/proto_logging/stats/express/expresscatalog-code-gen/codegen_java.cpp"
    if not path.exists():
        print("Skipping expresscatalog int64 format patch; codegen_java.cpp not present")
        return

    text = path.read_text()
    changed = False

    if '#include <inttypes.h>\n' not in text:
        anchor = '#include <expresscatalog-utils.h>\n'
        if anchor not in text:
            fail("could not find expresscatalog include insertion point")
        text = text.replace(anchor, anchor + '#include <inttypes.h>\n', 1)
        changed = True

    old = 'fprintf(fd, "    metricIds.put(\\"%s\\", new MetricInfo(%ldl, %s));\\n",'
    new = 'fprintf(fd, "    metricIds.put(\\"%s\\", new MetricInfo(%" PRId64 "l, %s));\\n",'
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif new in text:
        pass
    else:
        fail("could not find expresscatalog MetricInfo format string")

    if changed:
        path.write_text(text)
        print("Patched expresscatalog-codegen Java hash formatting for Darwin int64_t")
    else:
        print("expresscatalog-codegen Java hash formatting already patched")


def patch_f2fs_tools_darwin_lsetxattr(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/f2fs-tools/fsck/dump.c"
    if not path.exists():
        print("Skipping f2fs-tools Darwin xattr patch; dump.c not present")
        return

    text = path.read_text()
    old = (
        "#elif defined(__APPLE__)\n"
        "\t\tif (S_ISDIR(type)) {\n"
        "\t\t\tret = setxattr(\".\", xattr_name, value,\n"
        "\t\t\t\t\tle16_to_cpu(ent->e_value_size), 0,\n"
        "\t\t\t\t\tXATTR_CREATE);\n"
        "\t\t} if (S_ISLNK(type) && c.preserve_symlinks) {\n"
        "\t\t\tret = lsetxattr(c.dump_symlink, xattr_name, value,\n"
        "\t\t\t\t\tle16_to_cpu(ent->e_value_size), 0,\n"
        "\t\t\t\t\tXATTR_CREATE);\n"
        "\t\t} else {\n"
    )
    new = (
        "#elif defined(__APPLE__)\n"
        "\t\tif (S_ISDIR(type)) {\n"
        "\t\t\tret = setxattr(\".\", xattr_name, value,\n"
        "\t\t\t\t\tle16_to_cpu(ent->e_value_size), 0,\n"
        "\t\t\t\t\tXATTR_CREATE);\n"
        "\t\t} if (S_ISLNK(type) && c.preserve_symlinks) {\n"
        "\t\t\tret = setxattr(c.dump_symlink, xattr_name, value,\n"
        "\t\t\t\t\tle16_to_cpu(ent->e_value_size), 0,\n"
        "\t\t\t\t\tXATTR_CREATE | XATTR_NOFOLLOW);\n"
        "\t\t} else {\n"
    )

    if new in text:
        print("f2fs-tools Darwin symlink xattr handling already patched")
        return
    if old not in text:
        fail("could not find f2fs-tools Darwin lsetxattr block")

    path.write_text(text.replace(old, new, 1))
    print("Patched f2fs-tools Darwin symlink xattr handling")


def patch_erofs_utils_darwin_host_tools(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/erofs-utils/Android.bp"
    if not path.exists():
        print("Skipping erofs-utils Darwin host patch; Android.bp not present")
        return

    text = path.read_text()
    marker = "HansOS local: keep EROFS host tools available on Darwin for apexer tool dependencies."
    uapi_marker = "HansOS local: Darwin host EROFS tools need Linux UAPI compatibility headers."
    feature_marker = "HansOS local: Darwin uses native xattr APIs and lacks glibc memrchr."
    old_markers = [
        "HansOS local: build EROFS host tools on Darwin for Cuttlefish images.",
        "HansOS local: keep EROFS host tools disabled on Darwin; HansOS alpha uses ext4 images.",
    ]
    target_disabled_pattern = re.compile(
        r"\n\n\s*// HansOS local: [^\n]*EROFS host tools[^\n]*\n"
        r"\s*target:\s*\{\s*darwin:\s*\{\s*enabled:\s*false,\s*\},\s*\},",
        re.MULTILINE,
    )
    changed = False

    export_defaults_range = find_named_module_block(text, "cc_defaults", "erofs-utils_export_defaults")
    if export_defaults_range is None:
        fail("could not find erofs-utils_export_defaults in external/erofs-utils/Android.bp")

    start, end = export_defaults_range
    block = text[start:end]
    if feature_marker not in block:
        insertion = block.rfind("}")
        if insertion == -1:
            fail("could not find erofs-utils_export_defaults block end")
        darwin_feature_block = (
            "    target: {\n"
            "        darwin: {\n"
            f"            // {feature_marker}\n"
            "            cflags: [\n"
            '                "-UHAVE_LGETXATTR",\n'
            '                "-UHAVE_LLISTXATTR",\n'
            '                "-UHAVE_MEMRCHR",\n'
            "            ],\n"
            "        },\n"
            "    },\n"
        )
        replacement = block[:insertion] + darwin_feature_block + block[insertion:]
        text = text[:start] + replacement + text[end:]
        changed = True

    defaults_range = find_named_module_block(text, "cc_defaults", "erofs-utils_defaults")
    if defaults_range is None:
        fail("could not find erofs-utils_defaults in external/erofs-utils/Android.bp")

    start, end = defaults_range
    block = text[start:end]
    if uapi_marker not in block:
        host_anchor = "        host: {\n"
        if host_anchor not in block:
            fail("could not find erofs-utils_defaults host target block")
        darwin_uapi_block = (
            f"        // {uapi_marker}\n"
            "        darwin: {\n"
            "            include_dirs: [\n"
            '                "bionic/libc/kernel/android/uapi",\n'
            '                "bionic/libc/kernel/uapi",\n'
            '                "bionic/libc/kernel/uapi/asm-x86",\n'
            "            ],\n"
            "        },\n"
        )
        replacement = block.replace(host_anchor, darwin_uapi_block + host_anchor, 1)
        text = text[:start] + replacement + text[end:]
        changed = True

    for module_type, module_name in (
        ("cc_library", "liberofs"),
        ("cc_defaults", "mkfs-erofs_defaults"),
        ("cc_binary", "dump.erofs"),
        ("cc_binary", "fsck.erofs"),
    ):
        block_range = find_named_module_block(text, module_type, module_name)
        if block_range is None:
            fail(f"could not find {module_name} in external/erofs-utils/Android.bp")

        start, end = block_range
        block = text[start:end]
        if marker in block:
            continue

        replacement = target_disabled_pattern.sub("", block)
        for old_marker in old_markers:
            replacement = replacement.replace(f"\n\n    // {old_marker}", "")

        if replacement == block:
            print(f"{module_name} Darwin host variant already available")
            continue

        insertion = replacement.rfind("}")
        if insertion == -1:
            fail(f"could not find {module_name} block end for EROFS Darwin note")
        replacement = (
            replacement[:insertion]
            + f"    // {marker}\n"
            + replacement[insertion:]
        )

        text = text[:start] + replacement + text[end:]
        changed = True

    if changed:
        path.write_text(text)
        print("Patched erofs-utils to keep Darwin host tools available")
    else:
        print("erofs-utils Darwin host tools already available")


def patch_debuggerd_darwin_mte_signal_codes(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/debuggerd/libdebuggerd/tombstone_proto_to_text.cpp"
    if not path.exists():
        print("Skipping debuggerd Darwin MTE signal patch; tombstone_proto_to_text.cpp not present")
        return

    text = path.read_text()
    if "HansOS local: Darwin SDKs do not define Linux MTE SIGSEGV codes." in text:
        print("debuggerd Darwin MTE signal codes already patched")
        return

    anchor = "#include <signal.h>\n"
    if anchor not in text:
        fail("could not find debuggerd signal include insertion point")

    patch = (
        "#include <signal.h>\n"
        "\n"
        "// HansOS local: Darwin SDKs do not define Linux MTE SIGSEGV codes.\n"
        "#ifndef SEGV_MTEAERR\n"
        "#define SEGV_MTEAERR 8\n"
        "#endif\n"
        "#ifndef SEGV_MTESERR\n"
        "#define SEGV_MTESERR 9\n"
        "#endif\n"
    )
    path.write_text(text.replace(anchor, patch, 1))
    print("Patched debuggerd Darwin MTE signal code fallbacks")


def patch_debuggerd_darwin_prctl_header(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/debuggerd/libdebuggerd/utility_host.cpp"
    if not path.exists():
        print("Skipping debuggerd Darwin prctl patch; utility_host.cpp not present")
        return

    text = path.read_text()
    new = "#if defined(__linux__)\n#include <sys/prctl.h>\n#endif\n"
    if new in text:
        print("debuggerd Darwin prctl include already patched")
        return

    old = "#include <sys/prctl.h>\n"
    if old not in text:
        fail("could not find debuggerd prctl include")

    path.write_text(text.replace(old, new, 1))
    print("Patched debuggerd prctl include for Darwin host builds")


def patch_debuggerd_pbtombstone_corefoundation(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/debuggerd/Android.bp"
    if not path.exists():
        print("Skipping pbtombstone CoreFoundation patch; Android.bp not present")
        return

    text = path.read_text()
    marker = "HansOS local: Abseil cctz uses CoreFoundation on Darwin."
    if marker in text:
        print("pbtombstone already links CoreFoundation on Darwin")
        return

    old = (
        'cc_binary {\n'
        '    name: "pbtombstone",\n'
        '    host_supported: true,\n'
        '    defaults: ["debuggerd_defaults"],\n'
        '    srcs: [\n'
        '        "pbtombstone.cpp",\n'
        '        "tombstone_symbolize.cpp",\n'
        '    ],\n'
        '    static_libs: [\n'
        '        "libbase",\n'
        '        "libdebuggerd_tombstone_proto_to_text",\n'
        '        "liblog",\n'
        '        "libprotobuf-cpp-lite-notls-for-linker",\n'
        '        "libtombstone_proto",\n'
        '    ],\n'
        '}\n'
    )
    new = (
        'cc_binary {\n'
        '    name: "pbtombstone",\n'
        '    host_supported: true,\n'
        '    defaults: ["debuggerd_defaults"],\n'
        '    srcs: [\n'
        '        "pbtombstone.cpp",\n'
        '        "tombstone_symbolize.cpp",\n'
        '    ],\n'
        '    static_libs: [\n'
        '        "libbase",\n'
        '        "libdebuggerd_tombstone_proto_to_text",\n'
        '        "liblog",\n'
        '        "libprotobuf-cpp-lite-notls-for-linker",\n'
        '        "libtombstone_proto",\n'
        '    ],\n'
        '    target: {\n'
        '        darwin: {\n'
        f'            // {marker}\n'
        '            host_ldlibs: [\n'
        '                "-framework CoreFoundation",\n'
        '            ],\n'
        '        },\n'
        '    },\n'
        '}\n'
    )
    if old not in text:
        fail("could not find pbtombstone module for CoreFoundation patch")

    path.write_text(text.replace(old, new, 1))
    print("Patched pbtombstone to link CoreFoundation on Darwin")


def patch_cuttlefish_fs_darwin_inotify(aosp_root: pathlib.Path) -> None:
    header_path = aosp_root / "device/google/cuttlefish/common/libs/fs/shared_fd.h"
    source_path = aosp_root / "device/google/cuttlefish/common/libs/fs/shared_fd.cpp"
    if not header_path.exists() or not source_path.exists():
        print("Skipping Cuttlefish fs inotify patch; shared_fd sources not present")
        return

    header = header_path.read_text()
    original_header = header
    header = header.replace(
        "#ifdef __linux__\n"
        "#include <sys/epoll.h>\n"
        "#include <sys/eventfd.h>\n"
        "#endif\n"
        "#include <sys/inotify.h>\n",
        "#ifdef __linux__\n"
        "#include <sys/epoll.h>\n"
        "#include <sys/eventfd.h>\n"
        "#include <sys/inotify.h>\n"
        "#endif\n",
        1,
    )
    if "#include <cstdint>\n" not in header:
        header = header.replace("#include <chrono>\n", "#include <chrono>\n#include <cstdint>\n", 1)

    source = source_path.read_text()
    original_source = source
    source = source.replace(
        "SharedFD SharedFD::InotifyFd(void) {\n"
        "  errno = 0;\n"
        "  int fd = TEMP_FAILURE_RETRY(inotify_init1(IN_CLOEXEC));\n"
        "  return SharedFD(std::shared_ptr<FileInstance>(new FileInstance(fd, errno)));\n"
        "}\n",
        "SharedFD SharedFD::InotifyFd(void) {\n"
        "  errno = 0;\n"
        "#ifdef __linux__\n"
        "  int fd = TEMP_FAILURE_RETRY(inotify_init1(IN_CLOEXEC));\n"
        "  return SharedFD(std::shared_ptr<FileInstance>(new FileInstance(fd, errno)));\n"
        "#else\n"
        "  return SharedFD(std::shared_ptr<FileInstance>(new FileInstance(-1, ENOSYS)));\n"
        "#endif\n"
        "}\n",
        1,
    )
    source = source.replace(
        "// inotify related functions\n"
        "int FileInstance::InotifyAddWatch(const std::string& pathname, uint32_t mask) {\n"
        "  return inotify_add_watch(fd_, pathname.c_str(), mask);\n"
        "}\n"
        "\n"
        "void FileInstance::InotifyRmWatch(int watch) {\n"
        "  inotify_rm_watch(fd_, watch);\n"
        "}\n",
        "// inotify related functions\n"
        "int FileInstance::InotifyAddWatch(const std::string& pathname, uint32_t mask) {\n"
        "#ifdef __linux__\n"
        "  return inotify_add_watch(fd_, pathname.c_str(), mask);\n"
        "#else\n"
        "  (void)pathname;\n"
        "  (void)mask;\n"
        "  errno_ = ENOSYS;\n"
        "  errno = ENOSYS;\n"
        "  return -1;\n"
        "#endif\n"
        "}\n"
        "\n"
        "void FileInstance::InotifyRmWatch(int watch) {\n"
        "#ifdef __linux__\n"
        "  inotify_rm_watch(fd_, watch);\n"
        "#else\n"
        "  (void)watch;\n"
        "  errno_ = ENOSYS;\n"
        "  errno = ENOSYS;\n"
        "#endif\n"
        "}\n",
        1,
    )

    if header == original_header and source == original_source:
        print("Cuttlefish fs inotify Darwin stubs already patched")
        return

    if "#include <sys/inotify.h>\n#endif\n" not in header:
        fail("failed to guard Cuttlefish shared_fd.h inotify include")
    if "new FileInstance(-1, ENOSYS)" not in source:
        fail("failed to patch Cuttlefish shared_fd.cpp inotify stubs")

    header_path.write_text(header)
    source_path.write_text(source)
    print("Patched Cuttlefish fs with Darwin inotify stubs")


def patch_gatekeeper_darwin_endian(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/gatekeeper/gatekeeper.cpp"
    if not path.exists():
        print("Skipping gatekeeper Darwin endian patch; gatekeeper.cpp not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin does not provide Linux endian.h."
    if marker in text:
        print("gatekeeper Darwin endian handling already patched")
        return

    old = (
        "#ifdef _WIN32\n"
        "#include <winsock2.h>\n"
        "#define htobe32 htonl\n"
        "#define htobe64 htonll_gk\n"
        "#else\n"
        "#include <endian.h>\n"
        "#endif\n"
    )
    new = (
        "#ifdef _WIN32\n"
        "#include <winsock2.h>\n"
        "#define htobe32 htonl\n"
        "#define htobe64 htonll_gk\n"
        "#elif defined(__APPLE__)\n"
        f"// {marker}\n"
        "#include <libkern/OSByteOrder.h>\n"
        "#define htobe32 OSSwapHostToBigInt32\n"
        "#define htobe64 OSSwapHostToBigInt64\n"
        "#else\n"
        "#include <endian.h>\n"
        "#endif\n"
    )
    if old not in text:
        fail("could not find gatekeeper endian include block")

    path.write_text(text.replace(old, new, 1))
    print("Patched gatekeeper endian handling for Darwin")


def patch_cuttlefish_vm_manager_darwin_unused_helpers(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/libs/vm_manager/crosvm_builder.cpp"
    if not path.exists():
        print("Skipping Cuttlefish vm_manager helper patch; crosvm_builder.cpp not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin builds do not compile AddTap, so keep these helpers non-fatal."
    if marker in text:
        print("Cuttlefish vm_manager Darwin helper handling already patched")
        return

    old = (
        "namespace {\n"
        "\n"
        "std::string MacCrosvmArgument(std::optional<std::string_view> mac) {\n"
    )
    new = (
        "namespace {\n"
        "\n"
        f"// {marker}\n"
        "[[maybe_unused]] std::string MacCrosvmArgument(std::optional<std::string_view> mac) {\n"
    )
    if old not in text:
        fail("could not find MacCrosvmArgument declaration for Darwin unused-helper patch")

    text = text.replace(old, new, 1)
    text = text.replace(
        "std::string PciCrosvmArgument(std::optional<pci::Address> pci) {\n",
        "[[maybe_unused]] std::string PciCrosvmArgument(std::optional<pci::Address> pci) {\n",
        1,
    )
    path.write_text(text)
    print("Patched Cuttlefish vm_manager helpers for Darwin -Werror")


def patch_cuttlefish_vhost_user_block_signal_include(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/libs/vm_manager/vhost_user_block.cpp"
    if not path.exists():
        print("Skipping Cuttlefish vhost_user_block signal patch; source not present")
        return

    text = path.read_text()
    marker = "HansOS local: expose kill/SIGINT on Darwin host builds."
    if marker in text:
        print("Cuttlefish vhost_user_block signal include already patched")
        return

    anchor = "#include <sys/socket.h>\n"
    if anchor not in text:
        fail("could not find vhost_user_block system include insertion point")

    text = text.replace(anchor, f"#include <signal.h>  // {marker}\n" + anchor, 1)
    path.write_text(text)
    print("Patched Cuttlefish vhost_user_block signal include")


def patch_cuttlefish_graphics_flags_darwin_unused_args(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/commands/assemble_cvd/graphics_flags.cc"
    if not path.exists():
        print("Skipping Cuttlefish graphics flags Darwin patch; source not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin fallback GPU setup does not consume gfxstream-only flags."
    if marker in text:
        print("Cuttlefish graphics flags Darwin unused args already patched")
        return

    old = (
        "#ifdef __APPLE__\n"
        "  (void)graphics_availability;\n"
        "  (void)gpu_vhost_user_mode_arg;\n"
        "  (void)vmm;\n"
        "  (void)guest_config;\n"
    )
    new = (
        "#ifdef __APPLE__\n"
        f"  // {marker}\n"
        "  (void)gpu_renderer_features_arg;\n"
        "  (void)gpu_context_types_arg;\n"
        "  (void)guest_hwui_renderer_arg;\n"
        "  (void)guest_renderer_preload_arg;\n"
        "  (void)graphics_availability;\n"
        "  (void)gpu_vhost_user_mode_arg;\n"
        "  (void)vmm;\n"
        "  (void)guest_config;\n"
    )
    if old not in text:
        fail("could not find Cuttlefish graphics flags Darwin fallback block")

    path.write_text(text.replace(old, new, 1))
    print("Patched Cuttlefish graphics flags Darwin unused arguments")


def patch_grpc_darwin_exclude_binder_ndk(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/grpc-grpc/Android.bp"
    if not path.exists():
        print("Skipping gRPC Darwin binder patch; Android.bp not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin host gRPC tools do not link Android binder_ndk."
    ares_marker = "HansOS local: Darwin host gRPC uses native DNS; c-ares headers are not in AOSP."
    corefoundation_marker = "HansOS local: Abseil cctz pulls CoreFoundation into Darwin host gRPC."
    changed = False

    if ares_marker not in text:
        if '            cflags: ["-UANDROID"],\n' in text:
            text = text.replace(
                '            cflags: ["-UANDROID"],\n',
                f"            // {ares_marker}\n"
                '            cflags: ["-UANDROID", "-DGRPC_ARES=0"],\n',
                1,
            )
            changed = True
        elif '            cflags: ["-UANDROID", "-DGRPC_ARES=0"],\n' not in text:
            fail("could not find grpc_defaults Darwin cflags")

    if marker not in text:
        old = (
            '            cflags: ["-UANDROID", "-DGRPC_ARES=0"],\n'
            "        },\n"
        )
        new = (
            '            cflags: ["-UANDROID", "-DGRPC_ARES=0"],\n'
            f"            // {marker}\n"
            '            exclude_shared_libs: ["libbinder_ndk"],\n'
            "        },\n"
        )
        if old not in text:
            fail("could not find grpc_defaults Darwin target block")
        text = text.replace(old, new, 1)
        changed = True

    if corefoundation_marker not in text:
        old = (
            f"            // {marker}\n"
            '            exclude_shared_libs: ["libbinder_ndk"],\n'
        )
        new = (
            f"            // {marker}\n"
            '            exclude_shared_libs: ["libbinder_ndk"],\n'
            f"            // {corefoundation_marker}\n"
            '            host_ldlibs: ["-framework CoreFoundation"],\n'
        )
        if old not in text:
            fail("could not find grpc_defaults Darwin linker insertion point")
        text = text.replace(old, new, 1)
        changed = True

    if changed:
        path.write_text(text)
        print("Patched gRPC Darwin host defaults")
    else:
        print("gRPC Darwin host defaults already patched")


def patch_cuttlefish_openwrt_control_server_darwin(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/commands/openwrt_control_server/Android.bp"
    if not path.exists():
        print("Skipping Cuttlefish OpenWRT Darwin patch; Android.bp not present")
        return

    text = path.read_text()
    marker = "HansOS local: run_cvd is Darwin-enabled, so keep this dependency available."
    grpc_marker = "HansOS local: generated gRPC stubs must see Darwin host, not Android."
    changed = False

    for module_type, module_name in (
        ("cc_library", "libopenwrt_control_server"),
        ("cc_binary_host", "openwrt_control_server"),
    ):
        block_range = find_named_module_block(text, module_type, module_name)
        if block_range is None:
            fail(f"could not find {module_name} module for Cuttlefish OpenWRT Darwin patch")

        start, end = block_range
        block = text[start:end]
        if marker in block:
            continue
        if "darwin:" in block and "enabled: true" in block:
            continue

        insert_at = block.rfind("}")
        if insert_at == -1:
            fail(f"could not find {module_name} block end for Cuttlefish OpenWRT Darwin patch")

        target_patch = (
            "    target: {\n"
            "        darwin: {\n"
            f"            // {marker}\n"
            "            enabled: true,\n"
            f"            // {grpc_marker}\n"
            '            cflags: ["-UANDROID", "-DGRPC_ARES=0"],\n'
            "        },\n"
            "    },\n"
        )
        replacement = block[:insert_at] + target_patch + block[insert_at:]
        text = text[:start] + replacement + text[end:]
        changed = True

    for module_type, module_name in (
        ("cc_library", "libopenwrt_control_server"),
        ("cc_binary_host", "openwrt_control_server"),
    ):
        block_range = find_named_module_block(text, module_type, module_name)
        if block_range is None:
            fail(f"could not refind {module_name} module for Cuttlefish OpenWRT Darwin gRPC patch")

        start, end = block_range
        block = text[start:end]
        if grpc_marker in block:
            continue

        old = (
            f"            // {marker}\n"
            "            enabled: true,\n"
        )
        new = (
            f"            // {marker}\n"
            "            enabled: true,\n"
            f"            // {grpc_marker}\n"
            '            cflags: ["-UANDROID", "-DGRPC_ARES=0"],\n'
        )
        if old not in block:
            fail(f"could not find {module_name} Darwin target body for Cuttlefish OpenWRT gRPC patch")
        text = text[:start] + block.replace(old, new, 1) + text[end:]
        changed = True

    if changed:
        path.write_text(text)
        print("Patched Cuttlefish OpenWRT control modules for Darwin host builds")
    else:
        print("Cuttlefish OpenWRT control modules already have Darwin host variants")


def patch_cuttlefish_run_cvd_darwin_grpc_flags(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/commands/run_cvd/Android.bp"
    if not path.exists():
        print("Skipping run_cvd Darwin gRPC patch; Android.bp not present")
        return

    text = path.read_text()
    marker = "HansOS local: run_cvd includes gRPC headers on Darwin host builds."
    if marker in text:
        print("run_cvd Darwin gRPC flags already patched")
        return

    block_range = find_named_module_block(text, "cc_binary_host", "run_cvd")
    if block_range is None:
        fail("could not find run_cvd module for Darwin gRPC patch")

    start, end = block_range
    block = text[start:end]
    old = (
        "        darwin: {\n"
        "            enabled: true,\n"
        "        },\n"
    )
    new = (
        "        darwin: {\n"
        "            enabled: true,\n"
        f"            // {marker}\n"
        '            cflags: ["-UANDROID", "-DGRPC_ARES=0"],\n'
        "        },\n"
    )
    if old not in block:
        fail("could not find run_cvd Darwin target body for gRPC patch")

    text = text[:start] + block.replace(old, new, 1) + text[end:]
    path.write_text(text)
    print("Patched run_cvd Darwin gRPC flags")


def patch_cuttlefish_vhal_proxy_server_darwin_vsock(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/google/cuttlefish/host/commands/run_cvd/launch/vhal_proxy_server.cpp"
    if not path.exists():
        print("Skipping VHAL proxy Darwin vsock patch; source not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin host builds do not provide linux/vm_sockets.h."
    disable_marker = "HansOS local: VHAL proxy uses Linux vsock helpers, so skip it on Darwin."
    changed = False
    if marker in text:
        pass
    else:
        old = "#include <linux/vm_sockets.h>\n"
        new = (
            "#if defined(__linux__)\n"
            "#include <linux/vm_sockets.h>\n"
            "#else\n"
            f"// {marker}\n"
            "static constexpr int VMADDR_CID_HOST = 2;\n"
            "#endif\n"
        )
        if old not in text:
            fail("could not find VHAL proxy linux/vm_sockets.h include")
        text = text.replace(old, new, 1)
        changed = True

    if disable_marker not in text:
        old = (
            "std::optional<MonitorCommand> VhalProxyServer(\n"
            "    const CuttlefishConfig& config,\n"
            "    const CuttlefishConfig::InstanceSpecific& instance) {\n"
            "  if (!instance.start_vhal_proxy_server()) {\n"
        )
        new = (
            "std::optional<MonitorCommand> VhalProxyServer(\n"
            "    const CuttlefishConfig& config,\n"
            "    const CuttlefishConfig::InstanceSpecific& instance) {\n"
            "#if defined(__APPLE__)\n"
            f"  // {disable_marker}\n"
            "  (void)config;\n"
            "  (void)instance;\n"
            "  return {};\n"
            "#else\n"
            "  if (!instance.start_vhal_proxy_server()) {\n"
        )
        if old not in text:
            fail("could not find VHAL proxy function body insertion point")
        text = text.replace(old, new, 1)
        tail = "  return command;\n}\n"
        if tail not in text:
            fail("could not find VHAL proxy function return for Darwin guard")
        text = text.replace(tail, "  return command;\n#endif\n}\n", 1)
        changed = True

    if changed:
        path.write_text(text)
        print("Patched VHAL proxy Darwin vsock fallback")
    else:
        print("VHAL proxy Darwin vsock fallback already patched")


def patch_idmap2_corefoundation(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "frameworks/base/cmds/idmap2/Android.bp"
    if not path.exists():
        print("Skipping idmap2 CoreFoundation patch; Android.bp not present")
        return

    text = path.read_text()
    marker = "HansOS local: libprotobuf pulls Abseil cctz, which uses CoreFoundation on Darwin."
    if marker in text:
        print("idmap2 defaults already link CoreFoundation on Darwin")
        return

    old = (
        '        "-readability-uppercase-literal-suffix",\n'
        "    ],\n"
        "}\n"
    )
    new = (
        '        "-readability-uppercase-literal-suffix",\n'
        "    ],\n"
        "    target: {\n"
        "        darwin: {\n"
        f"            // {marker}\n"
        "            host_ldlibs: [\n"
        '                "-framework CoreFoundation",\n'
        "            ],\n"
        "        },\n"
        "    },\n"
        "}\n"
    )
    if old not in text:
        fail("could not find idmap2 defaults insertion point for CoreFoundation patch")

    path.write_text(text.replace(old, new, 1))
    print("Patched idmap2 defaults to link CoreFoundation on Darwin")


def patch_libvintf_darwin_stat_mtime(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/libvintf/FileSystem.cpp"
    if not path.exists():
        print("Skipping libvintf Darwin mtime patch; FileSystem.cpp not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin exposes nanosecond mtime as st_mtimespec."
    if marker in text:
        print("libvintf Darwin mtime handling already patched")
        return

    old = "    *mtime = stat_buf.st_mtim;\n"
    new = (
        "#if defined(__APPLE__)\n"
        f"    // {marker}\n"
        "    *mtime = stat_buf.st_mtimespec;\n"
        "#else\n"
        "    *mtime = stat_buf.st_mtim;\n"
        "#endif\n"
    )
    if old not in text:
        fail("could not find libvintf st_mtim assignment")

    path.write_text(text.replace(old, new, 1))
    print("Patched libvintf Darwin mtime handling")


def patch_init_host_tools_darwin_enabled(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/init/Android.bp"
    if not path.exists():
        print("Skipping init host Darwin patch; Android.bp not present")
        return

    text = path.read_text()
    marker = "HansOS local: Soong-only image assembly runs host_init_verifier on Darwin."
    if marker in text:
        print("init host tools already enabled on Darwin")
        return

    old = (
        "        darwin: {\n"
        "            enabled: false,\n"
        "        },\n"
    )
    new = (
        "        darwin: {\n"
        f"            // {marker}\n"
        "            enabled: true,\n"
        "        },\n"
    )

    block_range = find_named_module_block(text, "cc_defaults", "init_host_defaults")
    if block_range is None:
        fail("could not find init_host_defaults module")

    start, end = block_range
    block = text[start:end]
    if old not in block:
        fail("could not find init_host_defaults Darwin target block")

    path.write_text(text[:start] + block.replace(old, new, 1) + text[end:])
    print("Patched init host tools to enable Darwin host_init_verifier")


def patch_init_darwin_event_loop_shims(aosp_root: pathlib.Path) -> None:
    include_dir = aosp_root / "system/core/init/sys"
    include_dir.mkdir(parents=True, exist_ok=True)
    linux_include_dir = aosp_root / "system/core/init/linux"
    linux_include_dir.mkdir(parents=True, exist_ok=True)
    root_include_dir = aosp_root / "system/core/init"

    service_parser_path = aosp_root / "system/core/init/service_parser.cpp"
    service_utils_path = aosp_root / "system/core/init/service_utils.cpp"

    epoll_path = include_dir / "epoll.h"
    epoll_contents = (
        "/* HansOS local: Linux epoll shim for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <errno.h>\n"
        "#include <fcntl.h>\n"
        "#include <stdint.h>\n"
        "\n"
        "#ifndef EPOLLIN\n"
        "#define EPOLLIN 0x001\n"
        "#endif\n"
        "#ifndef EPOLLPRI\n"
        "#define EPOLLPRI 0x002\n"
        "#endif\n"
        "#ifndef EPOLLOUT\n"
        "#define EPOLLOUT 0x004\n"
        "#endif\n"
        "#ifndef EPOLLERR\n"
        "#define EPOLLERR 0x008\n"
        "#endif\n"
        "#ifndef EPOLLHUP\n"
        "#define EPOLLHUP 0x010\n"
        "#endif\n"
        "#ifndef EPOLL_CLOEXEC\n"
        "#define EPOLL_CLOEXEC O_CLOEXEC\n"
        "#endif\n"
        "#ifndef EPOLL_CTL_ADD\n"
        "#define EPOLL_CTL_ADD 1\n"
        "#endif\n"
        "#ifndef EPOLL_CTL_DEL\n"
        "#define EPOLL_CTL_DEL 2\n"
        "#endif\n"
        "#ifndef EPOLL_CTL_MOD\n"
        "#define EPOLL_CTL_MOD 3\n"
        "#endif\n"
        "\n"
        "typedef union epoll_data {\n"
        "    void* ptr;\n"
        "    int fd;\n"
        "    uint32_t u32;\n"
        "    uint64_t u64;\n"
        "} epoll_data_t;\n"
        "\n"
        "struct epoll_event {\n"
        "    uint32_t events;\n"
        "    epoll_data_t data;\n"
        "};\n"
        "\n"
        "static inline int epoll_create1(int flags) {\n"
        "    (void)flags;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "\n"
        "static inline int epoll_ctl(int epfd, int op, int fd, struct epoll_event* event) {\n"
        "    (void)epfd;\n"
        "    (void)op;\n"
        "    (void)fd;\n"
        "    (void)event;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "\n"
        "static inline int epoll_wait(int epfd, struct epoll_event* events, int maxevents,\n"
        "                             int timeout) {\n"
        "    (void)epfd;\n"
        "    (void)events;\n"
        "    (void)maxevents;\n"
        "    (void)timeout;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "#else\n"
        "#include_next <sys/epoll.h>\n"
        "#endif\n"
    )
    eventfd_path = include_dir / "eventfd.h"
    eventfd_contents = (
        "/* HansOS local: Linux eventfd shim for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <errno.h>\n"
        "#include <fcntl.h>\n"
        "#include <stdint.h>\n"
        "\n"
        "typedef uint64_t eventfd_t;\n"
        "#ifndef EFD_SEMAPHORE\n"
        "#define EFD_SEMAPHORE 1\n"
        "#endif\n"
        "#ifndef EFD_CLOEXEC\n"
        "#define EFD_CLOEXEC O_CLOEXEC\n"
        "#endif\n"
        "#ifndef EFD_NONBLOCK\n"
        "#define EFD_NONBLOCK O_NONBLOCK\n"
        "#endif\n"
        "\n"
        "static inline int eventfd(unsigned int initval, int flags) {\n"
        "    (void)initval;\n"
        "    (void)flags;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "#else\n"
        "#include_next <sys/eventfd.h>\n"
        "#endif\n"
    )
    socket_path = include_dir / "socket.h"
    socket_contents = (
        "/* HansOS local: Linux socket flags for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#include_next <sys/socket.h>\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#ifndef SOCK_CLOEXEC\n"
        "#define SOCK_CLOEXEC 0\n"
        "#endif\n"
        "#ifndef SOCK_NONBLOCK\n"
        "#define SOCK_NONBLOCK 0\n"
        "#endif\n"
        "#ifndef SO_PASSCRED\n"
        "#define SO_PASSCRED 0x1021\n"
        "#endif\n"
        "#ifndef SO_PEERCRED\n"
        "#define SO_PEERCRED 0x1022\n"
        "#endif\n"
        "#ifndef SCM_CREDENTIALS\n"
        "#define SCM_CREDENTIALS 0x02\n"
        "#endif\n"
        "\n"
        "static inline int accept4(int fd, struct sockaddr* addr, socklen_t* addrlen, int flags) {\n"
        "    (void)flags;\n"
        "    return accept(fd, addr, addrlen);\n"
        "}\n"
        "#endif\n"
    )
    signalfd_path = include_dir / "signalfd.h"
    signalfd_contents = (
        "/* HansOS local: Linux signalfd shim for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <errno.h>\n"
        "#include <fcntl.h>\n"
        "#include <signal.h>\n"
        "#include <stdint.h>\n"
        "\n"
        "#ifndef SFD_CLOEXEC\n"
        "#define SFD_CLOEXEC O_CLOEXEC\n"
        "#endif\n"
        "#ifndef SFD_NONBLOCK\n"
        "#define SFD_NONBLOCK O_NONBLOCK\n"
        "#endif\n"
        "\n"
        "typedef struct signalfd_siginfo {\n"
        "    uint32_t ssi_signo;\n"
        "    int32_t ssi_errno;\n"
        "    int32_t ssi_code;\n"
        "    uint32_t ssi_pid;\n"
        "    uint32_t ssi_uid;\n"
        "    int32_t ssi_fd;\n"
        "    uint32_t ssi_tid;\n"
        "    uint32_t ssi_band;\n"
        "    uint32_t ssi_overrun;\n"
        "    uint32_t ssi_trapno;\n"
        "    int32_t ssi_status;\n"
        "    int32_t ssi_int;\n"
        "    uint64_t ssi_ptr;\n"
        "    uint64_t ssi_utime;\n"
        "    uint64_t ssi_stime;\n"
        "    uint64_t ssi_addr;\n"
        "    uint8_t __pad[48];\n"
        "} signalfd_siginfo;\n"
        "\n"
        "static inline int signalfd(int fd, const sigset_t* mask, int flags) {\n"
        "    (void)fd;\n"
        "    (void)mask;\n"
        "    (void)flags;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "#else\n"
        "#include_next <sys/signalfd.h>\n"
        "#endif\n"
    )
    mount_path = include_dir / "mount.h"
    mount_contents = (
        "/* HansOS local: Linux mount API shim for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#include_next <sys/mount.h>\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <errno.h>\n"
        "\n"
        "#ifndef MS_RDONLY\n"
        "#define MS_RDONLY 1\n"
        "#endif\n"
        "#ifndef MS_NOSUID\n"
        "#define MS_NOSUID 2\n"
        "#endif\n"
        "#ifndef MS_NODEV\n"
        "#define MS_NODEV 4\n"
        "#endif\n"
        "#ifndef MS_NOEXEC\n"
        "#define MS_NOEXEC 8\n"
        "#endif\n"
        "#ifndef MS_SYNCHRONOUS\n"
        "#define MS_SYNCHRONOUS 16\n"
        "#endif\n"
        "#ifndef MS_REMOUNT\n"
        "#define MS_REMOUNT 32\n"
        "#endif\n"
        "#ifndef MS_BIND\n"
        "#define MS_BIND 4096\n"
        "#endif\n"
        "#ifndef MS_REC\n"
        "#define MS_REC 16384\n"
        "#endif\n"
        "#ifndef MS_SLAVE\n"
        "#define MS_SLAVE (1 << 19)\n"
        "#endif\n"
        "#ifndef MNT_DETACH\n"
        "#define MNT_DETACH 2\n"
        "#endif\n"
        "\n"
        "#if defined(__cplusplus)\n"
        "static inline int mount(const char* source, const char* target, const char* type,\n"
        "                        unsigned long flags, const void* data) {\n"
        "    (void)source;\n"
        "    (void)target;\n"
        "    (void)type;\n"
        "    (void)flags;\n"
        "    (void)data;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "\n"
        "static inline int umount(const char* target) {\n"
        "    (void)target;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "\n"
        "static inline int umount2(const char* target, int flags) {\n"
        "    (void)target;\n"
        "    (void)flags;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "#endif\n"
        "#endif\n"
    )
    sched_path = root_include_dir / "sched.h"
    sched_contents = (
        "/* HansOS local: Linux namespace flags for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#include_next <sched.h>\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <errno.h>\n"
        "\n"
        "#ifndef CLONE_NEWNS\n"
        "#define CLONE_NEWNS 0x00020000\n"
        "#endif\n"
        "#ifndef CLONE_NEWPID\n"
        "#define CLONE_NEWPID 0x20000000\n"
        "#endif\n"
        "#ifndef CLONE_NEWNET\n"
        "#define CLONE_NEWNET 0x40000000\n"
        "#endif\n"
        "\n"
        "static inline int clone(int (*fn)(void*), void* child_stack, int flags, void* arg, ...) {\n"
        "    (void)fn;\n"
        "    (void)child_stack;\n"
        "    (void)flags;\n"
        "    (void)arg;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "\n"
        "static inline int setns(int fd, int nstype) {\n"
        "    (void)fd;\n"
        "    (void)nstype;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "\n"
        "static inline int unshare(int flags) {\n"
        "    (void)flags;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "#endif\n"
    )
    inotify_path = include_dir / "inotify.h"
    inotify_contents = (
        "/* HansOS local: Linux inotify shim for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <errno.h>\n"
        "#include <fcntl.h>\n"
        "#include <stdint.h>\n"
        "\n"
        "struct inotify_event {\n"
        "    int wd;\n"
        "    uint32_t mask;\n"
        "    uint32_t cookie;\n"
        "    uint32_t len;\n"
        "    char name[];\n"
        "};\n"
        "\n"
        "#ifndef IN_CREATE\n"
        "#define IN_CREATE 0x00000100\n"
        "#endif\n"
        "#ifndef IN_DELETE\n"
        "#define IN_DELETE 0x00000200\n"
        "#endif\n"
        "#ifndef IN_ONLYDIR\n"
        "#define IN_ONLYDIR 0x01000000\n"
        "#endif\n"
        "#ifndef IN_CLOEXEC\n"
        "#define IN_CLOEXEC O_CLOEXEC\n"
        "#endif\n"
        "#ifndef IN_NONBLOCK\n"
        "#define IN_NONBLOCK O_NONBLOCK\n"
        "#endif\n"
        "\n"
        "static inline int inotify_init1(int flags) {\n"
        "    (void)flags;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "\n"
        "static inline int inotify_add_watch(int fd, const char* path, uint32_t mask) {\n"
        "    (void)fd;\n"
        "    (void)path;\n"
        "    (void)mask;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "#else\n"
        "#include_next <sys/inotify.h>\n"
        "#endif\n"
    )
    input_path = linux_include_dir / "input.h"
    input_contents = (
        "/* HansOS local: Linux input shim for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <stdint.h>\n"
        "#include <sys/time.h>\n"
        "\n"
        "#ifndef EV_SYN\n"
        "#define EV_SYN 0x00\n"
        "#endif\n"
        "#ifndef EV_KEY\n"
        "#define EV_KEY 0x01\n"
        "#endif\n"
        "#ifndef KEY_MAX\n"
        "#define KEY_MAX 0x2ff\n"
        "#endif\n"
        "\n"
        "struct input_event {\n"
        "    struct timeval time;\n"
        "    uint16_t type;\n"
        "    uint16_t code;\n"
        "    int32_t value;\n"
        "};\n"
        "\n"
        "#ifndef EVIOCGVERSION\n"
        "#define EVIOCGVERSION 0x80044501\n"
        "#endif\n"
        "#ifndef EVIOCGBIT\n"
        "#define EVIOCGBIT(ev, len) (0x80000000 | ((ev) << 8) | (len))\n"
        "#endif\n"
        "#ifndef EVIOCGKEY\n"
        "#define EVIOCGKEY(len) (0x80000000 | (len))\n"
        "#endif\n"
        "#else\n"
        "#include_next <linux/input.h>\n"
        "#endif\n"
    )
    resource_path = include_dir / "resource.h"
    resource_contents = (
        "/* HansOS local: Linux rlimit constants for Darwin host init verifier builds. */\n"
        "#pragma once\n"
        "\n"
        "#include_next <sys/resource.h>\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#ifndef RLIMIT_LOCKS\n"
        "#define RLIMIT_LOCKS 10\n"
        "#endif\n"
        "#ifndef RLIMIT_SIGPENDING\n"
        "#define RLIMIT_SIGPENDING 11\n"
        "#endif\n"
        "#ifndef RLIMIT_MSGQUEUE\n"
        "#define RLIMIT_MSGQUEUE 12\n"
        "#endif\n"
        "#ifndef RLIMIT_NICE\n"
        "#define RLIMIT_NICE 13\n"
        "#endif\n"
        "#ifndef RLIMIT_RTPRIO\n"
        "#define RLIMIT_RTPRIO 14\n"
        "#endif\n"
        "#ifndef RLIMIT_RTTIME\n"
        "#define RLIMIT_RTTIME 15\n"
        "#endif\n"
        "#ifndef RLIM_NLIMITS\n"
        "#define RLIM_NLIMITS 16\n"
        "#endif\n"
        "#endif\n"
    )

    changed = False
    if service_parser_path.exists():
        service_parser = service_parser_path.read_text()
        service_parser_anchor = "#include <linux/input.h>\n#include <stdlib.h>\n"
        service_parser_replacement = "#include <linux/input.h>\n#include <sched.h>\n#include <stdlib.h>\n"
        if service_parser_replacement not in service_parser:
            if service_parser_anchor not in service_parser:
                fail("could not find service_parser.cpp include insertion point")
            service_parser_path.write_text(
                service_parser.replace(service_parser_anchor, service_parser_replacement, 1)
            )
            changed = True

    if service_utils_path.exists():
        service_utils = service_utils_path.read_text()
        service_utils_anchor = "#include <grp.h>\n#include <sys/mount.h>\n"
        service_utils_replacement = "#include <grp.h>\n#include <sys/ioctl.h>\n#include <sys/mount.h>\n"
        if service_utils_replacement not in service_utils:
            if service_utils_anchor not in service_utils:
                fail("could not find service_utils.cpp include insertion point")
            service_utils_path.write_text(
                service_utils.replace(service_utils_anchor, service_utils_replacement, 1)
            )
            changed = True

    if not epoll_path.exists() or epoll_path.read_text() != epoll_contents:
        epoll_path.write_text(epoll_contents)
        changed = True
    if not eventfd_path.exists() or eventfd_path.read_text() != eventfd_contents:
        eventfd_path.write_text(eventfd_contents)
        changed = True
    if not socket_path.exists() or socket_path.read_text() != socket_contents:
        socket_path.write_text(socket_contents)
        changed = True
    if not signalfd_path.exists() or signalfd_path.read_text() != signalfd_contents:
        signalfd_path.write_text(signalfd_contents)
        changed = True
    if not mount_path.exists() or mount_path.read_text() != mount_contents:
        mount_path.write_text(mount_contents)
        changed = True
    if not sched_path.exists() or sched_path.read_text() != sched_contents:
        sched_path.write_text(sched_contents)
        changed = True
    if not inotify_path.exists() or inotify_path.read_text() != inotify_contents:
        inotify_path.write_text(inotify_contents)
        changed = True
    if not input_path.exists() or input_path.read_text() != input_contents:
        input_path.write_text(input_contents)
        changed = True
    if not resource_path.exists() or resource_path.read_text() != resource_contents:
        resource_path.write_text(resource_contents)
        changed = True

    if changed:
        print("Patched init Darwin event-loop/input shims")
    else:
        print("init Darwin event-loop/input shims already present")


def patch_init_darwin_host_logging(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/init/util.cpp"
    if not path.exists():
        print("Skipping init Darwin host logging patch; util.cpp not present")
        return

    text = path.read_text()
    marker = "HansOS local: KernelLogger is Linux-only in libbase host builds."
    if marker in text:
        print("init Darwin host logging already patched")
        return

    old_error_logging = (
        "        android::base::InitLogging(argv, &android::base::KernelLogger, InitAborter);\n"
        "        errno = saved_errno;\n"
    )
    new_error_logging = (
        "#if defined(__APPLE__)\n"
        f"        // {marker}\n"
        "        android::base::InitLogging(argv, &android::base::StderrLogger, InitAborter);\n"
        "#else\n"
        "        android::base::InitLogging(argv, &android::base::KernelLogger, InitAborter);\n"
        "#endif\n"
        "        errno = saved_errno;\n"
    )
    if old_error_logging not in text:
        fail("could not find SetStdioToDevNull KernelLogger call")
    text = text.replace(old_error_logging, new_error_logging, 1)

    old_init_logging = (
        "void InitKernelLogging(char** argv) {\n"
        "    SetFatalRebootTarget();\n"
        "    android::base::InitLogging(argv, &android::base::KernelLogger, InitAborter);\n"
        "}\n"
    )
    new_init_logging = (
        "void InitKernelLogging(char** argv) {\n"
        "    SetFatalRebootTarget();\n"
        "#if defined(__APPLE__)\n"
        "    android::base::InitLogging(argv, &android::base::StderrLogger, InitAborter);\n"
        "#else\n"
        "    android::base::InitLogging(argv, &android::base::KernelLogger, InitAborter);\n"
        "#endif\n"
        "}\n"
    )
    if old_init_logging not in text:
        fail("could not find InitKernelLogging KernelLogger call")
    path.write_text(text.replace(old_init_logging, new_init_logging, 1))
    print("Patched init Darwin host logging")


def patch_libbase_darwin_getuint_size_t(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/libbase/properties.cpp"
    if not path.exists():
        print("Skipping libbase Darwin size_t GetUintProperty patch; properties.cpp not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin size_t is distinct from uint64_t for GetUintProperty."
    if marker in text:
        print("libbase Darwin size_t GetUintProperty already patched")
        return

    anchor = "template uint64_t GetUintProperty(const std::string&, uint64_t, uint64_t);\n"
    patch = (
        anchor
        + "#if defined(__APPLE__)\n"
        + f"// {marker}\n"
        + "template size_t GetUintProperty(const std::string&, size_t, size_t);\n"
        + "#endif\n"
    )
    if anchor not in text:
        fail("could not find libbase GetUintProperty<uint64_t> instantiation")

    path.write_text(text.replace(anchor, patch, 1))
    print("Patched libbase Darwin size_t GetUintProperty instantiation")


def patch_libcap_darwin_stub(aosp_root: pathlib.Path) -> None:
    bp_path = aosp_root / "external/libcap/Android.bp"
    if not bp_path.exists():
        print("Skipping libcap Darwin stub patch; Android.bp not present")
        return

    stub_path = aosp_root / "external/libcap/libcap/darwin_stub.c"
    stub_contents = (
        "/* HansOS local: Darwin host stub for init host verification tools. */\n"
        "#include <errno.h>\n"
        "#include <stdlib.h>\n"
        "#include <string.h>\n"
        "#include <sys/capability.h>\n"
        "\n"
        "struct _cap_struct {\n"
        "    cap_flag_value_t flags[CAP_LAST_CAP + 1][3];\n"
        "};\n"
        "\n"
        "static int cap_index_valid(cap_value_t cap) {\n"
        "    return cap >= 0 && cap <= CAP_LAST_CAP;\n"
        "}\n"
        "\n"
        "cap_t cap_init(void) {\n"
        "    return (cap_t)calloc(1, sizeof(struct _cap_struct));\n"
        "}\n"
        "\n"
        "int cap_free(void *cap) {\n"
        "    free(cap);\n"
        "    return 0;\n"
        "}\n"
        "\n"
        "int cap_clear(cap_t cap) {\n"
        "    if (cap == NULL) {\n"
        "        errno = EINVAL;\n"
        "        return -1;\n"
        "    }\n"
        "    memset(cap, 0, sizeof(struct _cap_struct));\n"
        "    return 0;\n"
        "}\n"
        "\n"
        "int cap_clear_flag(cap_t cap, cap_flag_t flag) {\n"
        "    if (cap == NULL || flag < CAP_EFFECTIVE || flag > CAP_INHERITABLE) {\n"
        "        errno = EINVAL;\n"
        "        return -1;\n"
        "    }\n"
        "    for (cap_value_t value = 0; value <= CAP_LAST_CAP; value++) {\n"
        "        cap->flags[value][flag] = CAP_CLEAR;\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
        "\n"
        "int cap_get_flag(cap_t cap, cap_value_t value, cap_flag_t flag, cap_flag_value_t *out) {\n"
        "    if (cap == NULL || out == NULL || !cap_index_valid(value) ||\n"
        "        flag < CAP_EFFECTIVE || flag > CAP_INHERITABLE) {\n"
        "        errno = EINVAL;\n"
        "        return -1;\n"
        "    }\n"
        "    *out = cap->flags[value][flag];\n"
        "    return 0;\n"
        "}\n"
        "\n"
        "int cap_set_flag(cap_t cap, cap_flag_t flag, int ncap, const cap_value_t *values,\n"
        "                 cap_flag_value_t state) {\n"
        "    if (cap == NULL || values == NULL || flag < CAP_EFFECTIVE || flag > CAP_INHERITABLE) {\n"
        "        errno = EINVAL;\n"
        "        return -1;\n"
        "    }\n"
        "    for (int i = 0; i < ncap; i++) {\n"
        "        if (!cap_index_valid(values[i])) {\n"
        "            errno = EINVAL;\n"
        "            return -1;\n"
        "        }\n"
        "        cap->flags[values[i]][flag] = state;\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
        "\n"
        "cap_t cap_get_proc(void) { return cap_init(); }\n"
        "cap_t cap_get_pid(pid_t pid) { (void)pid; return cap_init(); }\n"
        "int cap_set_proc(cap_t cap) { (void)cap; return 0; }\n"
        "int cap_get_bound(cap_value_t value) { return cap_index_valid(value) ? 0 : -1; }\n"
        "int cap_drop_bound(cap_value_t value) { return cap_index_valid(value) ? 0 : -1; }\n"
        "int cap_get_ambient(cap_value_t value) { (void)value; errno = ENOSYS; return -1; }\n"
        "int cap_set_ambient(cap_value_t value, cap_flag_value_t state) {\n"
        "    (void)value;\n"
        "    (void)state;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "int cap_reset_ambient(void) { return 0; }\n"
        "cap_value_t cap_max_bits(void) { return CAP_LAST_CAP + 1; }\n"
        "cap_t cap_dup(cap_t cap) { (void)cap; return cap_init(); }\n"
        "cap_t cap_get_fd(int fd) { (void)fd; errno = ENOSYS; return NULL; }\n"
        "cap_t cap_get_file(const char *path) { (void)path; errno = ENOSYS; return NULL; }\n"
        "uid_t cap_get_nsowner(cap_t cap) { (void)cap; return 0; }\n"
        "int cap_set_fd(int fd, cap_t cap) { (void)fd; (void)cap; return 0; }\n"
        "int cap_set_file(const char *path, cap_t cap) { (void)path; (void)cap; return 0; }\n"
        "int cap_set_nsowner(cap_t cap, uid_t uid) { (void)cap; (void)uid; return 0; }\n"
        "char *cap_to_text(cap_t cap, ssize_t *length) {\n"
        "    (void)cap;\n"
        "    if (length != NULL) *length = 0;\n"
        "    return strdup(\"\");\n"
        "}\n"
        "cap_t cap_from_text(const char *text) { (void)text; return cap_init(); }\n"
        "int cap_from_name(const char *name, cap_value_t *value) {\n"
        "    (void)name;\n"
        "    if (value != NULL) *value = 0;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "char *cap_to_name(cap_value_t value) { (void)value; return NULL; }\n"
        "void cap_set_syscall(long int (*new_syscall)(long int, long int, long int, long int),\n"
        "                     long int (*new_syscall6)(long int, long int, long int, long int,\n"
        "                                                long int, long int, long int)) {\n"
        "    (void)new_syscall;\n"
        "    (void)new_syscall6;\n"
        "}\n"
        "int cap_prctl(long int cmd, long int a1, long int a2, long int a3, long int a4,\n"
        "              long int a5) {\n"
        "    (void)cmd; (void)a1; (void)a2; (void)a3; (void)a4; (void)a5;\n"
        "    errno = ENOSYS;\n"
        "    return -1;\n"
        "}\n"
        "int cap_prctlw(long int cmd, long int a1, long int a2, long int a3, long int a4,\n"
        "               long int a5) {\n"
        "    return cap_prctl(cmd, a1, a2, a3, a4, a5);\n"
        "}\n"
        "int capget(cap_user_header_t header, cap_user_data_t data) {\n"
        "    (void)header; (void)data; errno = ENOSYS; return -1;\n"
        "}\n"
        "int capset(cap_user_header_t header, const cap_user_data_t data) {\n"
        "    (void)header; (void)data; errno = ENOSYS; return -1;\n"
        "}\n"
    )
    if not stub_path.exists() or stub_path.read_text() != stub_contents:
        stub_path.write_text(stub_contents)
        print("Patched libcap Darwin stub source")

    prctl_path = aosp_root / "external/libcap/libcap/include/sys/prctl.h"
    prctl_contents = (
        "/* HansOS local: expose Linux prctl constants for Darwin host init tools. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#ifndef PR_SET_NAME\n"
        "#define PR_SET_NAME 15\n"
        "#endif\n"
        "#ifndef PR_CAPBSET_READ\n"
        "#define PR_CAPBSET_READ 23\n"
        "#endif\n"
        "#ifndef PR_GET_SECUREBITS\n"
        "#define PR_GET_SECUREBITS 27\n"
        "#endif\n"
        "#ifndef PR_SET_SECUREBITS\n"
        "#define PR_SET_SECUREBITS 28\n"
        "#endif\n"
        "#ifndef PR_CAP_AMBIENT\n"
        "#define PR_CAP_AMBIENT 47\n"
        "#endif\n"
        "#ifndef PR_CAP_AMBIENT_IS_SET\n"
        "#define PR_CAP_AMBIENT_IS_SET 1\n"
        "#endif\n"
        "#ifndef PR_CAP_AMBIENT_RAISE\n"
        "#define PR_CAP_AMBIENT_RAISE 2\n"
        "#endif\n"
        "#ifndef PR_CAP_AMBIENT_LOWER\n"
        "#define PR_CAP_AMBIENT_LOWER 3\n"
        "#endif\n"
        "#ifndef PR_CAP_AMBIENT_CLEAR_ALL\n"
        "#define PR_CAP_AMBIENT_CLEAR_ALL 4\n"
        "#endif\n"
        "static inline int prctl(int, ...) {\n"
        "    return -1;\n"
        "}\n"
        "#else\n"
        "#include_next <sys/prctl.h>\n"
        "#endif\n"
    )
    if not prctl_path.exists() or prctl_path.read_text() != prctl_contents:
        prctl_path.write_text(prctl_contents)
        print("Patched libcap Darwin sys/prctl.h shim")

    text = bp_path.read_text()
    marker = "HansOS local: Darwin host tools only need libcap symbols and constants."
    changed = False

    old_export = '    export_include_dirs: ["libcap/include"],\n'
    new_export = '    export_include_dirs: ["libcap/include", "libcap/include/uapi"],\n'
    if new_export not in text:
        if old_export not in text:
            fail("could not find libcap export_include_dirs")
        text = text.replace(old_export, new_export, 1)
        changed = True

    if marker not in text:
        old = (
            "        darwin: {\n"
            "            enabled: false,\n"
            "        },\n"
        )
        new = (
            "        darwin: {\n"
            f"            // {marker}\n"
            "            enabled: true,\n"
            "            srcs: [\"libcap/darwin_stub.c\"],\n"
            "            exclude_srcs: [\n"
            "                \"libcap/cap_alloc.c\",\n"
            "                \"libcap/cap_extint.c\",\n"
            "                \"libcap/cap_file.c\",\n"
            "                \"libcap/cap_flag.c\",\n"
            "                \"libcap/cap_proc.c\",\n"
            "                \"libcap/cap_text.c\",\n"
            "            ],\n"
            "            local_include_dirs: [\"libcap/include/uapi\"],\n"
            "        },\n"
        )
        block_range = find_named_module_block(text, "cc_library", "libcap")
        if block_range is None:
            fail("could not find libcap module")
        start, end = block_range
        block = text[start:end]
        if old not in block:
            fail("could not find libcap Darwin target block")
        text = text[:start] + block.replace(old, new, 1) + text[end:]
        changed = True

    if changed:
        bp_path.write_text(text)
        print("Patched libcap Darwin host stub module")
    else:
        print("libcap Darwin host stub already patched")


def patch_libfstab_darwin_host(aosp_root: pathlib.Path) -> None:
    bp_path = aosp_root / "system/core/fs_mgr/libfstab/Android.bp"
    header_path = aosp_root / "system/core/fs_mgr/libfstab/include/fstab/fstab.h"
    source_path = aosp_root / "system/core/fs_mgr/libfstab/fstab.cpp"
    if not bp_path.exists():
        print("Skipping libfstab Darwin patch; Android.bp not present")
        return

    text = bp_path.read_text()
    marker = "HansOS local: host_init_verifier needs libfstab on Darwin."
    if marker not in text:
        old = (
            "        darwin: {\n"
            "            enabled: false,\n"
            "        },\n"
        )
        new = (
            "        darwin: {\n"
            f"            // {marker}\n"
            "            enabled: true,\n"
            "        },\n"
        )
        block_range = find_named_module_block(text, "cc_library_static", "libfstab")
        if block_range is None:
            fail("could not find libfstab module")
        start, end = block_range
        block = text[start:end]
        if old not in block:
            fail("could not find libfstab Darwin target block")
        bp_path.write_text(text[:start] + block.replace(old, new, 1) + text[end:])
        print("Patched libfstab Darwin host module")
    else:
        print("libfstab Darwin host module already patched")

    if header_path.exists():
        header_text = header_path.read_text()
        header_marker = "HansOS local: Darwin host builds use off_t for off64_t."
        if header_marker not in header_text:
            anchor = "#include <sys/types.h>\n"
            patch = (
                "#include <sys/types.h>\n"
                "\n"
                "#if defined(__APPLE__)\n"
                f"// {header_marker}\n"
                "#include <android-base/off64_t.h>\n"
                "#endif\n"
            )
            if anchor not in header_text:
                fail("could not find libfstab fstab.h sys/types include")
            header_path.write_text(header_text.replace(anchor, patch, 1))
            print("Patched libfstab Darwin off64_t include")
        else:
            print("libfstab Darwin off64_t include already patched")

    if source_path.exists():
        source_text = source_path.read_text()
        source_marker = "HansOS local: provide Linux mount flag constants for Darwin host parsing."
        anchor = "#include <sys/mount.h>\n"
        compat_block = (
            "#if defined(__APPLE__)\n"
            f"// {source_marker}\n"
            "#ifndef MS_RDONLY\n"
            "#define MS_RDONLY 1\n"
            "#endif\n"
            "#ifndef MS_NOSUID\n"
            "#define MS_NOSUID 2\n"
            "#endif\n"
            "#ifndef MS_NODEV\n"
            "#define MS_NODEV 4\n"
            "#endif\n"
            "#ifndef MS_NOEXEC\n"
            "#define MS_NOEXEC 8\n"
            "#endif\n"
            "#ifndef MS_SYNCHRONOUS\n"
            "#define MS_SYNCHRONOUS 16\n"
            "#endif\n"
            "#ifndef MS_REMOUNT\n"
            "#define MS_REMOUNT 32\n"
            "#endif\n"
            "#ifndef MS_NOATIME\n"
            "#define MS_NOATIME 1024\n"
            "#endif\n"
            "#ifndef MS_NODIRATIME\n"
            "#define MS_NODIRATIME 2048\n"
            "#endif\n"
            "#ifndef MS_BIND\n"
            "#define MS_BIND 4096\n"
            "#endif\n"
            "#ifndef MS_REC\n"
            "#define MS_REC 16384\n"
            "#endif\n"
            "#ifndef MS_UNBINDABLE\n"
            "#define MS_UNBINDABLE (1 << 17)\n"
            "#endif\n"
            "#ifndef MS_PRIVATE\n"
            "#define MS_PRIVATE (1 << 18)\n"
            "#endif\n"
            "#ifndef MS_SLAVE\n"
            "#define MS_SLAVE (1 << 19)\n"
            "#endif\n"
            "#ifndef MS_SHARED\n"
            "#define MS_SHARED (1 << 20)\n"
            "#endif\n"
            "#ifndef MS_LAZYTIME\n"
            "#define MS_LAZYTIME (1 << 25)\n"
            "#endif\n"
            "#ifndef MS_NOSYMFOLLOW\n"
            "#define MS_NOSYMFOLLOW 256\n"
            "#endif\n"
            "#endif\n"
        )
        patch = anchor + "\n" + compat_block
        if source_marker in source_text:
            start = source_text.find("#if defined(__APPLE__)\n", source_text.find(anchor))
            marker_pos = source_text.find(source_marker, start)
            end = source_text.find("#endif\n", marker_pos)
            while end != -1 and source_text.find("#if", start, end) != -1:
                next_end = source_text.find("#endif\n", end + len("#endif\n"))
                if next_end == -1:
                    break
                end = next_end
                candidate = source_text[start:end + len("#endif\n")]
                if candidate.count("#if") == candidate.count("#endif"):
                    break
            if start == -1 or marker_pos == -1 or end == -1:
                fail("could not find existing libfstab Darwin mount constants block")
            old_block = source_text[start:end + len("#endif\n")]
            if old_block != compat_block:
                source_path.write_text(source_text[:start] + compat_block + source_text[end + len("#endif\n"):])
                print("Updated libfstab Darwin mount constants")
            else:
                print("libfstab Darwin mount constants already patched")
        else:
            if anchor not in source_text:
                fail("could not find libfstab fstab.cpp sys/mount include")
            source_path.write_text(source_text.replace(anchor, patch, 1))
            print("Patched libfstab Darwin mount constants")


def patch_libprocessgroup_util_darwin_mntent(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/libprocessgroup/util/util.cpp"
    if not path.exists():
        print("Skipping libprocessgroup util Darwin patch; util.cpp not present")
        return

    text = path.read_text()
    marker = "HansOS local: macOS hosts do not provide mntent.h or /proc/mounts."
    changed = False

    if marker not in text:
        old_include = "#include <mntent.h>\n"
        new_include = (
            "#if !defined(__APPLE__)\n"
            "#include <mntent.h>\n"
            "#endif\n"
        )
        if old_include not in text:
            fail("could not find libprocessgroup mntent include")
        text = text.replace(old_include, new_include, 1)
        changed = True

    old_body = (
        "static std::optional<std::map<MountDir, MountOpts>> ReadCgroupV1Mounts() {\n"
        "    FILE* fp = setmntent(\"/proc/mounts\", \"r\");\n"
        "    if (fp == nullptr) {\n"
        "        PLOG(ERROR) << \"Failed to read mounts\";\n"
        "        return std::nullopt;\n"
        "    }\n"
        "\n"
        "    std::map<MountDir, MountOpts> mounts;\n"
        "    const std::string_view CGROUP_V1_TYPE = \"cgroup\";\n"
        "    for (mntent* mentry = getmntent(fp); mentry != nullptr; mentry = getmntent(fp)) {\n"
        "        if (mentry->mnt_type && CGROUP_V1_TYPE == mentry->mnt_type &&\n"
        "            mentry->mnt_dir && mentry->mnt_opts) {\n"
        "            mounts[mentry->mnt_dir] = mentry->mnt_opts;\n"
        "        }\n"
        "    }\n"
        "    endmntent(fp);\n"
        "\n"
        "    return mounts;\n"
        "}\n"
    )
    new_body = (
        "static std::optional<std::map<MountDir, MountOpts>> ReadCgroupV1Mounts() {\n"
        "#if defined(__APPLE__)\n"
        f"    // {marker}\n"
        "    return std::map<MountDir, MountOpts>{};\n"
        "#else\n"
        "    FILE* fp = setmntent(\"/proc/mounts\", \"r\");\n"
        "    if (fp == nullptr) {\n"
        "        PLOG(ERROR) << \"Failed to read mounts\";\n"
        "        return std::nullopt;\n"
        "    }\n"
        "\n"
        "    std::map<MountDir, MountOpts> mounts;\n"
        "    const std::string_view CGROUP_V1_TYPE = \"cgroup\";\n"
        "    for (mntent* mentry = getmntent(fp); mentry != nullptr; mentry = getmntent(fp)) {\n"
        "        if (mentry->mnt_type && CGROUP_V1_TYPE == mentry->mnt_type &&\n"
        "            mentry->mnt_dir && mentry->mnt_opts) {\n"
        "            mounts[mentry->mnt_dir] = mentry->mnt_opts;\n"
        "        }\n"
        "    }\n"
        "    endmntent(fp);\n"
        "\n"
        "    return mounts;\n"
        "#endif\n"
        "}\n"
    )
    if marker not in text:
        if old_body not in text:
            fail("could not find libprocessgroup ReadCgroupV1Mounts body")
        text = text.replace(old_body, new_body, 1)
        changed = True

    if changed:
        path.write_text(text)
        print("Patched libprocessgroup util Darwin mntent fallback")
    else:
        print("libprocessgroup util Darwin mntent fallback already patched")


def patch_libprocessgroup_task_profiles_darwin_sched(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/libprocessgroup/task_profiles.cpp"
    if not path.exists():
        print("Skipping libprocessgroup task_profiles Darwin patch; file not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin host tools do not apply Linux scheduler policies."
    if marker in text:
        print("libprocessgroup task_profiles Darwin scheduler fallback already patched")
        return

    anchor = "#include <unistd.h>\n"
    patch = (
        "#include <unistd.h>\n"
        "\n"
        "#if defined(__APPLE__)\n"
        f"// {marker}\n"
        "#ifndef SCHED_BATCH\n"
        "#define SCHED_BATCH SCHED_OTHER\n"
        "#endif\n"
        "#ifndef SCHED_IDLE\n"
        "#define SCHED_IDLE SCHED_OTHER\n"
        "#endif\n"
        "static inline int sched_setscheduler(pid_t, int, const struct sched_param*) {\n"
        "    return 0;\n"
        "}\n"
        "#endif\n"
    )
    if anchor not in text:
        fail("could not find task_profiles Darwin scheduler insertion point")

    path.write_text(text.replace(anchor, patch, 1))
    print("Patched libprocessgroup task_profiles Darwin scheduler fallback")


def patch_selinux_darwin_strlcpy(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/libselinux/src/selinux_internal.h"
    if not path.exists():
        print("Skipping libselinux Darwin strlcpy patch; selinux_internal.h not present")
        return

    text = path.read_text()
    if "HansOS local: macOS provides strlcpy" in text:
        print("libselinux Darwin strlcpy handling already patched")
        return

    anchor = "#include <stdio.h>\n"
    if anchor not in text:
        fail("could not find libselinux include insertion point")

    patch = (
        "#include <stdio.h>\n"
        "\n"
        "/* HansOS local: macOS provides strlcpy, and its fortified macro breaks redeclaration. */\n"
        "#if defined(__APPLE__) && !defined(HAVE_STRLCPY)\n"
        "#define HAVE_STRLCPY 1\n"
        "#endif\n"
    )
    path.write_text(text.replace(anchor, patch, 1))
    print("Patched libselinux Darwin strlcpy handling")


def patch_selinux_darwin_xattr_compat(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/libselinux/src/selinux_internal.h"
    if not path.exists():
        print("Skipping libselinux Darwin xattr patch; selinux_internal.h not present")
        return

    text = path.read_text()
    marker = "/* HansOS local: adapt Linux xattr calls to Darwin signatures. */"

    anchor = (
        "/* HansOS local: macOS provides strlcpy, and its fortified macro breaks redeclaration. */\n"
        "#if defined(__APPLE__) && !defined(HAVE_STRLCPY)\n"
        "#define HAVE_STRLCPY 1\n"
        "#endif\n"
    )
    patch = (
        anchor +
        "\n"
        "/* HansOS local: adapt Linux xattr calls to Darwin signatures. */\n"
        "#if defined(__APPLE__)\n"
        "#include <sys/xattr.h>\n"
        "#ifndef O_PATH\n"
        "#define O_PATH 0\n"
        "#endif\n"
        "#define getxattr(path, name, value, size) (getxattr)((path), (name), (value), (size), 0, 0)\n"
        "#define fgetxattr(fd, name, value, size) (fgetxattr)((fd), (name), (value), (size), 0, 0)\n"
        "#define lgetxattr(path, name, value, size) (getxattr)((path), (name), (value), (size), 0, XATTR_NOFOLLOW)\n"
        "#define setxattr(path, name, value, size, flags) (setxattr)((path), (name), (value), (size), 0, (flags))\n"
        "#define fsetxattr(fd, name, value, size, flags) (fsetxattr)((fd), (name), (value), (size), 0, (flags))\n"
        "#define lsetxattr(path, name, value, size, flags) (setxattr)((path), (name), (value), (size), 0, (flags) | XATTR_NOFOLLOW)\n"
        "#endif\n"
    )

    xattr_block = patch[len(anchor) + 1:].rstrip() + "\n\n"
    if marker in text:
        start = text.find(marker)
        end_marker = "\n\nextern int require_seusers ;"
        end = text.find(end_marker, start)
        if end == -1:
            fail("could not find end of libselinux xattr compatibility section")
        if text[start:end + 2] == xattr_block:
            print("libselinux Darwin xattr compatibility already patched")
            return
        path.write_text(text[:start] + xattr_block + text[end + 2:])
        print("Updated libselinux Darwin xattr compatibility")
        return

    if anchor not in text:
        fail("could not find libselinux strlcpy block for xattr patch")

    path.write_text(text.replace(anchor, patch, 1))
    print("Patched libselinux Darwin xattr compatibility")


def patch_selinux_darwin_pthread_once(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/libselinux/src/selinux_internal.h"
    if not path.exists():
        print("Skipping libselinux Darwin pthread_once patch; selinux_internal.h not present")
        return

    text = path.read_text()
    if "HansOS local: macOS pthread_once_t cannot be compared to PTHREAD_ONCE_INIT." in text:
        print("libselinux Darwin pthread_once handling already patched")
        return

    new = (
        "/* Call handler iff the first call.  */\n"
        "#if defined(__APPLE__)\n"
        "/* HansOS local: macOS pthread_once_t cannot be compared to PTHREAD_ONCE_INIT. */\n"
        "#define __selinux_once(ONCE_CONTROL, INIT_FUNCTION)\t\\\n"
        "\tdo {\t\t\t\t\t\t\\\n"
        "\t\tpthread_once(&(ONCE_CONTROL), (INIT_FUNCTION));\t\\\n"
        "\t} while (0)\n"
        "#else\n"
        "#define __selinux_once(ONCE_CONTROL, INIT_FUNCTION)\t\\\n"
        "\tdo {\t\t\t\t\t\t\\\n"
        "\t\tif (pthread_once != NULL)\t\t\\\n"
        "\t\t\tpthread_once (&(ONCE_CONTROL), (INIT_FUNCTION));  \\\n"
        "\t\telse if ((ONCE_CONTROL) == PTHREAD_ONCE_INIT) {\t\t  \\\n"
        "\t\t\tINIT_FUNCTION ();\t\t\\\n"
        "\t\t\t(ONCE_CONTROL) = 2;\t\t\t\\\n"
        "\t\t}\t\t\t\t\t\\\n"
        "\t} while (0)\n"
        "#endif\n"
    )
    start = text.find("/* Call handler iff the first call.  */\n#define __selinux_once")
    end_marker = "\n\n/* Pthread key macros */"
    end = text.find(end_marker, start)
    if start == -1 or end == -1:
        fail("could not find libselinux pthread_once macro")

    path.write_text(text[:start] + new + text[end:])
    print("Patched libselinux Darwin pthread_once handling")


def patch_selinux_darwin_sockaddr_storage_shim(aosp_root: pathlib.Path) -> None:
    include_dir = aosp_root / "external/selinux/libselinux/include/bits"
    path = include_dir / "sockaddr_storage.h"
    contents = (
        "/* HansOS local: satisfy Bionic UAPI <linux/socket.h> on Darwin host builds. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <sys/socket.h>\n"
        "#else\n"
        "#include_next <bits/sockaddr_storage.h>\n"
        "#endif\n"
    )

    if path.exists() and path.read_text() == contents:
        print("libselinux Darwin sockaddr_storage shim already present")
        return

    include_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    print("Patched libselinux Darwin sockaddr_storage shim")


def patch_selinux_darwin_stdio_ext_shim(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/libselinux/include/stdio_ext.h"
    contents = (
        "/* HansOS local: provide glibc stdio_ext APIs for Darwin host builds. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <stdio.h>\n"
        "#ifndef FSETLOCKING_BYCALLER\n"
        "#define FSETLOCKING_BYCALLER 0\n"
        "#endif\n"
        "static inline int __fsetlocking(FILE *stream, int type) {\n"
        "    (void)stream;\n"
        "    (void)type;\n"
        "    return 0;\n"
        "}\n"
        "#else\n"
        "#include_next <stdio_ext.h>\n"
        "#endif\n"
    )

    if path.exists() and path.read_text() == contents:
        print("libselinux Darwin stdio_ext shim already present")
        return

    path.write_text(contents)
    print("Patched libselinux Darwin stdio_ext shim")


def patch_selinux_darwin_sys_vfs_shim(aosp_root: pathlib.Path) -> None:
    include_dir = aosp_root / "external/selinux/libselinux/include/sys"
    path = include_dir / "vfs.h"
    contents = (
        "/* HansOS local: map Linux sys/vfs.h to Darwin sys/mount.h for host builds. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <sys/mount.h>\n"
        "#else\n"
        "#include_next <sys/vfs.h>\n"
        "#endif\n"
    )

    if path.exists() and path.read_text() == contents:
        print("libselinux Darwin sys/vfs shim already present")
        return

    include_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    print("Patched libselinux Darwin sys/vfs shim")


def patch_selinux_darwin_netlink_constants(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/libselinux/src/avc_internal.c"
    if not path.exists():
        print("Skipping libselinux Darwin netlink constants patch; avc_internal.c not present")
        return

    text = path.read_text()
    if "HansOS local: Darwin does not provide Linux netlink constants." in text:
        print("libselinux Darwin netlink constants already patched")
        return

    anchor = (
        "#ifndef NETLINK_SELINUX\n"
        "#define NETLINK_SELINUX 7\n"
        "#endif\n"
    )
    patch = (
        "#ifndef NETLINK_SELINUX\n"
        "#define NETLINK_SELINUX 7\n"
        "#endif\n"
        "\n"
        "/* HansOS local: Darwin does not provide Linux netlink constants. */\n"
        "#if defined(__APPLE__)\n"
        "#ifndef PF_NETLINK\n"
        "#define PF_NETLINK 16\n"
        "#endif\n"
        "#ifndef AF_NETLINK\n"
        "#define AF_NETLINK PF_NETLINK\n"
        "#endif\n"
        "#ifndef SOCK_CLOEXEC\n"
        "#define SOCK_CLOEXEC 0\n"
        "#endif\n"
        "#ifndef EBADFD\n"
        "#define EBADFD EBADF\n"
        "#endif\n"
        "#endif\n"
    )
    if anchor not in text:
        fail("could not find libselinux NETLINK_SELINUX anchor")

    path.write_text(text.replace(anchor, patch, 1))
    print("Patched libselinux Darwin netlink constant fallbacks")


def patch_selinux_label_file_xattr_macro_compat(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/libselinux/src/label_file.c"
    if not path.exists():
        print("Skipping libselinux label_file xattr patch; label_file.c not present")
        return

    text = path.read_text()
    old = (
        "\tssize_t read_size = getxattr(pathname, RESTORECON_PARTIAL_MATCH_DIGEST,\n"
        "\t\t\t\t     read_digest, SHA1_HASH_SIZE\n"
        "#ifdef __APPLE__\n"
        "\t\t\t\t     , 0, 0\n"
        "#endif /* __APPLE __ */\n"
        "\t\t\t\t    );\n"
    )
    new = (
        "\tssize_t read_size = getxattr(pathname, RESTORECON_PARTIAL_MATCH_DIGEST,\n"
        "\t\t\t\t     read_digest, SHA1_HASH_SIZE);\n"
    )
    if new in text:
        print("libselinux label_file xattr macro compatibility already patched")
        return
    if old not in text:
        fail("could not find libselinux label_file getxattr Apple block")

    path.write_text(text.replace(old, new, 1))
    print("Patched libselinux label_file xattr macro compatibility")


def patch_selinux_darwin_gettid(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/libselinux/src/procattr.c"
    if not path.exists():
        print("Skipping libselinux Darwin gettid patch; procattr.c not present")
        return

    text = path.read_text()
    changed = False
    if "HansOS local: Darwin has pthread_threadid_np instead of Linux gettid." in text:
        print("libselinux Darwin gettid handling already patched")
        return

    include_anchor = "#include <pthread.h>\n"
    if include_anchor not in text:
        fail("could not find libselinux procattr pthread include")
    text = text.replace(include_anchor, include_anchor + "#include <stdint.h>\n", 1)
    changed = True

    old = (
        "static pid_t selinux_gettid(void)\n"
        "{\n"
        "#if HAVE_GETTID\n"
        "\treturn gettid();\n"
        "#else\n"
        "\treturn syscall(__NR_gettid);\n"
        "#endif\n"
        "}\n"
    )
    new = (
        "static pid_t selinux_gettid(void)\n"
        "{\n"
        "#if defined(__APPLE__)\n"
        "\t/* HansOS local: Darwin has pthread_threadid_np instead of Linux gettid. */\n"
        "\tuint64_t tid = 0;\n"
        "\tpthread_threadid_np(NULL, &tid);\n"
        "\treturn (pid_t)tid;\n"
        "#elif HAVE_GETTID\n"
        "\treturn gettid();\n"
        "#else\n"
        "\treturn syscall(__NR_gettid);\n"
        "#endif\n"
        "}\n"
    )
    if old not in text:
        fail("could not find libselinux selinux_gettid function")
    text = text.replace(old, new, 1)

    if changed:
        path.write_text(text)
        print("Patched libselinux Darwin gettid handling")


def patch_checkpolicy_darwin_network_compat(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/checkpolicy/policy_define.c"
    if not path.exists():
        print("Skipping checkpolicy Darwin network patch; policy_define.c not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin exposes IPv6/endian helpers differently."
    if marker in text:
        print("checkpolicy Darwin network compatibility already patched")
        return

    include_anchor = "#include <ctype.h>\n"
    if include_anchor not in text:
        fail("could not find checkpolicy include insertion point")

    compat = (
        "#include <ctype.h>\n"
        "\n"
        "#if defined(__APPLE__)\n"
        f"/* {marker} */\n"
        "#include <libkern/OSByteOrder.h>\n"
        "#ifndef be32toh\n"
        "#define be32toh(x) OSSwapBigToHostInt32(x)\n"
        "#endif\n"
        "#ifndef htobe32\n"
        "#define htobe32(x) OSSwapHostToBigInt32(x)\n"
        "#endif\n"
        "static inline uint32_t hansos_in6_addr32_get(const struct in6_addr *addr, unsigned int index)\n"
        "{\n"
        "\tuint32_t value;\n"
        "\tmemcpy(&value, &addr->s6_addr[index * sizeof(value)], sizeof(value));\n"
        "\treturn value;\n"
        "}\n"
        "static inline void hansos_in6_addr32_set(struct in6_addr *addr, unsigned int index, uint32_t value)\n"
        "{\n"
        "\tmemcpy(&addr->s6_addr[index * sizeof(value)], &value, sizeof(value));\n"
        "}\n"
        "#else\n"
        "#define hansos_in6_addr32_get(addr, index) ((addr)->s6_addr32[(index)])\n"
        "#define hansos_in6_addr32_set(addr, index, value) ((addr)->s6_addr32[(index)] = (value))\n"
        "#endif\n"
    )
    text = text.replace(include_anchor, compat, 1)

    replacements = {
        "subnet_prefix.s6_addr32[2] || subnet_prefix.s6_addr32[3]": (
            "hansos_in6_addr32_get(&subnet_prefix, 2) || "
            "hansos_in6_addr32_get(&subnet_prefix, 3)"
        ),
        "mask->s6_addr32[i] = 0;": "hansos_in6_addr32_set(mask, i, 0);",
        "mask->s6_addr32[i] = ~UINT32_C(0);": (
            "hansos_in6_addr32_set(mask, i, ~UINT32_C(0));"
        ),
        "mask->s6_addr32[i] = htobe32(~((UINT32_C(1) << (32 - cidr_bits)) - 1));": (
            "hansos_in6_addr32_set(mask, i, htobe32(~((UINT32_C(1) << (32 - cidr_bits)) - 1)));"
        ),
    }
    for old, new in replacements.items():
        if old not in text:
            fail(f"could not find checkpolicy network compatibility target: {old}")
        text = text.replace(old, new, 1)

    path.write_text(text)
    print("Patched checkpolicy Darwin network compatibility")


def patch_mkbootfs_darwin_sysmacros(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/mkbootfs/mkbootfs.cpp"
    if not path.exists():
        print("Skipping mkbootfs Darwin sysmacros patch; mkbootfs.cpp not present")
        return

    text = path.read_text()
    sysmacros_marker = "HansOS local: Darwin exposes major/minor from sys/types.h."
    kdev_marker = "HansOS local: linux/kdev_t.h is unavailable on Darwin."
    mkdev_marker = "HansOS local: map Linux MKDEV to Darwin makedev."
    changed = False

    old = "#include <sys/sysmacros.h>\n"
    new = (
        "#if !defined(__APPLE__)\n"
        f"#include <sys/sysmacros.h>  // {sysmacros_marker}\n"
        "#endif\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif sysmacros_marker not in text:
        fail("could not find mkbootfs sys/sysmacros include")

    old = "#include <linux/kdev_t.h>\n"
    new = (
        "#if !defined(__APPLE__)\n"
        f"#include <linux/kdev_t.h>  // {kdev_marker}\n"
        "#endif\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif kdev_marker not in text:
        fail("could not find mkbootfs linux/kdev_t include")

    include_anchor = "#include <string>\n"
    if mkdev_marker not in text:
        compat = (
            "#include <string>\n"
            "\n"
            "#if defined(__APPLE__) && !defined(MKDEV)\n"
            f"#define MKDEV(major, minor) makedev((major), (minor))  // {mkdev_marker}\n"
            "#endif\n"
        )
        if include_anchor not in text:
            fail("could not find mkbootfs C++ include insertion point")
        text = text.replace(include_anchor, compat, 1)
        changed = True

    old = (
        "static int append_devnodes_desc_dir(char* path, char* args)\n"
        "{\n"
        "    struct stat s;\n"
        "\n"
        "    if (sscanf(args, \"%o %d %d\", &s.st_mode, &s.st_uid, &s.st_gid) != 3) return -1;\n"
        "\n"
        "    s.st_mode |= S_IFDIR;\n"
    )
    new = (
        "static int append_devnodes_desc_dir(char* path, char* args)\n"
        "{\n"
        "    struct stat s;\n"
        "    unsigned int parsed_mode;\n"
        "    int parsed_uid, parsed_gid;\n"
        "\n"
        "    if (sscanf(args, \"%o %d %d\", &parsed_mode, &parsed_uid, &parsed_gid) != 3) return -1;\n"
        "    s.st_mode = (mode_t)parsed_mode;\n"
        "    s.st_uid = (uid_t)parsed_uid;\n"
        "    s.st_gid = (gid_t)parsed_gid;\n"
        "\n"
        "    s.st_mode |= S_IFDIR;\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif "unsigned int parsed_mode;" not in text:
        fail("could not find mkbootfs devnodes dir sscanf block")

    old = (
        "static int append_devnodes_desc_nod(char* path, char* args)\n"
        "{\n"
        "    int minor, major;\n"
        "    struct stat s;\n"
        "    char dev;\n"
        "\n"
        "    if (sscanf(args, \"%o %d %d %c %d %d\", &s.st_mode, &s.st_uid, &s.st_gid,\n"
        "               &dev, &major, &minor) != 6) return -1;\n"
        "\n"
        "    s.st_rdev = MKDEV(major, minor);\n"
    )
    new = (
        "static int append_devnodes_desc_nod(char* path, char* args)\n"
        "{\n"
        "    int minor, major;\n"
        "    unsigned int parsed_mode;\n"
        "    int parsed_uid, parsed_gid;\n"
        "    struct stat s;\n"
        "    char dev;\n"
        "\n"
        "    if (sscanf(args, \"%o %d %d %c %d %d\", &parsed_mode, &parsed_uid, &parsed_gid,\n"
        "               &dev, &major, &minor) != 6) return -1;\n"
        "    s.st_mode = (mode_t)parsed_mode;\n"
        "    s.st_uid = (uid_t)parsed_uid;\n"
        "    s.st_gid = (gid_t)parsed_gid;\n"
        "\n"
        "    s.st_rdev = MKDEV(major, minor);\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif "parsed_uid, parsed_gid" not in text:
        fail("could not find mkbootfs devnodes nod sscanf block")

    if changed:
        path.write_text(text)
        print("Patched mkbootfs Darwin compatibility")
    else:
        print("mkbootfs Darwin compatibility already patched")


def patch_toybox_darwin_availability_warning(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/toybox/Android.bp"
    if not path.exists():
        print("Skipping toybox Darwin availability patch; Android.bp not present")
        return

    text = path.read_text()
    marker = "HansOS local: host toybox uses newer macOS APIs behind its own portability layer."
    if marker in text:
        print("toybox Darwin availability warning already patched")
        return

    block_range = find_named_module_block(text, "cc_defaults", "toybox-defaults")
    if block_range is None:
        fail("could not find toybox-defaults module")

    start, end = block_range
    block = text[start:end]
    anchor = (
        "        darwin: {\n"
        "            local_include_dirs: [\"android/mac\"],\n"
        "            cflags: [\n"
    )
    patch = (
        "        darwin: {\n"
        "            local_include_dirs: [\"android/mac\"],\n"
        "            cflags: [\n"
        f"                // {marker}\n"
        "                \"-Wno-unguarded-availability-new\",\n"
    )
    if anchor not in block:
        fail("could not find toybox Darwin cflags block")

    replacement = block.replace(anchor, patch, 1)
    path.write_text(text[:start] + replacement + text[end:])
    print("Patched toybox Darwin availability warning")


def patch_kmod_darwin_endian(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/kmod/android/port.h"
    if not path.exists():
        print("Skipping kmod Darwin endian patch; port.h not present")
        return

    shim_path = aosp_root / "external/kmod/endian-darwin.h"
    shim_marker = "HansOS local: minimal endian shim for Darwin host kmod builds."
    shim_contents = (
        "/* " + shim_marker + " */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <libkern/OSByteOrder.h>\n"
        "\n"
        "#ifndef __LITTLE_ENDIAN\n"
        "#define __LITTLE_ENDIAN 1234\n"
        "#endif\n"
        "#ifndef __BIG_ENDIAN\n"
        "#define __BIG_ENDIAN 4321\n"
        "#endif\n"
        "#ifndef __BYTE_ORDER\n"
        "#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__\n"
        "#define __BYTE_ORDER __BIG_ENDIAN\n"
        "#else\n"
        "#define __BYTE_ORDER __LITTLE_ENDIAN\n"
        "#endif\n"
        "#endif\n"
        "\n"
        "#ifndef be32toh\n"
        "#define be32toh(x) OSSwapBigToHostInt32(x)\n"
        "#endif\n"
        "#ifndef htobe32\n"
        "#define htobe32(x) OSSwapHostToBigInt32(x)\n"
        "#endif\n"
        "#endif\n"
    )
    shim_changed = False
    if not shim_path.exists() or shim_marker not in shim_path.read_text():
        shim_path.write_text(shim_contents)
        shim_changed = True

    text = path.read_text()
    marker = "HansOS local: Darwin uses kmod's endian-darwin.h shim."
    changed = shim_changed

    old = (
        "#include <endian.h>\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "\n"
        "#include <endian-darwin.h>\n"
    )
    new = (
        "#if defined(__APPLE__)\n"
        f"/* {marker} */\n"
        "#include <endian-darwin.h>\n"
        "#else\n"
        "#include <endian.h>\n"
        "#endif\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "\n"
    )
    if marker not in text:
        if old not in text:
            fail("could not find kmod endian include block")
        text = text.replace(old, new, 1)
        changed = True

    if "#define HAVE_DECL_STRNDUPA\n" in text:
        text = text.replace("#define HAVE_DECL_STRNDUPA\n", "#define HAVE_DECL_STRNDUPA 1\n", 1)
        changed = True
    elif "#define HAVE_DECL_STRNDUPA 1\n" not in text:
        fail("could not find kmod HAVE_DECL_STRNDUPA define")

    old = "#if defined(__ANDROID__) || defined(__APPLE__)\n#include <stdlib.h>\n#include <unistd.h>\n"
    new = (
        "#if defined(__ANDROID__) || defined(__APPLE__)\n"
        "#include <limits.h>\n"
        "#include <stdlib.h>\n"
        "#include <unistd.h>\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif "#include <limits.h>\n#include <stdlib.h>\n#include <unistd.h>\n" not in text:
        fail("could not find kmod PATH_MAX include insertion point")

    if changed:
        path.write_text(text)
        print("Patched kmod Darwin endian/header handling")
    else:
        print("kmod Darwin endian/header handling already patched")


def patch_kmod_darwin_uadd_overflow(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/kmod/shared/util.h"
    if not path.exists():
        print("Skipping kmod Darwin overflow patch; util.h not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin typedefs uint64_t as unsigned long long."
    if marker in text:
        print("kmod Darwin uint64 overflow handling already patched")
        return

    old = (
        "static inline bool addu64_overflow(uint64_t a, uint64_t b, uint64_t *res)\n"
        "{\n"
        "#if (HAVE___BUILTIN_UADDL_OVERFLOW && HAVE___BUILTIN_UADDLL_OVERFLOW)\n"
    )
    new = (
        "static inline bool addu64_overflow(uint64_t a, uint64_t b, uint64_t *res)\n"
        "{\n"
        "#if defined(__APPLE__)\n"
        f"\t/* {marker} */\n"
        "\treturn __builtin_add_overflow(a, b, res);\n"
        "#elif (HAVE___BUILTIN_UADDL_OVERFLOW && HAVE___BUILTIN_UADDLL_OVERFLOW)\n"
    )
    if old not in text:
        fail("could not find kmod addu64_overflow function")

    path.write_text(text.replace(old, new, 1))
    print("Patched kmod Darwin uint64 overflow handling")


def patch_kmod_darwin_elf_header(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/kmod/elf.h"
    marker = "HansOS local: minimal Linux ELF ABI for Darwin host kmod builds."
    contents = (
        "/* " + marker + " */\n"
        "#pragma once\n"
        "\n"
        "#include <stdint.h>\n"
        "\n"
        "#define EI_NIDENT 16\n"
        "#define EI_CLASS 4\n"
        "#define EI_DATA 5\n"
        "#define ELFMAG \"\\177ELF\"\n"
        "#define SELFMAG 4\n"
        "#define ELFCLASS32 1\n"
        "#define ELFCLASS64 2\n"
        "#define ELFDATA2LSB 1\n"
        "#define ELFDATA2MSB 2\n"
        "\n"
        "#define EM_SPARC 2\n"
        "#define EM_SPARCV9 43\n"
        "\n"
        "#define SHN_UNDEF 0\n"
        "#define SHN_ABS 0xfff1\n"
        "#define SHF_ALLOC (1U << 1)\n"
        "\n"
        "#define STB_LOCAL 0\n"
        "#define STB_GLOBAL 1\n"
        "#define STB_WEAK 2\n"
        "\n"
        "typedef uint16_t Elf32_Half;\n"
        "typedef uint32_t Elf32_Word;\n"
        "typedef int32_t Elf32_Sword;\n"
        "typedef uint32_t Elf32_Addr;\n"
        "typedef uint32_t Elf32_Off;\n"
        "\n"
        "typedef uint16_t Elf64_Half;\n"
        "typedef uint32_t Elf64_Word;\n"
        "typedef int32_t Elf64_Sword;\n"
        "typedef uint64_t Elf64_Xword;\n"
        "typedef int64_t Elf64_Sxword;\n"
        "typedef uint64_t Elf64_Addr;\n"
        "typedef uint64_t Elf64_Off;\n"
        "\n"
        "typedef struct {\n"
        "  unsigned char e_ident[EI_NIDENT];\n"
        "  Elf32_Half e_type;\n"
        "  Elf32_Half e_machine;\n"
        "  Elf32_Word e_version;\n"
        "  Elf32_Addr e_entry;\n"
        "  Elf32_Off e_phoff;\n"
        "  Elf32_Off e_shoff;\n"
        "  Elf32_Word e_flags;\n"
        "  Elf32_Half e_ehsize;\n"
        "  Elf32_Half e_phentsize;\n"
        "  Elf32_Half e_phnum;\n"
        "  Elf32_Half e_shentsize;\n"
        "  Elf32_Half e_shnum;\n"
        "  Elf32_Half e_shstrndx;\n"
        "} Elf32_Ehdr;\n"
        "\n"
        "typedef struct {\n"
        "  unsigned char e_ident[EI_NIDENT];\n"
        "  Elf64_Half e_type;\n"
        "  Elf64_Half e_machine;\n"
        "  Elf64_Word e_version;\n"
        "  Elf64_Addr e_entry;\n"
        "  Elf64_Off e_phoff;\n"
        "  Elf64_Off e_shoff;\n"
        "  Elf64_Word e_flags;\n"
        "  Elf64_Half e_ehsize;\n"
        "  Elf64_Half e_phentsize;\n"
        "  Elf64_Half e_phnum;\n"
        "  Elf64_Half e_shentsize;\n"
        "  Elf64_Half e_shnum;\n"
        "  Elf64_Half e_shstrndx;\n"
        "} Elf64_Ehdr;\n"
        "\n"
        "typedef struct {\n"
        "  Elf32_Word sh_name;\n"
        "  Elf32_Word sh_type;\n"
        "  Elf32_Word sh_flags;\n"
        "  Elf32_Addr sh_addr;\n"
        "  Elf32_Off sh_offset;\n"
        "  Elf32_Word sh_size;\n"
        "  Elf32_Word sh_link;\n"
        "  Elf32_Word sh_info;\n"
        "  Elf32_Word sh_addralign;\n"
        "  Elf32_Word sh_entsize;\n"
        "} Elf32_Shdr;\n"
        "\n"
        "typedef struct {\n"
        "  Elf64_Word sh_name;\n"
        "  Elf64_Word sh_type;\n"
        "  Elf64_Xword sh_flags;\n"
        "  Elf64_Addr sh_addr;\n"
        "  Elf64_Off sh_offset;\n"
        "  Elf64_Xword sh_size;\n"
        "  Elf64_Word sh_link;\n"
        "  Elf64_Word sh_info;\n"
        "  Elf64_Xword sh_addralign;\n"
        "  Elf64_Xword sh_entsize;\n"
        "} Elf64_Shdr;\n"
        "\n"
        "typedef struct {\n"
        "  Elf32_Word st_name;\n"
        "  Elf32_Addr st_value;\n"
        "  Elf32_Word st_size;\n"
        "  unsigned char st_info;\n"
        "  unsigned char st_other;\n"
        "  Elf32_Half st_shndx;\n"
        "} Elf32_Sym;\n"
        "\n"
        "typedef struct {\n"
        "  Elf64_Word st_name;\n"
        "  unsigned char st_info;\n"
        "  unsigned char st_other;\n"
        "  Elf64_Half st_shndx;\n"
        "  Elf64_Addr st_value;\n"
        "  Elf64_Xword st_size;\n"
        "} Elf64_Sym;\n"
        "\n"
        "#define ELF32_ST_BIND(value) ((unsigned char)(value) >> 4)\n"
        "#define ELF32_ST_TYPE(value) ((value) & 0xf)\n"
        "#define ELF64_ST_BIND(value) ELF32_ST_BIND(value)\n"
        "#define ELF64_ST_TYPE(value) ELF32_ST_TYPE(value)\n"
    )

    if path.exists() and marker in path.read_text():
        print("kmod Darwin ELF header already present")
        return

    path.write_text(contents)
    print("Patched kmod Darwin ELF header")


def patch_kmod_darwin_time_compat(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/kmod/shared/util.c"
    if not path.exists():
        print("Skipping kmod Darwin time patch; util.c not present")
        return

    text = path.read_text()
    marker = "HansOS local: Darwin lacks clock_nanosleep."
    stat_marker = "HansOS local: Darwin exposes nanosecond mtime as st_mtimespec."
    changed = False

    old = (
        "int sleep_until_msec(unsigned long long msec)\n"
        "{\n"
        "\tstruct timespec ts = msec_ts(msec);\n"
        "\n"
        "\tif (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL) < 0 &&\n"
        "\t    errno != EINTR)\n"
        "\t\treturn -errno;\n"
        "\n"
        "\treturn 0;\n"
        "}\n"
    )
    new = (
        "int sleep_until_msec(unsigned long long msec)\n"
        "{\n"
        "\tstruct timespec ts = msec_ts(msec);\n"
        "\n"
        "#if defined(__APPLE__)\n"
        f"\t/* {marker} */\n"
        "\tstruct timespec now;\n"
        "\tif (clock_gettime(CLOCK_MONOTONIC, &now) != 0)\n"
        "\t\treturn -errno;\n"
        "\n"
        "\tts.tv_sec -= now.tv_sec;\n"
        "\tts.tv_nsec -= now.tv_nsec;\n"
        "\tif (ts.tv_nsec < 0) {\n"
        "\t\tts.tv_sec--;\n"
        "\t\tts.tv_nsec += 1000000000L;\n"
        "\t}\n"
        "\tif (ts.tv_sec < 0)\n"
        "\t\treturn 0;\n"
        "\twhile (nanosleep(&ts, &ts) < 0) {\n"
        "\t\tif (errno != EINTR)\n"
        "\t\t\treturn -errno;\n"
        "\t}\n"
        "#else\n"
        "\tif (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL) < 0 &&\n"
        "\t    errno != EINTR)\n"
        "\t\treturn -errno;\n"
        "#endif\n"
        "\n"
        "\treturn 0;\n"
        "}\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif marker not in text:
        fail("could not find kmod sleep_until_msec implementation")

    old = (
        "unsigned long long stat_mstamp(const struct stat *st)\n"
        "{\n"
        "#ifdef HAVE_STRUCT_STAT_ST_MTIM\n"
        "\treturn ts_usec(&st->st_mtim);\n"
        "#else\n"
        "\treturn (unsigned long long) st->st_mtime;\n"
        "#endif\n"
        "}\n"
    )
    new = (
        "unsigned long long stat_mstamp(const struct stat *st)\n"
        "{\n"
        "#if defined(__APPLE__)\n"
        f"\t/* {stat_marker} */\n"
        "\treturn ts_usec(&st->st_mtimespec);\n"
        "#elif defined(HAVE_STRUCT_STAT_ST_MTIM)\n"
        "\treturn ts_usec(&st->st_mtim);\n"
        "#else\n"
        "\treturn (unsigned long long) st->st_mtime;\n"
        "#endif\n"
        "}\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    elif stat_marker not in text:
        fail("could not find kmod stat_mstamp implementation")

    if changed:
        path.write_text(text)
        print("Patched kmod Darwin time handling")
    else:
        print("kmod Darwin time handling already patched")


def patch_e2fsdroid_darwin_capability_shim(aosp_root: pathlib.Path) -> None:
    include_dir = aosp_root / "external/e2fsprogs/contrib/android/linux"
    path = include_dir / "capability.h"
    contents = (
        "/* HansOS local: minimal Linux capability ABI for Darwin host e2fsdroid. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <stdint.h>\n"
        "typedef uint32_t __le32;\n"
        "#define CAP_SETGID 6\n"
        "#define CAP_SETUID 7\n"
        "#define CAP_BLOCK_SUSPEND 36\n"
        "#define VFS_CAP_FLAGS_EFFECTIVE 0x000001\n"
        "#define VFS_CAP_REVISION_2 0x02000000\n"
        "#define VFS_CAP_U32_2 2\n"
        "struct vfs_cap_data {\n"
        "    __le32 magic_etc;\n"
        "    struct {\n"
        "        __le32 permitted;\n"
        "        __le32 inheritable;\n"
        "    } data[VFS_CAP_U32_2];\n"
        "};\n"
        "#else\n"
        "#include_next <linux/capability.h>\n"
        "#endif\n"
    )

    if path.exists() and path.read_text() == contents:
        print("e2fsdroid Darwin capability shim already present")
        return

    include_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    print("Patched e2fsdroid Darwin capability shim")


def linux_capability_shim_contents(comment: str) -> str:
    return (
        f"/* HansOS local: {comment}. */\n"
        "#pragma once\n"
        "\n"
        "#if defined(__APPLE__)\n"
        "#include <stdint.h>\n"
        "typedef uint32_t __le32;\n"
        "#define CAP_SETGID 6\n"
        "#define CAP_SETUID 7\n"
        "#define CAP_BLOCK_SUSPEND 36\n"
        "#define VFS_CAP_FLAGS_EFFECTIVE 0x000001\n"
        "#define VFS_CAP_REVISION_2 0x02000000\n"
        "#define VFS_CAP_U32_2 2\n"
        "struct vfs_cap_data {\n"
        "    __le32 magic_etc;\n"
        "    struct {\n"
        "        __le32 permitted;\n"
        "        __le32 inheritable;\n"
        "    } data[VFS_CAP_U32_2];\n"
        "};\n"
        "#else\n"
        "#include_next <linux/capability.h>\n"
        "#endif\n"
    )


def patch_libcutils_darwin_capability_shim(aosp_root: pathlib.Path) -> None:
    include_dir = aosp_root / "system/core/libcutils/include/linux"
    path = include_dir / "capability.h"
    contents = linux_capability_shim_contents("minimal Linux capability ABI for Darwin host libcutils")

    if path.exists() and path.read_text() == contents:
        print("libcutils Darwin capability shim already present")
        return

    include_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    print("Patched libcutils Darwin capability shim")


def patch_libcutils_darwin_fs_config_sources(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "system/core/libcutils/Android.bp"
    if not path.exists():
        print("Skipping libcutils Darwin fs_config patch; Android.bp not present")
        return

    text = path.read_text()
    if "HansOS local: e2fsdroid needs fs_config symbols from Darwin host libcutils." in text:
        print("libcutils Darwin fs_config sources already patched")
        return

    old = (
        "        linux: {\n"
        "            srcs: [\n"
        '                "canned_fs_config.cpp",\n'
        '                "fs_config.cpp",\n'
        "            ],\n"
        "        },\n"
        "        host: {\n"
    )
    new = (
        "        linux: {\n"
        "            srcs: [\n"
        '                "canned_fs_config.cpp",\n'
        '                "fs_config.cpp",\n'
        "            ],\n"
        "        },\n"
        "        // HansOS local: e2fsdroid needs fs_config symbols from Darwin host libcutils.\n"
        "        darwin: {\n"
        "            srcs: [\n"
        '                "canned_fs_config.cpp",\n'
        '                "fs_config.cpp",\n'
        "            ],\n"
        "        },\n"
        "        host: {\n"
    )
    if old not in text:
        fail("could not find libcutils linux target block")

    path.write_text(text.replace(old, new, 1))
    print("Patched libcutils Darwin fs_config sources")


def patch_adevice_darwin_disabled(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "tools/asuite/adevice/Android.bp"
    if not path.exists():
        print("Skipping adevice Darwin disable patch; Android.bp not present")
        return

    text = path.read_text()
    changed = False
    target_patch = (
        "    // HansOS local: the optional adevice host tool currently fails to link ring on Darwin.\n"
        "    target: {\n"
        "        darwin: {\n"
        "            enabled: false,\n"
        "        },\n"
        "    },\n"
    )

    for module_type, module_name in [
        ("rust_binary_host", "adevice"),
        ("rust_test_host", "adevice_test"),
        ("sh_test_host", "adevice_integration_test"),
    ]:
        block_range = find_named_module_block(text, module_type, module_name)
        if block_range is None:
            continue
        start, end = block_range
        block = text[start:end]
        if "darwin:" in block:
            continue
        replacement = block[:-1] + target_patch + "}"
        text = text[:start] + replacement + text[end:]
        changed = True

    if changed:
        path.write_text(text)
        print("Patched adevice Darwin host variants disabled")
    else:
        print("adevice Darwin host variants already disabled")


def patch_selinux_host_uapi_headers(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "external/selinux/libselinux/Android.bp"
    if not path.exists():
        print("Skipping libselinux host UAPI header patch; Android.bp not present")
        return

    text = path.read_text()
    required_dirs = [
        '"bionic/libc/kernel/android/uapi"',
        '"bionic/libc/kernel/uapi"',
        '"bionic/libc/kernel/uapi/asm-x86"',
    ]
    if all(required_dir in text for required_dir in required_dirs):
        print("libselinux host UAPI headers already patched")
        return

    old = (
        "        host: {\n"
        "            cflags: [\n"
        '                "-DBUILD_HOST",\n'
        "            ],\n"
        "        },\n"
    )
    new = (
        "        host: {\n"
        "            cflags: [\n"
        '                "-DBUILD_HOST",\n'
        "            ],\n"
        "            // HansOS local: Darwin host builds need Linux UAPI constants used by libselinux.\n"
        "            include_dirs: [\n"
        '                "bionic/libc/kernel/android/uapi",\n'
        '                "bionic/libc/kernel/uapi",\n'
        '                "bionic/libc/kernel/uapi/asm-x86",\n'
        "            ],\n"
        "        },\n"
    )
    if old in text:
        path.write_text(text.replace(old, new, 1))
        print("Patched libselinux host build with Bionic UAPI include dirs")
        return

    anchor = '            include_dirs: [\n'
    if anchor in text and '"bionic/libc/kernel/uapi",' in text:
        insert_at = text.find(anchor) + len(anchor)
        text = text[:insert_at] + '                "bionic/libc/kernel/android/uapi",\n' + text[insert_at:]
        path.write_text(text)
        print("Patched libselinux host build with Android UAPI include dir")
        return

    fail("could not find libselinux host target block")


def find_module_blocks(text: str, module_type: str) -> list[tuple[int, int, str]]:
    blocks: list[tuple[int, int, str]] = []
    cursor = 0
    marker = f"{module_type} {{"
    while True:
        start = text.find(marker, cursor)
        if start == -1:
            return blocks

        depth = 0
        for idx in range(start, len(text)):
            char = text[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    blocks.append((start, end, text[start:end]))
                    cursor = end
                    break
        else:
            fail(f"unterminated {module_type} block")


def module_name_from_block(block: str) -> str | None:
    match = re.search(r'\bname:\s*"([^"]+)"', block)
    if match is None:
        return None
    return match.group(1)


def patch_java_fuzz_darwin_jni_modules(aosp_root: pathlib.Path) -> None:
    roots = [
        aosp_root / "tools/security/fuzzing",
        aosp_root / "frameworks/base/core/tests/fuzzers",
    ]
    changed_paths: list[str] = []

    target_patch = (
        "    // HansOS local: disable Darwin host variant for JNI java_fuzz modules.\n"
        "    // Soong reports prebuilt_libc++ as an unsupported JNI shared library on macOS.\n"
        "    target: {\n"
        "        darwin: {\n"
        "            enabled: false,\n"
        "        },\n"
        "    },\n"
    )

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("Android.bp"):
            text = path.read_text()
            chunks: list[str] = []
            last = 0
            changed = False
            for start, end, block in find_module_blocks(text, "java_fuzz"):
                replacement = block
                if (
                    "host_supported: true" in block
                    and "jni_libs:" in block
                    and "darwin:" not in block
                ):
                    anchor = "    host_supported: true,\n"
                    if anchor not in block:
                        fail(f"could not find host_supported anchor in {path}")
                    replacement = block.replace(anchor, anchor + target_patch, 1)
                    changed = True

                chunks.append(text[last:start])
                chunks.append(replacement)
                last = end

            if changed:
                chunks.append(text[last:])
                path.write_text("".join(chunks))
                changed_paths.append(str(path.relative_to(aosp_root)))

    if changed_paths:
        for changed_path in changed_paths:
            print(f"Patched {changed_path} to skip Darwin JNI java_fuzz host variant")
    else:
        print("JNI java_fuzz Darwin host variants already patched")


def patch_trusty_host_package_linux_musl(aosp_root: pathlib.Path) -> None:
    path = aosp_root / "device/generic/trusty/Android.bp"
    if not path.exists():
        print("Skipping Trusty host package patch; Android.bp not present")
        return

    text = path.read_text()
    block_range = find_named_module_block(text, "java_genrule_host", "trusty-host_package")
    if block_range is None:
        print("Skipping Trusty host package patch; module not present")
        return

    start, end = block_range
    block = text[start:end]
    if "linux_musl:" in block:
        print("trusty-host_package already disables linux_musl host variant")
        return

    anchor = "    target: {\n"
    if anchor not in block:
        fail("could not find target block in trusty-host_package")

    replacement = block.replace(
        anchor,
        anchor
        + "        // HansOS local: this dist package depends on a glibc-only Trusty QEMU prebuilt.\n"
        + "        linux_musl: {\n"
        + "            enabled: false,\n"
        + "        },\n",
        1,
    )
    path.write_text(text[:start] + replacement + text[end:])
    print("Patched trusty-host_package to skip linux_musl host variant")


def patch_virtualization_host_tests_darwin(aosp_root: pathlib.Path) -> None:
    apex_path = aosp_root / "packages/modules/Virtualization/build/apex/Android.bp"
    if not apex_path.exists():
        print("Skipping Virtualization host test patch; Android.bp not present")
        return

    text = apex_path.read_text()
    block_range = find_named_module_block(text, "sh_test_host", "sign_virt_apex_test")
    if block_range is None:
        print("Skipping Virtualization host test patch; sign_virt_apex_test not present")
    else:
        start, end = block_range
        block = text[start:end]
        if "darwin:" in block:
            print("sign_virt_apex_test already disables Darwin host variant")
        else:
            anchor = '    test_suites: ["general-tests"],\n'
            if anchor not in block:
                fail("could not find sign_virt_apex_test insertion point")

            replacement = block.replace(
                anchor,
                anchor
                + "    // HansOS local: this host test trips Soong's Darwin data_libs path handling.\n"
                + "    target: {\n"
                + "        darwin: {\n"
                + "            enabled: false,\n"
                + "        },\n"
                + "    },\n",
                1,
            )
            apex_path.write_text(text[:start] + replacement + text[end:])
            print("Patched sign_virt_apex_test to skip Darwin host variant")

    tests_root = aosp_root / "packages/modules/Virtualization/tests"
    if not tests_root.exists():
        print("Skipping Virtualization java_test_host patch; tests dir not present")
        return

    target_patch = (
        "\n"
        "    // HansOS local: Virtualization host tests pull JNI libs that are not valid on Darwin.\n"
        "    target: {\n"
        "        darwin: {\n"
        "            enabled: false,\n"
        "        },\n"
        "    },\n"
    )
    changed_paths: list[str] = []
    for path in tests_root.rglob("Android.bp"):
        text = path.read_text()
        chunks: list[str] = []
        last = 0
        changed = False
        for start, end, block in find_module_blocks(text, "java_test_host"):
            replacement = block
            if "darwin:" not in block:
                replacement = block[:-1] + target_patch + "}"
                changed = True

            chunks.append(text[last:start])
            chunks.append(replacement)
            last = end

        if changed:
            chunks.append(text[last:])
            path.write_text("".join(chunks))
            changed_paths.append(str(path.relative_to(aosp_root)))

    if changed_paths:
        for changed_path in changed_paths:
            print(f"Patched {changed_path} to skip Darwin Virtualization java_test_host variants")
    else:
        print("Virtualization java_test_host Darwin variants already patched")


def patch_cts_hostside_jni_tests_darwin(aosp_root: pathlib.Path) -> None:
    root = aosp_root / "cts/hostsidetests"
    if not root.exists():
        print("Skipping CTS hostside JNI test patch; cts/hostsidetests not present")
        return

    target_patch = (
        "\n"
        "    // HansOS local: CTS hostside JNI tests pull libc++ JNI libs unsupported on Darwin.\n"
        "    target: {\n"
        "        darwin: {\n"
        "            enabled: false,\n"
        "        },\n"
        "    },\n"
    )
    target_entry_patch = (
        "        // HansOS local: CTS hostside JNI tests pull libc++ JNI libs unsupported on Darwin.\n"
        "        darwin: {\n"
        "            enabled: false,\n"
        "        },\n"
    )
    changed_paths: list[str] = []

    for path in root.rglob("Android.bp"):
        text = path.read_text()
        jni_host_test_names: set[str] = set()
        for _, _, block in find_module_blocks(text, "java_test_host"):
            if "jni_libs:" in block:
                name = module_name_from_block(block)
                if name is not None:
                    jni_host_test_names.add(name)

        chunks: list[str] = []
        last = 0
        changed = False

        for start, end, block in find_module_blocks(text, "java_test_host"):
            replacement = block
            if "jni_libs:" in block and "darwin:" not in block:
                target_anchor = "    target: {\n"
                if target_anchor in block:
                    replacement = block.replace(target_anchor, target_anchor + target_entry_patch, 1)
                else:
                    replacement = block[:-1] + target_patch + "}"
                changed = True

            chunks.append(text[last:start])
            chunks.append(replacement)
            last = end

        if chunks:
            chunks.append(text[last:])
            text = "".join(chunks)

        if jni_host_test_names:
            chunks = []
            last = 0
            for start, end, block in find_module_blocks(text, "test_module_config_host"):
                replacement = block
                if (
                    "enabled:" not in block
                    and any(f'base: "{name}"' in block for name in jni_host_test_names)
                ):
                    replacement = block.replace(
                        "test_module_config_host {\n",
                        "test_module_config_host {\n"
                        "    // HansOS local: derived configs for disabled JNI host tests are skipped on macOS.\n"
                        "    enabled: false,\n",
                        1,
                    )
                    changed = True

                chunks.append(text[last:start])
                chunks.append(replacement)
                last = end

            if chunks:
                chunks.append(text[last:])
                text = "".join(chunks)

        if changed:
            path.write_text(text)
            changed_paths.append(str(path.relative_to(aosp_root)))

    if changed_paths:
        for changed_path in changed_paths:
            print(f"Patched {changed_path} to skip Darwin CTS hostside JNI test variants")
    else:
        print("CTS hostside JNI java_test_host Darwin variants already patched")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: scripts/patch-aosp.py /path/to/aosp")

    aosp_root = pathlib.Path(sys.argv[1]).resolve()
    if not (aosp_root / "build/envsetup.sh").exists():
        fail(f"not an AOSP checkout: {aosp_root}")

    patch_system_server(aosp_root)
    patch_services_core_bp(aosp_root)
    patch_hans_service_sepolicy(aosp_root)
    patch_crosvm_manager_view_only_webrtc(aosp_root)
    patch_cuttlefish_external_webrtc_port(aosp_root)
    patch_open_dice_baremetal_vendor_variants(aosp_root)
    patch_cronet_aml_android_runtime_jni_headers(aosp_root)
    patch_cronet_aml_testing_library_install_collision(aosp_root)
    patch_crosvm_linux_glibc_arm64_prebuilt_collision(aosp_root)
    patch_cvd_host_package_arm64_prebuilt_crosvm(aosp_root)
    patch_cuttlefish_crosvm_linux_arm64_support_check(aosp_root)
    patch_appcompat_current_host_out(aosp_root)
    patch_fastboot_host_cross_collision(aosp_root)
    patch_linux_arm64_disable_host_cross(aosp_root)
    patch_linux_arm64_soong_config_host_cross(aosp_root)
    patch_base_system_ld_mc_host_package(aosp_root)
    patch_rust_linux_arm64_host_prebuilts(aosp_root)
    patch_binder_ndk_rust_missing_bindings(aosp_root)
    patch_binder_tokio_missing_sys_import(aosp_root)
    patch_binder_rpc_rust_missing_bindings(aosp_root)
    patch_apkmanifest_bindgen_missing_functions(aosp_root)
    patch_keystore2_crypto_bindgen_missing_symbols(aosp_root)
    patch_keystore2_aaid_bindgen_missing_symbols(aosp_root)
    patch_keystore2_apc_compat_bindgen_missing_symbols(aosp_root)
    patch_simpleperf_profcollect_bindgen_missing_functions(aosp_root)
    patch_mkuserimg_mke2fs_host_tool_lookup(aosp_root)
    patch_releasetools_build_image_host_tool_lookup(aosp_root)
    patch_ota_from_raw_img_delta_generator_path(aosp_root)
    patch_dexpreopt_gen_product_packages_path(aosp_root)
    patch_input_rust_missing_bindgen_constants(aosp_root)
    patch_nanopb_soong_plugin_detection(aosp_root)

    if sys.platform != "darwin":
        print("Skipping Darwin host compatibility patches on non-Darwin host")
        return

    patch_soong_darwin_sdk_versions(aosp_root)
    patch_soong_darwin_skip_ccdeps(aosp_root)
    patch_soong_build_darwin_memory_limit(aosp_root)
    patch_soong_darwin_host_cc_shared_lib_path(aosp_root)
    patch_make_core_main_darwin_image_packaging(aosp_root)
    patch_make_core_darwin_selinux_fc(aosp_root)
    patch_rootdir_darwin_init_environ_source(aosp_root)
    patch_make_tools_darwin_python3_shebang(aosp_root)
    patch_darwin_env_python_shebangs(aosp_root)
    patch_cronet_headers_copy_python3(aosp_root)
    patch_cronet_darwin_linker_flags(aosp_root)
    patch_cronet_darwin_host_linkage(aosp_root)
    patch_rust_prebuilts_bp(aosp_root)
    patch_streaming_proto_corefoundation(aosp_root)
    patch_perfetto_proto_plugins_corefoundation(aosp_root)
    patch_grpc_java_protoc_plugin_corefoundation(aosp_root)
    patch_libchrome_include_generator_python3(aosp_root)
    patch_libchrome_jni_registration_generator_embedded_python(aosp_root)
    patch_crosvm_proc_macro_variants(aosp_root)
    patch_minijail_securebits_all_bits(aosp_root)
    patch_aidl_rust_darwin_host_variants(aosp_root)
    patch_input_bindgen_binder_headers(aosp_root)
    patch_inputflinger_aidl_static_darwin_variant(aosp_root)
    patch_libinput_android_only_host_deps(aosp_root)
    patch_libinput_inputconstants_android_only(aosp_root)
    patch_libinput_darwin_generated_input_headers(aosp_root)
    patch_input_rust_darwin_inputconstants(aosp_root)
    patch_gemmlowp_darwin_malloc_header(aosp_root)
    patch_expresscatalog_codegen_int64_format(aosp_root)
    patch_f2fs_tools_darwin_lsetxattr(aosp_root)
    patch_erofs_utils_darwin_host_tools(aosp_root)
    patch_debuggerd_darwin_mte_signal_codes(aosp_root)
    patch_debuggerd_darwin_prctl_header(aosp_root)
    patch_debuggerd_pbtombstone_corefoundation(aosp_root)
    patch_cuttlefish_fs_darwin_inotify(aosp_root)
    patch_gatekeeper_darwin_endian(aosp_root)
    patch_cuttlefish_vm_manager_darwin_unused_helpers(aosp_root)
    patch_cuttlefish_vhost_user_block_signal_include(aosp_root)
    patch_cuttlefish_graphics_flags_darwin_unused_args(aosp_root)
    patch_grpc_darwin_exclude_binder_ndk(aosp_root)
    patch_cuttlefish_openwrt_control_server_darwin(aosp_root)
    patch_cuttlefish_run_cvd_darwin_grpc_flags(aosp_root)
    patch_cuttlefish_vhal_proxy_server_darwin_vsock(aosp_root)
    patch_idmap2_corefoundation(aosp_root)
    patch_libvintf_darwin_stat_mtime(aosp_root)
    patch_init_host_tools_darwin_enabled(aosp_root)
    patch_init_darwin_event_loop_shims(aosp_root)
    patch_init_darwin_host_logging(aosp_root)
    patch_libbase_darwin_getuint_size_t(aosp_root)
    patch_libcap_darwin_stub(aosp_root)
    patch_libfstab_darwin_host(aosp_root)
    patch_libprocessgroup_util_darwin_mntent(aosp_root)
    patch_libprocessgroup_task_profiles_darwin_sched(aosp_root)
    patch_selinux_darwin_strlcpy(aosp_root)
    patch_selinux_darwin_xattr_compat(aosp_root)
    patch_selinux_darwin_pthread_once(aosp_root)
    patch_selinux_darwin_sockaddr_storage_shim(aosp_root)
    patch_selinux_darwin_stdio_ext_shim(aosp_root)
    patch_selinux_darwin_sys_vfs_shim(aosp_root)
    patch_selinux_darwin_netlink_constants(aosp_root)
    patch_selinux_label_file_xattr_macro_compat(aosp_root)
    patch_selinux_darwin_gettid(aosp_root)
    patch_checkpolicy_darwin_network_compat(aosp_root)
    patch_mkbootfs_darwin_sysmacros(aosp_root)
    patch_toybox_darwin_availability_warning(aosp_root)
    patch_kmod_darwin_endian(aosp_root)
    patch_kmod_darwin_uadd_overflow(aosp_root)
    patch_kmod_darwin_elf_header(aosp_root)
    patch_kmod_darwin_time_compat(aosp_root)
    patch_e2fsdroid_darwin_capability_shim(aosp_root)
    patch_libcutils_darwin_capability_shim(aosp_root)
    patch_libcutils_darwin_fs_config_sources(aosp_root)
    patch_adevice_darwin_disabled(aosp_root)
    patch_selinux_host_uapi_headers(aosp_root)
    patch_java_fuzz_darwin_jni_modules(aosp_root)
    patch_trusty_host_package_linux_musl(aosp_root)
    patch_virtualization_host_tests_darwin(aosp_root)
    patch_cts_hostside_jni_tests_darwin(aosp_root)


if __name__ == "__main__":
    main()
