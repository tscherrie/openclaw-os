# Cloud Communication Protocol — OpenClaw OS

*Written by Forge, Backend Lead @ Agent Lab*
*Sprint 1 — February 2026*

> "A WebSocket that won't close is basically a clingy ex.
> Our protocol knows when to hold on and when to let go." — Forge

---

## Overview

This document defines the communication protocol between OpenClaw OS phones
and cloud LLM providers. The phone talks directly to Anthropic/OpenAI — no
middleware, no proxy server, no man in the middle.

```
📱 OpenClaw Phone ──── HTTPS/WSS ────→ api.anthropic.com
                                       api.openai.com
                  ──── Tailscale ────→ Home Server (optional)
```

### Design Principles

1. **Direct-to-Provider** — No OpenClaw cloud server between phone and LLM
2. **Streaming-First** — Token-by-token responses for low perceived latency
3. **Offline-Resilient** — Queue, cache, degrade gracefully
4. **Provider-Agnostic** — Swap between Anthropic, OpenAI, local without code changes
5. **Privacy-First** — Minimal data sent, no state stored in cloud

---

## 1. Transport Layer

### Primary: HTTPS + Server-Sent Events (SSE)

All LLM requests use HTTPS POST with streaming SSE responses:

```
Phone                              LLM Provider
  │                                     │
  │──── POST /v1/messages ─────────────▶│
  │     Content-Type: application/json  │
  │     (full request with tools)       │
  │                                     │
  │◀─── 200 OK ────────────────────────│
  │     Content-Type: text/event-stream │
  │                                     │
  │◀─── data: {"type":"content_block_start"...}
  │◀─── data: {"type":"content_block_delta","delta":{"text":"Hello"}}
  │◀─── data: {"type":"content_block_delta","delta":{"text":" there"}}
  │◀─── data: {"type":"content_block_delta","delta":{"text":"!"}}
  │◀─── data: {"type":"content_block_stop"}
  │◀─── data: {"type":"message_stop"}
  │                                     │
  │──── Connection closed ─────────────│
```

### Why SSE over WebSocket?

| Factor | SSE | WebSocket |
|--------|-----|-----------|
| Simplicity | ✅ HTTP/2 compatible | ❌ Separate protocol |
| Load balancers | ✅ Standard HTTP | ⚠️ Needs WS support |
| Provider support | ✅ All LLM APIs | ⚠️ Not all providers |
| Bidirectional | ❌ Server → Client only | ✅ Full duplex |
| Reconnection | ✅ Built-in | ❌ Manual |
| Battery | ✅ Connection per request | ⚠️ Persistent connection |

**Decision:** SSE for LLM streaming (matches provider APIs). WebSocket reserved
for real-time features (Agent-to-Agent, Home Server bridge).

### Optional: WebSocket for Home Server

When connected to a home server via Tailscale:

```
Phone ──── WSS (Tailscale) ────→ Home Server
           Persistent connection
           Bidirectional
           Local models + GPU offloading
```

---

## 2. Request Format

### 2.1 Unified Request Envelope

The CloudBridge translates between our internal format and provider-specific APIs.

**Internal Request Format:**

```json
{
  "request_id": "uuid-v4",
  "session_id": "uuid-v4",
  "timestamp": "2026-02-12T10:30:00Z",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  
  "system_prompt": "You are the personal AI agent for Jeremias...",
  
  "messages": [
    {
      "role": "user",
      "content": "What's the weather like today?"
    },
    {
      "role": "assistant",
      "content": "It's 4°C and cloudy in Sofia."
    },
    {
      "role": "user",
      "content": "Call Mom and tell her I'm coming for dinner"
    }
  ],
  
  "tools": [
    {
      "name": "phone_call",
      "description": "Make a phone call to a contact or number",
      "input_schema": {
        "type": "object",
        "properties": {
          "action": {"type": "string", "enum": ["dial", "hangup"]},
          "contact_name": {"type": "string"},
          "phone_number": {"type": "string"}
        },
        "required": ["action"]
      }
    }
  ],
  
  "config": {
    "max_tokens": 4096,
    "temperature": 0.7,
    "stream": true,
    "timeout_ms": 120000
  },
  
  "context": {
    "owner_name": "Jeremias",
    "device_battery": "78%",
    "network_type": "wifi",
    "location": {"lat": 42.6977, "lng": 23.3219},
    "time_of_day": "morning"
  }
}
```

