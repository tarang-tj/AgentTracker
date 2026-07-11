# Jarvis AI Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace AgentTracker's rendered dashboard with the approved Jarvis identity-first companion interface while preserving deterministic status logic, demo safety, and dependency-free single-file output.

**Architecture:** Keep all collectors and status semantics unchanged in `gen-dashboard.py`. Add small deterministic presentation helpers, then replace only the HTML/CSS render layer with an inline decorative SVG face and responsive operations layout. A stdlib `unittest` suite becomes the repository's explicit gate because no CI or test configuration currently exists.

**Tech Stack:** Python 3 stdlib, generated semantic HTML, CSS, inline SVG, `unittest`; no JavaScript or runtime dependencies.

## Global Constraints

- `gen-dashboard.py` remains the single runtime generator.
- No changes to Career Engine, Kalshi, launchd jobs, connectors, delivery, or source-state collection.
- No network calls, web framework, external font, external image, JavaScript, canvas, or WebGL.
- Live `index.html` remains ignored; `demo.html` remains fabricated and public-safe.
- The avatar is original, decorative, and marked `aria-hidden="true"`.
- Status is always communicated by visible text, never color or facial expression alone.
- Motion must stop under `prefers-reduced-motion: reduce`.
- The layout must not horizontally overflow at 320px.
- Required gate after every task:
  `python3 -m unittest discover -s tests -v && python3 gen-dashboard.py --demo --out=/tmp/jarvis-demo.html`

---

### Task 1: Deterministic companion presentation model

**Files:**
- Modify: `gen-dashboard.py:209-261`
- Create: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: existing agent dictionaries with `name`, `status`, `facts`, `schedule`, `delivery`, and optional `note`.
- Produces: `greeting(now: datetime) -> str`.
- Produces: `companion_state(agents: list[dict]) -> dict[str, str]` with keys `summary`, `priority_label`, and `priority_detail`.
- Preserves: existing `career_state()`, `kalshi_state()`, `recent_activity()`, and status definitions.

- [ ] **Step 1: Add an import helper and failing presentation-model tests**

Create `tests/test_dashboard.py` with an `importlib.util.spec_from_file_location()` loader for `gen-dashboard.py`. Add tests asserting:

```python
def test_greeting_uses_local_hour():
    assert dashboard.greeting(datetime(2026, 7, 10, 9)) == "Good morning"
    assert dashboard.greeting(datetime(2026, 7, 10, 14)) == "Good afternoon"
    assert dashboard.greeting(datetime(2026, 7, 10, 20)) == "Good evening"


def test_companion_state_prioritizes_first_highest_severity_agent():
    agents = [
        {"name": "Brief", "status": "DEGRADED"},
        {"name": "Watcher", "status": "FAILED"},
        {"name": "Backup", "status": "FAILED"},
    ]
    result = dashboard.companion_state(agents)
    assert result["priority_label"] == "Watcher"
    assert "failed" in result["priority_detail"].lower()
    assert "1 system" in result["summary"].lower()


def test_companion_state_reports_nominal_when_all_healthy():
    result = dashboard.companion_state([
        {"name": "Brief", "status": "HEALTHY"},
        {"name": "Picks", "status": "HEALTHY"},
    ])
    assert result["priority_label"] == "Systems nominal"
    assert "operating normally" in result["summary"].lower()
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: errors because `greeting` and `companion_state` do not exist.

- [ ] **Step 3: Implement the minimal deterministic helpers**

In `gen-dashboard.py`, add:

```python
SEVERITY = {"FAILED": 0, "DEGRADED": 1, "STALE": 2, "HEALTHY": 3}


def greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Good morning"
    if now.hour < 18:
        return "Good afternoon"
    return "Good evening"


def companion_state(agents: list[dict]) -> dict[str, str]:
    if not agents:
        return {
            "summary": "No agent telemetry is available.",
            "priority_label": "Awaiting telemetry",
            "priority_detail": "No systems were discovered.",
        }
    healthy = sum(a["status"] == "HEALTHY" for a in agents)
    if healthy == len(agents):
        return {
            "summary": "All systems are operating normally.",
            "priority_label": "Systems nominal",
            "priority_detail": "No intervention is required.",
        }
    priority = min(agents, key=lambda a: SEVERITY.get(a["status"], 4))
    noun = "system" if healthy == 1 else "systems"
    return {
        "summary": f"{healthy} {noun} operating normally. {priority['name']} needs attention.",
        "priority_label": priority["name"],
        "priority_detail": f"Observed state: {priority['status'].lower()}.",
    }
