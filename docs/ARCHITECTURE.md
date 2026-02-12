# Architecture Overview

## Agent Hierarchy

```
Jeremias (Human Founder)
    ↕
Coordinator (Clawd) — Architecture owner, decision maker
    ├── Backend Lead (Forge) — AOSP, System Services, Cloud, Tailscale
    │   └── Workers — Implementation sub-agents (ephemeral)
    └── Frontend Lead (Prism) — UI, Launcher, Voice, Cards
        └── Workers — Implementation sub-agents (ephemeral)
```

## Communication Flow

1. Jeremias ↔ Coordinator: WhatsApp (natural language)
2. Coordinator ↔ Leads: sessions_send / shared docs in repo
3. Leads ↔ Workers: sessions_spawn (task-specific, ephemeral)
4. Leads ↔ Leads: Via shared interfaces defined in this doc + Coordinator mediation

## AOSP Stack Modifications

```
┌─────────────────────────────────────────┐
│ Agent Canvas (Prism)                     │  ← Custom Launcher
│ Card System · Voice UI · Notifications   │
├─────────────────────────────────────────┤
│ AgentCoreService (Forge)                 │  ← New System Service
│ Intent Intercept · Capability Engine     │
│ Cloud Bridge · Tailscale Bridge          │
├─────────────────────────────────────────┤
│ Accessibility Bridge (Forge)             │  ← App Control Layer
│ UI Automator · App State Reader          │
├─────────────────────────────────────────┤
│ Android Framework (minimal changes)      │  ← AOSP Base
│ SystemServer · AMS · PMS · WMS          │
├─────────────────────────────────────────┤
│ Treble HAL Interface                     │  ← Unchanged
├─────────────────────────────────────────┤
│ Linux Kernel                             │  ← Unchanged
└─────────────────────────────────────────┘
```

## Shared Interfaces

See Backend Lead and Frontend Lead SOULs for API definitions.

Key contract: AgentCoreService exposes a stable API that the Agent Canvas consumes. Changes to this API require Coordinator approval.