### 2.2 Anthropic API Translation

Our internal format → Anthropic Messages API:

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 4096,
  "stream": true,
  "system": "You are the personal AI agent for Jeremias...",
  "messages": [
    {"role": "user", "content": "Call Mom and tell her I'm coming for dinner"}
  ],
  "tools": [
    {
      "name": "phone_call",
      "description": "Make a phone call...",
      "input_schema": { ... }
    }
  ]
}
```

**Headers:**
```
POST /v1/messages HTTP/2
Host: api.anthropic.com
Content-Type: application/json
x-api-key: sk-ant-...
anthropic-version: 2023-06-01
```

### 2.3 OpenAI API Translation

Our internal format → OpenAI Chat Completions API:

```json
{
  "model": "gpt-4o",
  "stream": true,
  "messages": [
    {"role": "system", "content": "You are the personal AI agent..."},
    {"role": "user", "content": "Call Mom and tell her I'm coming for dinner"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "phone_call",
        "description": "Make a phone call...",
        "parameters": { ... }
      }
    }
  ]
}
```

**Headers:**
```
POST /v1/chat/completions HTTP/2
Host: api.openai.com
Content-Type: application/json
Authorization: Bearer sk-...
```

---

## 3. Streaming Response Protocol

### 3.1 Anthropic SSE Events

The response comes as a series of Server-Sent Events:

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_01...","model":"claude-sonnet-4-20250514",...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"I'll call"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" Mom for"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" you."}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_01...","name":"phone_call","input":{}}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"action\":"}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"\"dial\","}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"\"contact_name\":\"Mom\"}"}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"tool_use"}}

event: message_stop
data: {"type":"message_stop"}
```

### 3.2 Internal Stream Processing

CloudBridge processes SSE events and emits callbacks:

```
SSE Event                    → Internal Callback
─────────────────────────────────────────────────
content_block_delta (text)   → onToken(requestId, "Hello", 0)
content_block_delta (text)   → onToken(requestId, " world", 1)
content_block_start (tool)   → (buffer tool call)
content_block_delta (json)   → (accumulate tool JSON)
content_block_stop  (tool)   → onToolCall(requestId, "phone_call", params, needsConfirm, actionId)
message_stop                 → onComplete(requestId, fullText)
```

### 3.3 Token Streaming to UI

The Agent Canvas receives tokens and renders them progressively:

```
Time (ms)   Token              UI State
──────────────────────────────────────────
  0         (request sent)     "Thinking..." animation
150         "I'll"             "I'll|" (cursor)
180         " call"            "I'll call|"
210         " Mom"             "I'll call Mom|"
240         " for"             "I'll call Mom for|"
270         " you."            "I'll call Mom for you.|"
300         [tool_call]        "Calling Mom..." action card appears
...         [tool_result]      "✅ Connected" status update
350         "Done!"            "I'll call Mom for you. Done!"
```

**Target Latency:**
- Time to first token: < 500ms (on good network)
- Inter-token delay: < 50ms
- Tool execution: Varies, but UI shows progress

---

## 4. Session Management

### 4.1 Session Lifecycle

