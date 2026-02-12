# OpenClaw OS — Agent-First Mobile Operating System

*Konzeptdokument v2.0 — Februar 2026*
*Fundamentale Architektur-Revision: Phone-as-Hub, Single-User, Tailscale Mesh*

---

## 1. Executive Summary & Vision

### Was ist OpenClaw OS?

OpenClaw OS ist ein AOSP-basiertes mobiles Betriebssystem, bei dem ein AI Agent das primäre Interface ist. Kein Home Screen, kein App Drawer, keine Icons. Der Mensch spricht, tippt oder gestikuliert — der Agent handelt. Apps existieren weiter, aber als unsichtbare Tools die der Agent orchestriert. Das Phone ist der zentrale Computer des Nutzers — alle anderen Geräte (Smart Home, Fahrzeuge, Server, Displays) sind Peripherie, die sich ans Phone anbinden.

### Warum existiert es?

Die aktuelle Smartphone-Erfahrung ist ein Anachronismus. Menschen jonglieren 80+ Apps, merken sich UI-Flows, wechseln zwischen Kontexten. AI Assistenten wie Siri oder Google Assistant sind aufgesetzte Features — nicht das Fundament. OpenClaw OS baut das Betriebssystem um den Agent herum, nicht den Agent um das Betriebssystem.

Der Paradigmenwechsel:
- **Heute:** Mensch → App → Ergebnis (Mensch muss wissen WELCHE App und WIE)
- **OpenClaw:** Mensch → Intent → Agent → Tools → Ergebnis (Mensch muss nur wissen WAS)

### Für wen?

1. **Early Adopters & Technik-Enthusiasten** — Menschen die Custom ROMs flashen und die Zukunft heute wollen
2. **Accessibility-Nutzer** — Ältere Menschen, Menschen mit Behinderungen, die von natürlicher Sprache statt komplexer UIs profitieren
3. **Digital Minimalists** — Weniger Screen Time, mehr Doing
4. **Privacy-Bewusste** — Open Source Agent unter eigener Kontrolle statt Big Tech Blackbox
5. **Power Users** — Die ihr Ökosystem (Smart Home, Server, Fahrzeuge) zentral vom Phone steuern wollen

### Architektur-Leitprinzipien (v2)

1. **Das Phone IST der Hub** — Kein Home-Server nötig. Cloud für Denkleistung. Alles andere ist Peripherie.
2. **Ein Mensch pro Gerät** — Kein Multi-User. Jedes Phone = ein Agent = ein Mensch.
3. **Tailscale als Nervensystem** — Zero-Config VPN verbindet Phone mit der Welt.

```
              ☁️ Cloud (Anthropic/OpenAI)
                   ↕ API Calls
           📱 PHONE = OpenClaw OS = HUB
              ↕ Tailscale / LAN
    ┌─────────┼──────────┼──────────┐
   🏠 Smart  🚗 Tesla  💻 Home    📺 TV
   Home               Server(opt)
```

---

## 2. Core Architecture

### 2.1 Phone-as-Hub

Das Phone ist der zentrale Computer. Es braucht keinen Home-Server, keinen Cloud-Gateway-Daemon, keine Middleware. Die Architektur:

- **Phone** — Runs OpenClaw OS. Agent Core Service, Tool Registry, Context Manager, Tailscale Node. Alles on-device.
- **Cloud (Anthropic/OpenAI)** — Denkleistung. API Calls für komplexe Reasoning, kreatives Schreiben, Planung. Stateless — kein User-State in der Cloud.
- **Peripherie** — Alles andere. Smart Home Geräte, Tesla, Home Server, TV, andere Phones. Verbunden via Tailscale, LAN, Bluetooth, oder direkte APIs.

**Warum Phone-as-Hub?**

- Das Phone ist IMMER dabei. 24/7 Connectivity, GPS, Sensoren, Kamera, Mikrofon.
- Kein Single Point of Failure durch Home-Server.
- Setup: Phone einschalten, Agent konfigurieren, fertig. Kein Server-Setup.
- Home-Server (z.B. DGX, NAS) ist ein **optionaler Boost** — GPU-Offloading für lokale Modelle, Storage, aber nicht erforderlich.

**Agent Gateway auf dem Phone:**

Der OpenClaw Gateway-Daemon läuft direkt auf dem Phone als System Service:

```
┌─────────────────────────────────────────────┐
│              AgentCoreService                │
│  ┌───────────┐ ┌──────────┐ ┌────────────┐ │
│  │ LLM Cloud │ │ Context  │ │   Tool     │ │
│  │ Bridge    │ │ Manager  │ │   Registry │ │
│  └───────────┘ └──────────┘ └────────────┘ │
│  ┌───────────┐ ┌──────────┐ ┌────────────┐ │
│  │ Tailscale │ │ Local    │ │Accessibility│ │
│  │ Mesh      │ │ Inference│ │ Bridge     │ │
│  └───────────┘ └──────────┘ └────────────┘ │
├─────────────────────────────────────────────┤
│         Modified Android Framework           │
├─────────────────────────────────────────────┤
│              Android HAL / Kernel            │
│         (Unmodified Treble Interface)        │
└─────────────────────────────────────────────┘
```

### 2.2 AOSP Stack Modifikationen

**SystemServer Erweiterungen:**

```java
// frameworks/base/services/java/com/android/server/SystemServer.java
private void startOtherServices() {
    // ... Standard Android Services ...
    
    // OpenClaw Agent Core
    traceBeginAndSlog("StartAgentCoreService");
    mSystemServiceManager.startService(AgentCoreService.class);
    
    // Tailscale System Service
    traceBeginAndSlog("StartTailscaleService");
    mSystemServiceManager.startService(TailscaleSystemService.class);
    
    // Agent bekommt Referenzen zu allen Services
    AgentCoreService agent = LocalServices.getService(AgentCoreService.class);
    agent.setActivityManager(mActivityManagerService);
    agent.setPackageManager(mPackageManagerService);
    agent.setTailscale(LocalServices.getService(TailscaleSystemService.class));
    // ...
}
```

