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
5. When BYOK speech output is enabled, the final agent answer is also spoken
   through the phone speaker.

HansCanvas remains a black, always-on status surface in user mode. It shows only
the current transcript, the current answer, and a compact status line.

## Implemented Path

- HansCanvas reports all key down/up events to `HansManagerService`.
- Push-to-talk candidates include Android assistant, voice assistant, camera,
  headset hook, button, symbol, picture symbol, period, and refresh-style keys.
- On the physical MP01, the middle side button has been captured as
  `/dev/input/event1` with Linux key code `00fc`, which Android delivers to
  HansCanvas as `KEYCODE_REFRESH` / keycode `285`.
- A device-specific key can be selected with the global setting
  `hansos_ptt_keycode`.
- `dumpsys hans voice` reports the last input key, action, PTT-candidate flag,
  voice session state, byte count, and transcription status. It never prints
  audio payloads.
- `dumpsys hans input <keyCode> <action> <pttCandidate>` is available for
  deterministic diagnostics and smoke tests.
- `scripts/mp01-ptt-diagnose.sh` captures input devices, keylayout hints,
  `getevent` output, and Hans voice diagnostics.
- HansRuntimeService always owns speech output through OpenAI `audio/speech` and
  plays the result locally. HansCanvas remains display-only so the voice quality
  is consistent across images and devices.
- HansCanvas requests show-when-locked, turn-screen-on, and keep-screen-on so the
  black status surface can behave like a minimal lockscreen-adjacent appliance.
- PTT can be tuned with `persist.hansos.ptt_min_hold_ms` and
  `persist.hansos.ptt_max_hold_ms`. Very short accidental taps cancel, while
  over-long holds auto-finish instead of hanging the audio session.
- HansRuntimeService applies the v1 device policy on boot: gesture navigation,
  immersive fullscreen, hidden lockscreen notifications, hidden lockscreen
  controls, default MP01 PTT keycode, and default OpenAI speech settings.

## App Pilot

The first general app-control layer is Accessibility-first. It is intentionally
small and auditable:

- Observe active package/class, visible text, node count, and event reason.
- Open Settings and inspect network state.
- Perform safe navigation actions such as Back/Home, open safe apps, click
  visible text, scroll, and enter text into a focused field.
- Enforce an allowlist, step limit, timeout, and audit marker before expanding
  beyond harmless navigation.

Current generic commands include observing the current screen, opening Settings
network, Home, Back, Scroll, clicking visible text, and launching harmless
stock apps such as Clock or Calculator when available.

Sensitive operations such as calls, SMS, deleting data, sending purchases,
logins, PIN/password entry, and flashing remain manual-mode operations.

## Verification

Current required checks:

- Local static tests:
  - `python3 -m pytest tests/test_voice_first_static.py tests/test_patch_aosp.py`
- MP01 image marker verification:
  - `scripts/verify-mp01-image.sh --product-out <tdgsi_arm64_ab product out>`
- Physical MP01 smoke:
  - `scripts/smoke-mp01.sh --serial <serial> --include-degraded --include-openai-tts --require-baked-home`
- Button diagnosis:
  - `scripts/mp01-ptt-diagnose.sh --serial <serial> --duration 20`

## Current Device State

- The physical side-button mapping is known and covered by the default
  HansCanvas PTT candidate list.
- The current MP01 dev device also has `hansos_ptt_keycode=285` set explicitly
  as a global setting.
- OpenAI BYOK is configured on the current MP01 dev device for direct WiFi
  testing. The key itself is not stored in this repository.
