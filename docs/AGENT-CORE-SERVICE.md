# AgentCoreService — Technical Specification

*Written by Forge, Backend Lead @ Agent Lab*
*Sprint 1 — February 2026*

> "Every great operating system needs a soul. Ours just happens to be
> running on a cloud LLM and making phone calls on your behalf." — Forge

---

## Overview

The **AgentCoreService** is the central nervous system of OpenClaw OS. It's an
Android System Service that:

1. Receives user input (text, voice, intents) from the Agent Canvas
2. Builds context (time, location, history, device state)
3. Sends requests to LLM providers (Anthropic Claude, OpenAI, local models)
4. Handles tool calls (phone, messages, smart home, etc.)
5. Streams responses back to the UI

It's the bridge between "the user wants something" and "something happens."

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     Agent Canvas (Prism)                      │
│              Voice Input · Text Input · Cards                 │
└──────────────────┬───────────────────────────┬───────────────┘
                   │ IAgentCoreService (AIDL)  │ IAgentEventListener
                   ▼                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    AgentCoreService                           │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ CloudBridge   │  │ ContextMgr   │  │ CapabilityMgr    │   │
│  │              │  │              │  │                  │   │
│  │ • Anthropic  │  │ • System     │  │ • can_communicate│   │
│  │ • OpenAI     │  │   Prompt     │  │ • can_navigate   │   │
│  │ • Local      │  │ • History    │  │ • can_purchase   │   │
│  │ • Streaming  │  │ • Location   │  │ • can_control_*  │   │
│  └──────┬───────┘  │ • Calendar   │  └──────────────────┘   │
│         │          │ • Device     │                          │
│         │          │ • Audit Log  │  ┌──────────────────┐   │
│         │          └──────────────┘  │ ToolRegistry      │   │
│         │                            │                  │   │
│         └────── LLM Response ───────▶│ • phone_call     │   │
│                 (with tool calls)     │ • send_message   │   │
│                                      │ • camera         │   │
│                                      │ • calendar       │   │
│                                      │ • smart_home     │   │
│                                      │ • app_control    │   │
│                                      │ • device_settings│   │
│                                      └────────┬─────────┘   │
│                                               │             │
│  ┌────────────────────────┐  ┌───────────────┴──────────┐  │
│  │ AccessibilityBridge     │  │ TailscaleBridge           │  │
│  │ (app control fallback)  │  │ (mesh networking)         │  │
│  └────────────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
src/packages/AgentCoreService/
├── Android.bp                          # Build configuration
├── config/
│   └── privapp-permissions-openclaw-agent.xml
├── src/
│   ├── main/
│   │   ├── AndroidManifest.xml
│   │   ├── aidl/com/openclaw/agent/
│   │   │   ├── IAgentCoreService.aidl      # Main service API
│   │   │   ├── IAgentResponseCallback.aidl  # Streaming response
│   │   │   ├── IAgentEventListener.aidl     # Event notifications
│   │   │   ├── AgentRequest.aidl            # Request parcelable
│   │   │   └── AgentCapability.aidl         # Capability parcelable
│   │   ├── kotlin/com/openclaw/agent/
│   │   │   ├── core/
│   │   │   │   ├── AgentApplication.kt      # Application lifecycle
│   │   │   │   ├── AgentCoreService.kt      # THE service
│   │   │   │   ├── BootReceiver.kt          # Start on boot
│   │   │   │   └── Models.kt               # Data classes
│   │   │   ├── cloud/
│   │   │   │   └── CloudBridge.kt           # LLM communication
│   │   │   ├── context/
│   │   │   │   └── ContextManager.kt        # Memory & awareness
│   │   │   ├── tools/
│   │   │   │   └── ToolRegistry.kt          # Tool system + built-ins
│   │   │   ├── permissions/
│   │   │   │   └── CapabilityManager.kt     # Agent permissions
│   │   │   ├── accessibility/
│   │   │   │   └── AgentAccessibilityBridge.kt  # App automation
│   │   │   └── tailscale/
│   │   │       └── TailscaleBridge.kt       # Mesh networking
│   │   └── res/
│   │       ├── values/strings.xml
│   │       └── xml/accessibility_config.xml
│   └── test/kotlin/com/openclaw/agent/       # Tests (next sprint)
```

---

## AIDL API Reference

### IAgentCoreService

The main interface between the Agent Canvas (frontend) and the Agent Core (backend).

| Method | Description | Returns |
|--------|-------------|---------|
| `submitRequest(request, callback)` | Send user input to agent | `requestId: String` |
| `cancelRequest(requestId)` | Cancel in-flight request | `Boolean` |
| `getAgentState()` | Current state (idle/thinking/acting/...) | `Int` |
| `registerEventListener(listener)` | Subscribe to agent events | `void` |
| `unregisterEventListener(listener)` | Unsubscribe | `void` |
| `getCapabilities()` | List all capabilities | `List<AgentCapability>` |
| `setCapabilityEnabled(id, enabled)` | Toggle a capability | `Boolean` |
| `confirmAction(actionId, confirmed)` | Approve/reject pending action | `void` |
| `emergencyStop()` | 🚨 KILL SWITCH — stop everything | `void` |
| `getHistory(limit)` | Recent conversation history | `List<AgentRequest>` |
| `isCloudAvailable()` | Check cloud connectivity | `Boolean` |
| `getContextSummary()` | Current context state | `String` |

### IAgentResponseCallback

Streaming response interface — tokens arrive one by one.

| Callback | When | Key Params |
|----------|------|------------|
| `onToken(requestId, token, index)` | Each LLM output token | Token text, sequence number |
| `onToolCall(requestId, tool, params, needsConfirm, actionId)` | Agent wants to use a tool | Tool name, parameters |
| `onToolResult(requestId, tool, result, success)` | Tool execution completed | Result JSON |
| `onComplete(requestId, finalText)` | Response fully complete | Full text |
| `onError(requestId, code, message)` | Something went wrong | Error code + message |

### IAgentEventListener

Push notifications from the agent to the UI.

| Event | When | Payload |
|-------|------|---------|
| `onStateChanged(newState)` | Agent state transition | State enum |
| `onProactiveSuggestion(json)` | Agent suggests something | Suggestion JSON |
| `onCardUpdate(json)` | New/updated Card for Canvas | Card JSON |
| `onConnectivityChanged(connected)` | Cloud status change | Boolean |
| `onDeviceDiscovered(json)` | New Tailscale peer | Device JSON |
| `onContextUpdate(key, json)` | Context changed | Key + value |

---

## Agent States

```
                    ┌──────────┐
              ┌────▶│  IDLE    │◀──── emergencyStop()
              │     └────┬─────┘
              │          │ submitRequest()
              │     ┌────▼─────┐
              │     │ THINKING │──── LLM processing
              │     └────┬─────┘
              │          │
              │     ┌────▼──────────────┐
              │     │ Need confirmation? │
              │     └─┬──────────────┬──┘
              │    Yes│              │No
              │  ┌────▼────────┐ ┌──▼──────┐
              │  │ WAITING_    │ │ ACTING   │──── Tool executing
              │  │ CONFIRMATION│ └──┬───────┘
              │  └────┬────────┘    │
              │       │ confirm()   │
              │       ▼             │
              │  ┌──────────┐       │
              │  │ ACTING   │───────┘
              │  └──┬───────┘
              │     │ Complete
              └─────┘

        ──── Any state can transition to ERROR
        ──── emergencyStop() goes to IDLE from anywhere
