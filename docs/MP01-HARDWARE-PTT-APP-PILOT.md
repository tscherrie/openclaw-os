# MP01 Hardware PTT and App Pilot

This note captures the current MP01 hardware path for the v1 voice-first build.

## Goal

HansOS should be usable without daily touch navigation. The MP01 middle side
button is the primary push-to-talk surface:

1. Hold starts a voice session.
2. Speech streams into the centered HansCanvas transcript.
3. Release finishes transcription and sends the turn to Hans.
4. The agent response replaces the transcript and remains centered until the
   next input or visual state.

HansCanvas remains a black, always-on status surface in user mode. It shows only
the current transcript, the current answer, and a compact status line.

## Implemented Path

- HansCanvas reports all key down/up events to `HansManagerService`.
- Push-to-talk candidates include Android assistant, voice assistant, camera,
  headset hook, button, symbol, picture symbol, period, and refresh-style keys.
- A device-specific key can be selected with the global setting
  `hansos_ptt_keycode`.
- `dumpsys hans voice` reports the last input key, action, PTT-candidate flag,
  voice session state, byte count, and transcription status. It never prints
  audio payloads.
- `dumpsys hans input <keyCode> <action> <pttCandidate>` is available for
  deterministic diagnostics and smoke tests.
- `scripts/mp01-ptt-diagnose.sh` captures input devices, keylayout hints,
  `getevent` output, and Hans voice diagnostics.

## App Pilot

The first general app-control layer is Accessibility-first. It is intentionally
small and auditable:

- Observe active package/class, visible text, node count, and event reason.
- Open Settings and inspect network state.
- Perform safe navigation actions such as Back/Home, click visible text, scroll,
  and enter text into a focused field.
- Enforce an allowlist, step limit, timeout, and audit marker before expanding
  beyond harmless navigation.

Sensitive operations such as calls, SMS, deleting data, sending purchases,
logins, PIN/password entry, and flashing remain manual-mode operations.

## Verification

Current required checks:

- Local static tests:
  - `python3 -m pytest tests/test_voice_first_static.py tests/test_patch_aosp.py`
- MP01 image marker verification:
  - `scripts/verify-mp01-image.sh --product-out <tdgsi_arm64_ab product out>`
- Physical MP01 smoke:
  - `scripts/smoke-mp01.sh --serial <serial> --include-degraded --require-baked-home`
- Button diagnosis:
  - `scripts/mp01-ptt-diagnose.sh --serial <serial> --duration 20`

## Current Limit

The Android KeyEvent PTT path is proven through HansCanvas and the full
SystemServer/runtime path. The real physical side-button press still needs one
live captured `getevent`/KeyEvent sample on the MP01 so that the final default
keycode can be locked down without relying on the broader candidate list.
