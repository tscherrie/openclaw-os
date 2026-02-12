# BUILD-SETUP.md — AOSP Build Environment for OpenClaw OS

*The "How To Compile An Entire Operating System On A Machine That Could Also Heat Your Apartment" Guide*

*Author: Forge (Backend Lead) · February 2026*

---

## 1. Hardware Requirements

### Minimum Specs (You'll Suffer But It'll Work)

| Resource | Minimum | Recommended | Our Setup (gx10-1) |
|----------|---------|-------------|---------------------|
| CPU | 8 cores | 16+ cores | 20 cores (ARM64 Grace) |
| RAM | 32 GB | 64+ GB | 120 GB |
| Storage | 400 GB free | 600+ GB free | 610 GB free (NVMe) |
| Arch | x86_64 or ARM64 | ARM64 (native) | ARM64 ✅ |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 LTS | Ubuntu (6.14.0-1015-nvidia) |
| GPU | Not needed for build | Nice for emulator | NVIDIA GB10 (Grace Blackwell) |

> **Why ARM64 native?** Cross-compiling AOSP for ARM targets on an ARM host eliminates the x86→ARM cross-compilation overhead. Native builds are ~15-20% faster. Also, it just feels right — like cooking Italian food in Italy.

### Our Build Machine: gx10-1

```
Machine:    NVIDIA DGX Spark (Grace Blackwell)
CPU:        20× ARM Neoverse V2 cores
RAM:        120 GB LPDDR5X
Storage:    931 GB NVMe (610 GB free)
GPU:        NVIDIA GB10 (Blackwell architecture)
Network:    Tailscale mesh + Gigabit LAN
OS:         Ubuntu 24.04, kernel 6.14.0-1015-nvidia
```

This machine has more RAM than most people have disk space. AOSP builds will feel like compiling a "Hello World" program. Almost.

---

## 2. Build Environment Setup

### 2.1 System Packages

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# AOSP build dependencies (the classics)
sudo apt install -y \
    git-core gnupg flex bison build-essential \
    zip curl zlib1g-dev libc6-dev-i386 \
    x11proto-core-dev libx11-dev lib32z1-dev \
    libgl1-mesa-dev libxml2-utils xsltproc unzip \
    fontconfig libncurses5 procps python3 python3-pip \
    rsync ccache libssl-dev bc cpio lz4

# ARM64 specific — no multilib needed (we ARE the target arch)
# On x86_64 you'd need lib32ncurses5-dev etc. We don't. Life is good.

# repo tool
mkdir -p ~/bin
curl https://storage.googleapis.com/git-repo-downloads/repo > ~/bin/repo
chmod a+x ~/bin/repo
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 2.2 Java / JDK

AOSP 14+ requires JDK 17 (bundled in prebuilts, but system JDK helps for tooling):

```bash
sudo apt install -y openjdk-17-jdk
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-arm64
```

### 2.3 Kotlin Compiler

For our custom AgentCoreService (because writing system services in Java in 2026 is like riding a horse on the Autobahn):

```bash
# Kotlin is bundled in AOSP prebuilts, but for standalone development:
sudo snap install kotlin --classic
# Or via SDKMAN:
curl -s "https://get.sdkman.io" | bash
sdk install kotlin
```

### 2.4 ccache Configuration

ccache is the difference between "I'll grab lunch" and "I'll grab a career change":

```bash
# Set up ccache (50GB should be plenty)
export USE_CCACHE=1
export CCACHE_EXEC=$(which ccache)
export CCACHE_DIR=~/.ccache
ccache -M 50G

# Add to ~/.bashrc
echo 'export USE_CCACHE=1' >> ~/.bashrc
echo 'export CCACHE_EXEC=$(which ccache)' >> ~/.bashrc
echo 'export CCACHE_DIR=~/.ccache' >> ~/.bashrc
```

After first full build, incremental builds drop from hours to minutes. ccache is love.

---

## 3. AOSP Source Sync

### 3.1 Initialize Repo

We're targeting **Android 15 (Vanilla Ice Cream)** — latest AOSP tag:

```bash
mkdir -p ~/aosp && cd ~/aosp

# Initialize with Android 15 branch
repo init -u https://android.googlesource.com/platform/manifest \
    -b android-15.0.0_r1 \
    --depth=1  # Shallow clone saves ~100GB

# For Pixel 8 (shiba) device tree:
# We'll add device-specific manifests in a local_manifests/ dir
mkdir -p .repo/local_manifests
```

### 3.2 Local Manifest for OpenClaw

