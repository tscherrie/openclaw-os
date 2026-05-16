# HansOS Architecture

## Product Direction

HansOS is an OS-first agent system. The phone boots into Hans Canvas instead of
Launcher3. Hans has high autonomy, local rules, local memory, and local audit.
Classic app UI can appear temporarily when Hans needs to operate an app, but the
system always returns to Canvas.

## Voice-First UX Direction

HansOS v1 is not a small touch-first Android launcher. The intended default
interaction model is closer to a dictation recorder:

- The primary input is push-to-talk through the MP01 middle side button between
  the volume keys.
- Holding the button starts listening; releasing it ends the user turn and sends
  the captured speech to Hans.
- The display is primarily a status and visualization surface, not a control
  surface.
- Touch is reserved for setup, PIN/password entry, SIM/network configuration,
  recovery, emergency fallback, and explicitly delegated app surfaces that must
  be seen.

In normal operation, HansCanvas should render one centered live phrase area on a
black background:

- While the user speaks, the current transcript streams into the center of the
  display in bold white text.
- Only the current user input is shown; it remains visible until Hans starts
  answering.
- As Hans answers, the agent response replaces the user transcript and streams
  into the same centered bold white text area.
- The latest agent response remains centered until replaced by a new user input
  or by a visual artifact such as a photo, map, app view, warning, or setup
  screen.

Buttons, quick actions, text fields, and chat-history UI are developer or
fallback affordances. They must not be part of the v1 default user-facing mode.

## Process Split

HansOS intentionally splits authority from risky runtime work.

```text
SystemServer
  HansManagerService
    - binder authority: "hans"
    - agent state machine
    - runtime registration
    - rules and memory ownership
    - audit event ownership
    - emergency stop

Privileged app process
  HansRuntimeService
    - OpenAI provider integration
    - push-to-talk audio transcription
    - MP01 system provider adapters
    - Cuttlefish fake daily-phone providers
    - tool execution adapters
    - streaming event production

Home app
  HansCanvas
    - primary OS surface
    - no icons, no app drawer
    - speaks to HansManagerService through Binder
```

This avoids placing network, voice, and provider code inside `system_server`,
while still giving Hans OS-level authority through `HansManagerService`.

## Binder Contract

The canonical contract lives in `protocol/aidl/ai/hansos/agent`.

- `IHansManager` is the SystemServer-facing service exposed as `hans`.
- `IHansRuntime` is implemented by the runtime process and registered with the
  manager.
- `IHansStreamCallback` carries JSON event envelopes back to Canvas.

The first wire format is JSON to keep the early contract stable while the event
taxonomy changes quickly. Once the alpha flows harden, replace JSON envelopes
with typed parcelables.

## State Model

Hans starts in `STARTING`, reaches `IDLE`, then transitions through
`LISTENING`, `TRANSCRIBING`, `THINKING`, `ACTING`, `SPEAKING`, or `ERROR`.
`STOPPED` is reserved for emergency stop. State constants are mirrored in Java
for AOSP clients.

## Alpha Flow Strategy

Daily-phone APIs are represented by real Android-facing adapters plus
Cuttlefish fake implementations. Cuttlefish keeps deterministic fake data for
repeatable build/smoke gates. MP01 can switch to
`persist.hansos.context_provider=real` to use live phone state.

The fake layer covers:

- Calls
- SMS
- Calendar
- Notifications
- App-control fixtures

The MP01 system-provider layer covers:

- Battery and charging state.
- Active network transport and validation.
- SIM/operator state.
- Calendar instances for the current day.
- NotificationListener-backed notification snapshots.
- Focus mode through notification interruption/zen-mode APIs.
- Temporary Settings app launch for explicit app-control flows.

Sensitive intents such as calls, SMS, password/PIN handling, destructive
deletes, bootloader unlock, or flash operations must emit
`confirmation_required` plus `manual_mode_required` and stop before action.