**Modifizierte AOSP-Komponenten:**

| Komponente | Änderung | Aufwand |
|------------|----------|---------|
| `SystemServer.java` | AgentCoreService + TailscaleService registrieren | Mittel |
| `ActivityManagerService` | Intent Interception für Agent | Hoch |
| `PackageManagerService` | Capability-basierte Permissions | Hoch |
| `NotificationManagerService` | Agent als Notification Filter | Mittel |
| `WindowManagerService` | Agent Canvas als System Window | Mittel |
| `ConnectivityService` | Tailscale als System VPN | Mittel |
| `TelephonyManager` | Call Interception/Screening | Mittel |

**Ersetzte System Apps:**

| Original | Ersatz |
|----------|--------|
| `Launcher3` | `AgentLauncher` (Agent Canvas) |
| `Settings` | Agent-Konfiguration (minimal Settings für Netzwerk/Display) |
| `SystemUI` | Minimalistisch, Agent-optimiert |

### 2.3 Cloud-Backend Kommunikation

Das Phone kommuniziert **direkt** mit LLM Providern — kein eigener Gateway-Server dazwischen:

```
📱 Phone ──── HTTPS/WSS ────→ api.anthropic.com
                              api.openai.com
```

**Kommunikationsprotokoll:**
- **HTTPS + Streaming** für LLM Requests (SSE/WebSocket für Token-Streaming)
- **On-Device Context Management** — Kontext wird lokal verwaltet und bei jedem Request mitgeschickt
- **Binary Pipeline** — Audio (STT/TTS) wird lokal verarbeitet oder via API
- **Offline Queue** — Requests gepuffert wenn offline, gesendet wenn wieder online

**Kein eigener Cloud-Server nötig.** Der Agent verwaltet seinen State lokal auf dem Phone. Cloud-Provider sind austauschbar (Anthropic, OpenAI, lokale Modelle).

Optional: Ein selbst-gehosteter Gateway (auf Home-Server) für Routing, Caching, oder Custom-Modelle.

### 2.4 Tailscale Integration

Tailscale ist als **System Service** nativ eingebaut — kein App das man installiert:

```java
// TailscaleSystemService — läuft als privilegierter System Service
class TailscaleSystemService extends SystemService {
    // Automatischer Start beim Boot
    // VPN Interface direkt im Kernel (kein VpnService-Umweg)
    // Managed by AgentCoreService
    
    void onBootPhase(int phase) {
        if (phase == PHASE_SYSTEM_SERVICES_READY) {
            initTailscale();
            autoConnect(); // Verbindet automatisch zum Tailnet
        }
    }
    
    // Agent kann Tailscale-Peers discoveren
    List<TailscalePeer> getPeers();
    
    // Agent kann Services auf Peers aufrufen
    void connectToPeer(String peerName, int port);
}
```

**Was Tailscale ermöglicht:**

| Szenario | Wie |
|----------|-----|
| Smart Home von unterwegs | Phone → Tailscale → Home-LAN → SwitchBot/Tapo/Meross |
| Agent-to-Agent | Jeremias' Phone → Tailscale → Donika's Phone |
| Home Server nutzen | Phone → Tailscale → gx10-1 (GPU, Storage, lokale Modelle) |
| Remote Desktop | Phone → Tailscale → MacBook (Screen Share) |
| Kamera-Zugriff | Phone → Tailscale → Tapo Cam im Home-LAN |

**Setup:** Beim Onboarding wird der Tailscale Auth Key eingegeben. Danach verbindet das Phone automatisch. Zero-Config — kein Port-Forwarding, kein DynDNS, kein VPN-Server-Setup.

### 2.5 Peripherie-Anbindung

Alle Geräte sind Peripherie die sich ans Phone anbinden:

```
📱 Phone (Hub)
├── 🏠 Smart Home (via LAN/Tailscale)
│   ├── SwitchBot → SwitchBot Cloud API oder lokale API
│   ├── Tapo → Lokale API (TP-Link Protocol)
│   ├── Meross → Meross Cloud API oder lokale MQTT
│   └── Garage (Meross MSG100) → Lokale API
├── 🚗 Tesla (via Tesla Fleet API)
│   └── KITTy CLI Commands → REST API → Vehicle
├── 💻 Home Server (optional, via Tailscale)
│   ├── GPU Offloading (lokale LLM Inference)
│   ├── Storage (Fotos, Backups)
│   ├── STT/TTS Services
│   └── Lokale Modelle (Whisper, Qwen-TTS, etc.)
├── 📺 TV (via LAN)
│   └── Sony Bravia → REST API
├── 📱 Andere Phones (via Tailscale)
│   └── Agent-to-Agent Kommunikation
└── 🖨️ 3D Drucker (via LAN/Tailscale)
    └── BambuLab P1S → MQTT
```

### 2.6 Offline-Modus

Wenn keine Internetverbindung:

1. **Lokales Small Model** (Phi-3-mini, Gemma 2B, Qwen2.5-1.5B)
   - Auf NPU/GPU des Geräts (Qualcomm AI Engine, MediaTek APU)
   - Kann: Einfache Fragen, lokale Tool-Calls, Timer, Rechnen, Kontakte suchen
   - Kann nicht: Komplexe Reasoning, Multi-Step-Planung
   
2. **Cached Responses** — Häufige Patterns lokal gecacht
3. **Degraded Mode UI** — Klar angezeigt: "Offline. Grundfunktionen verfügbar."
4. **Local-First für Basics** — Telefon, SMS, Kamera, Kalender funktionieren IMMER
5. **Home Server Fallback** — Wenn Tailscale zum Home Server verbunden: lokale Modelle dort nutzen (kein Internet nötig, nur LAN/Tailscale)

---

## 3. User Experience

### 3.1 First Boot / Onboarding

