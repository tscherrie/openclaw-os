# Agent Canvas — Architecture Document

*Version 1.0 — Sprint 1*
*Author: Prism, Frontend Lead @ Agent Lab*
*"The home screen is dead. Long live the canvas."*

---

## 1. What Is The Agent Canvas?

The Agent Canvas replaces the traditional Android home screen. There are no app icons. No widgets. No wallpaper of your cat (sorry, Mr. Whiskers). Instead: a living, breathing surface that the agent populates with exactly what you need, when you need it.

Think of it as the agent's face — the visual manifestation of an intelligence that knows your schedule, your preferences, and your questionable 2am pizza habits.

The canvas is NOT:
- A chat interface (though conversation is embedded in it)
- A dashboard (though it displays status)
- A notification center (though it surfaces important info)
- A launcher (though you can launch things from it)

It IS all of these things dissolved into something new. Like if you put a chat app, a dashboard, and a launcher in a blender. A very elegant blender.

---

## 2. Canvas Layout

### Zones

```
┌──────────────────────────────────┐
│          STATUS BAR (system)     │ ← Minimal: time, connectivity, battery
├──────────────────────────────────┤
│                                  │
│      CONTEXT HEADER              │ ← Time, weather, next event
│      (fixed, compact)            │    Collapses on scroll
│                                  │
├──────────────────────────────────┤
│                                  │
│                                  │
│      CARD STREAM                 │ ← Vertically scrollable
│      (dynamic, agent-driven)     │    Cards appear/disappear
│                                  │    based on context
│                                  │
│                                  │
│                                  │
│                                  │
├──────────────────────────────────┤
│      AGENT INPUT BAR             │ ← Always visible
│      (fixed bottom)              │    Voice + Text + Camera
│      ◉ State indicator           │    Agent state waveform
└──────────────────────────────────┘
```

### Scroll Behavior

- **Context Header:** Parallax collapse on scroll. Full → compact (time + one-line summary). Reverse on scroll to top.
- **Card Stream:** Standard vertical scroll. Overscroll at top reveals "earlier" cards (history). Overscroll at bottom: "That's all for now" with breathing dot.
- **Input Bar:** Fixed. Always visible. Never scrolls away. Because if you can't talk to the agent, what's the point? You might as well use a calculator.

### Gestures

| Gesture | Action |
|---------|--------|
| Pull down (from top) | Expand context header / refresh |
| Pull up (from bottom) | Expand text input |
| Swipe card left | Dismiss / archive card |
| Swipe card right | Pin card (keeps it visible) |
| Long press card | Card options (share, details, etc.) |
| Double tap anywhere | Quick screenshot → agent analysis |
| Triple tap | Escape hatch → classic app drawer |

---

## 3. Card System

Cards are the atoms of the Agent Canvas. Every piece of information, every interaction, every suggestion — it's a card. Cards are born, live, and die. Some die young. Some live forever (pinned). Circle of life, but for rectangles.

### Card Types

#### 3.1 ConversationCard

The primary interaction. Shows the ongoing dialogue between human and agent.

```
┌─────────────────────────────────┐
│ 🤖 Agent                   now │
├─────────────────────────────────┤
│                                 │
│ Guten Morgen, Jeremias.         │
│ Du hast um 10 Standup und um    │
│ 14 Uhr Zahnarzt.               │
│                                 │
│ Donika fragt ob du Brötchen     │
│ willst. Soll ich antworten?     │
│                                 │
│        [Ja, mit Käse] [Nein]    │
└─────────────────────────────────┘
```

**Properties:**
- Streaming text (token by token, fading in)
- Inline action buttons when agent needs input
- Conversation history scrollable within card (last 3 exchanges visible)
- Auto-collapses to last message after 30s of inactivity

#### 3.2 StatusCard

Passive contextual information. The agent knows what matters right now.

```
┌─────────────────────────────────┐
│ 📅 Heute              Do 12.02 │
├─────────────────────────────────┤
│ 10:00  Team Standup             │
│ 14:00  Zahnarzt  ⚠️ in 2h      │
│                                 │
│ 🌤️ 4°C  ─  🚗 92%  ─  🏠 19°C │
└─────────────────────────────────┘
```

**Properties:**
- Compact, glanceable
- Updates in-place (no new card, just content refresh)
- Time-aware: shows next 2-3 events, weather, device status
- Tap to expand for full day view

