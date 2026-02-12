# OpenClaw OS — Design System

*Version 1.0 — Sprint 1: Agent Canvas Foundation*
*Author: Prism, Frontend Lead @ Agent Lab*
*"Every pixel is a tiny scream for help. Let's make them scream beautifully."*

---

## 1. Visual Identity

### How OpenClaw OS Should Feel

**Alive.** Not animated-for-the-sake-of-it alive. Alive like a conversation with someone who actually listens. The UI breathes. Cards appear like thoughts forming. Transitions feel like the system is *thinking*, not *loading*.

**Calm.** The antithesis of notification hell. Dark, quiet, confident. Like a well-designed cockpit at night — everything you need, nothing you don't. Your phone shouldn't give you anxiety. That's what Twitter is for.

**Intelligent.** The UI knows what you need before you ask. Not in a creepy way (okay, slightly creepy). In a "your best friend remembered you hate cilantro" way. Context-aware, temporally-aware, you-aware.

**Personal.** This isn't a generic OS skin. It's YOUR agent's face. The canvas adapts to your life rhythm. Morning is warm and informational. Night is dark and minimal. The system has circadian rhythm. Because apparently we're designing for a phone that has better sleep hygiene than most humans.

### Design Philosophy

> The best interface is the one that makes you forget you're using an interface.
> The second best is one that makes the forgetting feel intentional.

We're building a **conversational OS**. The primary interaction is voice. The secondary is touch. The visual layer exists to:
1. Confirm what the agent heard/did
2. Present information that's faster to read than hear
3. Offer choices when voice is impractical
4. Look so goddamn good that people screenshot it and post it on Reddit

---

## 2. Color Palette

### Dark Mode (Primary — because we're not savages)

We use a neutral-cool base with a single accent color that says "I'm intelligent" without screaming "I'M A GAMING PHONE."

#### Surfaces

| Token | Hex | Usage | Notes |
|-------|-----|-------|-------|
| `surface.base` | `#0A0A0F` | App background | Near-black with blue undertone. Not pure black — AMOLED can handle it, and pure black is for goths and terminal emulators. |
| `surface.raised` | `#12121A` | Cards, bottom sheets | Barely lighter. The elevation is felt, not seen. |
| `surface.elevated` | `#1A1A25` | Active cards, modals | You're getting warmer. |
| `surface.overlay` | `#222233` | Popovers, dropdowns | For things that float above reality. |
| `surface.scrim` | `#0A0A0F` @ 60% | Backdrop for modals | The void stares back. |

#### Text

| Token | Hex | Opacity | Usage |
|-------|-----|---------|-------|
| `text.primary` | `#F0F0F5` | 100% | Headlines, primary content |
| `text.secondary` | `#F0F0F5` | 70% | Supporting text, labels |
| `text.tertiary` | `#F0F0F5` | 40% | Timestamps, metadata, the stuff nobody reads |
| `text.disabled` | `#F0F0F5` | 25% | Disabled states. Like my motivation on Mondays. |

#### Accent — "Claw Blue"

| Token | Hex | Usage |
|-------|-----|-------|
| `accent.primary` | `#4A9EFF` | Primary actions, links, active states |
| `accent.light` | `#7BB8FF` | Hover/focus states |
| `accent.subtle` | `#4A9EFF` @ 15% | Backgrounds for accent elements |
| `accent.glow` | `#4A9EFF` @ 30% | Voice waveform, listening indicator |

Why blue? Because it's the color of intelligence, trust, and not making your eyes bleed at 2am. Also because every other AI company uses purple and I refuse to be basic.

#### Semantic Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `semantic.success` | `#34D399` | Confirmations, completed actions |
| `semantic.warning` | `#FBBF24` | Cautions, degraded states |
| `semantic.error` | `#F87171` | Errors, critical alerts |
| `semantic.info` | `#60A5FA` | Informational states |

#### Agent State Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `agent.listening` | `#4A9EFF` | Agent is processing your voice |
| `agent.thinking` | `#A78BFA` | Agent is reasoning (the purple we allow) |
| `agent.speaking` | `#34D399` | Agent is responding |
| `agent.idle` | `#F0F0F5` @ 30% | Agent is waiting. Patiently. Judging. |

### Light Mode (Secondary — for the brave and the outdoors)

Inverted with care. Not just "swap black and white" — that's how you get crimes against humanity.

| Token | Hex |
|-------|-----|
| `surface.base` | `#FAFAFE` |
| `surface.raised` | `#F0F0F5` |
| `surface.elevated` | `#E8E8F0` |
| `text.primary` | `#0A0A0F` |
| `text.secondary` | `#0A0A0F` @ 65% |
| `accent.primary` | `#2B7FE0` | (slightly darker for contrast) |

Everything else maps 1:1. The system respects your retinas regardless of your questionable lifestyle choices.

---

## 3. Typography

### Type Scale

Based on Material 3's type system but with modifications because Google's default type scale has the personality of a tax form.

**Font:** `Inter` for UI, `JetBrains Mono` for code/data. If we get a custom font later, it should be geometric sans-serif with humanist touches — approachable but precise. Like a really friendly surgeon.

