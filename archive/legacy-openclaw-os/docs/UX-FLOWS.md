# UX Flows — Text Storyboards

*Version 1.0 — Sprint 1*
*Author: Prism, Frontend Lead @ Agent Lab*
*"Every good story has a beginning, a middle, and a user who didn't have to think."*

---

## Flow 1: First Boot / Onboarding

### Context
User just flashed OpenClaw OS onto their Pixel 8. They boot it up with the naive optimism of someone who thinks "this will only take 5 minutes."

### Storyboard

```
FRAME 1: Boot Screen
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Black → OpenClaw logo fades in (claw mark, minimal)
Audio: Silent
Duration: 2s
Haptic: None
Note: No splash screen carousel. No "powered by Android."
      We're not insecure about our parentage.

FRAME 2: Language Selection
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Minimal picker. Globe icon.
        Languages in their native script.
        "Deutsch" "English" "Español" etc.
Audio: Silent
Duration: User-driven
Note: System language, not agent language.
      Agent can speak whatever you want later.

FRAME 3: WiFi Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Standard WiFi picker (we're not reinventing this)
Audio: Silent
Duration: User-driven
Note: Required. The agent needs a brain (cloud).
      "Zum Setup brauchst du Internet. Danach geht vieles auch offline.
       Vieles. Nicht alles. Wir sind ehrlich."

FRAME 4: "Wer bist du?"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Dark canvas. Centered text field.
        "Wie heißt du?"
        Keyboard slides up. Cursor blinks patiently.
Audio: Silent
Transition: Fade in, 500ms
Note: One field. One question. No "first name, last name,
      email, blood type, mother's maiden name."
      Just: who are you, human?

FRAME 5: "Dein Agent braucht ein Gehirn"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Provider selection cards:
        ◉ Anthropic (Claude) — "Empfohlen"
        ○ OpenAI (GPT-4)
        ○ Selbst-gehostet — "Fortgeschritten"

        Below: API Key input field
        "Du behältst deinen Key. Wir speichern nichts in der Cloud."

Audio: Silent
Duration: User-driven
Note: API key goes into Android Keystore immediately.
      Small "?" icon explains what an API key is, for the non-nerds.
      (Who are we kidding. Our Phase 1 users compile kernels for fun.)

FRAME 6: Tailscale (Optional)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: "Dein Netzwerk verbinden?"
        Illustration: Phone connected to house, car, server
        [Jetzt verbinden] ← Primary button
        [Später] ← Text link
Audio: Silent
Note: If connected: phone joins Tailnet, discovers peers.
      If skipped: agent works, just no remote periphery.
      We don't guilt-trip. Tailscale is genuinely optional.

FRAME 7: First Contact
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Canvas appears. Dark. Empty except:
        - Breathing pulse dot in center (agent state: idle)
        - Text fades in, token by token:
          "Hallo, Jeremias. Ich bin dein Agent."
          [1s pause]
          "Was soll ich als erstes für dich tun?"
        - Three suggestion chips fade in below:
          💡 "Zeig mir was du kannst"
          💡 "Verbinde mein Smart Home"
          💡 "Stell mir einen Wecker"
Audio: Agent speaks the greeting (warm, calm TTS)
Haptic: Subtle tick when agent starts speaking
Transition: 800ms dramatic entrance
Note: THIS IS THE MOMENT. The first time the agent speaks.
      It has to feel like meeting someone. Not booting a device.
      The pause after "Ich bin dein Agent" is intentional.
      Let it breathe. Let the user feel the shift.
      Their phone just became something else.

FRAME 8: First Interaction
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: User either taps a suggestion or speaks.
        Agent responds. First ConversationCard appears.
        Canvas is now alive.
Audio: Conversation begins
Note: From here, it's freeform. The agent adapts.
      Onboarding is DONE. No 12-step tutorial.
      No "tip of the day." No coach marks.
      The agent IS the onboarding. Ask it anything.
```

