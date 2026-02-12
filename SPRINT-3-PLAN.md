# Sprint 3 Plan — Forge (Backend)

## Goals (from Coordinator)
- **CloudBridge** extracted as a **shared Kotlin module** + real tests.
- **AgentCoreService** integrated as **privileged app** under `packages/services/AgentCoreService` (no `frameworks/base` SystemServer mods).
- **Cuttlefish device definition** created: `device/openclaw/cuttlefish_clawdroid` (or similar).
- **AOSP 14 build boots on Cuttlefish** with AgentCoreService + Canvas App integrated.
- **Minimal privapp permissions** only (full SEPolicy deferred to Sprint 4).
- **min_sdk_version = 34** (AOSP 14).
- **AIDL is canonical** → update specs/docs that diverge and notify Prism.

---

## Current State (quick scan)
- `src/packages/AgentCoreService/` contains Kotlin skeleton + AIDL + Android.bp.
- CloudBridge is a stub inside AgentCoreService (not shared).
- `AndroidManifest.xml` references `BootReceiver` + `AccessibilityBridge` **classes that don’t exist as Android components**.
- Docs (`docs/AGENT-CORE-SERVICE.md`) list AIDL methods **not present** in canonical AIDL.
- `min_sdk_version` in `Android.bp` = **35** (needs 34).
- No device definition for OpenClaw Cuttlefish yet.

---

## Plan of Attack

### 1) Repo/Branch Hygiene
- Work on `forge/sprint-3-aosp-boot`.
- Ensure **repo of truth**: `~/openclaw-os`.
- Update `memory/2026-02-12-forge.md` with sprint notes.

### 2) Canonical API Alignment (AIDL → Docs)
- Compare `src/.../aidl/*.aidl` vs `docs/AGENT-CORE-SERVICE.md`.
- **Update docs to match AIDL** (remove non-existent methods like `getCapabilities()`, `getHistory()` etc).
- Send summary to Coordinator → Prism.

### 3) CloudBridge → Shared Kotlin Module
**Goal:** Make CloudBridge reusable by AgentCoreService + future clients.

**Proposed structure:**
```
src/shared/agent-core/
├── Android.bp           # java_library or java_library_static
├── src/main/kotlin/com/openclaw/agent/model/Models.kt
└── src/main/kotlin/com/openclaw/agent/bridge/CloudBridge.kt
```

**Steps:**
- Move `Models.kt` + `CloudBridge.kt` into shared module.
- Update `AgentCoreService` imports + Android.bp `static_libs`.
- Add **JVM unit tests** for CloudBridge request building + streaming parser (sample SSE fixtures).
- Add coroutines-test dependency if needed (keep tests lightweight).

### 4) AgentCoreService as Privileged App
**Goal:** Make it a real Android service that boots as a priv-app.

**Steps:**
- Convert `AgentCoreService` to extend `android.app.Service` (or wrap in `AgentCoreServiceApp`), implement `IAgentCoreService.Stub`.
- Provide minimal binder behaviors:
  - `submitRequest()` → stub stream or placeholder via callback.
  - `getAgentState()` + `isCloudAvailable()` + `emergencyStop()`.
- Add **BootReceiver** stub to start service on boot (manifest already expects it).
- Add **AccessibilityService** stub class (manifest currently points to `.bridge.AccessibilityBridge` which is not an Android component).
- Keep core logic class if needed (e.g., `AgentCoreEngine`) to avoid tight coupling with Android Service lifecycle.

### 5) Minimal Privapp Permissions
- Replace current broad allowlist with minimal set required for boot + network + accessibility stub.
- Start with: `INTERNET`, `ACCESS_NETWORK_STATE`, `FOREGROUND_SERVICE`, `RECEIVE_BOOT_COMPLETED`, `BIND_ACCESSIBILITY_SERVICE` (if service present).
- Defer everything else to Sprint 4.

### 6) Device Definition (Cuttlefish)
**Create:** `device/openclaw/cuttlefish_clawdroid/`

**Files:**
- `AndroidProducts.mk`
- `openclaw_cf_arm64_phone.mk` (inherit from `device/google/cuttlefish/vsoc_arm64/phone/aosp_cf.mk`)
- `device.mk` or similar for OpenClaw packages

**Include packages:**
- `AgentCoreService`
- `AgentCanvas` (from Prism workspace)
- Shared module(s)

### 7) AOSP Integration + Build
- In AOSP 14 tree (`~/aosp-android14`):
  - Map `packages/services/AgentCoreService` → openclaw-os repo via local manifest.
  - Map `device/openclaw/cuttlefish_clawdroid`.
  - Map `packages/apps/AgentCanvas` (from Prism) into AOSP.
- Update `min_sdk_version` → 34 in all AOSP modules.
- Build:
  - `m AgentCoreService AgentCanvas`
  - `lunch openclaw_cf_arm64_phone-userdebug`
  - Full build + **Cuttlefish boot**

### 8) Validation Checklist
- `adb shell service list | grep agent_core`
- `logcat -s AgentCoreService:V`
- Canvas app launches & binds to AIDL
- Cuttlefish boots to home screen without SEPolicy aborts

---

## Open Questions / Risks
- Kotlin module build in AOSP: ensure `java_library` w/ Kotlin support + coroutines deps available.
- CloudBridge SSE parser spec (Anthropic/OpenAI) may need fixture alignment.
- Accessibility service needs correct manifest metadata to avoid boot crash.

---

## Deliverables
- **SPRINT-3-PLAN.md** ✅
- Shared CloudBridge module + unit tests.
- Priv-app AgentCoreService with minimal binder + boot receiver.
- Device definition for Cuttlefish + build configs.
- AOSP 14 build boots with AgentCoreService + Canvas app.
- Updated docs reflecting canonical AIDL.

---

## Next Step (Immediate)
- Implement shared module + move Models/CloudBridge.
- Fix `min_sdk_version` to 34.
- Stub missing Android components (BootReceiver + AccessibilityService).