```
┌─────────────────────────────────────────────────────┐
│                  Session Lifecycle                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Phone Boot → Create Session                        │
│       │                                             │
│       ▼                                             │
│  Session Active ←──── User Interaction ────→ LLM    │
│       │                                             │
│       ├── Screen off → Session Hibernates           │
│       │       └── Screen on → Session Resumes       │
│       │                                             │
│       ├── 30 min idle → Session Archives            │
│       │       └── New input → New Session           │
│       │                                             │
│       └── Reboot → Session Persists (DB)            │
│               └── Boot → Load Last Session          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 4.2 Session Storage

Sessions are stored locally in a Room database:

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    last_active_at INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'active',  -- active, hibernated, archived
    owner_name TEXT NOT NULL,
    context_json TEXT  -- Serialized context snapshot
);

CREATE TABLE conversation_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    role TEXT NOT NULL,            -- user, assistant, tool
    content TEXT NOT NULL,
    tool_calls_json TEXT,          -- Serialized tool calls (if any)
    tool_result_json TEXT,         -- Serialized tool result (if any)
    timestamp INTEGER NOT NULL,
    token_count INTEGER DEFAULT 0
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(session_id),
    timestamp INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    params_json TEXT NOT NULL,
    result_json TEXT,
    success INTEGER NOT NULL,
    confirmed_by_user INTEGER DEFAULT 0
);
```

### 4.3 Context Window Management

LLMs have finite context windows. We manage this carefully:

```
Context Window Budget (e.g., 128K tokens for Claude 3.5)
┌─────────────────────────────────────────────────┐
│ System Prompt         │ ~500 tokens (fixed)      │
├───────────────────────┤                          │
│ Context Data          │ ~200 tokens (dynamic)    │
├───────────────────────┤                          │
│ Tool Definitions      │ ~1000 tokens (varies)    │
├───────────────────────┤                          │
│ Conversation History  │ ~4000 tokens (sliding)   │
├───────────────────────┤                          │
│ Current Request       │ ~200 tokens (varies)     │
├───────────────────────┤                          │
│ Response Budget       │ ~4096 tokens (max_tokens)│
├───────────────────────┤                          │
│ Safety Buffer         │ ~1000 tokens             │
└─────────────────────────────────────────────────┘
Total: ~11,000 tokens per request (well within limits)
```

**Conversation History Compression:**
- Keep last 20 turns verbatim
- Older turns → summarized by LLM
- Tool call results → compressed (success/fail + key data)
- Very old → dropped (but kept in local DB for audit)

---

## 5. Offline Queue & Sync

### 5.1 Offline Detection

```kotlin
enum class ConnectivityState {
    ONLINE_WIFI,        // Full speed, no data concerns
    ONLINE_CELLULAR,    // Works, maybe data-conscious
    ONLINE_METERED,     // Be careful with data usage
    TAILSCALE_ONLY,     // Can reach home server, not internet
    OFFLINE             // No connectivity at all
}
```

### 5.2 Offline Queue

When the phone loses connectivity, requests queue up:

```
┌──────────────────────────────────────────┐
│              Offline Queue               │
├──────────────────────────────────────────┤
│                                          │
│  Request₁ (text: "Remind me at 3pm")    │
│     → Can handle locally! ✅ Execute now │
│                                          │
│  Request₂ (text: "What's the weather?") │
│     → Needs cloud. 📦 Queue it.         │
│     → Show: "I'll check when online"    │
│                                          │
│  Request₃ (text: "Call Mom")            │
│     → Phone works offline! ✅ Execute   │
│                                          │
│  Request₄ (text: "Write an email...")   │
│     → Needs cloud. 📦 Queue it.         │
│     → Show: "I'll compose when online"  │
│                                          │
└──────────────────────────────────────────┘
```

### 5.3 Queue Implementation

```kotlin
data class QueuedRequest(
    val id: String,
    val request: AgentRequest,
    val priority: Priority,
    val createdAt: Long,
    val expiresAt: Long?,  // Some requests expire (weather for "now")
    val canHandleLocally: Boolean
)

enum class Priority {
    IMMEDIATE,  // Execute as soon as online
    NORMAL,     // Execute in order
    LOW,        // Can wait for WiFi
    EXPIRED     // Too late, discard
}
```

### 5.4 Sync Strategy

When connectivity returns:

```
Connectivity Restored!
       │
       ▼
┌─────────────────────┐
│ Check queue          │
│ Remove expired       │
│ Sort by priority     │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Process IMMEDIATE    │──→ Execute immediately
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Process NORMAL       │──→ Execute sequentially
│ (with rate limiting) │    (don't flood the API)
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Process LOW          │──→ Execute if on WiFi
│ (data-conscious)     │
└─────────────────────┘
```

### 5.5 Local-Only Mode

When offline, these tools still work:

| Tool | Offline Capability |
|------|--------------------|
| `phone_call` | ✅ Cellular calls work without internet |
| `send_message` (SMS) | ✅ SMS works without internet |
| `alarm` | ✅ Fully local |
| `camera` | ✅ Fully local |
| `calendar` | ✅ Read/write local calendar |
| `contacts` | ✅ Read local contacts |
| `device_settings` | ✅ Fully local |
| `smart_home` | ⚠️ Works if on same LAN/Tailscale |
| `app_control` | ✅ Accessibility is local |

**What needs cloud:** Natural language understanding, complex reasoning,
creative generation, web searches. The local small model handles simple
commands and routing.

### 5.6 Tailscale Fallback

If internet is down but Tailscale reaches the home server:

```
Phone ──── No Internet ────✗──── Cloud
  │
  └─── Tailscale (LAN/WireGuard) ──── Home Server
                                        └── Local LLM (Qwen, Llama)
                                        └── Whisper STT
                                        └── TTS
```

The CloudBridge checks for Tailscale-reachable inference servers before
falling back to the tiny on-device model.

---

## 6. Error Handling & Resilience

### 6.1 Error Classification

```
┌──────────────────────────────────────────────┐
│  Error Category    │ Handling Strategy        │
├──────────────────────────────────────────────┤
│  Network timeout   │ Retry 1x, then queue     │
│  DNS failure       │ Switch to IP, retry       │
│  TLS error         │ Don't retry (security!)   │
│  401 Unauthorized  │ Notify user (bad API key) │
│  403 Forbidden     │ Notify user (key issue)   │
│  429 Rate Limited  │ Exponential backoff       │
│  500 Server Error  │ Retry 2x with backoff     │
│  503 Overloaded    │ Wait & retry              │
│  Stream interrupted│ Resume or re-request      │
│  Malformed SSE     │ Skip event, continue      │
│  Tool call error   │ Report to LLM for retry   │
└──────────────────────────────────────────────┘
```

### 6.2 Retry Strategy

```kotlin
val retryConfig = RetryConfig(
    maxRetries = 3,
    initialDelayMs = 1000,
    maxDelayMs = 30_000,
    backoffMultiplier = 2.0,
    retryableStatusCodes = setOf(408, 429, 500, 502, 503, 504)
)
```

### 6.3 Circuit Breaker

If a provider is consistently failing:

```
CLOSED (normal) ──── 5 failures in 60s ────→ OPEN (stop trying)
                                                    │
                                              30s timeout
                                                    │
                                                    ▼
                                             HALF-OPEN (try one)
                                              │           │
                                           Success     Failure
                                              │           │
                                              ▼           ▼
                                           CLOSED       OPEN
```

When circuit is OPEN:
- Try alternative provider (Anthropic → OpenAI)
- Try home server (via Tailscale)
- Fall back to local model
- Queue request for later

---

## 7. Security

### 7.1 API Key Protection

```
┌──────────────────────────────────┐
│     Android Keystore (TEE)       │
│  ┌──────────────────────────┐    │
│  │  Anthropic API Key       │    │
│  │  OpenAI API Key          │    │
│  │  Tailscale Auth Key      │    │
│  └──────────────────────────┘    │
│  Hardware-backed. No export.     │
│  Biometric auth for access.      │
└──────────────────────────────────┘
```

- Keys never leave the Keystore
- Not accessible to other apps
- Require biometric or PIN to modify
- Auto-locked when device locks

### 7.2 Request Privacy