### Total time: ~3 minutes (WiFi + name + API key + Tailscale skip)
### Emotional arc: Curiosity → Simplicity → "Wait, that's it?" → Wonder

---

## Flow 2: Morning Wake-Up Scenario

### Context
It's 6:45 on a Thursday. Jeremias's alarm goes off. He hates mornings. His agent knows this.

### Storyboard

```
FRAME 1: Alarm
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Lock screen. Time large. Subtle gradient animation.
Audio: Gentle alarm (agent learned Jeremias hates loud ones)
       Starts soft, gradually increases over 30s
Haptic: Gentle pulse, synced with alarm tone
Note: No "WAKE UP" banner. No aggressive visuals.
      The phone respects that consciousness is a process, not an event.

FRAME 2: Snooze/Dismiss
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Swipe to dismiss. Tap for snooze (5min default).
Audio: Alarm continues
Note: If snoozed, agent says nothing. Judges silently.
      If dismissed, transition to Frame 3.

FRAME 3: Morning Canvas
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Canvas slides up. Cards load:

  ┌─ Context Header ─────────────────┐
  │ Guten Morgen · Do 12. Feb · 4°C ☁️│
  └──────────────────────────────────┘

  ┌─ StatusCard ─────────────────────┐
  │ 📅 10:00 Team Standup            │
  │ 📅 14:00 Zahnarzt                │
  │ 🚗 92% · 🏠 19°C                │
  └──────────────────────────────────┘

  ┌─ NotificationSummaryCard ────────┐
  │ 💬 3 Nachrichten                  │
  │ Donika (2): Brötchen?            │
  │ Max (1): Meme                    │
  │     [Donika antworten]           │
  └──────────────────────────────────┘

  ┌─ SuggestionCard ─────────────────┐
  │ ☕ Heizung auf 22° hochdrehen?   │
  │     [Ja] [Nein]                  │
  └──────────────────────────────────┘

Audio: Agent (TTS): "Guten Morgen. Du hast um 10 Standup
       und um 14 Zahnarzt. Donika fragt ob du Brötchen
       willst. Soll ich antworten?"
Haptic: Subtle tick when agent speaks
Note: The agent SPEAKS the summary. Cards are visual backup.
      Voice-first. Always.

FRAME 4: Interaction
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User (voice): "Ja, sag ihr mit Käse bitte."
Screen: ConversationCard appears with user's text.
        Agent responds: "Geschickt. Heizung?"
        NotificationSummaryCard updates (Donika ✓)
Audio: Agent speaks response
Note: Agent chains the next logical question (heizung)
      without being asked. Proactive, not robotic.

FRAME 5: Smart Home Control
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User (voice): "Ja, hoch."
Screen: SuggestionCard animates: "Heizung → 22°C ✓"
        StatusCard updates: 🏠 22°C (arrow up)
Audio: Agent: "Erledigt. Sonst noch was?"
Note: Heizung controlled via Tailscale → Home LAN → Tapo.
      User sees none of this. Magic.

FRAME 6: Day Begins
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User puts phone down. No more interaction.
Screen: Canvas settles. ConversationCard collapses.
        StatusCard stays. SuggestionCards dismissed.
        Agent enters idle state. Breathing dot.
Audio: Silent
Note: The phone goes quiet when you go quiet.
      No follow-up. No "anything else?" nagging.
      It's calm technology. It knows when to shut up.
```

### Total interaction time: ~45 seconds
### Emotional arc: Groggy → Informed → Taken care of → Ready for the day

---

## Flow 3: "Bestell Pizza" — End to End

### Context
It's 8pm. Jeremias is hungry. He doesn't want to open an app, scroll through menus, customize toppings, enter payment info, and confirm. He wants pizza.

### Storyboard