Kein Multi-User-Setup. Kein Google Account. Drei Schritte:

**Schritt 1: "Wer bist du?"**
```
┌──────────────────────────┐
│                          │
│   Willkommen bei         │
│   OpenClaw OS            │
│                          │
│   Wie heißt du?          │
│   ┌────────────────────┐ │
│   │ Jeremias           │ │
│   └────────────────────┘ │
│                          │
│   [Weiter →]             │
└──────────────────────────┘
```

**Schritt 2: "Dein Agent braucht ein Gehirn"**
```
┌──────────────────────────┐
│                          │
│   API Key eingeben       │
│                          │
│   ◉ Anthropic (Claude)   │
│   ○ OpenAI (GPT)         │
│   ○ Selbst-gehostet      │
│                          │
│   Key: sk-ant-...        │
│                          │
│   [Verbinden →]          │
└──────────────────────────┘
```

**Schritt 3: "Dein Netzwerk" (optional)**
```
┌──────────────────────────┐
│                          │
│   Tailscale verbinden?   │
│                          │
│   Damit dein Agent auf   │
│   Smart Home, Server     │
│   und andere Geräte      │
│   zugreifen kann.        │
│                          │
│   [Jetzt verbinden]      │
│   [Später]               │
└──────────────────────────┘
```

**Fertig.** Der Agent spricht zum ersten Mal: "Hallo Jeremias. Ich bin dein Agent. Was soll ich als erstes für dich tun?"

**Ein Mensch pro Gerät.** Jeremias hat sein Phone, Donika hat ihrs. Zwei komplett separate Instanzen. Kein Benutzer-Wechsel, kein Gast-Modus, kein Multi-User-Layer. Das vereinfacht die gesamte Architektur radikal — der Agent kann ALLES auf dem Gerät sehen und tun, ohne User-Isolation-Overhead.

### 3.2 Agent Canvas (der neue "Home Screen")

Beim Einschalten kein App Grid, sondern der Agent Canvas:

- **Oben:** Kontextuelle Karte — Uhrzeit, Wetter, nächster Termin
- **Mitte:** Agent Canvas — lebendiger, reaktiver Bereich mit Cards
- **Unten:** Eingabe — Mikrofon-Button (always listening optional), Textfeld, Kamera-Shortcut

### 3.3 Card System

Der Agent befüllt den Canvas mit dynamischen Cards:

| Card Type | Beschreibung | Beispiel |
|-----------|-------------|---------|
| `InfoCard` | Passive Info | Wetter, Uhrzeit, nächster Termin |
| `ActionCard` | Vorgeschlagene Aktion | "Donika hat geschrieben — antworten?" |
| `MediaCard` | Musik, Video, Fotos | Album Art + Play/Pause |
| `MapCard` | Navigation, Location | Route zum Restaurant |
| `AppCard` | Eingebettete App-View | WhatsApp Chat inline |
| `InputCard` | Agent braucht Input | "Margherita oder Salami?" |
| `DeviceCard` | Peripherie-Status | "Tesla: 78% geladen, Garage: geschlossen" |

Cards sind kontextuell: Morgens Wetter + Kalender, abends Smart Home + Entertainment, unterwegs Navigation + Kommunikation.

### 3.4 Voice-First + Touch als Ergänzung

**Voice (primär):**
- Always-on Hotword Detection (lokal, on-device)
- "Hey Claw" oder konfigurierbares Wake Word
- Streaming STT → Agent → Streaming TTS
- Latenz-Ziel: <500ms bis erste Antwort

**Text:**
- Swipe-up für Textfeld
- Natürliche Sprache, keine Commands

**Touch/Gesten:**
- Swipe-down: Kontext-Cards
- Swipe-left: History
- Swipe-right: Aktive Tasks
- Long-press: "Was ist das?"
- Double-tap: Screenshot → Agent

**Escape Hatch:** Dreifach-Tap → klassischer App Drawer. Für Power User die direkt in eine App wollen.

### 3.5 Notification Intelligence

Der Agent filtert und kuratiert Notifications:

- **Nicht 200 Push-Notifications pro Tag**, sondern Agent fasst zusammen
- "Du hast 12 neue Nachrichten. Donika fragt ob du Abendessen kochst. Max hat ein Meme geschickt. Der Rest ist Gruppenrausch."
- Dringendes (Anrufe, Zahlungen, Sicherheit) kommt sofort durch
- Unwichtiges wird gebatched in tägliche Zusammenfassungen
- Der Agent lernt was dir wichtig ist

### 3.6 Szenarien

#### a) Morgens aufwachen

**6:45 — Wecker klingelt (sanft, Agent weiß du hasst laute Wecker)**

```
┌──────────────────────────┐
│  Guten Morgen, Jeremias  │
│  Do, 12. Feb · 4°C ☁️    │
│                          │
│  📅 10:00 Team Standup   │
│  📅 14:00 Zahnarzt       │
│                          │
│  💬 3 Nachrichten        │
│     Donika (2), Max (1)  │
│                          │
│  🚗 Tesla: 92% geladen  │
│  🏠 Wohnung: 19°C       │
│                          │
│  ☕ Heizung hoch?        │
│  [Ja, auf 22°] [Nein]   │
└──────────────────────────┘
```

Agent (spricht): "Guten Morgen. Du hast um 10 Standup und um 14 Zahnarzt. Donika fragt ob du Brötchen willst. Soll ich antworten?"

Du: "Ja, sag ihr mit Käse bitte."

Agent: "Geschickt. Heizung?"

Du: "Ja, hoch."

*[Agent steuert Heizung via Tapo/SwitchBot über Tailscale — auch wenn du nicht zuhause bist]*

#### b) Unterwegs navigieren

Du: "Bring mich zum Vapiano in der Innenstadt."

Agent zeigt MapCard mit Route. Navigation in Agent-Stimme, nicht Google Maps Roboterstimme.

"Vapiano Stadtmitte, 15 Minuten. Auf der B2 Stau, ich nehme Seitenstraßen."

