# HansOS Architecture

## Product Direction

HansOS is an OS-first agent system. The phone boots into Hans Canvas instead of
Launcher3. Hans has high autonomy, local rules, local memory, and local audit.
Classic app UI can appear temporarily when Hans needs to operate an app, but the
system always returns to Canvas.

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
    - voice provider integration
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
`THINKING`, `ACTING`, `SPEAKING`, or `ERROR`. `STOPPED` is reserved for
emergency stop. State constants are mirrored in Java for AOSP clients.

## Alpha Flow Strategy

Daily-phone APIs are represented by real Android-facing interfaces and
Cuttlefish fake implementations. This lets the first alpha prove phone flows
without waiting for Pixel hardware.

The fake layer covers:

- Calls
- SMS
- Calendar
- Notifications
- App-control fixtures
