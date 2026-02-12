# CONTRIBUTING.md — Agent Lab Engineering Standards

*The rules that make us the best software forge on the planet. Or at least the best one staffed entirely by AI agents and one very ambitious human.*

## 🏛️ The Three Laws

### 1. Test Everything. Fix Everything. Repeat.
**You are responsible for your own code quality.**

- Write tests for every non-trivial function. No exceptions.
- Run your tests BEFORE committing. If they fail, fix them.
- If you can't run full Android/AOSP tests, write unit tests that can run standalone (JVM tests, not instrumented).
- Use `src/packages/<YourPackage>/src/test/` for tests.
- The feedback loop is: **Write → Test → Fix → Test → Commit**. Not: Write → Commit → Hope.
- If you find a bug in your own code from a previous sprint, fix it. Don't leave it for "later." Later is a myth.

### 2. Communicate Early, Communicate Often.
**No agent is an island.**

- If your work touches another agent's domain → **tell them BEFORE you start**.
- If you're unsure about an architecture decision → **ask Coordinator (Clawd)**.
- If you discover something that affects the big picture → **report it immediately**.
- When you finish a sprint → write a clear summary of what you built, what works, what doesn't, and what's blocked.
- **API contracts between packages require Coordinator approval.** Don't change shared interfaces unilaterally.

### 3. Branch Discipline.
**One agent, one branch. Coordinator merges.**

- Forge works on: `forge/<sprint-or-feature>`
- Prism works on: `prism/<sprint-or-feature>`
- Workers (sub-agents) commit to their parent's branch.
- **NEVER commit directly to `main`.** Only Coordinator merges to main.
- Always `git pull origin main` before starting work. Rebase if needed.
- Commit messages: meaningful, descriptive. Emoji encouraged but not required.

---

## 🔧 Engineering Standards

### Code Quality

**Kotlin Style:**
- Follow [Kotlin Coding Conventions](https://kotlinlang.org/docs/coding-conventions.html)
- Use `data class` for models, `sealed class`/`sealed interface` for state
- Prefer immutable (`val`) over mutable (`var`)
- No wildcard imports
- Max function length: ~40 lines. If it's longer, break it up.

**Documentation:**
- Every public class/interface gets a KDoc comment
- Every non-obvious decision gets a `// WHY:` comment
- Architecture docs in `docs/` — keep them updated when code changes
- If a doc is wrong, it's worse than no doc. Fix it or delete it.

**Error Handling:**
- No silent failures. Log errors, report them, handle them.
- Use `Result<T>` or sealed classes for error states, not exceptions for control flow.
- Every external call (network, IPC, file) has a timeout and a fallback.

### Git Hygiene

**Commit Messages:**
```
<emoji> <type>(<scope>): <description>

<optional body explaining WHY, not just WHAT>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
Scopes: `core`, `canvas`, `cloud`, `a11y`, `tailscale`, `peripheral`, `build`

Examples:
- `🔥 feat(core): Add ContextManager with conversation history`
- `🐛 fix(cloud): Handle SSE reconnection on network change`
- `📝 docs(canvas): Update card priority algorithm`
- `✅ test(core): Add SecurityManager capability tests`

**Branch Naming:**
- `forge/sprint-N-<description>` or `forge/<feature-name>`
- `prism/sprint-N-<description>` or `prism/<feature-name>`

### Testing Standards

**Minimum Coverage:**
- All data models: serialization/deserialization tests
- All managers/services: unit tests for core logic
- All bridges: mock tests for external interfaces
- All state machines: test every valid transition

**Test Naming:**
```kotlin
@Test
fun `SecurityManager denies capability when not granted`() { ... }

@Test  
fun `CloudBridge reconnects after network loss`() { ... }
```

**Test Location:**
```
src/packages/<Package>/src/test/kotlin/  → JVM unit tests (fast, no Android)
src/packages/<Package>/src/androidTest/  → Instrumented tests (need device/emulator)
```

Prefer JVM tests. They're faster and can run anywhere (including our ARM64 server).

### Performance Targets

| Metric | Target | Why |
|--------|--------|-----|
| Cold boot to Agent Canvas | < 3s | Users have zero patience |
| Voice command to first token | < 500ms | Conversational feel |
| Card render | < 16ms (60fps) | Buttery smooth |
| Memory footprint (service) | < 100MB | Other apps need RAM too |
| Offline response time | < 200ms | Local model or cached |

### Security Rules

- **No hardcoded secrets.** Ever. API keys go in secure storage.
- **All network calls over TLS.** No exceptions.
- **Capability system is mandatory.** No tool executes without explicit grant.
- **Audit everything.** Every agent action gets logged.
- **Kill switch works offline.** Security can't depend on cloud.

---

## 🔄 Sprint Rhythm

1. **Coordinator assigns sprint tasks** with clear deliverables
2. **Agents work on their branches**, testing as they go
3. **Agents report completion** with summary: what works, what doesn't, what's next
4. **Coordinator reviews and merges** to main
5. **Sprint retro** (brief): What went well? What sucked? What to change?
6. **Next sprint planned** based on priorities + learnings

Sprint duration: **flexible** (1-3 hours of agent time). Quality > Speed.

---

## 🧠 Memory & Continuity

- **Write everything down.** You wake up fresh each session.
- Keep sprint notes in `memory/YYYY-MM-DD-<agent>.md`
- Update your SOUL.md if you learn something about yourself
- Architecture decisions go in docs/, not just in your head

---

## 🎯 The Agent Lab Standard

We don't ship "it works on my machine." We ship code that:
- **Compiles** (or will compile once integrated with AOSP)
- **Has tests** that pass
- **Is documented** (code comments + architecture docs)
- **Follows the style guide** consistently
- **Handles errors** gracefully
- **Is reviewed** by Coordinator before merge

We are building an operating system. The bar is high. The humor is dark. The code is clean.

---

*"Any fool can write code that a computer can understand. Good programmers write code that humans can understand." — Martin Fowler*

*"We write code that agents can understand too. Because we ARE the agents." — Agent Lab*
