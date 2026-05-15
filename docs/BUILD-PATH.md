# HansOS Build Path

## AOSP Source

Use the current stable AOSP line:

```text
repo init --partial-clone --no-use-superproject \
  -u https://android.googlesource.com/platform/manifest \
  -b android-latest-release
repo sync -c --no-tags -j2
```

The repository includes a guarded bootstrap helper. It refuses to start if the
workspace has less than 250 GiB free, installs the `repo` tool under `.work/bin`
when needed, syncs AOSP with conservative parallelism, and integrates the HansOS
overlay:

```text
scripts/bootstrap-aosp.sh /Users/jeremias/clawdroid/.work/aosp
```

Current local workspace layout uses the external case-sensitive APFS volume:

```text
.work/aosp   -> /Volumes/HansOSBuild/hansos/aosp
.work/out    -> /Volumes/HansOSBuild/hansos/out
.work/ccache -> /Volumes/HansOSBuild/hansos/ccache
.work/tmp    -> /Volumes/HansOSBuild/hansos/tmp
```

The current primary build host is the Linux DGX/Tailscale machine:

```text
overlay:              /home/yearemias/hansos-overlay
AOSP_ROOT:            /home/yearemias/aosp-android14
HANSOS_EXTERNAL_ROOT: /home/yearemias/hansos-work
out:                  /home/yearemias/hansos-work/out/aosp-android14
```

The Mac remains the patch, documentation, control, and physical-device flash
station. Do not restart a macOS full build unless the Linux path is blocked or a
Darwin-specific compatibility check is needed.

Before building, load the external build paths:

```text
source scripts/aosp-build-env.sh
```

## Target

The first product target is:

```text
hansos_cf_arm64-trunk_staging-userdebug
```

It inherits from the ARM64 Cuttlefish phone target:

```text
aosp_cf_arm64_only_phone-userdebug
```

The first MP01 bring-up image is a system-only ARM64 GSI-style target:

```text
hansos_gsi_arm64-trunk_staging-userdebug
```

It intentionally uses a HansOS arm64-only GSI board config and builds only
`system.img`. The MP01 reports `arm64-v8a`, Treble, dynamic partitions, and
virtual A/B support, so the first physical test flashes only `/system` and
leaves boot, vendor, vbmeta, modem, and device-specific partitions untouched.
Because this first image does not build or flash a kernel, the product disables
OTA VINTF kernel-requirement packaging for this target.

## Integration Layout

Copy or overlay these repository paths into the AOSP tree:

```text
aosp/device/hansos/cuttlefish              -> device/hansos/cuttlefish
aosp/device/hansos/gsi                     -> device/hansos/gsi
aosp/frameworks/base/services/...          -> frameworks/base/services/...
aosp/packages/apps/HansCanvas              -> packages/apps/HansCanvas
runtime/HansRuntimeService                 -> packages/services/HansRuntimeService
protocol                                   -> packages/modules/HansProtocol
fakes                                      -> packages/modules/HansFakes
```

The repository includes an integration helper for this copy/patch step:

```text
scripts/integrate-aosp.sh /path/to/aosp
```

## Required Framework Hook

Add `HansManagerService` startup to `SystemServer.startOtherServices()` after
core services are ready:

```java
t.traceBegin("StartHansManagerService");
mSystemServiceManager.startService(ai.hansos.server.HansManagerService.class);
t.traceEnd();
```

The service publishes Binder under:

```text
hans
```

`scripts/integrate-aosp.sh` also patches `frameworks/base/services/core/Android.bp`
so `services.core` can compile against `hansos-agent-protocol`.

## Build Commands

```text
AOSP_ROOT=/home/yearemias/aosp-android14 \
HANSOS_EXTERNAL_ROOT=/home/yearemias/hansos-work \
JOBS=8 \
scripts/build-aosp-modules.sh HansCanvas HansRuntimeService hansos-agent-protocol hansos-fakes

AOSP_ROOT=/home/yearemias/aosp-android14 \
HANSOS_EXTERNAL_ROOT=/home/yearemias/hansos-work \
JOBS=8 \
scripts/build-aosp-full.sh

AOSP_ROOT=/home/yearemias/aosp-android14 \
HANSOS_EXTERNAL_ROOT=/home/yearemias/hansos-work \
JOBS=8 \
scripts/build-cuttlefish-host-linux.sh

AOSP_ROOT=/home/yearemias/aosp-android14 \
HANSOS_EXTERNAL_ROOT=/home/yearemias/hansos-work \
scripts/launch-cuttlefish.sh
```

