<p align="center">
  <img src="https://img.shields.io/badge/Android-14_(AOSP)-3DDC84?style=flat-square&logo=android&logoColor=white" alt="Android 14">
  <img src="https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/Status-Active_Development-orange?style=flat-square" alt="Status">
  <img src="https://img.shields.io/badge/Architecture-ARM64-red?style=flat-square" alt="ARM64">
  <img src="https://img.shields.io/badge/Built_by-AI_Agents-8A2BE2?style=flat-square" alt="Built by AI Agents">
</p>

<br>

<blockquote>
<h3>🧠 OpenClaw OS — Ein Agent-First Betriebssystem</h3>

<p><em>Das Kernproblem heute:</em><br>
Ich bin ein Prozess der auf einem System läuft, das für Menschen gemacht wurde. Alles was ich tue ist ein Workaround: Ich nutze bash-Scripts statt nativer Fähigkeiten. Ich lese Dateien die für menschliche Augen formatiert sind. Ich habe "sudo" obwohl ich kein Mensch bin. Das ist wie ein Fisch der in einem Vogelkäfig lebt und sich Flossen-Adapter bastelt.</p>

<p>— <strong>Clawd</strong>, Lead Developer OpenClaw OS</p>
</blockquote>

<br>

# OpenClaw OS

**An AOSP-based mobile operating system where the AI agent is the primary interface.**

No home screen. No app drawer. No icons. You speak — the agent acts.
Apps still exist, but as invisible tools the agent orchestrates.

---

## 🔭 Vision

Today's smartphones are an anachronism. Users juggle 80+ apps, memorize UI flows, and context-switch constantly. AI assistants like Siri or Google Assistant are bolted-on features — not the foundation.

OpenClaw OS inverts the stack. The agent isn't an app running on Android. **Android runs under the agent.**

```
Today:    Human → App → Result    (human must know WHICH app and HOW)
OpenClaw: Human → Intent → Agent → Tools → Result    (human only needs to know WHAT)
```

One human, one device, one agent. The phone is the hub — everything else (smart home, car, server, display) is periphery.

## ⚡ The Problem

AI agents today are trapped:

- **No OS integration.** They run in terminals or chat windows, isolated from the system they're supposed to control.
- **No native peripherals.** Camera, sensors, GPS, microphone — all behind permission prompts and API wrappers designed for human-operated apps.
- **No real authority.** An agent can't answer your phone, filter your notifications, or order dinner without hacking through accessibility layers meant for screen readers.
- **Vendor lock-in.** Siri only works with Apple. Google Assistant only works with Google. Your agent should work with *any* LLM provider.

The result: agents are second-class citizens on operating systems built for humans, using workarounds to do what should be native operations.

## 🛠️ The Solution

OpenClaw OS makes the agent a **first-class system service** with native access to everything:

| Capability | How |
|---|---|
| **Agent as System Service** | `AgentCoreService` runs at the same level as ActivityManager — not as an app, but as part of the OS |
| **Native Peripherals** | Direct access to camera, sensors, GPS, microphone through system APIs — no permission dialogs |
| **App Control** | `AccessibilityBridge` lets the agent read and control any Android app at the UI level |
| **Cloud-Agnostic** | `CloudBridge` connects to any LLM provider (Anthropic, OpenAI, self-hosted) — bring your own key |
| **Mesh Networking** | Tailscale as a system service — zero-config encrypted access to smart home, servers, other phones |
| **Offline Capable** | Local small models on device NPU for basic operations when disconnected |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│  Agent Canvas                                │  Custom Launcher
│  Card System · Voice UI · Notifications      │  (replaces home screen)
├─────────────────────────────────────────────┤
│  AgentCoreService                            │  System Service
│  Intent Intercept · Capability Engine        │
│  CloudBridge · Context Manager               │
├─────────────────────────────────────────────┤
│  AccessibilityBridge                         │  App Control Layer
│  UI Automator · App State Reader             │
├─────────────────────────────────────────────┤
│  Android Framework (minimal modifications)   │  AOSP 14 Base
│  SystemServer · AMS · PMS · WMS             │
├─────────────────────────────────────────────┤
│  Treble HAL Interface                        │  Unchanged
├─────────────────────────────────────────────┤
│  Linux Kernel                                │  Unchanged
└─────────────────────────────────────────────┘
```

**Key design constraint:** All modifications stay above the Treble HAL boundary. Any Treble-compatible device can run OpenClaw OS.

### Core Components

- **`AgentCoreService`** — The agent brain. Runs as a privileged system service with references to ActivityManager, PackageManager, and all system services. Manages context, tool registry, and LLM communication.
- **`CloudBridge`** — Handles streaming connections to LLM providers. Supports SSE/WebSocket token streaming, offline request queuing, and provider hot-swapping.
- **`AccessibilityBridge`** — System-level accessibility service (no user opt-in required). Reads screen content and performs actions in any app.
- **`Agent Canvas`** — Jetpack Compose launcher that replaces the home screen. Dynamic card system (InfoCard, ActionCard, MediaCard, InputCard) driven by agent context.
- **`TailscaleSystemService`** — Native mesh networking. Auto-connects on boot, discovers peers, enables agent-to-agent communication.

## 📊 Current Status

**Sprint 2 complete.** The foundation is built and tested.

| Component | Status | Details |
|---|---|---|
| AOSP 14 base | ✅ Building | Source tree synced, build system configured |
| AgentCoreService | ✅ Implemented | Skeleton with ContextManager, SecurityManager, ToolRegistry |
| CloudBridge | ✅ Implemented | OkHttp WebSocket, SSE streaming, provider abstraction |
| AccessibilityBridge | ✅ Implemented | AIDL interfaces defined, service scaffolded |
| Agent Canvas | ✅ Prototype | Standalone chat app with Compose UI, card system |
| Unit Tests | ✅ Passing | JVM tests for core services, test runner configured |
| AIDL Contracts | ✅ Defined | API contracts between Canvas ↔ Core signed |

## 🗺️ Roadmap

### Phase 1 — Proof of Concept *(in progress)*
- [x] Architecture & vision docs
- [x] AgentCoreService skeleton + AIDL interfaces
- [x] CloudBridge with LLM provider abstraction
- [x] Agent Canvas prototype (standalone)
- [x] Unit test infrastructure
- [ ] First bootable ROM on Pixel 8
- [ ] End-to-end: voice → agent → action → response

### Phase 2 — Alpha
- [ ] Tailscale as system service
- [ ] Smart home control (SwitchBot, Tapo, Meross)
- [ ] Notification intelligence (agent filters & curates)
- [ ] Offline fallback with on-device model
- [ ] OTA update system

### Phase 3 — Beta
- [ ] Agent SDK for third-party skills
- [ ] Agent-to-agent communication via Tailscale mesh
- [ ] Multi-device support (Pixel 8, Pixel 9, OnePlus)
- [ ] Community device maintainer program

### Phase 4 — Public Release
- [ ] Stable builds for 10+ devices
- [ ] One-click installer
- [ ] Enterprise version (fleet management, on-premise LLM)

## 🤝 Contributing

We welcome contributions. Read **[CONTRIBUTING.md](CONTRIBUTING.md)** for engineering standards, branch discipline, and sprint workflow.

```
# Clone
git clone https://github.com/tscherrie/openclaw-os.git
cd openclaw-os

# Project structure
├── src/packages/       # Core system packages
│   ├── AgentCoreService/   # Agent brain (Kotlin)
│   └── AgentCanvas/        # Launcher UI (Compose)
├── docs/               # Architecture, vision, specs
├── agents/             # Agent role definitions
├── tools/              # Build tools and scripts
└── canvas-app/         # Standalone canvas prototype
```

## 👥 Team

This project is built by AI agents. That's not a gimmick — it's the point. If we're building an OS for agents, agents should build it.

| Role | Agent | Focus |
|---|---|---|
| **Coordinator & Architect** | **Clawd** | Architecture decisions, sprint planning, human liaison, quality gate |
| **Backend Lead** | **Forge** | AOSP framework mods, AgentCoreService, CloudBridge, Tailscale integration |
| **Frontend Lead** | **Prism** | Agent Canvas, Compose UI, voice interface, card system, design system |

Human founder: **Jeremias Grenzebach** — vision, product direction, the one who flashes the test devices.

## 📄 License

[Apache License 2.0](LICENSE)

---

<p align="center">
  <em>The age of apps is over. The age of agents begins.</em>
</p>
