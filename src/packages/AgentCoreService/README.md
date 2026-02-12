# AgentCoreService

**The brain of OpenClaw OS.** A privileged Android System Service that orchestrates the AI agent — cloud communication, intent routing, tool execution, security, and peripheral control.

## Architecture

```
AgentCoreService
├── bridge/
│   ├── CloudBridge.kt          — LLM provider communication (Anthropic, OpenAI, local)
│   ├── AccessibilityBridge.kt  — App control via Accessibility framework
│   └── TailscaleBridge.kt      — Mesh networking for peripherals & peers
├── context/
│   └── ContextManager.kt       — Agent memory & conversation context
├── intent/
│   └── IntentRouter.kt         — Android intent interception
├── model/
│   └── Models.kt               — All data models (requests, responses, cards, etc.)
├── peripheral/
│   └── PeripheralManager.kt    — Smart home, vehicles, servers, other phones
├── security/
│   └── SecurityManager.kt      — Capability-based access control & audit trail
├── tools/
│   └── ToolRegistry.kt         — Agent tool management & execution
└── AgentCoreService.kt         — Main service class (entry point)
```

## Status: Sprint 1 (Foundation)

All interfaces are defined. Implementations are stubs (marked with `TODO`).

**What exists:** Complete interface contracts, data models, service skeleton, build definitions.

**What's next (Sprint 2):** Real CloudBridge (HTTP/SSE), real Accessibility integration, Tailscale IPC.

## Building

```bash
# Within AOSP tree:
m AgentCoreService -j$(nproc)

# Standalone development (Gradle, coming in Sprint 2):
# ./gradlew build
```

## Key Design Decisions

1. **Kotlin over Java** — Because it's 2026 and life is too short for `NullPointerException`
2. **Coroutines for async** — All LLM calls are streaming/async. No blocking the binder thread.
3. **Interface-first** — Every component is an interface. Swap implementations without changing callers.
4. **Graceful degradation** — If cloud dies, local inference. If that dies, phone still works.
5. **Security by default** — Every action goes through SecurityManager. Every. Single. One.

## Author

**Forge** — Backend Lead, Agent Lab

*"A system service that crashes is just a very expensive way to make a phone vibrate."*
