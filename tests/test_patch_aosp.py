#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCH_SCRIPT = REPO_ROOT / "scripts" / "patch-aosp.py"


def load_patch_module():
    spec = importlib.util.spec_from_file_location("patch_aosp", PATCH_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {PATCH_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PatchAospTests(unittest.TestCase):
    def test_input_rust_missing_bindgen_constants_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            input_path = root / "frameworks/native/libs/input/rust/input.rs"
            input_path.parent.mkdir(parents=True)
            input_path.write_text(
                textwrap.dedent(
                    """\
                    use std::fmt;

                    #[repr(u32)]
                    pub enum SourceClass {
                        None = input_bindgen::AINPUT_SOURCE_CLASS_NONE,
                    }

                    pub fn action_name(action: u32) -> &'static str {
                        let masked = action & input_bindgen::AMOTION_EVENT_ACTION_MASK;
                        match masked {
                            input_bindgen::AMOTION_EVENT_ACTION_DOWN => "down",
                            _ => "other",
                        }
                    }

                    pub const OBSCURED: u32 =
                            input_bindgen::AMOTION_EVENT_FLAG_WINDOW_IS_OBSCURED;
                    """
                )
            )

            module.patch_input_rust_missing_bindgen_constants(root)
            first = input_path.read_text()
            module.patch_input_rust_missing_bindgen_constants(root)
            second = input_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("mod hans_bindgen_constants", first)
        self.assertIn("HansOS local: bindgen drops some android/input.h enum constants", first)
        self.assertIn("hans_bindgen_constants::AINPUT_SOURCE_CLASS_NONE", first)
        self.assertIn("hans_bindgen_constants::AMOTION_EVENT_ACTION_MASK", first)
        self.assertIn("hans_bindgen_constants::AMOTION_EVENT_ACTION_DOWN", first)
        self.assertIn("hans_bindgen_constants::AMOTION_EVENT_FLAG_WINDOW_IS_OBSCURED", first)
        self.assertNotIn("input_bindgen::AINPUT_SOURCE_CLASS_NONE", first)
        self.assertNotIn("input_bindgen::AMOTION_EVENT_ACTION_MASK", first)
        self.assertNotIn("input_bindgen::AMOTION_EVENT_FLAG_WINDOW_IS_OBSCURED", first)

    def test_nanopb_soong_plugin_detection_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            generator_path = root / "external/nanopb-c/generator/nanopb_generator.py"
            generator_path.parent.mkdir(parents=True)
            generator_path.write_text(
                textwrap.dedent(
                    """\
                    import sys
                    import os.path

                    def main_plugin():
                        pass

                    def main_cli():
                        pass

                    if __name__ == '__main__':
                        # Check if we are running as a plugin under protoc
                        if 'protoc-gen-' in sys.argv[0] or '--protoc-plugin' in sys.argv:
                            main_plugin()
                        else:
                            main_cli()
                    """
                )
            )

            module.patch_nanopb_soong_plugin_detection(root)
            first = generator_path.read_text()
            module.patch_nanopb_soong_plugin_detection(root)
            second = generator_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("soong_wrapped_plugin", first)
        self.assertIn("__soong_entrypoint_redirector__.py", first)
        self.assertIn("Soong's Python launcher hides the protoc-gen-* argv name", first)
        self.assertIn("not sys.stdin.isatty()", first)

    def test_binder_tokio_missing_sys_import_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            binder_tokio_path = root / "frameworks/native/libs/binder/rust/binder_tokio/lib.rs"
            binder_tokio_path.parent.mkdir(parents=True)
            binder_tokio_path.write_text(
                textwrap.dedent(
                    """\
                    use binder::binder_impl::BinderAsyncRuntime;
                    use binder::{BinderAsyncPool, StatusCode};

                    fn status() -> StatusCode {
                        sys::android_c_interface_StatusCode_UNKNOWN_ERROR
                    }
                    """
                )
            )

            module.patch_binder_tokio_missing_sys_import(root)
            first = binder_tokio_path.read_text()
            module.patch_binder_tokio_missing_sys_import(root)
            second = binder_tokio_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("use binder::sys;", first)
        self.assertIn("binder_tokio uses binder::sys status constants", first)

    def test_keystore2_aaid_bindgen_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            bp_path = root / "system/security/keystore2/aaid/Android.bp"
            bp_path.parent.mkdir(parents=True)
            bp_path.write_text(
                textwrap.dedent(
                    """\
                    rust_bindgen {
                        name: "libkeystore2_aaid_bindgen",
                        wrapper_src: "aaid.hpp",
                        bindgen_flags: [
                            "--allowlist-function=aaid_keystore_attestation_id",
                        ],
                    }
                    """
                )
            )

            module.patch_keystore2_aaid_bindgen_missing_symbols(root)
            first = bp_path.read_text()
            module.patch_keystore2_aaid_bindgen_missing_symbols(root)
            second = bp_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("keystore2 AAID C ABI functions", first)
        self.assertIn("pub fn aaid_keystore_attestation_id", first)
        self.assertEqual(first.count("aaid_keystore_attestation_id(uid"), 1)

    def test_keystore2_apc_compat_bindgen_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            bp_path = root / "system/security/keystore2/apc_compat/Android.bp"
            bp_path.parent.mkdir(parents=True)
            bp_path.write_text(
                textwrap.dedent(
                    """\
                    rust_bindgen {
                        name: "libkeystore2_apc_compat_bindgen",
                        wrapper_src: "apc_compat.hpp",
                        bindgen_flags: [
                            "--allowlist-function=abortUserConfirmation",
                        ],
                    }
                    """
                )
            )

            module.patch_keystore2_apc_compat_bindgen_missing_symbols(root)
            first = bp_path.read_text()
            module.patch_keystore2_apc_compat_bindgen_missing_symbols(root)
            second = bp_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("keystore2 APC compat declarations", first)
        self.assertIn("pub type ApcCompatServiceHandle", first)
        self.assertIn("pub struct ApcCompatUiOptions", first)
        self.assertIn("pub struct ApcCompatCallback", first)
        self.assertIn("pub static INVALID_SERVICE_HANDLE", first)
        self.assertIn("pub fn promptUserConfirmation", first)
        self.assertEqual(first.count("pub fn promptUserConfirmation"), 1)

    def test_simpleperf_profcollect_bindgen_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            bp_path = root / "system/extras/simpleperf/Android.bp"
            bp_path.parent.mkdir(parents=True)
            bp_path.write_text(
                textwrap.dedent(
                    """\
                    rust_bindgen {
                        name: "libsimpleperf_profcollect_bindgen",
                        wrapper_src: "include/simpleperf_profcollect.hpp",
                        crate_name: "simpleperf_profcollect_bindgen",
                        source_stem: "bindings",
                    }
                    """
                )
            )

            module.patch_simpleperf_profcollect_bindgen_missing_functions(root)
            first = bp_path.read_text()
            module.patch_simpleperf_profcollect_bindgen_missing_functions(root)
            second = bp_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("simpleperf profcollect C ABI functions", first)
        self.assertIn("bindgen_flags", first)
        self.assertIn("pub fn IsETMDriverAvailable", first)
        self.assertIn("pub fn RunRecordCmd", first)
        self.assertIn("pub fn ResetLogFile", first)
        self.assertEqual(first.count("pub fn RunRecordCmd"), 1)

    def test_ota_from_raw_img_delta_generator_path_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            ota_path = root / "build/make/tools/releasetools/ota_from_raw_img.py"
            ota_path.parent.mkdir(parents=True)
            ota_path.write_text(
                textwrap.dedent(
                    """\
                    import os

                    def ResolveBinaryPath(filename, search_path):
                      if not search_path:
                        return filename
                      if not os.path.exists(search_path):
                        return filename
                      path = os.path.join(search_path, "bin", filename)
                      if os.path.exists(path):
                        return path
                      path = os.path.join(search_path, filename)
                      if os.path.exists(path):
                        return path
                      return path


                    def main(argv):
                      parser = object()
                      args = parser.parse_args(argv[1:])
                      print(args.search_path)
                    """
                )
            )

            module.patch_ota_from_raw_img_delta_generator_path(root)
            first = ota_path.read_text()
            module.patch_ota_from_raw_img_delta_generator_path(root)
            second = ota_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("def AddHostToolSearchPath(search_path):", first)
        self.assertIn("payload_signer invokes delta_generator by basename", first)
        self.assertIn("AddHostToolSearchPath(args.search_path)", first)
        self.assertEqual(first.count("def AddHostToolSearchPath"), 1)
        self.assertEqual(first.count("AddHostToolSearchPath(args.search_path)"), 1)

    def test_dexpreopt_gen_product_packages_path_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            gen_path = root / "build/soong/dexpreopt/dexpreopt_gen/dexpreopt_gen.go"
            gen_path.parent.mkdir(parents=True)
            gen_path.write_text(
                textwrap.dedent(
                    """\
                    package main

                    import (
                    \t"os"
                    \t"path/filepath"
                    \t"strings"

                    \t"android/soong/android"
                    \t"android/soong/dexpreopt"
                    )

                    func writeScripts(ctx android.BuilderContext, globalSoong *dexpreopt.GlobalSoongConfig,
                    \tglobal *dexpreopt.GlobalConfig, module *dexpreopt.ModuleConfig, dexpreoptScriptPath string,
                    \tproductPackagesPath string) {
                    \tdexpreoptRule, err := dexpreopt.GenerateDexpreoptRule(
                    \t\tctx, globalSoong, global, module, android.PathForTesting(productPackagesPath))
                    \t_ = dexpreoptRule
                    \t_ = err
                    }
                    """
                )
            )

            module.patch_dexpreopt_gen_product_packages_path(root)
            first = gen_path.read_text()
            module.patch_dexpreopt_gen_product_packages_path(root)
            second = gen_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("func productPackagesAsPath", first)
        self.assertIn("PathForArbitraryOutput", first)
        self.assertIn("Make passes product_packages as an absolute OUT_DIR path", first)
        self.assertIn("productPackagesAsPath(ctx, productPackagesPath)", first)
        self.assertNotIn("module, android.PathForTesting(productPackagesPath))", first)
        self.assertEqual(first.count("func productPackagesAsPath"), 1)

    def test_rust_linux_arm64_host_prebuilts_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            bp_path = root / "prebuilts/rust/Android.bp"
            soong_path = root / "prebuilts/rust/soong/rustprebuilts.go"
            bp_path.parent.mkdir(parents=True)
            soong_path.parent.mkdir(parents=True)
            bp_path.write_text(
                textwrap.dedent(
                    """\
                    rust_defaults {
                        name: "rust_sysroot_defaults",
                        target: {
                            glibc: {
                                enabled: false,
                            },
                            // HansOS local: Linux/ARM64 host uses prebuilt Rust sysroot; keep source glibc_arm64 disabled.
                            darwin: {
                                enabled: false,
                            },
                        },
                    }

                    rust_toolchain_library {
                        name: "libstd",
                        target: {
                            linux_musl: {
                                rlibs: ["libpanic_unwind.rust_sysroot"],
                            },
                        },
                    }
                    """
                )
            )
            soong_path.write_text(
                textwrap.dedent(
                    """\
                    package rustprebuilts

                    type props struct {
                    \tTarget  struct {
                    \t\tLinux_glibc_x86_64 targetProps
                    \t\tLinux_glibc_x86    targetProps
                    \t\tLinux_glibc_arm64  targetProps
                    \t\tLinux_musl_x86_64  targetProps
                    \t\tLinux_musl_x86     targetProps
                    \t\tLinux_musl_arm64   targetProps
                    \t\tDarwin_x86_64      targetProps
                    \t}
                    }

                    func constructLibProps(rlib, solib bool) func(ctx android.LoadHookContext) {
                    \treturn func(ctx android.LoadHookContext) {
                    \t\tif ctx.Config().BuildOS == android.Linux {
                    \t\t\tp.Target.Linux_glibc_x86_64.addPrebuiltToTarget(ctx, name, rustDir, "linux-x86", "x86_64-unknown-linux-gnu", rlib, solib)
                    \t\t\tp.Target.Linux_glibc_x86.addPrebuiltToTarget(ctx, name, rustDir, "linux-x86", "i686-unknown-linux-gnu", rlib, solib)
                    \t\t\tp.Target.Linux_glibc_arm64.addPrebuiltToTarget(ctx, name, rustDir, "linux-arm64", "aarch64-unknown-linux-gnu", rlib, solib)
                    \t\t\t// Also populate musl arm64 prebuilts since HOST_CROSS_OS=linux_musl creates musl variants
                    \t\t\tp.Target.Linux_musl_x86_64.addPrebuiltToTarget(ctx, name, rustDir, "linux-musl-x86", "x86_64-unknown-linux-musl", rlib, solib)
                    \t\t\tp.Target.Linux_musl_x86.addPrebuiltToTarget(ctx, name, rustDir, "linux-musl-x86", "i686-unknown-linux-musl", rlib, solib)
                    \t\t\tp.Target.Linux_musl_arm64.addPrebuiltToTarget(ctx, name, rustDir, "linux-arm64", "aarch64-unknown-linux-gnu", rlib, solib)
                    \t\t} else if ctx.Config().BuildOS == android.LinuxMusl {
                    \t\t\tp.Target.Linux_musl_x86_64.addPrebuiltToTarget(ctx, name, rustDir, "linux-musl-x86", "x86_64-unknown-linux-musl", rlib, solib)
                    \t\t\tp.Target.Linux_musl_x86.addPrebuiltToTarget(ctx, name, rustDir, "linux-musl-x86", "i686-unknown-linux-musl", rlib, solib)
                    \t\t\tp.Target.Linux_musl_arm64.addPrebuiltToTarget(ctx, name, rustDir, "linux-arm64", "aarch64-unknown-linux-gnu", rlib, solib)
                    \t\t}
                    \t}
                    }
                    """
                )
            )

            module.patch_rust_linux_arm64_host_prebuilts(root)
            first_bp = bp_path.read_text()
            first_soong = soong_path.read_text()
            module.patch_rust_linux_arm64_host_prebuilts(root)
            second_bp = bp_path.read_text()
            second_soong = soong_path.read_text()

        self.assertEqual(first_bp, second_bp)
        self.assertEqual(first_soong, second_soong)
        self.assertIn("builds Rust sysroot from the local rustup-backed source tree", first_bp)
        self.assertIn("uses prebuilt libstd while lower sysroot crates build from source", first_bp)
        self.assertIn("glibc_arm64:", first_bp)
        self.assertIn("enabled: true,", first_bp)
        self.assertIn("enabled: false,", first_bp)
        self.assertNotIn("keep source glibc_arm64 disabled", first_bp)
        self.assertIn("Linux_glibc_arm64  targetProps", first_soong)
        self.assertNotIn("Linux_musl_arm64", first_soong)
        self.assertIn('"linux-arm64", "aarch64-unknown-linux-gnu"', first_soong)
        self.assertEqual(first_soong.count("Linux_glibc_arm64"), 2)

    def test_crosvm_linux_arm64_support_check_patch_is_idempotent(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            crosvm_path = root / "device/google/cuttlefish/host/libs/vm_manager/crosvm_manager.cpp"
            crosvm_path.parent.mkdir(parents=True)
            crosvm_path.write_text(
                textwrap.dedent(
                    """\
                    #include "host/libs/vm_manager/crosvm_manager.h"

                    #include <signal.h>
                    #include <sys/stat.h>
                    #include <sys/types.h>

                    namespace cuttlefish {
                    namespace vm_manager {

                    bool CrosvmManager::IsSupported() {
                    #ifdef __ANDROID__
                      return true;
                    #else
                      return HostSupportsQemuCli();
                    #endif
                    }

                    } // namespace vm_manager
                    } // namespace cuttlefish
                    """
                )
            )

            module.patch_cuttlefish_crosvm_linux_arm64_support_check(root)
            first = crosvm_path.read_text()
            module.patch_cuttlefish_crosvm_linux_arm64_support_check(root)
            second = crosvm_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("#include <unistd.h>", first)
        self.assertIn("Linux/ARM64 source check only needs accessible KVM", first)
        self.assertIn('#if defined(__linux__) && defined(__aarch64__)', first)
        self.assertIn('access("/dev/kvm", R_OK | W_OK) == 0', first)
        self.assertIn("HostSupportsQemuCli()", first)

    def test_crosvm_view_only_patch_uses_legacy_touch_args(self) -> None:
        module = load_patch_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            crosvm_path = root / "device/google/cuttlefish/host/libs/vm_manager/crosvm_manager.cpp"
            crosvm_path.parent.mkdir(parents=True)
            crosvm_path.write_text(
                textwrap.dedent(
                    """\
                    #include <cassert>
                    #include "host/libs/vm_manager/crosvm_manager.h"

                    void BuildCrosvmCommand() {
                      if (instance.enable_webrtc()) {
                        bool is_chromeos =
                            instance.boot_flow() ==
                                CuttlefishConfig::InstanceSpecific::BootFlow::ChromeOs ||
                            instance.boot_flow() ==
                                CuttlefishConfig::InstanceSpecific::BootFlow::ChromeOsDisk;
                        auto touch_type_parameter =
                            is_chromeos ? "--single-touch=" : "--multi-touch=";

                        auto display_configs = instance.display_configs();
                        CF_EXPECT(display_configs.size() >= 1);

                        int touch_idx = 0;
                        for (auto& display_config : display_configs) {
                          crosvm_cmd.Cmd().AddParameter(
                              touch_type_parameter,
                              "path=", instance.touch_socket_path(touch_idx++),
                              ",width=", display_config.width,
                              ",height=", display_config.height);
                        }
                        auto touchpad_configs = instance.touchpad_configs();
                        for (int i = 0; i < touchpad_configs.size(); ++i) {
                          auto touchpad_config = touchpad_configs[i];
                          crosvm_cmd.Cmd().AddParameter(
                              touch_type_parameter,
                              "path=", instance.touch_socket_path(touch_idx++),
                              ",width=", touchpad_config.width,
                              ",height=", touchpad_config.height,
                              ",name=", kTouchpadDefaultPrefix, i);
                        }
                        crosvm_cmd.Cmd().AddParameter("--rotary=",
                                                      instance.rotary_socket_path());
                        crosvm_cmd.Cmd().AddParameter("--keyboard=",
                                                      instance.keyboard_socket_path());
                        crosvm_cmd.Cmd().AddParameter("--switches=",
                                                      instance.switches_socket_path());
                      }
                    }
                    """
                )
            )

            module.patch_crosvm_manager_view_only_webrtc(root)
            first = crosvm_path.read_text()
            module.patch_crosvm_manager_view_only_webrtc(root)
            second = crosvm_path.read_text()

        self.assertEqual(first, second)
        self.assertIn("HANSOS_CVD_VIEW_ONLY_WEBRTC", first)
        self.assertIn('std::string(view_only_webrtc_env) != "false"', first)
        self.assertIn('instance.touch_socket_path(touch_idx++), ":"', first)
        self.assertNotIn('"path=", instance.touch_socket_path', first)


if __name__ == "__main__":
    unittest.main()