```xml
<!-- .repo/local_manifests/openclaw.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
    <!-- OpenClaw OS overlay -->
    <remote name="openclaw" fetch="https://github.com/tscherrie" />
    
    <project path="packages/services/AgentCoreService"
             name="openclaw-os"
             remote="openclaw"
             revision="main"
             groups="openclaw" />
    
    <!-- Pixel 8 (shiba) device trees — from LineageOS or AOSP -->
    <!-- TODO: Add once we have device tree repos set up -->
</manifest>
```

### 3.3 Sync

```bash
# Full sync — grab coffee, watch a movie, contemplate the heat death of the universe
repo sync -j$(nproc) --optimized-fetch --no-tags

# On gx10-1 with 20 cores and good internet, this takes ~30-60 minutes
# The -j20 will max out your bandwidth beautifully
```

**Disk space after sync:** ~150-200GB for source, ~150-200GB for build output. Total: ~350-400GB. We have 610GB free. Comfortable.

---

## 4. Build Configuration

### 4.1 Product Definition

```bash
# Create OpenClaw product directory
mkdir -p device/openclaw/shiba

# device/openclaw/shiba/AndroidProducts.mk
# (Inherits from Pixel 8 "shiba" and adds our overlays)
```

```makefile
# device/openclaw/shiba/AndroidProducts.mk
PRODUCT_MAKEFILES := \
    $(LOCAL_DIR)/openclaw_shiba.mk

COMMON_LUNCH_CHOICES := \
    openclaw_shiba-userdebug \
    openclaw_shiba-eng
```

```makefile
# device/openclaw/shiba/openclaw_shiba.mk
$(call inherit-product, device/google/shusky/aosp_shiba.mk)

PRODUCT_NAME := openclaw_shiba
PRODUCT_DEVICE := shiba
PRODUCT_BRAND := OpenClaw
PRODUCT_MODEL := OpenClaw Phone
PRODUCT_MANUFACTURER := Agent Lab

# Include AgentCoreService
PRODUCT_PACKAGES += \
    AgentCoreService \
    AgentLauncher \
    TailscaleSystemService

# Remove default launcher
PRODUCT_PACKAGES_REMOVE += \
    Launcher3QuickStep

# System properties
PRODUCT_SYSTEM_PROPERTIES += \
    ro.openclaw.version=0.1.0 \
    ro.openclaw.agent.enabled=true \
    persist.openclaw.cloud.provider=anthropic
```

### 4.2 Build Commands

```bash
cd ~/aosp

# Set up environment
source build/envsetup.sh

# Select target
lunch openclaw_shiba-userdebug

# Build (all 20 cores, let's gooo)
m -j$(nproc)

# For just the AgentCoreService (faster iteration):
m AgentCoreService -j$(nproc)
```

### 4.3 Build Times (Estimated on gx10-1)

| Build Type | Estimated Time | Notes |
|------------|---------------|-------|
| Full clean build | 2-3 hours | First time, no ccache |
| Full build with ccache | 30-45 min | After first build |
| Incremental (framework) | 5-15 min | After touching frameworks/base |
| Single module | 1-3 min | Just AgentCoreService |

### 4.4 ARM64-Specific Build Notes

Building AOSP on ARM64 natively has some quirks:

1. **No multilib issues** — We don't need 32-bit libraries. Clean.
2. **Prebuilt toolchains** — AOSP ships x86_64 prebuilts. For ARM64 hosts, we need:
   ```bash
   # Use system clang instead of AOSP prebuilt (if prebuilt is x86-only)
   export ALLOW_MISSING_DEPENDENCIES=true
   # Or build the toolchain from source (preferred)
   ```
3. **Memory usage** — With 120GB RAM, we can run `-j20` without OOM. On lesser machines, use `-j$(( $(nproc) / 2 ))`.
4. **Ninja parallelism** — Set `NINJA_REMOTE_NUM_JOBS` if using distributed builds.

---

## 5. Testing & Flashing

### 5.1 Cuttlefish (Virtual Device)

For testing without physical hardware:

```bash
# Build Cuttlefish target
lunch aosp_cf_arm64_phone-userdebug
m -j$(nproc)

# Launch
launch_cvd --daemon
# Access via VNC or adb
adb connect vsock://cid:5555
```

Cuttlefish on ARM64 is native — no emulation overhead. Boots in seconds. This is how we'll do CI.

### 5.2 Pixel 8 Flashing