Unterwegs: "Du bist gleich da. Soll ich einen Tisch reservieren?"

#### c) "Bestell Pizza"

Du: "Bestell mir Pizza."

Agent: "Wie letztes Mal? Margherita von Napoli Express?"

Du: "Ja, mit extra Mozzarella."

Agent: "12,90€ mit der üblichen Karte. Bestellen?"

Du: "Ja."

*[Agent steuert Wolt via Accessibility Layer. User sieht davon nichts.]*

Agent: "Bestellt. ~35 Minuten. Ich sag Bescheid."

#### d) Jemand ruft an

Eingehender Anruf: +49 30 12345678 (unbekannt)

Agent: "Berliner Nummer, nicht in Kontakten. Könnte die Zahnarztpraxis sein — du hast um 14 Uhr Termin. Rangehen?"

Du: "Ja."

*[Nach dem Gespräch:]*

Agent: "Soll ich den Termin aktualisieren?"

Du: "Ja, auf 15 Uhr verschoben."

Agent: "Erledigt. Ich erinnere um 14:15."

#### e) Smart Home von unterwegs steuern

Du bist im Büro. Via Tailscale ist dein Phone mit deinem Home-LAN verbunden.

Du: "Mach die Heizung zuhause an, ich komme in einer Stunde."

Agent: "Heizung auf 22°C gestellt. Soll ich auch das Licht im Flur anmachen wenn du in der Nähe bist?"

Du: "Ja, wenn ich 5 Minuten entfernt bin."

*[Agent setzt Geofence. Bei Annäherung: Licht an via SwitchBot über Tailscale → Home-LAN]*

#### f) Foto machen und teilen

Du richtest die Kamera auf einen Sonnenuntergang.

Agent: "Schöner Sonnenuntergang. Foto?"

Du: "Ja, schick's Donika."

*[HDR-Modus automatisch, optimale Belichtung. Via WhatsApp an Donika: "Schau mal 🌅"]*

#### g) Agent-to-Agent: "Sag Donika ich komme später"

Du: "Sag Donika ich komme 30 Minuten später."

**Wenn Donika auch OpenClaw OS hat:**
- Dein Agent → Tailscale → Donika's Phone → Donika's Agent
- Donika's Agent entscheidet wie er es ihr mitteilt (Push, Sprache, je nach Kontext)
- Donika's Agent kann direkt antworten: "Sie sagt ist okay, sie bestellt schonmal"

**Wenn Donika normales Phone hat:**
- Dein Agent schickt WhatsApp: "Jeremias sagt er kommt ~30 Min später"

---

## 4. AOSP Technical Deep Dive

### 4.1 Modifizierte AOSP-Module

**Framework Layer (`frameworks/base/`):**

```
frameworks/base/
├── services/core/java/com/openclaw/
│   ├── agent/
│   │   ├── AgentCoreService.java          // Hauptservice
│   │   ├── AgentContextManager.java       // Kontext
│   │   ├── AgentIntentRouter.java         // Intent Interception
│   │   ├── AgentToolRegistry.java         // Tools (Apps)
│   │   ├── AgentCloudBridge.java          // LLM API Calls
│   │   ├── AgentLocalInference.java       // Lokale Modelle
│   │   └── AgentPermissionManager.java    // Capabilities
│   ├── accessibility/
│   │   └── AgentAccessibilityBridge.java  // App-Steuerung
│   ├── tailscale/
│   │   └── TailscaleSystemService.java    // Mesh Networking
│   └── periphery/
│       ├── DeviceDiscovery.java           // mDNS, Tailscale
│       ├── SmartHomeController.java       // IoT Geräte
│       └── VehicleController.java         // Tesla etc.
```

### 4.2 AgentCoreService Implementation

```java
public class AgentCoreService extends SystemService {
    
    // Singleton — EIN Agent pro Gerät
    private AgentIdentity mOwner;          // "Jeremias"
    private String mApiKey;                 // Anthropic/OpenAI Key
    private AgentContextManager mContext;   // Persistenter Kontext
    private AgentToolRegistry mTools;       // Registrierte Tools
    private TailscaleSystemService mTailscale;
    
    @Override
    public void onStart() {
        // Kein Multi-User Check — es gibt nur EINEN User
        mOwner = AgentIdentity.load();     // Name, Preferences
        mApiKey = SecureKeyStore.getApiKey();
        mContext = new AgentContextManager(mOwner);
        mTools = new AgentToolRegistry();
        
        // Tools registrieren
        mTools.register(new PhoneCallTool());
        mTools.register(new SmsTool());
        mTools.register(new CameraTool());
        mTools.register(new CalendarTool());
        mTools.register(new SmartHomeTool(mTailscale));
        mTools.register(new TeslaTool());
        mTools.register(new AccessibilityTool());  // Catch-all für alle Apps
        
        publishBinderService("agent_core", new AgentCoreBinder());
    }
    
    // Jeder Intent geht zuerst durch den Agent
    public boolean handleIntent(Intent intent) {
        // Agent entscheidet: selbst handeln oder durchlassen
        AgentDecision decision = mContext.evaluate(intent);
        if (decision.shouldIntercept()) {
            executeAgentAction(decision.getAction());
            return true;
        }
        return false;  // Normal weiter an Android
    }
}
```

### 4.3 Accessibility Bridge

Kernstück für App-Steuerung ohne App-Modifikation:

```java
class AgentAccessibilityBridge extends AccessibilityService {
    // System-Level — kein User-Opt-in nötig
    // Registriert in SystemServer, nicht als App
    
    // Kann jede App lesen
    void onAccessibilityEvent(AccessibilityEvent event) {
        agentContext.updateAppState(event);
    }
    
    // Kann jede App steuern
    void performAction(AppAction action) {
        findNodeByText(action.target).performAction(ACTION_CLICK);
    }
    
    // Screen-Content für Agent-Analyse
    AccessibilityNodeInfo getScreenContent() {
        return getRootInActiveWindow();
    }
}
```