```

Keep tie-breaking deterministic through Python's stable `min()` behavior.

- [ ] **Step 4: Run focused and full gates**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
python3 -m unittest discover -s tests -v
python3 gen-dashboard.py --demo --out=/tmp/jarvis-demo.html
```

Expected: presentation-model tests pass; demo render exits 0 and reports all four fabricated agents.

- [ ] **Step 5: Commit**

```bash
git add gen-dashboard.py tests/test_dashboard.py
git commit -m "Add deterministic Jarvis companion state"
```

---

### Task 2: Jarvis identity-first renderer and holographic face

**Files:**
- Modify: `gen-dashboard.py:216-363`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `greeting(NOW)`, `companion_state(agents)`, existing agent dictionaries, and existing activity tuples.
- Produces: `jarvis_face() -> str`, returning inline decorative SVG.
- Produces: updated `card(a: dict) -> str`.
- Produces: updated `render(agents, activity) -> str`, returning one offline HTML document.

- [ ] **Step 1: Add failing render-contract tests**

Add tests that render `demo_agents()` and `demo_activity()` and assert:

```python
def test_render_contains_jarvis_identity_and_human_face():
    html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())
    assert "<title>Jarvis — AI Companion</title>" in html
    assert ">JARVIS<" in html
    assert "AI Companion" in html
    assert 'class="jarvis-face"' in html
    assert 'aria-hidden="true"' in html
    assert "orb" not in html.lower()


def test_render_preserves_status_text_and_operational_details():
    html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())
    for status in ("HEALTHY", "STALE", "DEGRADED", "FAILED"):
        assert status in html
    assert "Daily Brief Agent" in html
    assert "Recent intelligence" in html
    assert "System readiness" in html


def test_render_is_offline_responsive_and_reduced_motion_safe():
    html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())
    assert "@media (max-width: 760px)" in html
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "overflow-x:hidden" in html.replace(" ", "")
    assert "https://" not in html
    assert "http://" not in html
    assert "<script" not in html.lower()
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: render-contract assertions fail against the existing Agent Tracker UI.

- [ ] **Step 3: Implement `jarvis_face()`**

Return an original inline SVG with:

- a human-head outline;
- symmetrical facial construction lines;
- eye, nose, and mouth geometry;
- cyan primary strokes and sparse amber diagnostic paths;
- `class="jarvis-face"`;
- `viewBox="0 0 260 330"`;
- `aria-hidden="true"`;
- no text, external references, raster images, character logos, or actor likeness.

- [ ] **Step 4: Replace the render composition**

Update `render()` to emit:

1. a semantic `<header>` with `JARVIS`, `AI Companion`, and generated timestamp;
2. `<main class="hud">`;
3. `<section class="identity-panel" aria-labelledby="companion-heading">` containing the face, greeting, summary, and companion status;
4. `<section class="operations-panel" aria-labelledby="readiness-heading">` containing readiness, priority, status pills, and agent modules;
5. `<section class="intelligence" aria-labelledby="intelligence-heading">` containing the activity timeline;
6. a read-only provenance footer.

Use the approved graphite/navy, cyan-white, amber, and failure-red system. Replace emoji-led card branding with compact agent indices and explicit status labels. Keep every existing fact, schedule, delivery field, and note visible.

- [ ] **Step 5: Add bounded CSS motion and responsive behavior**

Add:

- one finite entrance animation;
- a slow bounded contour scan on the face;
- `@media (prefers-reduced-motion: reduce)` disabling all animation and transitions;
- `@media (max-width: 760px)` collapsing the HUD to one column;
- `overflow-x: hidden`;
- `min-width: 0` on grid children;
- typography and spacing that remain readable at 320px.

Do not add JavaScript, continuous render loops, external assets, broad outer glows, or auto-playing audio.

- [ ] **Step 6: Run focused and full gates**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
python3 -m unittest discover -s tests -v
python3 gen-dashboard.py --demo --out=/tmp/jarvis-demo.html
```