```
FRAME 1: Intent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User (voice): "Bestell mir Pizza."
Screen: Agent indicator → Listening → Thinking
Audio: -
Note: Two words. That's all the user should ever need.

FRAME 2: Clarification (Smart)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: ConversationCard:
  Agent: "Wie letztes Mal? Margherita von Napoli Express?"
  [Ja, genau] [Nein, was anderes]
Audio: Agent speaks the question
Note: Agent remembers last order (context persistence).
      If first time: "Wo bestellst du normalerweise?"
      then app discovery via installed apps.

FRAME 3: Customization
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User: "Ja, aber mit extra Mozzarella."
Screen: ConversationCard updates:
  Agent: "Margherita, extra Mozzarella. 12,90€ mit Visa ****4242.
          Bestellen?"
  [Bestellen ✓] [Ändern] [Abbrechen]
Audio: Agent confirms details
Note: Agent knows the price, knows the payment method.
      All from previous orders / app data.
      One confirmation step for payment. Non-negotiable.

FRAME 4: Execution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User taps [Bestellen ✓] or says "Ja"
Screen: AppCard appears below ConversationCard:
  ┌─────────────────────────────────┐
  │ 📱 Wolt                         │
  │ Agent steuert...                │
  │ ████████████░░░░ Warenkorb      │
  │ [Abbrechen]                     │
  └─────────────────────────────────┘
Audio: Agent: "Wird bestellt..."
Note: The AppCard shows progress. Agent navigates Wolt
      via Accessibility Bridge:
      1. Open Wolt → Napoli Express
      2. Add Margherita
      3. Modify: extra Mozzarella
      4. Proceed to checkout
      5. Confirm payment
      All automated. User sees progress bar + narration.

FRAME 5: Confirmation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: AppCard collapses.
  ConversationCard:
  Agent: "Bestellt. Ankunft ca. 35 Minuten. Ich sag Bescheid."
  [OK] [Bestellung tracken]
Audio: Agent speaks confirmation
Haptic: Success pattern

FRAME 6: Delivery Update (35 min later)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: SuggestionCard appears:
  "🍕 Deine Pizza ist gleich da. Fahrer ist 2 Min entfernt."
Audio: Agent: "Deine Pizza ist gleich da."
Haptic: Notification tick
Note: Agent intercepted Wolt push notification,
      translated it into human language, and told you
      at the right moment. Not 5 updates. One.
```

### Total user effort: 3 sentences + 1 confirmation tap
### Traditional app flow: ~15 taps, 3 screens, 2 minutes
### Emotional arc: Hungry → "Just handle it" → Handled → Pizza 🍕

---

## Flow 4: Incoming Call During Active Agent Interaction

### Context
Agent is in the middle of reading Jeremias his schedule for tomorrow when an unknown Berlin number calls. Agent suspects it's the dentist because Jeremias has an appointment today.

### Storyboard