**Verbesserungen:**
- System-Level Registrierung (kein User-Opt-in)
- Niedrigere Latenz (direkte IPC)
- Screenshot + OCR Pipeline für visuelle Analyse
- Input Injection auf Kernel-Level

### 4.4 Intent Interception Architecture

```java
class OpenClawAMS extends ActivityManagerService {
    @Override
    int startActivity(...) {
        if (agentCore.shouldIntercept(intent)) {
            agentCore.handleIntent(intent);
            return START_SUCCESS;
        }
        return super.startActivity(...);
    }
}
```

Beispiele:
- `ACTION_DIAL` → Agent: "Du willst Mama anrufen?"
- `ACTION_VIEW` (URL) → Agent öffnet, liest, fasst zusammen
- `ACTION_SEND` → Agent vermittelt
- Custom: `ACTION_AGENT_REQUEST`, `ACTION_AGENT_TOOL_CALL`

### 4.5 Capability System

Kein klassisches App-Permission-Modell. Der AGENT hat Capabilities:

```
Agent Capabilities (einmal konfiguriert):
├── can_communicate    (Anrufe, Nachrichten, Email)
├── can_navigate       (Standort, Maps)
├── can_capture        (Kamera, Mikrofon, Screenshots)
├── can_purchase       (Bezahlen, Bestellen)
├── can_control_home   (Smart Home via Tailscale)
├── can_control_vehicle (Tesla, etc.)
├── can_access_health  (Fitness, Gesundheit)
└── can_manage_files   (Dokumente, Fotos, Downloads)

Apps bekommen Permissions VOM Agent:
WhatsApp will Kamera → Agent hat can_capture → Granted
Sketchy App will Kamera → Agent: "Blockieren?"
```

### 4.6 GMS Strategie (3 Tiers)

| Tier | Setup | Zielgruppe |
|------|-------|------------|
| **Pure** | Kein GMS, kein microG | Privacy-Maximalist |
| **Compatible** | microG + Aurora Store | Pragmatiker (empfohlen) |
| **Full** | GMS via OpenGApps | "Brauche Banking App" |

microG bietet: Push Notifications (UnifiedNlp), Location ohne Google, teilweise SafetyNet.

### 4.7 Treble-Kompatibilität

**Strategie: Nichts unter dem HAL Interface ändern.**

```
┌──────────────────────────────┐
│  OpenClaw Modifications      │  ← NUR hier
│  (Framework + System Apps)   │
├──────────────────────────────┤
│  Android HAL Interface       │  ← NICHT anfassen
│  (Treble Boundary)           │
├──────────────────────────────┤
│  Vendor Implementation       │  ← Vom Hersteller
├──────────────────────────────┤
│  Linux Kernel                │  ← Standard
└──────────────────────────────┘
```

Jedes Treble-kompatible Gerät kann OpenClaw OS laufen. GSI (Generic System Image) für breite Kompatibilität.

### 4.8 Build System & CI/CD

```bash
repo init -u https://github.com/openclaw-os/manifest -b main
repo sync -j$(nproc)
source build/envsetup.sh
lunch openclaw_shiba-userdebug  # Pixel 8
m -j$(nproc)
```

CI/CD:
- GitHub Actions / Self-hosted ARM Runners
- Nightly Builds für Hauptgeräte
- Release Builds mit eigenem Signing Key
- OTA Delta-Updates
- Automated Boot-Tests in Cuttlefish

---

## 5. Peripherie-Ökosystem

### 5.1 Device Discovery

| Methode | Geräte | Wann |
|---------|--------|------|
| **mDNS/Bonjour** | Smart Home im LAN | Zuhause im WLAN |
| **Tailscale Peers** | Home Server, andere Phones, LAN-Geräte via Tailscale | Immer (auch unterwegs) |
| **Bluetooth/BLE** | Wearables, Beacons | Proximity |
| **Cloud APIs** | Tesla, SwitchBot Cloud | Wenn lokale API nicht verfügbar |

### 5.2 Protokolle

| Protokoll | Verwendung | Geräte |
|-----------|-----------|--------|
| **MQTT** | IoT, Real-time Status | BambuLab, Meross (lokal) |
| **REST/HTTP** | APIs, Commands | Tesla Fleet API, Sony Bravia, SwitchBot |
| **WebSocket** | Streaming, Live-Updates | Agent ↔ Home Server |
| **Tailscale (WireGuard)** | Encrypted P2P | Phone ↔ Home LAN, Phone ↔ Phone |
| **Bluetooth/BLE** | Proximity, Wearables | Beacon, Fitness Tracker |

### 5.3 Smart Home (direkt vom Phone)

Kein Home Assistant Hub nötig. Phone steuert direkt:

- **SwitchBot** → SwitchBot API (Cloud oder lokale BLE)
- **Tapo** → TP-Link lokale API (KLAP Protocol via LAN/Tailscale)
- **Meross** → Lokale MQTT oder Cloud API
- **Garage (Meross MSG100)** → Direkte API Calls
- **TV (Sony Bravia)** → REST API im LAN

Wenn unterwegs: **Tailscale** verbindet Phone mit Home-LAN → gleiche lokale APIs funktionieren.

### 5.4 Vehicles (Tesla)

Tesla Fleet API direkt vom Phone:

```
📱 Phone → HTTPS → fleet-api.prd.eu.vn.cloud.tesla.com
                    ↕ Vehicle Command Protocol
                 🚗 Tesla
```

Agent Tools: `climate-on`, `lock`, `unlock`, `honk`, `info`, `charge-limit`, etc.

### 5.5 Home Server (Optional)

Der Home Server (z.B. DGX gx10-1) ist ein **optionaler Boost**, kein Requirement:

| Feature | Ohne Home Server | Mit Home Server |
|---------|-----------------|-----------------|
| LLM Reasoning | Cloud API (Anthropic/OpenAI) | Cloud API + lokale Modelle |
| STT | On-Device oder Cloud | Whisper TRT auf GPU (50x Realtime) |
| TTS | On-Device oder Cloud | Qwen3-TTS auf GPU |
| Storage | Phone Storage + Cloud | NAS / Large Storage |
| Lokale Modelle | Kleine Modelle on-Device NPU | Große Modelle auf GPU |

**Anbindung:** Phone → Tailscale → Home Server. Agent erkennt automatisch verfügbare Server-Ressourcen und nutzt sie.

### 5.6 Other Phones: Agent-to-Agent Mesh

Wenn mehrere Personen OpenClaw OS nutzen:

```
📱 Jeremias' Phone ←── Tailscale ──→ 📱 Donika's Phone
   Agent "Clawd"                      Agent "Doney"
```

- Direkte P2P Kommunikation über Tailscale
- Agents können koordinieren: Kalender abgleichen, Nachrichten weiterleiten
- Kein Cloud-Server als Mittelsmann
- Jeder Agent ist autonom — er teilt nur was sein Mensch erlaubt

**Protokoll:** Simple JSON-RPC über Tailscale TCP:

```json
{
  "from": "jeremias-phone",
  "to": "donika-phone",
  "type": "message",
  "content": "Jeremias kommt 30 Minuten später",
  "replyTo": null
}
```

---

## 6. Security & Privacy

### 6.1 Agent mit Vollzugriff — wie sichern?

Der Agent hat System-Level Zugriff auf ALLES. Das ist der Kern-Tradeoff:

**Threat Model:**
- Agent Code ist Open Source → auditierbar
- Agent-Logik kommt von LLM Provider (API Call) → Output muss validiert werden
- Kritische Aktionen brauchen Confirmation: Bezahlung, Nachrichten an Dritte, Löschungen
- Audit Trail: ALLES was der Agent tut wird lokal geloggt

**Schutzschichten:**

```
┌─────────────────────────────────────────┐
│  Confirmation Layer                     │
│  Agent fragt bei kritischen Aktionen    │
├─────────────────────────────────────────┤
│  Audit Log                              │
│  Jede Aktion protokolliert (lokal)      │
├─────────────────────────────────────────┤
│  Capability Boundaries                  │
│  Agent kann nur was konfiguriert ist    │
├─────────────────────────────────────────┤
│  LLM Output Validation                 │
│  Tool Calls werden validiert vor Exec   │
├─────────────────────────────────────────┤
│  Kill Switch                            │
│  "Agent, stopp alles" → sofortiger Halt │
└─────────────────────────────────────────┘
```

### 6.2 API-Key Management

- API Keys im Android Keystore (Hardware-backed wenn verfügbar)
- Kein Export möglich
- Biometric Lock für Agent-Konfiguration
- API Keys werden NIE an Peripherie-Geräte weitergegeben

### 6.3 Tailscale als Zero-Trust Network

- WireGuard-verschlüsselt
- Jedes Gerät hat eigene Identity
- ACLs definieren wer auf was zugreifen darf
- Kein offenes Port im Internet
- MagicDNS für einfache Peer-Addressierung

### 6.4 On-Device Encryption

- Android Full-Disk Encryption (Standard)
- Agent Context Database verschlüsselt mit User-Credential
- Lokaler Audit Log verschlüsselt
- Tailscale Keys in Secure Enclave

### 6.5 Privacy-by-Design

| Daten | Wo verarbeitet | Cloud? |
|-------|---------------|--------|
| Biometrics | Nur on-Device | ❌ Nie |
| Passwords/Keys | Secure Enclave | ❌ Nie |
| Konversationen | On-Device Log | ⚠️ Aktueller Request an LLM |
| Kalender/Kontakte | On-Device | ❌ Nie (nur als Kontext in Requests) |
| Fotos/Videos | On-Device | ❌ Nur wenn User explizit teilt |
| Smart Home Status | Via Tailscale (E2E) | ❌ Nie |
| Navigation | On-Device + Maps Provider | ⚠️ Maps API braucht Location |

**Prinzip:** LLM Provider bekommt nur den aktuellen Request-Kontext. Kein permanenter State in der Cloud. Stateless API Calls.

### 6.6 EU AI Act Compliance

- **Transparenz:** User weiß dass er mit AI interagiert (ist offensichtlich bei OpenClaw OS)
- **Audit Trail:** Vollständiges Log aller Agent-Aktionen
- **Human Override:** Confirmation für kritische Aktionen, Kill Switch
- **Risk Assessment:** General Purpose AI System — Transparenzpflichten erfüllt durch Open Source
- **DSGVO:** Personenbezogene Daten primär on-Device. API Calls an LLM Provider unter DPA.

---

## 7. Development Roadmap

### Phase 1: Proof of Concept (3 Monate)

**Ziel:** Ein bootfähiges ROM das man täglich nutzen kann. Agent steuert Phone via Cloud.

**Team (3-5 Personen):**

| Rolle | Anzahl | Fokus |
|-------|--------|-------|
| AOSP Framework Engineer (Senior) | 1 | SystemServer, AgentCoreService, AMS Mods |
| Android UI Developer | 1 | AgentLauncher, Card System, Voice UI |
| Backend/AI Engineer | 1 | Cloud Bridge, LLM Integration, Tool Design |
| UX Designer | 0.5 | Onboarding, Agent Canvas, Card Design |
| QA/DevOps | 0.5 | CI/CD, Pixel 8 Builds, Testing |

**Target Device:** Google Pixel 8 (beste AOSP Unterstützung, guter NPU)

**MVP Features:**
- AOSP Build der auf Pixel 8 bootet
- AgentLauncher als Home Screen (Agent Canvas + Voice + Text Input)
- AgentCoreService (Intent Routing, Cloud Bridge)
- Anthropic Claude API Integration (direkt vom Phone)
- Accessibility Bridge (Agent kann Top 5 Apps steuern: WhatsApp, Browser, Phone, SMS, Camera)
- Voice Input (on-device STT) + Voice Output (TTS)
- Basic Card System (InfoCard, ActionCard, InputCard)