```

---

## Component Deep Dives

### CloudBridge

Handles all communication with LLM providers.

**Supported Providers:**
- ✅ Anthropic (Claude) — Primary, SSE streaming
- 🔜 OpenAI (GPT) — Coming next sprint
- 🔜 Local Models — On-device inference (Phi-3, Gemma, Qwen)

**Request Flow:**
1. ContextManager builds `RequestContext` (system prompt + history + tools)
2. CloudBridge serializes to provider-specific JSON
3. HTTP POST with `stream=true`
4. Parse SSE events token by token
5. Detect tool calls in the stream
6. Return `LlmResponse` with full text + tool calls

**Error Handling:**
- Network timeout → retry once, then switch to local
- 401/403 → API key invalid, notify user
- 429 → Rate limited, exponential backoff
- 500+ → Provider issue, try fallback provider
- Connection lost mid-stream → resume or re-request

**Security:**
- API keys stored in Android Keystore (hardware-backed)
- TLS 1.3 for all connections
- No API key logging (redacted in logs)
- Request content not persisted in cloud bridge

### ContextManager

The agent's "memory" system.

**Context Components:**

| Component | Source | Update Frequency |
|-----------|--------|-----------------|
| Owner identity | Onboarding | Once |
| Current time/date | System clock | Every request |
| Location | LocationManager | On significant change |
| Battery & charging | BatteryManager | On change |
| Network state | ConnectivityManager | On change |
| Calendar events | CalendarProvider | Periodic (15 min) |
| Conversation history | In-memory deque | Every turn |
| Audit log | In-memory + DB | Every action |

**System Prompt Architecture:**

The system prompt is dynamically generated for each request:

```
┌───────────────────────────────────────────┐
│ Static Identity                           │
│ "You are the personal AI agent for..."    │
├───────────────────────────────────────────┤
│ Dynamic Context                           │
│ Time, location, battery, network          │
├───────────────────────────────────────────┤
│ Behavioral Guidelines                     │
│ When to confirm, when to act, style       │
├───────────────────────────────────────────┤
│ Personality Configuration                 │
│ Warm, concise, adaptive                   │
└───────────────────────────────────────────┘
```

### ToolRegistry

The agent's "toolbox" — mapping between LLM tool calls and Android capabilities.

**Built-in Tools (Sprint 1):**

| Tool | Capability | Confirmation | Status |
|------|------------|-------------|--------|
| `phone_call` | can_communicate | Always | Stub |
| `send_message` | can_communicate | Always | Stub |
| `notifications` | can_communicate | Never | Stub |
| `camera` | can_capture | Never | Stub |
| `calendar` | can_navigate | For create/delete | Stub |
| `contacts` | can_communicate | Never | Stub |
| `alarm` | general | Never | Stub |
| `smart_home` | can_control_home | For locks/security | Stub |
| `app_control` | general | Context-dependent | Stub |
| `device_settings` | general | Never | Stub |

**Adding a New Tool (Developer Guide):**

```kotlin
class MyNewTool : AgentTool() {
    override val name = "my_tool"
    override val description = "What this tool does (LLM reads this!)"
    override val requiredCapability = "can_do_thing"
    override val parametersSchema = """{ ... JSON Schema ... }"""