Expected: all tests pass; demo render exits 0.

- [ ] **Step 7: Commit**

```bash
git add gen-dashboard.py tests/test_dashboard.py
git commit -m "Redesign dashboard as Jarvis AI companion"
```

---

### Task 3: Public artifact, documentation, and browser verification

**Files:**
- Modify: `README.md`
- Modify: `demo.html`
- Create or modify: `assets/dashboard.png`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: the final `gen-dashboard.py --demo` output.
- Produces: committed public-safe `demo.html`.
- Produces: committed browser screenshot `assets/dashboard.png`.
- Produces: README usage and identity documentation.

- [ ] **Step 1: Add failing public-demo safety tests**

Add a test that renders demo HTML to a temporary file and checks:

```python
def test_demo_output_contains_only_public_safe_fabricated_content():
    html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())
    forbidden = (
        str(Path.home()),
        "Documents/Obsidian Vault",
        ".career-engine",
        "kalshi-engine",
        "TJ Apple ID",
    )
    for value in forbidden:
        assert value not in html
```

Also assert the README's first heading and description identify Jarvis (AI Companion), while retaining a plain explanation that the repository tracks autonomous local agents.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: README identity assertion fails before documentation is updated.

- [ ] **Step 3: Update README**

Change the lead identity to `Jarvis (AI Companion)` and explain:

- AgentTracker is the dependency-free engine beneath Jarvis;
- the face and companion summary are deterministic presentation;
- the dashboard is read-only;
- demo data is fabricated;
- live `index.html` never leaves the machine.

Preserve usage commands, status definitions, architecture, adaptation guidance, and public-safety explanation.

- [ ] **Step 4: Regenerate the committed demo**

Run:

```bash
python3 gen-dashboard.py --demo --out=demo.html
```

Expected: exit 0 with `(DEMO — sample data)` and four status lines.

- [ ] **Step 5: Verify in a real browser**

Open `demo.html` through a local static server and inspect at desktop and 320px widths. Verify:

- Jarvis identity appears before telemetry;
- the face renders as a human head;
- no horizontal overflow;
- priority and readiness are visible without scrolling on desktop;
- status labels and facts are readable;
- reduced-motion emulation disables animation;
- DevTools reports zero failed network requests and zero console errors.

- [ ] **Step 6: Capture the public screenshot**

Capture `assets/dashboard.png` from demo mode only after animations have settled. Verify the image visually at full resolution and confirm cyan, amber, green, and red status signals are visible.

- [ ] **Step 7: Run the complete gate**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 gen-dashboard.py --demo --out=/tmp/jarvis-demo.html
```

Expected: all tests pass; demo render exits 0.

- [ ] **Step 8: Commit**

```bash
git add README.md demo.html assets/dashboard.png tests/test_dashboard.py
git commit -m "Publish the Jarvis AI companion demo"
```

---

### Task 4: Independent adversarial review and release gate

**Files:**
- Review only: all branch changes against `main`

**Interfaces:**
- Consumes: completed Tasks 1–3.
- Produces: independent review verdict and fresh verification evidence.

- [ ] **Step 1: Inspect the complete diff**

Review `git diff main...HEAD` for:

- changes outside approved scope;
- collector or status-semantics changes;
- live-data leakage;
- unescaped or malformed output;
- accessibility regressions;
- external dependencies or network requests;
- always-running animation/render loops;
- mobile overflow;
- mismatch between tests and actual browser behavior.

- [ ] **Step 2: Independently rerun the full gate**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 gen-dashboard.py --demo --out=/tmp/jarvis-demo-review.html
```

Expected: exit 0 for both commands.

- [ ] **Step 3: Independently repeat browser verification**

Check desktop, 320px, reduced motion, console, network, and visual face rendering from `/tmp/jarvis-demo-review.html`.

- [ ] **Step 4: Fix findings and rerun all checks**

Any finding blocks release until the complete gate and browser verification pass again.

- [ ] **Step 5: Push branch and open PR**

Only after all checks pass:

```bash
git push -u origin feat/jarvis-ai-companion
gh pr create --title "Redesign AgentTracker as Jarvis AI Companion" --body-file <prepared-pr-body>
```