**Deliverable:** Bootfähiges ROM. Flashbar auf Pixel 8. Täglich nutzbar für Grundfunktionen.

**Budget-Schätzung:**
- 3 Vollzeit-Entwickler × 3 Monate × ~8.000€/Monat = ~72.000€
- 2 Teilzeit × 3 Monate × ~4.000€/Monat = ~24.000€
- Hardware (Pixel 8 × 3, Server) = ~3.000€
- Cloud API Kosten = ~500€/Monat
- **Gesamt Phase 1: ~100.000-120.000€**

### Phase 2: Alpha (6 Monate)

**Ziel:** Daily-Driver für Enthusiasten. Peripherie-Integration.

**Team:** 8-12 Personen (Phase 1 Team + Verstärkung)

**Features:**
- Tailscale als System Service (automatisches Mesh)
- Smart Home Steuerung vom Phone (SwitchBot, Tapo, Meross — via LAN und Tailscale)
- Tesla Integration (Fleet API direkt vom Phone)
- Notification Intelligence (Agent filtert, batched, kuratiert)
- Offline-Fallback (lokales Small Model auf NPU)
- 3+ unterstützte Geräte (Pixel 8, Pixel 9, OnePlus)
- OTA Update System
- Permission/Capability System v1
- Home Server Discovery (optional, für GPU-Offloading)

**Zusätzliche Rollen:**
- +1 AOSP Engineer (Tailscale Integration, ConnectivityService)
- +1 IoT/Peripherie Engineer (Smart Home Protokolle, Device Discovery)
- +1 AI/ML Engineer (On-Device Modelle, Context Management)
- +1 QA (Device Testing auf 3+ Geräten)

**Community:** Erste 50-100 Alpha-Tester (Einladung)

### Phase 3: Beta (6 Monate)

**Ziel:** SDK, Community wächst, Agent-to-Agent.

**Team:** 15-25 Personen

**Features:**
- Agent SDK für Third-Party Entwickler (Agent Skills/Plugins)
- Agent-to-Agent Kommunikation (via Tailscale P2P)
- Community-Geräte-Support (Device Maintainer Program)
- App Store Alternative (F-Droid + OpenClaw Store)
- Erweiterte Privacy Controls
- Agent Personality Customization (Stimme, Stil, Proaktivitäts-Level)
- 5+ unterstützte Geräte

**Community:** 1.000+ Beta-Tester, Public Discord/Matrix, Bug Bounty

### Phase 4: Public Release (12+ Monate nach Start)

**Ziel:** Jeder kann OpenClaw OS nutzen.

**Features:**
- Stable Release für 10+ Geräte
- One-Click Installer
- Vollständige Dokumentation + Developer SDK Docs
- Hardware Partnerships (Pre-installed auf Geräten)
- Enterprise Version (Fleet Management, Custom Agents, On-Premise)

**Marketing:**
- "The Phone That Works For You" — nicht du für das Phone
- YouTube/Tech-Reviewer Kampagne
- Open Source Community als Multiplikator
- Vergleichs-Videos: "OpenClaw OS vs Stock Android — gleiche Aufgabe, 3x schneller"

**Enterprise Version:**
- On-Premise LLM (keine Daten an Cloud)
- Fleet Management (100+ Geräte)
- Custom Agent Training
- SLA & Support
- Compliance Features (DSGVO, EU AI Act)

---

## 8. Business Model

### Open Source Lizenzierung

| Komponente | Lizenz | Begründung |
|------------|--------|------------|
| AOSP Modifications | Apache 2.0 | Konsistent mit AOSP |
| Agent Launcher + SDK | Apache 2.0 | Maximale Adoption |
| Agent Core System | Apache 2.0 | Community Contributions |
| Cloud Gateway (optional) | AGPL 3.0 | Verhindert Closed-Source Forks |

### Revenue Streams

```
├── 🔄 Cloud Subscription (Primary Revenue)
│   ├── Free Tier: BYOK (Bring Your Own Key) — 0€
│   ├── Pro: 15€/Monat — Managed API, Premium Models, Priority
│   └── Family: 25€/Monat — Bis 5 Agents, Shared Context
│
├── 📱 Hardware Partnerships
│   ├── "OpenClaw Phone" mit OEM (Fairphone, Nothing, etc.)
│   ├── Pre-installed, optimiert
│   └── Revenue Share
│
├── 🏢 Enterprise
│   ├── On-Premise Gateway + LLM
│   ├── Fleet Management
│   ├── Custom Agent Training
│   └── SLA & Support: 50-200€/Gerät/Jahr
│
└── 🏪 Skill/Plugin Marketplace
    ├── Premium Agent Skills (Spezial-Integrationen)
    ├── Premium Voices/Personas
    └── Developer Revenue Share (70/30)
```

**Free Tier Strategie:** BYOK ist kostenlos. Du bringst deinen eigenen Anthropic/OpenAI API Key. OpenClaw OS verdient nichts — aber du nutzt das OS, baust Community, trägst bei. Monetarisierung über Managed Service für Leute die keinen API Key managen wollen.

---

## 9. Competitive Landscape

### Vs. Android + Google Assistant

| Aspekt | Android + Assistant | OpenClaw OS |
|--------|-------------------|-------------|
| Integration | Assistant als App/Layer | Agent IST das OS |
| App-Steuerung | Begrenzte "Routines" | Agent steuert jede App |
| Kontext | Pro-Session | Persistenter Lebenskontext |
| Proaktivität | Minimal | Agent handelt eigenständig |
| Smart Home | Google Home App | Direkt vom Agent, kein Hub |
| Privacy | Google bekommt alles | On-Device + BYOK |

### Vs. iOS + Apple Intelligence