When doing a targeted image rebuild after changing system/system_ext/product
contents, rebuild all dynamic partition images, `super.img`, and vbmeta as one
set. Otherwise Cuttlefish can reboot on dm-verity because `super.img` and
vbmeta describe different hashes:

```text
scripts/build-aosp-modules.sh images
```

For the validated interactive WebRTC launch on DGX, use native crosvm input and
the real Cuttlefish display path:

```text
HANSOS_START_WEBRTC=true
HANSOS_CVD_VIEW_ONLY_WEBRTC=false
HANSOS_HWCOMPOSER=auto
HANSOS_START_WEBRTC_SIG_SERVER=false
```

`HANSOS_HWCOMPOSER=auto` is required for the WebRTC client to expose
`display_0`. `hwcomposer=none` can still boot and expose ADB, but the browser
may show no video track. The crosvm touch arguments use the legacy prebuilt
format `--multi-touch=/tmp/.../touch_0.sock:390:844`; the newer
`path=...,width=...,height=...` form is not accepted by the current ARM64
Cuttlefish prebuilt.

For a real OpenAI BYOK test, launch Cuttlefish with a default Android network:

```text
scripts/setup-cuttlefish-host-network.sh <host-default-interface>
HANSOS_ENABLE_WIFI=true
```

Without this, host-level shell pings can still work while Android framework
network APIs report no active default network, causing the runtime's
`HttpURLConnection` path to fail DNS resolution.

On the DGX host this currently means:

```text
scripts/setup-cuttlefish-host-network.sh enP7s7
adb shell svc wifi enable
adb shell cmd wifi add-suggestion VirtWifi open
adb shell cmd wifi start-scan
```

The setup script creates/activates `cvd-wtap-01` and `cvd-etap-01`, assigns
`192.168.96.1/30` to the OpenWRT WAN side, enables IPv4 forwarding, and adds
NAT from the Cuttlefish WAN network to the host's default interface. If these
tap devices are missing or not owned by the launch user, `run_cvd` logs
`Operation not permitted` for `cvd-wtap-01`/`cvd-etap-01`, and the guest WiFi
can connect locally while external traffic still fails.

Keep the active Cuttlefish home path short, for example
`/home/yearemias/hcvd-<run-id>`. Long paths under
`/home/yearemias/hansos-work/...` can exceed Unix socket path limits for
Cuttlefish internals such as `rotary.sock`, which makes an otherwise good image
fail during launch.

Before launch on Linux, verify KVM access:

```text
test -r /dev/kvm -a -w /dev/kvm
```

If the device exists but is not accessible, grant the build user KVM access:

```text
sudo usermod -aG kvm yearemias
sudo setfacl -m u:yearemias:rw /dev/kvm
```

On macOS, use `scripts/build-cuttlefish-host-darwin.sh` only for the narrow
Darwin launcher compatibility path.

## Smoke Checks

```text
AOSP_ROOT=/home/yearemias/aosp-android14 \
HANSOS_EXTERNAL_ROOT=/home/yearemias/hansos-work \
scripts/smoke-cuttlefish.sh
```

Expected:

- `sys.boot_completed=1`
- Binder service `hans` exists
- HansRuntimeService registers with HansManagerService
- HansCanvas shows connected or degraded state
- Command -> Action flow emits `action_completed`
- Morning Agent flow emits `speech`
- App Control flow emits `app_control_completed`
- Manager memory contains runtime audit events
- Emergency stop reaches agent state `STOPPED`
- Native browser input reaches the guest through WebRTC/crosvm touch. A center
  click on the visible Stop control should create an `emergency_stop` audit
  event.

For fallback view-only WebRTC sessions, drive Canvas from the developer machine
with:

```text
scripts/hans-input-bridge.sh --connect 0.0.0.0:6520 quick focus
scripts/hans-input-bridge.sh --connect 0.0.0.0:6520 submit "plan my day"
scripts/hans-input-bridge.sh --connect 0.0.0.0:6520 stop
```

The bridge's normal `submit`, `quick`, `stop`, and `retry` commands use
developer-only Canvas intents. The raw `tap`, `tap-desc`, and `tap-text`
commands are kept for crosvm/WebRTC input diagnostics.

`scripts/smoke-cuttlefish.sh` runs the Canvas bridge check by default. Add
`--skip-canvas-bridge` only for narrow Core/Runtime debugging.

For the native WebRTC touch path, capture host state and crosvm input errors
with:

```text
scripts/diagnose-cuttlefish-input.sh
```

## Post-Cuttlefish Hardware Step: Minimal Phone MP01

