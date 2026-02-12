# 🐾 OpenClaw OS

**Agent-First Mobile Operating System**

An AOSP-based mobile OS where the AI agent is the primary interface. No home screen. No app drawer. Just your agent.

## Vision

The age of apps is over. The age of agents begins.

OpenClaw OS puts an AI agent at the core of your phone. Instead of you tapping through apps, your agent handles everything — messaging, navigation, smart home, ordering food, managing your calendar. You just talk.

**Phone = Hub.** Your phone is the central computer. Cloud provides the intelligence. Everything else (smart home, car, server) is periphery connected via Tailscale.

**One human, one device, one agent.** No multi-user complexity. Your phone is YOUR agent.

## Architecture

```
         ☁️ Cloud (Anthropic / OpenAI)
              ↕ WebSocket
      📱 Phone = OpenClaw OS = Hub
         ↕ Tailscale Mesh
    ┌────┴────┬────────┬────────┐
   🏠 Smart  🚗 Car    💻 Server  📺 Display
   Home                (optional)
```

## Key Components

- **AgentCoreService** — System-level service running the agent brain
- **Agent Canvas** — Custom launcher replacing the home screen
- **Accessibility Bridge** — Lets the agent control any Android app
- **Tailscale System Service** — Zero-config mesh to all your devices
- **Capability System** — Fine-grained permissions for agent actions

## Development

Built on AOSP (Android Open Source Project). Treble-compatible for broad device support.

```bash
# Clone
git clone https://github.com/tscherrie/openclaw-os.git

# Project structure
├── docs/           # Vision, architecture, specs
├── agents/         # Agent role definitions (Coordinator, Backend Lead, Frontend Lead)
├── tools/          # Build tools and scripts
└── src/            # Source code (coming soon)
```

## Team

| Role | Agent | Focus |
|------|-------|-------|
| Coordinator | Clawd | Architecture, decisions, human liaison |
| Backend Lead | Forge | AOSP mods, Agent Core, Cloud, Tailscale |
| Frontend Lead | Prism | Agent Canvas, UI/UX, Voice, Cards |

## Status

🚧 **Phase 0: Foundation** — Architecture, tooling, initial AOSP setup

## License

Apache 2.0 (OS) · AGPL 3.0 (Cloud components)