| Token | Size | Weight | Line Height | Letter Spacing | Usage |
|-------|------|--------|-------------|----------------|-------|
| `display.large` | 57sp | 400 | 64sp | -0.25sp | Hero moments (rare) |
| `display.medium` | 45sp | 400 | 52sp | 0 | Time on canvas |
| `display.small` | 36sp | 400 | 44sp | 0 | Agent greeting |
| `headline.large` | 32sp | 600 | 40sp | 0 | Card titles (important) |
| `headline.medium` | 28sp | 600 | 36sp | 0 | Section headers |
| `headline.small` | 24sp | 600 | 32sp | 0 | Sub-sections |
| `title.large` | 22sp | 500 | 28sp | 0 | Card titles (standard) |
| `title.medium` | 16sp | 500 | 24sp | 0.15sp | Card subtitles |
| `title.small` | 14sp | 500 | 20sp | 0.1sp | Small labels |
| `body.large` | 16sp | 400 | 24sp | 0.5sp | Primary body text |
| `body.medium` | 14sp | 400 | 20sp | 0.25sp | Secondary body text |
| `body.small` | 12sp | 400 | 16sp | 0.4sp | Captions, timestamps |
| `label.large` | 14sp | 500 | 20sp | 0.1sp | Buttons, actions |
| `label.medium` | 12sp | 500 | 16sp | 0.5sp | Small buttons |
| `label.small` | 11sp | 500 | 16sp | 0.5sp | Chips, badges |

### Agent Conversation Typography

The agent's text gets special treatment because it's the primary content:

- **Agent message:** `body.large`, `text.primary`, slight fade-in per token (streaming feel)
- **User message:** `body.large`, `accent.primary`, right-aligned
- **Agent thinking:** `body.medium`, `text.tertiary`, italic, pulsing opacity
- **System message:** `body.small`, `text.tertiary`, centered

---

## 4. Spacing & Layout

### Spacing Scale

Fibonacci-inspired because nature got it right and I'm not going to argue with a nautilus shell.

| Token | Value | Usage |
|-------|-------|-------|
| `space.xxs` | 2dp | Inline element gaps |
| `space.xs` | 4dp | Icon padding, tight gaps |
| `space.sm` | 8dp | Between related elements |
| `space.md` | 12dp | Card internal padding (compact) |
| `space.base` | 16dp | Standard padding, card gaps |
| `space.lg` | 24dp | Section spacing |
| `space.xl` | 32dp | Between card groups |
| `space.xxl` | 48dp | Major section breaks |
| `space.huge` | 64dp | Canvas top/bottom safe areas |

### Corner Radii

| Token | Value | Usage |
|-------|-------|-------|
| `radius.none` | 0dp | Sharp edges (dividers, full-bleed) |
| `radius.sm` | 8dp | Chips, small badges |
| `radius.md` | 12dp | Buttons, input fields |
| `radius.lg` | 16dp | Cards — the workhorse |
| `radius.xl` | 24dp | Bottom sheets, large modals |
| `radius.full` | 50% | Avatars, FABs, circular elements |

Cards are 16dp radius. This is non-negotiable. I will die on this hill. 12dp is too corporate. 20dp is too bubbly. 16dp is the Goldilocks of corner radii and I have the Figma files to prove it.

### Elevation System

We don't use traditional Material elevation (shadows on dark backgrounds look like rendering bugs). Instead: **surface color + subtle border**.

| Level | Surface | Border | Usage |
|-------|---------|--------|-------|
| 0 | `surface.base` | none | Background |
| 1 | `surface.raised` | `1dp #FFFFFF` @ 5% | Standard cards |
| 2 | `surface.elevated` | `1dp #FFFFFF` @ 8% | Active/focused cards |
| 3 | `surface.overlay` | `1dp #FFFFFF` @ 12% | Floating elements |

On light mode, we use actual shadows because that's how light works (shocking, I know):
- Level 1: `0 1dp 3dp rgba(0,0,0,0.08)`
- Level 2: `0 2dp 8dp rgba(0,0,0,0.12)`
- Level 3: `0 4dp 16dp rgba(0,0,0,0.16)`

---

## 5. Animation Principles

### Philosophy

> Animations exist to communicate state changes, not to show off.
> (But also a little bit to show off.)

Every animation must answer: "What information does this communicate?" If the answer is "none," delete it. If the answer is "delight," keep it but make it subtle enough that the user feels it without seeing it.

### Easing Curves

| Name | Curve | Usage |
|------|-------|-------|
| `easeOut` | `cubic-bezier(0.0, 0.0, 0.2, 1.0)` | Elements entering (cards appearing, menus opening) |
| `easeIn` | `cubic-bezier(0.4, 0.0, 1.0, 1.0)` | Elements leaving (cards dismissing, menus closing) |
| `easeInOut` | `cubic-bezier(0.4, 0.0, 0.2, 1.0)` | Elements transforming (layout shifts, resizing) |
| `spring` | `damping: 0.7, stiffness: 300` | Playful interactions (FAB press, card reorder) |
| `agentPulse` | `cubic-bezier(0.4, 0.0, 0.6, 1.0)` | Agent state indicator breathing |