```
FRAME 1: Agent Active
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: ConversationCard, agent speaking about tomorrow's schedule
Audio: Agent TTS: "Morgen hast du um 9—"
Note: Normal canvas state, agent mid-sentence.

FRAME 2: Call Interrupt
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Agent STOPS mid-word. No fade-out, immediate silence.
        Call card slides in from top (300ms, easeOut):
  ┌─────────────────────────────────┐
  │ 📞 Eingehender Anruf            │
  │ +49 30 12345678                 │
  │                                 │
  │ 🤖 "Berliner Nummer, nicht in   │
  │ Kontakten. Könnte die Zahnarzt- │
  │ praxis sein — du hast um 14     │
  │ Uhr Termin."                    │
  │                                 │
  │  [📞 Annehmen]  [❌ Ablehnen]  │
  │  [💬 "Bin beschäftigt, rufe    │
  │       zurück"]                  │
  └─────────────────────────────────┘
Audio: Ringtone (respectful volume)
       Agent context note is TEXT ONLY — doesn't speak over the ring.
Haptic: Call vibration pattern
Note: The call card has MAXIMUM priority. It slides in over
      everything. The agent's insight ("könnte Zahnarzt sein")
      is the killer feature here — context-aware call screening.

FRAME 3a: User Accepts
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User taps [Annehmen] or says "Rangehen"
Screen: Call UI (minimal, dark)
        Timer, speaker/mute buttons, end call
        Small banner: "Agent pausiert"
Audio: Phone call audio
Note: Agent is PAUSED. Not gone. Waiting patiently.
      Like a butler who stepped outside while you take a call.
      (The most British thing about this German OS.)

FRAME 3b: User Declines with Message
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User taps [💬 message]
Screen: Call dismissed. SMS sent automatically.
        ConversationCard: "SMS gesendet: 'Bin beschäftigt, rufe zurück'"
Audio: Agent: "Anruf abgelehnt, Nachricht gesendet."
Note: Agent resumes previous conversation seamlessly.

FRAME 4: Post-Call (if accepted)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call ends.
Screen: Canvas returns. New ConversationCard:
  Agent: "Zurück. War das die Zahnarztpraxis?"
  [Ja] [Nein]
Audio: Agent speaks
Note: Agent is curious. If user confirms, agent follows up.

FRAME 5: Context Update
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User: "Ja, Termin auf 15 Uhr verschoben."
Screen: Agent: "Kalender aktualisiert. Ich erinnere um 14:15.
         So, wo waren wir... Morgen hast du um 9—"
Audio: Agent resumes the interrupted sentence
Note: AGENT REMEMBERS WHERE IT WAS INTERRUPTED.
      It doesn't start over. It picks up mid-thought.
      This is the difference between an assistant and an OS.
      The OS doesn't forget because someone called.
```

### Key design decisions:
1. Call ALWAYS interrupts agent (phone calls are sacred)
2. Agent provides context VISUALLY during ring (no competing audio)
3. Agent pauses gracefully, resumes seamlessly
4. Post-call follow-up is natural, not robotic

### Emotional arc: Engaged → Interrupted → Informed → "oh that's smart" → Back to normal

---

## Flow 5: Bonus — "Ich bin spät dran"

### Context
Jeremias realizes he's running late for the dentist. Panic mode. One sentence should fix everything.

### Storyboard

```
FRAME 1: Panic
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User (voice, probably while running): "Ich bin spät dran für den Zahnarzt!"
Screen: Agent → Listening → Thinking
Note: The agent hears urgency. Context: Zahnarzt at 15:00.
      Current time: 14:45. Location: 20 min away by car.

FRAME 2: Multi-Action Response
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Screen: Multiple cards appear simultaneously:

  ┌─ ConversationCard ───────────────┐
  │ Agent: "Du bist 20 Minuten weg.  │
  │ Ich rufe an und sage Bescheid,   │
  │ und starte Navigation."          │
  │      [Mach das] [Nein warte]     │
  └──────────────────────────────────┘

Audio: Agent speaks this. Fast. Matches the urgency.
Note: Agent doesn't ask 5 questions. It KNOWS:
      - Which appointment (context)
      - Where it is (calendar has address)
      - How far away you are (GPS)
      - What to do (call + navigate)

FRAME 3: Execution (parallel)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User: "Mach das" or just "Ja"
Screen:
  ┌─ StatusCard (updated) ───────────┐
  │ 📞 Zahnarztpraxis angerufen...   │
  │ 🗺️ Navigation gestartet          │
  └──────────────────────────────────┘

  Map appears (MapCard or full-screen nav)

Audio: Agent: "Praxis informiert. Schnellste Route, 18 Minuten.
       Los geht's."
       → Transitions to navigation voice
Note: Agent called the dentist office (via Accessibility Bridge
      on phone app), left a message or spoke to receptionist,
      AND started navigation. Simultaneously.
      User said 4 words total.
```

### Total user effort: 1 panicked sentence + 1 confirmation
### Without agent: Unlock → Phone app → Find number → Call → Wait → Explain → Hang up → Maps → Type address → Start nav = 2-3 minutes of fumbling
### Emotional arc: PANIC → "Fix it" → Fixed → Relief

---

*"Good UX is invisible. Great UX makes the user feel like the world is bending to their will. We're going for great."*
*— Prism, sleep-deprived and correct*