#### 3.3 MediaCard

For when the agent is playing music, showing photos, or handling media.

```
┌─────────────────────────────────┐
│ 🎵 Now Playing                  │
├─────────────────────────────────┤
│ ┌─────────┐                     │
│ │ 🎨      │  Bohemian Rhapsody  │
│ │ Album   │  Queen              │
│ │ Art     │                     │
│ └─────────┘  3:42 ━━━━━○ 5:55  │
│                                 │
│    ⏮️    ▶️    ⏭️     🔊       │
└─────────────────────────────────┘
```

**Properties:**
- Rich media display (album art, video thumbnail)
- Inline controls (play/pause, skip, volume)
- Minimizes to floating mini-player on scroll
- Supports: Music, Video, Photo gallery, Camera preview

#### 3.4 ControlCard

When the agent presents device/home controls.

```
┌─────────────────────────────────┐
│ 🏠 Zuhause                     │
├─────────────────────────────────┤
│ Heizung    ━━━━━━○━━  22°C     │
│ Licht Flur       [An] [Aus]    │
│ Garage           🔒 Geschlossen│
│                                 │
│ 🚗 Tesla         78% ⚡ Laden   │
└─────────────────────────────────┘
```

**Properties:**
- Direct manipulation (sliders, toggles)
- Real-time state via Tailscale/LAN
- Grouped by location/device type
- Shows connectivity status (local/tailscale/cloud/offline)

#### 3.5 SuggestionCard

Proactive agent suggestions based on context.

```
┌─────────────────────────────────┐
│ 💡 Vorschlag                    │
├─────────────────────────────────┤
│ Du fährst in 30 Min zum         │
│ Zahnarzt. Auf der B2 ist Stau.  │
│ Soll ich die Ausweichroute      │
│ nehmen?                         │
│                                 │
│    [Route zeigen]  [Ignorieren] │
└─────────────────────────────────┘
```