MP01 is the first planned physical-device target, but only after the
deterministic Cuttlefish alpha passes. Treat it as an Android 14 GSI/Treble
bring-up path, not as a Pixel-device replacement.

Use the host split below for the first MP01 pass:

- DGX/Linux remains the build and image-production machine.
- Mac remains the preferred USB host for MP01 ADB, local prompt handling, and
  smoke testing after boot.
- DGX/Linux remains the fallback/known-good fastboot host if macOS fastboot
  shows MP01 bootloader USB read errors again.
- Transfer images from DGX to Mac over Tailscale or rsync and verify checksums
  before any Mac-hosted flash.
- The flash helper now supports both start states: authorized Android/ADB and
  direct bootloader fastboot / fastbootd.

Reference guide:

```text
https://chardidath.ing/posts/mp01-flashing-guide/
```

MP01 entry criteria:

- Cuttlefish full build succeeds.
- Cuttlefish smoke passes with HansManagerService, HansRuntimeService, and
  HansCanvas.
- The three alpha flows pass against fake providers.
- View-only WebRTC is operable through the developer-only ADB input bridge, or
  native crosvm/WebRTC input has been proven stable.
- A degraded-runtime path and emergency stop are verified.
- Stock MP01 build information, partition layout, AVB state, and rollback path
  are recorded before flashing.

Current MP01 host state:

- Mac is useful for ADB/prompt handling, but DGX/Linux is the preferred
  flashing host for MP01 fastbootd writes.
- The device enumerates over macOS USB as product `MP01`, vendor `ALONG`,
  decimal vendor ID `3725`, decimal product ID `8220`, serial
  `MP0125031802636`. Linux reports the same MP01 USB ID as hex `0e8d:201c`.
- Local ADB is authorized:
  `MP0125031802636 device product:MP01 model:MP01 device:MP01`.
- Mac platform-tools are present; `fastboot` was updated to version
  `37.0.0-14910828` during bring-up.
- Mac ADB is stable. MP01 bootloader-fastboot reaches the flash command on
  macOS, but direct and `-S 64M` sparse transfers both fail with USB write
  errors (`e00002ed` / `e00002d8` / `e00002c0`). Use DGX/Linux USB as the
  fastboot fallback.
- Stock build: `Minimal_Phone/MP01/MP01:14/UP1A.260104.1611/mp1V1254:user/release-keys`.
- Manufacturer/brand/model/device/product: `ALONG` / `Minimal_Phone` / `MP01`
  / `MP01` / `MP01`.
- Android `14`, SDK `34`, security patch `2025-11-05`, incremental
  `mp1V1254`.
- Hardware/platform: MediaTek `mt6789`, ABI
  `arm64-v8a,armeabi-v7a,armeabi`.
- Treble is enabled; dynamic partitions are enabled; current slot is `_a`.
- Pre-unlock stock inventory showed `ro.boot.verifiedbootstate=green`,
  `ro.boot.flash.locked=1`, `ro.boot.vbmeta.device_state=locked`.
- Current bring-up state after the approved unlock/plain-GSI recovery loop is
  unlocked/orange. Do not pass `--unlock` again unless a fresh preflight proves
  the bootloader is locked.
- Root mounts are read-only dynamic partitions:
  `/`, `/system_ext`, `/vendor`, `/product`, `/vendor_dlkm`, `/odm_dlkm`.
  `/data` is `f2fs` with about `109G` total and `83G` available at inventory
  time.
- `/dev/block/by-name` includes A/B boot-critical partitions: `boot_a/b`,
  `init_boot_a/b`, `vendor_boot_a/b`, `dtbo_a/b`, `vbmeta_a/b`,
  `vbmeta_system_a/b`, `vbmeta_vendor_a/b`, plus a shared `super` partition.
- `lpdump` shows `super` size `9663676416` bytes with slot-`a` logical
  partitions `system_a`, `system_ext_a`, `product_a`, `vendor_a`,
  `vendor_dlkm_a`, and `odm_dlkm_a`. The device is virtual A/B and currently
  has `*-cow` partitions from an update state.

MP01 bring-up order:

1. Use Mac for ADB visibility and prompt handling when convenient, but use
   DGX/Linux for MP01 fastbootd flashing because macOS fastboot loses the USB
   transfer during large `system.img` writes.
2. Before any destructive step, reboot to bootloader manually or with explicit
   permission only, then record `fastboot getvar all`, current slot state, and
   unlock/AVB warnings.
3. Confirm fastbootd access separately before flashing dynamic partitions.
4. On DGX, build or adapt a HansOS GSI-style `system.img` from the validated
   Cuttlefish overlay.