    override fun requiresConfirmation(toolCall: ToolCall): Boolean {
        // Return true for dangerous operations
        return false
    }

    override suspend fun execute(toolCall: ToolCall): ToolResult {
        // Do the thing
        return ToolResult(toolCall.id, success = true)
    }
}
```

Then register in `AgentCoreService.registerBuiltInTools()`.

### CapabilityManager

User-controlled boundaries for the agent.

**Default Capabilities:**

| Capability | Default | Confirmation |
|------------|---------|-------------|
| `general` | ✅ Enabled | No |
| `can_communicate` | ✅ Enabled | Yes (for sending) |
| `can_navigate` | ✅ Enabled | No |
| `can_capture` | ✅ Enabled | No |
| `can_purchase` | ❌ Disabled | Always |
| `can_control_home` | ✅ Enabled | For locks |
| `can_control_vehicle` | ❌ Disabled | Always |
| `can_access_health` | ❌ Disabled | No |
| `can_manage_files` | ✅ Enabled | For deletion |

**Design Philosophy:**
- Safe capabilities enabled by default (alarms, settings, navigation)
- Sensitive capabilities disabled by default (purchases, vehicle, health)
- Users can adjust anytime
- Some capabilities always require confirmation regardless of enabled state

### AccessibilityBridge

The "universal remote" for any Android app.

**Capabilities:**
- Read screen content (UI tree)
- Find elements by text or view ID
- Tap, type, scroll interactions
- Global actions (back, home, recents, screenshot)
- Screen content dump (for LLM analysis)

**Usage Flow:**
1. Agent needs to interact with an app (e.g., WhatsApp)
2. No native tool exists → falls back to `app_control` tool
3. `app_control` uses AccessibilityBridge
4. Bridge reads screen, finds target element, performs action
5. Bridge reads result, reports back to agent

**Limitations:**
- Some apps may have accessibility anti-tampering
- Performance depends on app complexity
- Custom views may not expose useful accessibility info
- WebViews need special handling

---

## Security Considerations

### Privilege Model

AgentCoreService runs as `android.uid.system` with platform certificate.
This gives it:
- Access to all system APIs
- Permission to interact across users (though we're single-user)
- Ability to inject input events
- Access to privileged content providers

### Audit Trail

**Every** tool call is logged locally:
```json
{
  "timestamp": "2026-02-12T10:30:00Z",
  "tool": "send_message",
  "params": {"contact": "Donika", "message": "Coming in 30 min"},
  "success": true,
  "confirmed_by_user": true
}
```

Audit log is:
- Stored on device only (never sent to cloud)
- Encrypted with user credentials
- Exportable for review
- Retained for 30 days (configurable)

### Kill Switch

`emergencyStop()` is the panic button:
1. Cancels all active LLM requests
2. Disconnects all cloud connections
3. Stops all pending tool executions
4. Returns to IDLE state
5. Plays confirmation sound/haptic

Triggered by:
- Voice: "Agent, stop everything"
- UI: Emergency stop button (always visible)
- Triple power button press (hardware)

---

## Future Roadmap

### Sprint 2: Implementation
- [ ] Implement all tool stubs (actual Android API calls)
- [ ] Room database for persistent history and audit log
- [ ] Real API key management via Android Keystore
- [ ] Notification listener service integration
- [ ] Location observer for context updates

### Sprint 3: Intelligence
- [ ] On-device inference engine (NNAPI / Qualcomm QNN)
- [ ] Proactive suggestions system
- [ ] Context learning (user patterns, preferences)
- [ ] Multi-turn conversation improvements

### Sprint 4: Connectivity
- [ ] Tailscale system service integration
- [ ] Smart home device discovery and protocols
- [ ] Agent-to-Agent communication
- [ ] Home server GPU offloading

---

> "This service is simultaneously the simplest and most complex thing
> I've ever designed. Simple because it does one thing: serve the human.
> Complex because serving the human means... everything." — Forge

*Last updated: 2026-02-12 by Forge*
