# HansOS

HansOS is an agent-first Android operating system.

The phone does not boot into a launcher full of icons. It boots into Hans: a
personal, playful, highly autonomous agent with OS-level authority.

## North Star

HansOS is not a chatbot app. It is an AOSP-based mobile OS where:

- Hans is the primary interface.
- Apps exist as tools Hans can orchestrate.
- The first target is Cuttlefish, not a generic Android emulator.
- The first hardware candidate after Cuttlefish is Minimal Phone MP01.
- The first public surface is the Hans Canvas, not Launcher3.
- OpenAI is the default BYOK intelligence provider.
- Memory, rules, and audit logs are local and inspectable.
- There is no telemetry by default.

## Current Implementation

This repository has been rebooted from the legacy OpenClaw/Clawdroid prototype.
The old project is preserved under `archive/legacy-openclaw-os/`, and the Git
branch `legacy-openclaw-os-reference` points to the original checked-out state.

HansOS v0 contains the build-oriented skeleton for the first Cuttlefish alpha:

```text
aosp/
  device/hansos/cuttlefish/             Custom Cuttlefish product
  frameworks/base/.../HansManagerService SystemServer service skeleton
  packages/apps/HansCanvas/             Pure-agent launcher surface
runtime/HansRuntimeService/             Privileged runtime process
protocol/                               AIDL contract and shared constants
fakes/                                  Cuttlefish fake daily-phone providers
docs/                                   Architecture, build path, alpha flows
archive/                                Legacy project snapshot
```

## First Alpha Definition

The first alpha is successful when a Cuttlefish build:

1. Boots into Hans Canvas.
2. Starts `HansManagerService` from SystemServer.
3. Starts `HansRuntimeService` as a privileged persistent service.
4. Runs these flows end-to-end:
   - Command to action
   - Morning Agent
   - App Control
5. Records every autonomous action in a local audit stream.

## Design Defaults

- Product name: HansOS
- Agent name: Hans
- UI model: Pure Agent
- Recovery model: ADB only
- AOSP branch: `android-latest-release`
- Cuttlefish target base: `aosp_cf_arm64_only_phone-userdebug`
- Product target: `hansos_cf_arm64-trunk_staging-userdebug`
- Post-Cuttlefish hardware target: Minimal Phone MP01 via Android 14 GSI/Treble path
- LLM provider: OpenAI direct BYOK
- Voice direction: OpenAI Realtime, text/fake injection for early Cuttlefish
- Autonomy: autonomous defaults plus local rules and memory

## References

See:

- `docs/ARCHITECTURE.md`
- `docs/BUILD-PATH.md`
- `docs/ALPHA-FLOWS.md`
- `docs/SECURITY-MEMORY.md`