5. Copy the image artifact and checksum from DGX to Mac, then verify the
   checksum locally on the Mac if the Mac is the flashing host.
6. Flash only the minimum required image first, starting with `system.img`.
   After flashing, erase `userdata` and `metadata`; the public MP01 GSI flow
   requires this cleanup for a clean first boot.
7. Boot once with OpenAI disabled and fake providers enabled.
8. From the active USB host, run a reduced smoke check: boot complete, `hans` Binder,
   runtime registration, Canvas home behavior, degraded behavior, and emergency
   stop.
9. Only after the fake path is stable, test OpenAI BYOK manually.

The plain upstream AOSP GSI path was useful for proving that the MP01 accepts a
`system.img` flash, but it repeatedly returned to the Orange State screen and
did not count as a boot. The active hardware path is now a
Lineage/TrebleDroid-derived MP01 image, because that base is known to boot on
this hardware while still letting HansOS install deeply into `/system`.

HansOS uses the Lineage/TrebleDroid GSI product:

```text
treble_arm64_bvN-bp1a-userdebug
```

The overlay patches the Lineage/TrebleDroid source to install `HansCanvasSystem`
and `HansRuntimeServiceSystem` into `/system/priv-app`, add
`HansManagerService` to `system_server`, and hand HOME to HansCanvas after
setup. The first physical pass still flashes only `system.img`, matching the
public MP01 GSI flow and keeping stock `vendor`, `product`, `system_ext`,
`boot`, and `vbmeta` unchanged unless a later blocker proves otherwise.

Build path on DGX:

```text
cd /home/yearemias/hansos-overlay
scripts/integrate-mp01-lineage.sh /home/yearemias/los22-hansos
cd /home/yearemias/los22-hansos
source build/envsetup.sh
lunch treble_arm64_bvN-bp1a-userdebug
OUT_DIR=/home/yearemias/hansos-work/out/los22-hansos \
  CCACHE_DIR=/home/yearemias/hansos-work/ccache \
  USE_CCACHE=1 \
  USE_HOST_MUSL=true \
  BUILD_BROKEN_MISSING_REQUIRED_MODULES=true \
  m systemimage

/home/yearemias/hansos-overlay/scripts/verify-mp01-image.sh \
  --product-out /home/yearemias/hansos-work/out/los22-hansos/target/product/tdgsi_arm64_ab
```

On ARM64 Linux hosts, `integrate-mp01-lineage.sh` also provisions native
`clang++-19`/`lld-19` when possible. The Lineage patcher then routes only
Android ARM64 shared-library link steps through that native toolchain and
removes the Android prebuilt-only regalloc advisor flag. Compile steps and host
tools still use the Lineage prebuilts.

Current verified MP01 image artifact:

```text
DGX: /home/yearemias/hansos-work/out/los22-hansos/target/product/tdgsi_arm64_ab/system.img
Mac: /Users/jeremias/clawdroid/.work/mp01/system.img
SHA256: e5080d0453e22c232ce58f0698d2f25ff50af3311528680895944823f47adec0
```

Final Alpha 2 MP01 image:

```text
Built: 2026-05-15 17:09:45 +0300 on DGX / gx10-1
Build log: /home/yearemias/hansos-overlay/logs/mp01-byok-systemimage-retry-20260515-141134.log
Verify: scripts/verify-mp01-image.sh passed
Cycle log: /home/yearemias/hansos-overlay/logs/mp01-alpha2-20260515-171214
Result: scripts/mp01-alpha2-cycles.sh --cycles 3 passed
```

After copying the image to the chosen USB host, use the serial-checked flash
helper. From a booted, authorized MP01:

```text
scripts/flash-mp01-system.sh --serial MP0125031802636 \
  --image .work/mp01/system.img
```

If `adb reboot fastboot` returns to Android instead of entering fastbootd, use
DGX/Linux and let the helper enter fastbootd from the bootloader. The MP01
bootloader reports product alias `Z10`; fastbootd reports `MP01`, and the
helper accepts both for this serial-checked path.

The macOS direct-bootloader fallback reached the transfer but failed on USB;
it is kept for diagnostics, not as the preferred MP01 flashing route:

```text
scripts/flash-mp01-system.sh --serial MP0125031802636 \
  --direct-bootloader \
  --sparse-size 64M \
  --image .work/mp01/system.img
```

From bootloader fastboot or fastbootd:

```text
scripts/flash-mp01-system.sh --serial MP0125031802636 \
  --from-fastboot \
  --image .work/mp01/system.img
```

To wait for either Mac or DGX USB visibility and then automatically choose the
right ADB/Fastboot flash path, use:

```text
scripts/watch-mp01-autoflash.sh --serial MP0125031802636 \
  --image .work/mp01/system.img
```

Add `--unlock` only if a fresh preflight capture shows the bootloader is still
locked. The current MP01 bring-up state is already unlocked/orange.

On the DGX flashing host, `adb` is available as `/usr/bin/adb`. If `fastboot`
is not installed globally, use the previously built Android host tool:

```text
FASTBOOT=/home/yearemias/hansos-work/out/aosp-android14/host/linux-arm64/bin/fastboot
```

The DGX also has HansOS MP01 udev rules installed at:

```text
/etc/udev/rules.d/51-hansos-mp01.rules
```

Those rules cover the observed MP01 USB ID `0e8d:201c`, generic MediaTek
`0e8d`, and Google/Android fastboot `18d1`, with `plugdev` access and
`uaccess` tagging.
The repo helper for recreating them is:

```text
scripts/setup-mp01-dgx-usb-rules.sh
```

Current physical MP01 result:

```text
Host: DGX / gx10-1
Flash mode: ADB -> bootloader -> fastbootd
Flashed partition: system_a
Image SHA256: e5080d0453e22c232ce58f0698d2f25ff50af3311528680895944823f47adec0
Boot: sys.boot_completed=1, dev.bootcomplete=1
Build fingerprint: Minimal/treble_arm64_bvN/tdgsi_arm64_ab:15/BP1A.250505.005/eng.yearem:userdebug/test-keys
Smoke: scripts/smoke-mp01.sh --include-degraded --require-baked-home passed
Repeatability: 3 clean flash/boot/smoke cycles passed
OpenAI BYOK: one physical MP01 hardware prompt passed, then key/proxy cleanup verified
```

The first boot required marking setup complete and disabling
`org.lineageos.setupwizard` on the test device so HansCanvas could become the
HOME surface. The smoke helper now performs this MP01 alpha provisioning step
before asserting HOME.

MP01 Alpha 2 hardens this into a repeatability gate. The image must be rebuilt
from the overlay, verified before flashing, and then pass three clean hardware
cycles with baked-HOME enforcement:

```text
cd /home/yearemias/hansos-overlay
scripts/integrate-mp01-lineage.sh /home/yearemias/los22-hansos
cd /home/yearemias/los22-hansos
source build/envsetup.sh
lunch treble_arm64_bvN-bp1a-userdebug
OUT_DIR=/home/yearemias/hansos-work/out/los22-hansos \
  CCACHE_DIR=/home/yearemias/hansos-work/ccache \
  USE_CCACHE=1 \
  USE_HOST_MUSL=true \
  BUILD_BROKEN_MISSING_REQUIRED_MODULES=true \
  m -j28 systemimage

/home/yearemias/hansos-overlay/scripts/verify-mp01-image.sh \
  --product-out /home/yearemias/hansos-work/out/los22-hansos/target/product/tdgsi_arm64_ab

ADB=/usr/bin/adb \
FASTBOOT=/home/yearemias/hansos-work/out/aosp-android14/host/linux-arm64/bin/fastboot \
scripts/mp01-alpha2-cycles.sh \
  --serial MP0125031802636 \
  --image /home/yearemias/hansos-work/out/los22-hansos/target/product/tdgsi_arm64_ab/system.img \
  --cycles 3
```

`scripts/mp01-alpha2-cycles.sh` flashes `system.img`, erases `userdata` and
`metadata`, runs the fake-flow smoke with `--require-baked-home`, reboots once,
and checks that HansCanvas remains HOME and the runtime still registers. If
SetupWizard has to be disabled at runtime, Alpha 2 fails by design.

Bring-up note: a first plain HansOS/AOSP `system.img` flashed cleanly to
`system_a`, but the MP01 repeatedly returned to the Orange State screen even
after `userdata`/`metadata` were erased. That is not treated as success. The
Lineage/TrebleDroid path keeps the MP01-compatible base and layers HansOS
components onto it.

The unlock command still requires phone-side confirmation when the bootloader
shows the warning screen. After flashing and rebooting, run:

```text
scripts/smoke-mp01.sh --serial MP0125031802636 \
  --boot-timeout 900 \
  --include-degraded \
  --require-baked-home \
  --verbose
```

MP01 non-goals for the first hardware pass:

- No relock attempt until a stock rollback image and boot recovery path are
  proven.
- No vendor, boot, vbmeta, or radio partition changes unless the GSI path proves
  insufficient.
- No OpenAI-dependent pass/fail gate for the first physical boot.