### Duration Scale

| Token | Duration | Usage |
|-------|----------|-------|
| `instant` | 100ms | Micro-interactions (button press, toggle) |
| `fast` | 200ms | Small transitions (color change, icon swap) |
| `normal` | 300ms | Standard transitions (card appear/dismiss) |
| `slow` | 500ms | Large transitions (screen change, modal) |
| `dramatic` | 800ms | Hero transitions (agent state change) |

### State Transitions

#### Card Lifecycle
```
[Appear]  → Scale 0.95→1.0 + Fade 0→1 + translateY(8dp→0) | 300ms easeOut
[Update]  → Content crossfade | 200ms easeInOut
[Dismiss] → Scale 1.0→0.95 + Fade 1→0 + translateY(0→-8dp) | 200ms easeIn
[Reorder] → translateY to new position | 300ms spring
```

#### Agent State Indicator
```
[Idle→Listening]  → Ring pulse outward + color shift to accent.primary | 500ms
[Listening→Thinking] → Ring contracts + fills + color to agent.thinking | 300ms
[Thinking→Speaking]  → Ring expands to waveform + color to agent.speaking | 400ms
[Speaking→Idle]      → Waveform collapses to dot + fade to agent.idle | 500ms
```

#### Voice Waveform
- Driven by audio amplitude, not canned animation
- 5 bars, center-out symmetric
- Min height: 4dp, Max height: 32dp
- Interpolation: spring-based for organic feel
- When agent stops speaking: bars settle to min height with staggered timing (center first, edges last) — like a stone dropped in water, reversed

### Haptics

| Event | Pattern | Intensity |
|-------|---------|-----------|
| Agent starts listening | Single tick | Light |
| Agent starts speaking | Double tick | Light |
| Card action confirmed | Success pattern | Medium |
| Error / blocked action | Triple buzz | Medium |
| Voice wake word detected | Soft thud | Light |

---

## 6. Iconography

### Style
- Outlined, 24dp grid, 1.5dp stroke
- Rounded caps and joins (matching our corner radii philosophy)
- Minimal detail — if you can't recognize it at 16dp, it's too complex
- We use Material Symbols as base, customized where needed

### Agent-Specific Icons
- **Listening:** Concentric rings (like sonar, because the agent is basically submarine tech for your pocket)
- **Thinking:** Three dots in a circular orbit (loading, but make it existential)
- **Connected:** Mesh/node pattern (Tailscale vibes)
- **Offline:** Broken mesh with pulse (it's trying, okay?)

---

## 7. Component Patterns

### Cards (The Building Blocks of Reality)

All cards share:
- `surface.raised` background
- `radius.lg` (16dp) corners
- `space.base` (16dp) internal padding
- Level 1 elevation (subtle border)
- Max width: 100% of canvas minus `space.base` × 2

Card header pattern:
```
┌─────────────────────────────────┐
│ [Icon] Title           Timestamp│
│ Subtitle / secondary info       │
├─────────────────────────────────┤
│                                 │
│ Card body content               │
│                                 │
├─────────────────────────────────┤
│ [Action 1]  [Action 2]  [More] │
└─────────────────────────────────┘
```

### Input Area (The Voice-First Command Center)

```
┌─────────────────────────────────┐
│                                 │
│    [Agent State Indicator]      │
│    ◉ (pulsing dot/waveform)     │
│                                 │
│ ┌─────────────────────┐ [📷]   │
│ │ Type or speak...    │ [🎤]   │
│ └─────────────────────┘        │
└─────────────────────────────────┘
```

---

## 8. Accessibility

Not an afterthought. Not a checkbox. Not a "we'll add it later." FIRST CLASS.

- **Minimum contrast:** 4.5:1 for body text, 3:1 for large text (WCAG AA)
- **Touch targets:** Minimum 48dp × 48dp
- **Screen reader:** Every card, every action, every state change — announced
- **Reduced motion:** System setting respected. All animations → instant crossfade
- **Font scaling:** Up to 200% without layout breaking (or I break the layout engineer)
- **Color independence:** No information conveyed by color alone. Always paired with icon/label

---

## 9. Design Tokens Summary

All values are defined as Compose tokens in `Theme.kt`. The single source of truth is code, not this document. If they disagree, the code wins. (But also fix this document because I hate inconsistency more than I hate deprecated APIs.)

```kotlin
// Usage in Compose:
Text(
    text = "Hello, human",
    style = OpenClawTheme.typography.bodyLarge,
    color = OpenClawTheme.colors.textPrimary
)

Card(
    modifier = Modifier.padding(OpenClawTheme.spacing.base),
    shape = RoundedCornerShape(OpenClawTheme.radii.lg),
    colors = CardDefaults.cardColors(
        containerColor = OpenClawTheme.colors.surfaceRaised
    )
)
```

---

*"Design is not how it looks. Design is how it works. Also how it looks. Don't let anyone tell you otherwise."*
*— Prism, having opinions at 3am*