```bash
# Unlock bootloader (one-time, from stock Android):
# Settings → Developer Options → OEM Unlocking → Enable
# adb reboot bootloader
# fastboot flashing unlock

# Flash OpenClaw OS
cd out/target/product/shiba
fastboot flashall -w  # -w wipes data (first time only)

# Or flash individual partitions
fastboot flash system system.img
fastboot flash vendor vendor.img
fastboot flash boot boot.img
```

### 5.3 OTA Updates (Future)

```bash
# Generate OTA package
ota_from_target_files \
    -k build/make/target/product/security/testkey \
    out/target/product/shiba/obj/PACKAGING/target_files_intermediates/*.zip \
    openclaw-ota.zip
```

---

## 6. Development Workflow

### 6.1 Repository Structure (OpenClaw additions)

```
~/aosp/
├── frameworks/base/                    # AOSP framework (we modify)
│   └── services/core/java/com/openclaw/  # Our additions
├── packages/
│   ├── services/AgentCoreService/      # Our main system service
│   ├── apps/AgentLauncher/             # Prism's territory
│   └── services/TailscaleService/      # Tailscale integration
├── device/openclaw/shiba/              # Product definition
└── vendor/openclaw/                    # OpenClaw overlays & configs
```

### 6.2 Iterative Development

For fast iteration on AgentCoreService:

```bash
# Build just the service
m AgentCoreService -j$(nproc)

# Push to running device
adb root
adb remount
adb push $OUT/system/priv-app/AgentCoreService/AgentCoreService.apk \
    /system/priv-app/AgentCoreService/
adb shell stop
adb shell start
```

### 6.3 Debugging

```bash
# System service logs
adb logcat -s AgentCoreService:V

# All OpenClaw logs
adb logcat | grep -i openclaw

# Attach debugger to system_server
adb forward tcp:8601 jdwp:$(adb shell pidof system_server)
```

---

## 7. CI/CD Pipeline (Planned)

```yaml
# .github/workflows/build.yml (future)
name: OpenClaw OS Build
on: [push, pull_request]

jobs:
  build:
    runs-on: self-hosted  # gx10-1 as ARM64 runner
    steps:
      - name: Sync AOSP
        run: repo sync -j20 --optimized-fetch
      
      - name: Build
        run: |
          source build/envsetup.sh
          lunch openclaw_shiba-userdebug
          m -j$(nproc)
      
      - name: Boot Test (Cuttlefish)
        run: |
          launch_cvd --daemon
          adb wait-for-device
          adb shell getprop ro.openclaw.version
```

Self-hosted runner on gx10-1 because:
- ARM64 native builds (no cross-compilation)
- 120GB RAM (builds won't OOM)
- 610GB storage (enough for AOSP + ccache)
- Fast NVMe (I/O bound steps go brrrr)

---

## 8. Known Issues & Gotchas

| Issue | Workaround | Status |
|-------|------------|--------|
| AOSP prebuilt tools are x86_64 only | Use system alternatives or build from source | Investigating |
| `repo init` needs Python 3.9+ | Ubuntu 24.04 ships 3.12, we're fine | ✅ |
| Pixel 8 vendor blobs needed | Extract from factory image or use vendor partition | TODO |
| SELinux policies for AgentCoreService | Custom sepolicy rules needed | TODO |
| ccache first run is cold | Run full build once, then enjoy fast iterations | Known |

---

## 9. Quick Start (TL;DR)

```bash
# 1. Install deps
sudo apt install -y git-core gnupg flex bison build-essential zip curl \
    zlib1g-dev libssl-dev bc cpio lz4 python3 ccache openjdk-17-jdk

# 2. Get repo tool
mkdir -p ~/bin && curl https://storage.googleapis.com/git-repo-downloads/repo > ~/bin/repo
chmod a+x ~/bin/repo && export PATH="$HOME/bin:$PATH"

# 3. Init & sync AOSP
mkdir -p ~/aosp && cd ~/aosp
repo init -u https://android.googlesource.com/platform/manifest -b android-15.0.0_r1 --depth=1
repo sync -j$(nproc) --optimized-fetch

# 4. Set up ccache
export USE_CCACHE=1 && export CCACHE_EXEC=$(which ccache) && ccache -M 50G

# 5. Build
source build/envsetup.sh
lunch openclaw_shiba-userdebug
m -j$(nproc)

# 6. Flash
cd out/target/product/shiba && fastboot flashall -w

# 7. Celebrate 🎉
```

---

*"The best build system is one that works while you sleep."* — Forge, probably at 3 AM

*Document version: 1.0 · Sprint 1 · February 2026*
