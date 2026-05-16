# HansOS First Alpha Flows

## Flow 1: Command to Action

Intent:

```text
Hans, set the phone to focus mode.
```

Expected Cuttlefish behavior:

- Canvas sends the text to `IHansManager.submitIntent`.
- Manager forwards to runtime.
- Runtime emits:
  - `thinking`
  - `plan`
  - `action_started`
  - `action_completed`
  - `audit`
  - `done`
- Fake device-state provider records `focus_mode=true`.
- Canvas shows the action and an Undo affordance.

## Flow 2: Morning Agent

Trigger:

```text
Hans, start my morning.
```

Expected Cuttlefish behavior:

- Runtime reads fake calendar, fake notifications, and fake device state.
- Hans produces a spoken-style summary event.
- Hans proposes and executes safe default actions.
- Every action emits an audit event.

## Flow 3: App Control

Intent:

```text
Hans, open settings and show me network status.
```

Expected Cuttlefish behavior:

- Runtime emits `app_control_started`.
- Runtime launches a known target activity or fixture.
- Fake app-control provider emits observed screen state.
- Runtime emits `app_control_completed`.
- Canvas returns to foreground and shows the summary.

## Failure Behavior

For every flow:

- If runtime is missing, manager emits a degraded local fake response.
- If an action fails, Hans emits `error`, `repair_suggestion`, and `audit`.
- Emergency stop cancels active runtime work and moves state to `STOPPED`.

## Native WebRTC Input

The primary Cuttlefish alpha input path is real browser input through
WebRTC/crosvm touch. Launch with native input enabled and hardware composer set
to `auto`:

```text
HANSOS_START_WEBRTC=true
HANSOS_CVD_VIEW_ONLY_WEBRTC=false
HANSOS_HWCOMPOSER=auto
```

Expected browser state:

- The WebRTC page exposes `display_0`.
- The video track reports the Cuttlefish display size, currently `390x844`.
- Developer stop intents and the hardware Emergency Stop path record an
  `emergency_stop` audit event in `dumpsys hans`. The v1 Canvas default mode no
  longer exposes a visible Stop button.

## Developer Input Bridge

The bridge remains a fallback and diagnostic tool for view-only sessions. It
uses developer-only Canvas intents for the main commands so it is not affected
by display rotation or touch-socket diagnostics:

```text
scripts/hans-input-bridge.sh --connect 0.0.0.0:6520 quick focus
scripts/hans-input-bridge.sh --connect 0.0.0.0:6520 submit "plan my day"
scripts/hans-input-bridge.sh --connect 0.0.0.0:6520 stop
```

Raw UI tap helpers remain available for diagnostics:

```text
scripts/hans-input-bridge.sh --connect 0.0.0.0:6520 tap-desc "Hans live phrase"
scripts/hans-input-bridge.sh --connect 0.0.0.0:6520 dump
```

This bridge is a developer tool only. It does not replace the native
crosvm/WebRTC touch path.

The Cuttlefish smoke script validates this bridge by default before the direct
Binder fake-flow loop. Use `--skip-canvas-bridge` only when debugging a
headless Core/Runtime issue where Canvas is intentionally out of scope.