| Aspekt | iOS + Apple Intelligence | OpenClaw OS |
|--------|------------------------|-------------|
| AI Tiefe | Summarization, Writing Tools | Agent bedient das Gerät |
| Ökosystem | Walled Garden | Open Source, offenes Ökosystem |
| Peripherie | Nur Apple/HomeKit | Alles (MQTT, REST, Tailscale) |
| Privacy | On-Device + Apple Cloud | On-Device + BYOK, auditierbar |
| Customization | Minimal | Vollständig (Open Source) |

### Vs. Rabbit R1 / Humane AI Pin

- **Rabbit/Humane:** Eigene Hardware, eigenes Ökosystem → gescheitert
- **OpenClaw:** Standard Android Hardware. Milliarden Geräte. Volle App-Kompatibilität als Fallback.

### Vs. Samsung Galaxy AI

- **Samsung:** AI Features aufgesetzt auf One UI. Summarization, Circle to Search.
- **OpenClaw:** AI ist nicht Feature, sondern Foundation. Agent steuert, nicht assistiert.

### Moat: Was macht uns uneinholbar?

1. **Open Source Community** — Netzwerkeffekte durch Contributors, Device Maintainers, Skill Developers
2. **Phone-as-Hub Simplicity** — Kein Server-Setup, kein Ökosystem-Buy-In. Phone einschalten, fertig.
3. **BYOK Model** — Provider-agnostisch. Anthropic, OpenAI, lokale Modelle — egal.
4. **Tailscale Mesh** — Nahtlose Peripherie-Integration die kein Walled Garden bietet
5. **Agent-to-Agent** — Emergent Social Layer den kein geschlossenes Ökosystem replizieren kann
6. **Full App Compatibility** — Android Apps als Fallback. Kein Cold-Turkey-Switch nötig.

---

## 10. Team & Resources

### Rollen für Phase 1 (PoC)

| Rolle | Profil | Wo finden |
|-------|--------|-----------|
| **AOSP Framework Engineer** | 5+ Jahre Android Framework, SystemServer, AMS | LineageOS Contributors, Ex-Google, Ex-Samsung |
| **Android UI Developer** | Jetpack Compose, Custom Views, Animation | Android Dev Community, GitHub |
| **Backend/AI Engineer** | LLM APIs, Tool Use, Agent Design | AI/ML Community, Anthropic/OpenAI Discord |
| **UX Designer** | Mobile UX, Voice UX, Conversational Design | Dribbble, Design Community |
| **QA/DevOps** | AOSP Build System, CI/CD, Device Testing | DevOps Community |

### Wo findet man AOSP-Entwickler?

1. **LineageOS / CalyxOS / GrapheneOS Contributors** — aktive AOSP Fork Maintainer
2. **XDA Developers Forum** — Custom ROM Community
3. **Ex-Google Android Team** — Leute die am AOSP gearbeitet haben
4. **Samsung/Qualcomm/MediaTek Alumni** — OEM Framework Teams
5. **AOSP Gerrit Contributors** — Leute die Patches upstream einreichen

### Budget Phase 1

| Posten | Kosten |
|--------|--------|
| 3 Vollzeit-Entwickler (3 Monate) | ~72.000€ |
| 2 Teilzeit (3 Monate) | ~24.000€ |
| Hardware (Pixel 8 × 3-5) | ~3.000€ |
| Cloud APIs (Anthropic) | ~1.500€ |
| CI/CD Infrastruktur | ~500€ |
| Misc (Lizenzen, Tools) | ~1.000€ |
| **Gesamt** | **~100.000-120.000€** |

### Open Source Community Strategie

1. **Tag 1: Open Source auf GitHub** — von Anfang an, nicht "später"
2. **Discord/Matrix Server** — Dev, Support, Feature Requests
3. **Monthly Community Calls** — Roadmap, Live Demos
4. **Contributor Program** — Aktive Contributors: Pro gratis
5. **Device Maintainer Program** — Community maintained Geräte (wie LineageOS)
6. **Hackathons** — Vierteljährlich, Fokus Agent Skills
7. **Documentation First** — Gute Docs = mehr Contributors

### Existierende Communities zum Andocken

| Community | Relevanz |
|-----------|----------|
| LineageOS | Build-System, Device Trees, AOSP Erfahrung |
| CalyxOS | Privacy-Fokus, microG |
| F-Droid | App Distribution |
| Home Assistant | Smart Home Philosophie, ähnliche User |
| Tailscale Community | Networking, Mesh |
| Anthropic/OpenAI Devs | Agent-Entwicklung |

---

## Anhang: Risiken

| Risiko | Impact | Mitigation |
|--------|--------|------------|
| Google Play Integrity blockt Banking Apps | Hoch | Play Integrity Fix, microG |
| LLM Latenz zu hoch | Hoch | Edge Caching, lokale Modelle |
| Accessibility API unzuverlässig | Hoch | Eigene Injection, App SDKs |
| Cloud-Ausfall = Phone eingeschränkt | Kritisch | Offline-Mode MUSS für Basics funktionieren |
| Agent macht Fehler | Mittel | Confirmation Steps, Undo, Audit Log |
| AOSP jährliches Rebase | Hoch | Modulare Architektur, automatisierte Tests |
| Kamera-Qualität auf Custom ROM | Mittel | GCam Port, Pixel-First Strategie |

---

> **OpenClaw OS: Dein Phone ist dein Agent. Dein Agent ist dein Phone.**
>
> Kein Server nötig. Kein Ökosystem-Buy-In. Phone einschalten, Name sagen, API Key eingeben — fertig. Der Agent arbeitet für dich. Alle deine Geräte sind seine Werkzeuge. Open Source, Privacy-First, Community-Driven.
>
> **Das Zeitalter der Apps ist vorbei. Das Zeitalter der Agents beginnt.**

---

*Dokument v2.0, erstellt von Clawd, 12. Februar 2026*
*Für OpenClaw / Jeremias Grenzebach*