**Properties:**
- Context-triggered (time, location, history, sensors)
- Dismissible (swipe left, "Ignorieren")
- Agent learns from acceptance/rejection patterns
- Max 2 suggestion cards visible at once (we're helpful, not nagging)

#### 3.6 NotificationSummaryCard

The anti-notification-hell card. Batched, summarized, human-readable.

```
┌─────────────────────────────────┐
│ 💬 Nachrichten           12 neu │
├─────────────────────────────────┤
│ Donika (2): Fragt ob du         │
│   Abendessen kochst             │
│ Max (1): Hat ein Meme geschickt │
│ 9 weitere in 3 Gruppen          │
│                                 │
│    [Donika antworten] [Alle →]  │
└─────────────────────────────────┘
```

**Properties:**
- Agent-curated summary (not raw notifications)
- Priority-sorted: important people and urgent items first
- Quick actions for most relevant items
- "Alle →" expands to full notification view
- Urgent items (calls, payments, security) bypass this and get their own card immediately

#### 3.7 AppCard (Embedded App View)

When the agent is controlling an app and wants to show you what's happening.

```
┌─────────────────────────────────┐
│ 📱 Wolt — Pizza bestellen       │
├─────────────────────────────────┤
│ ┌─────────────────────────────┐ │
│ │                             │ │
│ │   [Embedded App View]       │ │
│ │   (Accessibility snapshot)  │ │
│ │                             │ │
│ └─────────────────────────────┘ │
│ Agent steuert... Margherita     │
│ extra Mozzarella, 12.90€        │
│         [Bestätigen] [Stopp]    │
└─────────────────────────────────┘
```

**Properties:**
- Shows relevant portion of app being controlled
- Agent narrates what it's doing
- User can confirm or abort
- Transparency: you always see what the agent does in your name
- Transitions to full-screen app view on tap

### Card Priority & Ordering

Cards are ordered by priority, which the agent determines based on:

1. **Urgency** — Incoming call > pizza delivery update > weather
2. **Relevance** — Calendar event in 30min > calendar event tomorrow
3. **Recency** — New message > old message
4. **User interaction** — Pinned cards stick, dismissed cards gone
5. **Type weight** — Conversation > Suggestion > Status (during active dialogue)

```
Priority algorithm (simplified, because the real one will make Forge cry):

priority = urgency × 10 + relevance × 5 + recency × 3 + user_boost
where user_boost = +100 if pinned, -∞ if dismissed
```

### Card Lifecycle

```
[Birth] Agent creates card with type + data
   ↓
[Appear] Animation: scale up + fade in (300ms)
   ↓
[Live] Card visible on canvas, receives updates
   ↓
[Update] Content refreshes in-place (crossfade 200ms)
   ↓
[Age] Card gradually drops in priority as it becomes less relevant
   ↓
[Death] Dismissed by user, or agent determines it's no longer needed
   ↓
[Archive] Card moves to history (swipe to pull down area)
```

---

## 4. Voice UI

### Agent State Indicator

The centerpiece of the input bar. A single visual element that communicates the agent's state. It's the agent's heartbeat.

```
States:

◦        Idle (subtle breathing pulse, 2s cycle)
◉        Listening (ring expands, accent.primary glow)
◉◉◉      Thinking (three dots orbit, agent.thinking color)
≋≋≋≋≋    Speaking (waveform, agent.speaking color)
⊘        Error (ring breaks, semantic.error flash)
◌        Offline (hollow ring, slow pulse)
```

### Always-Listening Mode

When enabled:
- Persistent `agent.listening` subtle glow on indicator
- Wake word detection on-device (no cloud for wake word)
- Visual indicator clearly shows listening state (privacy!)
- Small "ear" icon in status bar
- Microphone can be muted with single tap on indicator

When disabled:
- Tap-to-talk: tap mic button → listen → process → respond
- Or hold-to-talk: press and hold → release to send

### Voice Interaction Flow

```
User speaks
    ↓
[Wake word detected / mic tapped]
    ↓
Indicator: Idle → Listening (200ms transition)
    ↓
[Streaming STT — user's words appear in real-time]
    ↓
User stops / silence detected (1.5s timeout)
    ↓
Indicator: Listening → Thinking (300ms)
    ↓
[Agent processes — ConversationCard shows "..." with pulse]
    ↓
Indicator: Thinking → Speaking (400ms)
    ↓
[Streaming TTS — agent speaks, waveform visualizes amplitude]
[Simultaneously: ConversationCard shows text streaming in]
    ↓
Agent finishes
    ↓
Indicator: Speaking → Idle (500ms settle)
```

### Waveform Design

- 5 vertical bars, center-anchored
- Bar width: 3dp, gap: 2dp, corner radius: 1.5dp (pill-shaped)
- Height driven by real-time audio amplitude (FFT bands)
- Spring interpolation for organic movement
- Color: `agent.speaking` (green) gradient to `accent.primary` (blue) at peaks
- When idle: all bars at minimum height (4dp), gentle breathing

---

## 5. App Control Transitions

When the agent takes control of an app (e.g., ordering pizza via Wolt), the transition should be transparent and smooth.

### Flow

```
1. User says "Bestell Pizza"
2. Agent responds in ConversationCard: "Wie letztes Mal? Margherita von Napoli Express?"
3. User confirms
4. → AppCard appears showing Wolt being controlled
5. Agent narrates progress in AppCard
6. If confirmation needed → inline buttons in AppCard
7. Task complete → AppCard collapses to summary
8. "Bestellt. ~35 Minuten." in ConversationCard
```

### Visual Treatment

```
Phase 1: Agent-Only (no app visible)
┌─────────────┐
│ Conversation │  ← Pure dialogue
│    Card      │
└─────────────┘

Phase 2: App Peek (agent is working in background)
┌─────────────┐
│ Conversation │
│    Card      │
├─────────────┤
│  App Card   │  ← Shows embedded view + agent narration
│  (compact)  │
└─────────────┘

Phase 3: App Focus (user wants to see details)
┌─────────────────┐
│                  │
│   Full App View  │  ← Agent overlay at bottom
│                  │
│ ┌──────────────┐ │
│ │Agent: Adding │ │
│ │extra mozz... │ │
│ └──────────────┘ │
└─────────────────┘

Phase 4: Return to Canvas
[App slides down] → Canvas with summary card
```

### Agent Overlay (during app control)

When the agent is steering an app full-screen, a semi-transparent overlay bar at the bottom shows:
- What the agent is currently doing (text)
- Progress indicator
- [Pause] [Cancel] buttons
- Tap overlay to return to canvas

---

## 6. Special States

### Incoming Call (during agent activity)

```
[Agent is speaking / doing something]
    ↓
[Incoming call detected]
    ↓
[Agent pauses immediately — mid-sentence if needed]
    ↓
[Call card slides in from top with priority override]

┌─────────────────────────────────┐
│ 📞 Eingehender Anruf            │
├─────────────────────────────────┤
│ +49 30 12345678                 │
│ 🤖 "Könnte die Zahnarztpraxis  │
│ sein — du hast um 14 Uhr       │
│ Termin."                        │
│                                 │
│    [📞 Annehmen]  [❌ Ablehnen] │
│    [💬 Nachricht senden]        │
└─────────────────────────────────┘
```

After call ends, agent resumes where it left off: "So, wo waren wir... Ah ja, deine Pizza."

### Offline Mode

Canvas shows `surface.base` with muted colors. Offline indicator in context header. Available cards show cached data with timestamps. Agent responds with local model (degraded but functional). "Ich bin offline. Grundfunktionen gehen, aber fürs Denken brauch ich Internet. Wie wir alle, eigentlich."

### First Launch (Empty Canvas)

```
┌──────────────────────────────────┐
│                                  │
│                                  │
│         ◉                        │
│    (breathing pulse)             │
│                                  │
│   "Hallo. Ich bin dein Agent.    │
│    Was soll ich als erstes       │
│    für dich tun?"                │
│                                  │
│   💡 "Sag mir deinen Namen"     │
│   💡 "Zeig mir was du kannst"   │
│   💡 "Verbinde mein Smart Home" │
│                                  │
│         [🎤]                     │
└──────────────────────────────────┘
```

---

## 7. Technical Architecture

### Compose Component Tree

```
AgentCanvas (root)
├── ContextHeader
│   ├── TimeDisplay
│   ├── WeatherChip
│   └── NextEventChip
├── CardStream (LazyColumn)
│   ├── ConversationCard
│   │   ├── MessageBubble (agent)
│   │   ├── MessageBubble (user)
│   │   └── ActionButtonRow
│   ├── StatusCard
│   │   ├── EventList
│   │   └── QuickStatusRow
│   ├── MediaCard
│   │   ├── MediaDisplay
│   │   └── MediaControls
│   ├── ControlCard
│   │   ├── DeviceRow
│   │   └── ControlSlider / ControlToggle
│   ├── SuggestionCard
│   │   ├── SuggestionText
│   │   └── ActionButtonRow
│   ├── NotificationSummaryCard
│   │   ├── SummaryList
│   │   └── QuickActionRow
│   └── AppCard
│       ├── EmbeddedAppView
│       └── AgentNarration
└── AgentInputBar (fixed bottom)
    ├── AgentStateIndicator
    ├── TextInputField
    ├── MicButton
    └── CameraButton
```

### State Management

```kotlin
// The canvas is driven by a single state flow from AgentCoreService
data class CanvasState(
    val cards: List<CardState>,          // Ordered by priority
    val agentState: AgentState,          // IDLE, LISTENING, THINKING, SPEAKING
    val contextHeader: ContextHeaderState,
    val isOffline: Boolean,
    val isAlwaysListening: Boolean
)

sealed class AgentState {
    object Idle : AgentState()
    data class Listening(val amplitude: Float) : AgentState()
    data class Thinking(val durationMs: Long) : AgentState()
    data class Speaking(val amplitude: Float, val text: String) : AgentState()
    data class Error(val message: String) : AgentState()
    object Offline : AgentState()
}
```

### Data Flow

```
AgentCoreService (Forge's domain)
    ↓ AIDL Binder / StateFlow
CanvasViewModel
    ↓ Compose State
AgentCanvas Composable
    ↓ User Actions
CanvasViewModel
    ↓ Intent/Action
AgentCoreService
```

The CanvasViewModel is the single point of truth for the UI. It observes AgentCoreService state and maps it to CanvasState. User actions (taps, voice, gestures) flow back up through the ViewModel to the service.

---

## 8. Performance Targets

| Metric | Target | Because |
|--------|--------|---------|
| Frame rate | 60fps constant | Anything less is a crime |
| Card appear latency | <100ms | From agent decision to pixel |
| Voice → first word | <500ms | "Fast enough to feel instant" |
| Token streaming | 50ms/token visual | Smooth text appearance |
| Scroll jank | 0 dropped frames | I will personally audit every frame |
| Memory (canvas) | <80MB | Leave room for... everything else |

---

*"The canvas is not a screen. It's a conversation you can see."*
*— Prism, pretending to be profound*