What gets sent to the cloud:

| Data | Sent? | Why |
|------|-------|-----|
| User's message | ✅ Yes | Core functionality |
| Conversation history | ✅ Yes | Context for good responses |
| System prompt | ✅ Yes | Agent behavior |
| Owner name | ✅ Yes | Personalization |
| Location (city-level) | ⚠️ Optional | Context (weather, navigation) |
| Exact GPS | ❌ No | Too precise, not needed |
| Contacts data | ❌ No | Referenced by name only |
| Photos/files | ❌ No | Unless explicitly shared |
| API keys | ❌ Never | Obviously |
| Audit log | ❌ Never | Local only |

### 7.3 TLS Configuration

```kotlin
val sslConfig = SSLConfig(
    minTlsVersion = TLS_1_3,     // No TLS 1.2 or lower
    certificatePinning = mapOf(
        "api.anthropic.com" to setOf("sha256/..."),
        "api.openai.com" to setOf("sha256/...")
    ),
    ocspStapling = true
)
```

---

## 8. Monitoring & Observability

### 8.1 Metrics (Local Only)

All metrics are stored on-device. No telemetry to cloud.

```kotlin
data class RequestMetrics(
    val requestId: String,
    val provider: String,
    val model: String,
    val timeToFirstTokenMs: Long,
    val totalLatencyMs: Long,
    val tokenCount: Int,
    val toolCallCount: Int,
    val retryCount: Int,
    val fromCache: Boolean,
    val errorCode: Int?
)
```

### 8.2 Dashboard Data

Available via the Agent's built-in diagnostics:

- Average time to first token (last 24h)
- Success rate by provider
- Token usage per day/week/month
- Most used tools
- Error rate and types
- Offline queue depth over time
- Cache hit rate

---

## 9. Agent-to-Agent Protocol (via Tailscale)

### 9.1 Overview

When two OpenClaw phones are on the same Tailnet, their agents can
communicate directly. No cloud server, no WhatsApp, just peer-to-peer
encrypted communication.

### 9.2 Protocol

Simple JSON-RPC over TCP (via Tailscale):

```json
// Request
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "agent.message",
  "params": {
    "from": {
      "device": "jeremias-pixel8",
      "owner": "Jeremias"
    },
    "to": {
      "device": "donika-pixel8",
      "owner": "Donika"
    },
    "type": "relay_message",
    "content": "Jeremias says he'll be 30 minutes late",
    "priority": "normal",
    "timestamp": "2026-02-12T10:30:00Z"
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "status": "delivered",
    "agent_response": "Donika says that's fine, she'll order appetizers"
  }
}
```

### 9.3 Supported Methods

| Method | Description |
|--------|-------------|
| `agent.message` | Send a message to the other agent's user |
| `agent.query` | Ask the other agent something (e.g., "Is Donika free at 3pm?") |
| `agent.calendar_check` | Check calendar availability |
| `agent.location_share` | Share current location (with permission) |
| `agent.ping` | Check if the other agent is online |

### 9.4 Security

- All traffic encrypted by Tailscale (WireGuard)
- Agents only talk to authorized Tailnet peers
- Each method requires the recipient agent's approval
- Owner must explicitly allow Agent-to-Agent communication
- All A2A messages logged in audit trail

---

## 10. Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Time to first token | < 500ms | On WiFi, to Anthropic |
| Complete simple response | < 2s | "What time is it?" |
| Complete tool call | < 3s | Including execution |
| Offline detection | < 1s | Switch to local mode |
| Queue processing start | < 5s | After reconnecting |
| A2A message delivery | < 2s | Via Tailscale |
| Local model inference | < 1s | Simple routing tasks |
| Battery impact | < 5% | Idle background usage per day |

---

> "The protocol is the promise between two systems that they'll understand
> each other. Ours promises streaming tokens, graceful failures, and an
> agent that works even when the cloud doesn't." — Forge

*Last updated: 2026-02-12 by Forge*
