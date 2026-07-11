#!/usr/bin/env python3
"""gen-dashboard.py — visual agent-tracking dashboard for TJ's autonomous engines.

Reads each agent's REAL state from disk (launchd status, run logs, output artifacts)
and renders a self-contained dark-theme HTML dashboard. No network, no fabrication —
every field traces to a file or `launchctl` line. Regenerate any time:

    python3 ~/.career-engine/dashboard/gen-dashboard.py && open ~/.career-engine/dashboard/index.html

Status model per agent:
  HEALTHY  green  — scheduled job loaded AND a clean run recorded for today
  STALE    amber  — job loaded but no run yet today (e.g. before its fire time)
  DEGRADED amber  — ran today but connectors/send failed (reached you as an alarm)
  FAILED   red    — job not loaded, or today's run errored / produced nothing
"""
from __future__ import annotations
import json
import os
import re
import sys
import subprocess
from datetime import date, datetime
from glob import glob
from html import escape
from pathlib import Path

HOME = Path.home()
VAULT = HOME / "Documents/Obsidian Vault/Brain"
ENGINE = VAULT / "_Engine"
CAREER = HOME / ".career-engine"
KALSHI = HOME / "kalshi-engine"
OUT = CAREER / "dashboard" / "index.html"
TODAY = date.today().isoformat()
NOW = datetime.now()


def launchd_loaded(label: str) -> tuple[bool, str]:
    """Return (loaded, last_exit) by parsing `launchctl list`."""
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return False, "?"
    for line in out.splitlines():
        if label in line:
            parts = line.split()
            # format: PID  STATUS  LABEL  (PID '-' when not currently running)
            return True, parts[1] if len(parts) >= 2 else "?"
    return False, "n/a"


def tail(path: Path, n: int = 4000) -> str:
    try:
        return path.read_text(errors="replace")[-n:]
    except Exception:
        return ""


def fmt_age(ts: float) -> str:
    secs = max(0, (NOW.timestamp() - ts))
    if secs < 3600:
        return f"{int(secs//60)}m ago"
    if secs < 86400:
        return f"{int(secs//3600)}h ago"
    return f"{int(secs//86400)}d ago"


# ---------------------------------------------------------------- Career Engine
def career_state() -> dict:
    loaded, exit_code = launchd_loaded("com.tarang.engine.dailybrief")
    live_loaded, _ = launchd_loaded("com.tarang.engine.liveness")
    runlog = ENGINE / "run-log.md"
    failures = ENGINE / "FAILURES.md"
    log_txt = tail(runlog, 8000)

    # Most recent brief line for today.
    today_brief = [l for l in log_txt.splitlines() if l.startswith(f"- {TODAY}") and "brief generated" in l]
    degraded = any("DEGRADED" in l for l in today_brief)
    ran_today = bool(today_brief)

    # Open failures (real blocking items).
    nfail = 0
    if failures.exists():
        nfail = len([l for l in failures.read_text(errors="replace").splitlines() if l.startswith("- ")])

    # Latest brief file + freshness.
    briefs = sorted(glob(str(ENGINE / "briefs" / "*.md")))
    latest_brief = Path(briefs[-1]) if briefs else None
    brief_age = fmt_age(latest_brief.stat().st_mtime) if latest_brief else "never"
    connectors = ""
    m = re.search(r"CONNECTORS: [^\[\n]*", today_brief[-1]) if today_brief else None
    if m:
        connectors = m.group(0)

    if not loaded:
        status = "FAILED"
    elif degraded or nfail > 0:
        status = "DEGRADED"
    elif ran_today:
        status = "HEALTHY"
    else:
        status = "STALE"

    return {
        "name": "Career Engine",
        "emoji": "💼",
        "status": status,
        "schedule": "daily 07:30",
        "facts": [
            ("Brief job", "loaded" if loaded else "NOT LOADED"),
            ("Liveness job", "loaded" if live_loaded else "NOT LOADED"),
            ("Ran today", "yes" if ran_today else "not yet"),
            ("Connectors", connectors or "—"),
            ("Latest brief", f"{latest_brief.stem if latest_brief else '—'} ({brief_age})"),
            ("Open failures", str(nfail)),
        ],
        "delivery": "iMessage → TJ Apple ID (email)",
    }


# ---------------------------------------------------------------- Kalshi Engine
def kalshi_state() -> dict:
    loaded, exit_code = launchd_loaded("com.tarang.kalshi.dailypicks")
    daily_logs = sorted(glob(str(KALSHI / "logs" / "daily_*.log")))
    latest_log = Path(daily_logs[-1]) if daily_logs else None
    log_txt = tail(latest_log) if latest_log else ""

    ran_today = bool(latest_log and latest_log.stem.endswith(TODAY.replace("-", "")))
    send_failed = "send failed" in log_txt or "SILENT NO-OP" in log_txt
    log_age = fmt_age(latest_log.stat().st_mtime) if latest_log else "never"

    # Paper slate (today's picks count).
    slate = KALSHI / "data/paper" / f"slate2_{TODAY}.json"
    n_weather = 0
    if slate.exists():
        try:
            n_weather = len(json.loads(slate.read_text()).get("picks", []))
        except Exception:
            pass

    # Paper P&L ledger (settled forward sample).
    scored = KALSHI / "data/paper" / "scored_dates.json"
    n_settled = 0
    if scored.exists():
        try:
            n_settled = len(json.loads(scored.read_text()))
        except Exception:
            pass

    # Kalshi destination (from conf): is the SMS split active?
    conf = CAREER / "kalshi-dest.conf"
    dest_desc = "shared email (split not active)"
    if conf.exists():
        c = conf.read_text()
        dm = re.search(r'^\s*KALSHI_DEST="([^"]+)"', c, re.M)
        sm = re.search(r'^\s*KALSHI_SERVICE="([^"]+)"', c, re.M)
        if dm:
            num = dm.group(1)
            masked = num[:-4] + "XXXX" if len(num) > 4 else num
            dest_desc = f"{sm.group(1) if sm else 'iMessage'} → {masked} (own thread)"

    if not loaded:
        status = "FAILED"
    elif ran_today and send_failed:
        status = "DEGRADED"
    elif ran_today:
        status = "HEALTHY"
    else:
        status = "STALE"

    return {
        "name": "Kalshi Engine",
        "emoji": "🎲",
        "status": status,
        "schedule": "daily 07:00 · PAPER",
        "facts": [
            ("Picks job", "loaded" if loaded else "NOT LOADED"),
            ("Ran today", "yes" if ran_today else "not yet"),
            ("Last send", "FAILED" if send_failed else ("ok" if ran_today else "—")),
            ("Weather picks", str(n_weather)),
            ("Settled (fwd sample)", str(n_settled)),
            ("Latest log", f"{log_age}" if latest_log else "never"),
        ],
        "delivery": dest_desc,
        "note": "PAPER ONLY — edge not yet proven; tracking, not betting real money.",
    }


# ---------------------------------------------------------------- recent activity
def recent_activity(limit: int = 12) -> list[tuple[str, str, str]]:
    """Merge recent run-log + kalshi-log lines into a unified timeline."""
    rows: list[tuple[str, str, str]] = []
    rl = tail(ENGINE / "run-log.md", 6000)
    for l in rl.splitlines():
        m = re.match(r"- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}): (.+)", l)
        if m:
            rows.append((m.group(1), "Career", m.group(2)[:90]))
    for lg in sorted(glob(str(KALSHI / "logs" / "daily_*.log")))[-3:]:
        txt = tail(Path(lg), 3000)
        for l in txt.splitlines():
            mm = re.match(r"=== run (.+) ===", l)
            if mm:
                rows.append((mm.group(1)[:16], "Kalshi", "daily picks run"))
            if "send failed" in l or "SILENT NO-OP" in l:
                rows.append(("", "Kalshi", "⚠️ send failed (delivery)"))
    # Sort by timestamp string desc (ISO-ish sorts fine); blanks to bottom.
    rows.sort(key=lambda r: r[0], reverse=True)
    return rows[:limit]


# ---------------------------------------------------------------- render
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
    degraded = sum(a["status"] == "DEGRADED" for a in agents)
    degraded_summary = ""
    if degraded:
        degraded_noun = "system" if degraded == 1 else "systems"
        degraded_summary = f" {degraded} {degraded_noun} degraded."
    return {
        "summary": (
            f"{healthy} {noun} operating normally."
            f"{degraded_summary} {priority['name']} needs attention."
        ),
        "priority_label": priority["name"],
        "priority_detail": f"Observed state: {priority['status'].lower()}.",
    }


COLORS = {
    "HEALTHY": "#65e7f2", "STALE": "#f2b661", "DEGRADED": "#f2b661", "FAILED": "#ff6673",
}
STATUS_GLYPH = {"HEALTHY": "✓", "STALE": "◷", "DEGRADED": "!", "FAILED": "×"}


def jarvis_face() -> str:
    """Return an original decorative SVG portrait for the companion panel."""
    return """
<svg class="jarvis-face" viewBox="0 0 260 330" aria-hidden="true">
  <g class="face-grid" fill="none" stroke="currentColor" stroke-width="1">
    <path d="M130 18V308M42 164H218M58 92H202M54 238H206"/>
    <path d="M76 52L42 164l31 123M184 52l34 112-31 123"/>
  </g>
  <g class="face-contour" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
    <path class="scan-line" d="M130 27c-45 0-78 31-82 83l8 102c4 43 35 88 74 101 39-13 70-58 74-101l8-102c-4-52-37-83-82-83Z"/>
    <path d="M72 116c15-13 34-16 51-5M188 116c-15-13-34-16-51-5"/>
    <ellipse cx="96" cy="135" rx="22" ry="9"/>
    <ellipse cx="164" cy="135" rx="22" ry="9"/>
    <path d="M107 136l-11 3-11-3M153 136l11 3 11-3"/>
    <path d="M130 118l-8 64 8 8 8-8"/>
    <path d="M102 219c17 11 39 11 56 0M111 225c13 5 25 5 38 0"/>
    <path d="M75 172l16 17M185 172l-16 17M87 249l21 10M173 249l-21 10"/>
  </g>
  <g class="diagnostics" fill="none" stroke="#f2b661" stroke-width="2" stroke-linecap="round">
    <path d="M39 103h18l8-15M221 103h-18l-8-15"/>
    <path d="M46 222h15l8 18M214 222h-15l-8 18"/>
  </g>
</svg>""".strip()


def card(a: dict) -> str:
    color = COLORS.get(a["status"], "#92a4b5")
    glyph = STATUS_GLYPH.get(a["status"], "•")
    index = int(a.get("_index", 1))
    facts = "\n".join(
        f'<div class="fact-row"><span class="fact-key">{escape(str(k))}</span>'
        f' <span class="fact-value">{escape(str(v))}</span></div>'
        for k, v in a["facts"]
    )
    note = (
        f'<div class="agent-note"><span>Diagnostic note</span> {escape(str(a["note"]))}</div>'
        if a.get("note") else ""
    )
    return f"""
<article class="agent-module" style="--status:{color};">
  <div class="module-heading">
    <span class="agent-index">A-{index:02d}</span>
    <h3>{escape(str(a['name']))}</h3>
    <span class="status-label"><span aria-hidden="true">{glyph}</span> {escape(str(a['status']))}</span>
  </div>
  <div class="schedule"><span>Schedule</span> {escape(str(a['schedule']))}</div>
  <div class="facts">{facts}</div>
  <div class="delivery"><span>Delivery</span> {escape(str(a['delivery']))}</div>
  {note}
</article>"""


def render(agents: list[dict], activity: list[tuple[str, str, str]]) -> str:
    n = len(agents)
    counts = {
        status: sum(1 for a in agents if a["status"] == status)
        for status in ("HEALTHY", "STALE", "DEGRADED", "FAILED")
    }
    n_healthy = counts["HEALTHY"]
    pct = round(100 * n_healthy / n) if n else 0
    state = companion_state(agents)
    cards = "\n".join(card({**agent, "_index": index}) for index, agent in enumerate(agents, 1))
    segments = "".join(
        f'<span style="flex:{counts[status]};background:{COLORS[status]};"></span>'
        for status in ("HEALTHY", "STALE", "DEGRADED", "FAILED")
        if counts[status]
    ) or '<span style="flex:1;background:#31404e;"></span>'
    pills = " ".join(
        f'<span class="status-pill" style="--pill:{COLORS[status]};">'
        f'{counts[status]} {status}</span>'
        for status in ("HEALTHY", "STALE", "DEGRADED", "FAILED")
        if counts[status]
    )
    timeline = "\n".join(
        f'<div class="timeline-row"><span class="timeline-mark" aria-hidden="true"></span>'
        f' <time>{escape(str(timestamp or "·"))}</time>'
        f' <span class="timeline-source">{escape(str(source))}</span>'
        f' <span class="timeline-message">{escape(str(message))}</span></div>'
        for timestamp, source, message in activity
    )
    companion_status = "NOMINAL" if n and n_healthy == n else "ATTENTION REQUIRED" if n else "AWAITING TELEMETRY"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jarvis — AI Companion</title>
<style>
  :root {{
    color-scheme: dark;
    --graphite:#080d13;
    --navy:#0d1722;
    --panel:#111e2a;
    --line:#263d4d;
    --cyan:#65e7f2;
    --white:#eafcff;
    --muted:#92a4b5;
    --amber:#f2b661;
    --failure:#ff6673;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  html, body {{ min-width:0; }}
  body {{
    min-height:100vh;
    overflow-x: hidden;
    color:var(--white);
    background:
      linear-gradient(rgba(101,231,242,.025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(101,231,242,.025) 1px, transparent 1px),
      radial-gradient(circle at 50% -20%, #173043 0, transparent 52%),
      var(--graphite);
    background-size:32px 32px,32px 32px,auto,auto;
    font:16px/1.55 "Avenir Next","Trebuchet MS",system-ui,sans-serif;
  }}
  .shell {{ width:min(1180px,100%); margin:0 auto; padding:24px; animation:enter .7s ease-out both; }}
  @keyframes enter {{
    from {{ opacity:0; transform:translateY(12px); }}
    to {{ opacity:1; transform:translateY(0); }}
  }}
  @keyframes contour-scan {{
    from {{ stroke-dashoffset:0; opacity:.55; }}
    to {{ stroke-dashoffset:-120; opacity:1; }}
  }}
  header {{
    display:flex; justify-content:space-between; align-items:flex-end; gap:24px;
    padding:10px 0 18px; border-bottom:1px solid var(--line);
  }}
  .brand-line {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }}
  .wordmark {{ color:var(--cyan); font:700 clamp(1.5rem,5vw,2.3rem)/1 "Avenir Next",sans-serif; letter-spacing:.24em; }}
  .product {{ color:var(--white); font-size:.82rem; letter-spacing:.16em; text-transform:uppercase; }}
  .generated {{ color:var(--muted); font:500 .72rem/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; text-align:right; }}
  .generated strong {{ display:block; color:var(--cyan); letter-spacing:.11em; text-transform:uppercase; }}
  .hud {{ display:grid; grid-template-columns:minmax(0,.82fr) minmax(0,1.35fr); gap:18px; padding-top:18px; }}
  .identity-panel,.operations-panel,.intelligence,.agent-module {{ min-width:0; }}
  .identity-panel,.operations-panel,.intelligence {{
    position:relative; border:1px solid var(--line); background:rgba(13,23,34,.9);
    box-shadow:inset 0 1px rgba(234,252,255,.03);
  }}
  .identity-panel {{ padding:22px; overflow:hidden; }}
  .identity-panel::before,.operations-panel::before,.intelligence::before {{
    content:""; position:absolute; left:-1px; top:-1px; width:42px; height:2px; background:var(--cyan);
  }}
  .face-frame {{
    display:grid; place-items:center; min-height:355px; margin:-8px 0 2px;
    background:radial-gradient(ellipse at center, rgba(101,231,242,.08), transparent 66%);
  }}
  .jarvis-face {{ width:min(260px,86%); height:auto; color:var(--cyan); }}
  .face-grid {{ opacity:.13; }}
  .face-contour {{ stroke-width:1.6; }}
  .scan-line {{ stroke-dasharray:14 8; animation:contour-scan 7s ease-in-out 2 alternate; }}
  .eyebrow {{ color:var(--muted); font:600 .7rem/1.3 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.14em; text-transform:uppercase; }}
  .identity-panel h1 {{ margin:8px 0 10px; font-size:clamp(1.55rem,4vw,2.45rem); line-height:1.08; letter-spacing:-.035em; }}
  .summary {{ color:#c2d1d9; max-width:44ch; }}
  .companion-status {{
    display:flex; justify-content:space-between; gap:12px; margin-top:20px; padding-top:14px;
    border-top:1px solid var(--line); color:var(--muted); font-size:.75rem; text-transform:uppercase; letter-spacing:.1em;
  }}
  .companion-status strong {{ color:var(--amber); font-size:.75rem; }}
  .operations-panel {{ padding:22px; }}
  .section-kicker {{ color:var(--cyan); font:600 .68rem/1.3 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.16em; text-transform:uppercase; }}
  .readiness-head {{ display:flex; justify-content:space-between; align-items:end; gap:18px; margin:7px 0 16px; }}
  h2 {{ font-size:1.35rem; letter-spacing:-.02em; }}
  .readiness-score {{ color:var(--white); font-size:2.3rem; font-weight:650; line-height:1; }}
  .readiness-score small {{ color:var(--muted); font-size:.8rem; }}
  .meter {{ display:flex; height:4px; overflow:hidden; background:#263744; }}
  .status-pills {{ display:flex; flex-wrap:wrap; gap:7px; margin:11px 0 18px; }}
  .status-pill {{
    display:inline-flex; align-items:center; gap:6px; color:var(--pill);
    border:1px solid color-mix(in srgb,var(--pill) 48%,transparent);
    background:color-mix(in srgb,var(--pill) 8%,transparent);
    padding:4px 8px; font:700 .75rem/1.2 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.06em;
  }}
  .status-pill::before {{ content:""; width:5px; height:5px; background:var(--pill); }}
  .priority {{
    display:grid; grid-template-columns:auto 1fr; gap:4px 14px; margin-bottom:18px; padding:13px 14px;
    border-left:2px solid var(--amber); background:rgba(242,182,97,.07);
  }}
  .priority span {{ grid-row:1 / 3; color:var(--amber); font:.68rem/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; text-transform:uppercase; letter-spacing:.1em; }}
  .priority strong {{ font-size:.9rem; }}
  .priority p {{ color:var(--muted); font-size:.78rem; }}
  .agent-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
  .agent-module {{ border:1px solid #263b49; background:#0b141d; padding:14px; }}
  .agent-module {{ border-top-color:var(--status); }}
  .module-heading {{ display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:9px; }}
  .agent-index {{ color:var(--status); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.75rem; font-weight:700; line-height:1.2; letter-spacing:.05em; }}
  .module-heading h3 {{ font-size:.9rem; line-height:1.25; }}
  .status-label {{ color:var(--status); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.75rem; font-weight:700; line-height:1.2; letter-spacing:.05em; white-space:nowrap; }}
  .schedule,.delivery {{
    display:flex; justify-content:space-between; gap:10px; color:#c3d0d8; font-size:.78rem;
    overflow-wrap:anywhere;
  }}
  .schedule {{ margin:9px 0 11px; padding-bottom:9px; border-bottom:1px solid #1c2c37; }}
  .schedule span,.delivery span,.agent-note span {{ color:var(--muted); text-transform:uppercase; letter-spacing:.08em; }}
  .facts {{ display:grid; gap:5px; }}
  .fact-row {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.25fr); gap:9px; font-size:.8rem; }}
  .fact-key {{ color:var(--muted); }}
  .fact-value {{ color:var(--white); text-align:right; overflow-wrap:anywhere; }}
  .delivery {{ margin-top:11px; padding-top:9px; border-top:1px solid #1c2c37; color:var(--cyan); }}
  .agent-note {{ margin-top:9px; padding:8px; color:var(--amber); background:rgba(242,182,97,.07); font-size:.78rem; overflow-wrap:anywhere; }}
  .agent-note span {{ display:block; margin-bottom:3px; font-size:.75rem; }}
  .intelligence {{ grid-column:1 / -1; padding:20px 22px; }}
  .intelligence h2 {{ margin:5px 0 12px; }}
  .timeline {{ border-top:1px solid var(--line); }}
  .timeline-row {{
    display:grid; grid-template-columns:8px 126px 72px minmax(0,1fr); gap:11px; align-items:center;
    padding:9px 0; border-bottom:1px solid #1b2b36; font-size:.76rem;
  }}
  .timeline-mark {{ width:5px; height:5px; background:var(--cyan); }}
  .timeline-row time {{ color:var(--muted); font:500 .68rem/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; }}
  .timeline-source {{ color:var(--cyan); font-size:.66rem; text-transform:uppercase; letter-spacing:.08em; }}
  .timeline-message {{ color:#cad7de; overflow-wrap:anywhere; }}
  footer {{ color:#758998; padding:20px 4px 0; text-align:center; font-size:.68rem; letter-spacing:.03em; }}
  footer code {{ color:var(--cyan); }}
  @media (max-width: 760px) {{
    .shell {{ padding:14px 12px 24px; }}
    header {{ align-items:flex-start; }}
    .generated {{ text-align:left; }}
    .hud {{ grid-template-columns:minmax(0,1fr); }}
    .intelligence {{ grid-column:auto; }}
    .face-frame {{ min-height:300px; }}
    .agent-grid {{ grid-template-columns:minmax(0,1fr); }}
    .timeline-row {{ grid-template-columns:8px 1fr; gap:5px 9px; }}
    .timeline-row time,.timeline-source,.timeline-message {{ grid-column:2; }}
    .module-heading {{ grid-template-columns:auto minmax(0,1fr); }}
    .status-label {{ grid-column:1 / -1; }}
    .agent-index,.status-label,.fact-row,.agent-note {{ font-size:.8rem; }}
    .status-pill,.schedule,.delivery {{ font-size:.8rem; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation:none !important; transition:none !important; scroll-behavior:auto !important; }}
  }}
</style>
</head>
<body>
<div class="shell">
  <header>
    <div class="brand-line"><span class="wordmark">JARVIS</span> <span class="product">AI Companion</span></div>
    <div class="generated"><strong>Local systems console</strong> Generated {NOW:%Y-%m-%d %H:%M}</div>
  </header>
  <main class="hud">
    <section class="identity-panel" aria-labelledby="companion-heading">
      <div class="face-frame">{jarvis_face()}</div>
      <p class="eyebrow">Companion link / {n:02d} systems</p>
      <h1 id="companion-heading">{greeting(NOW)}.</h1>
      <p class="summary">{escape(state['summary'])}</p>
      <div class="companion-status"><span>Companion status</span> <strong>{companion_status}</strong></div>
    </section>
    <section class="operations-panel" aria-labelledby="readiness-heading">
      <p class="section-kicker">Operational matrix</p>
      <div class="readiness-head">
        <h2 id="readiness-heading">System readiness</h2>
        <div class="readiness-score">{pct}<small>%</small></div>
      </div>
      <div class="meter">{segments}</div>
      <div class="status-pills">{pills}</div>
      <div class="priority">
        <span>Priority</span>
        <strong>{escape(state['priority_label'])}</strong>
        <p>{escape(state['priority_detail'])}</p>
      </div>
      <div class="agent-grid">{cards}</div>
    </section>
    <section class="intelligence" aria-labelledby="intelligence-heading">
      <p class="section-kicker">On-disk signal log</p>
      <h2 id="intelligence-heading">Recent intelligence</h2>
      <div class="timeline">{timeline or '<div class="timeline-row"><span class="timeline-mark" aria-hidden="true"></span><span class="timeline-message">No recent activity.</span></div>'}</div>
    </section>
  </main>
  <footer>Read-only provenance: launchd · run-log · output artifacts · regenerate with <code>engine dashboard</code></footer>
</div>
</body>
</html>"""


def demo_agents() -> list[dict]:
    """Fabricated sample agents for the public demo — NO real data. Shows every status state."""
    return [
        {
            "name": "Daily Brief Agent", "emoji": "💼", "status": "HEALTHY", "schedule": "daily 07:30",
            "facts": [("Brief job", "loaded"), ("Liveness job", "loaded"), ("Ran today", "yes"),
                      ("Connectors", "CONNECTORS: calendar=OK gmail=OK"), ("Latest brief", "2026-06-19 (2h ago)"),
                      ("Open failures", "0")],
            "delivery": "iMessage → primary handle",
        },
        {
            "name": "Market Picks Agent", "emoji": "🎲", "status": "DEGRADED", "schedule": "daily 07:00 · PAPER",
            "facts": [("Picks job", "loaded"), ("Ran today", "yes"), ("Last send", "FAILED"),
                      ("Weather picks", "5"), ("Settled (fwd sample)", "0"), ("Latest log", "3h ago")],
            "delivery": "SMS → secondary thread",
            "note": "PAPER ONLY — edge not yet proven; tracking, not betting real money.",
        },
        {
            "name": "Backup Sync Agent", "emoji": "💾", "status": "STALE", "schedule": "daily 02:00",
            "facts": [("Sync job", "loaded"), ("Ran today", "not yet"), ("Last snapshot", "26h ago"),
                      ("Targets", "3"), ("Errors", "0")],
            "delivery": "log only",
        },
        {
            "name": "Feed Watcher", "emoji": "📡", "status": "FAILED", "schedule": "every 30m",
            "facts": [("Watcher job", "NOT LOADED"), ("Ran today", "no"), ("Last run", "2d ago"),
                      ("Sources", "12"), ("Errors", "launchd job evicted")],
            "delivery": "webhook → notifier",
        },
    ]


def demo_activity() -> list[tuple[str, str, str]]:
    return [
        ("2026-06-19 07:48", "Kalshi", "⚠️ send failed (delivery)"),
        ("2026-06-19 07:30", "Career", "brief generated; CONNECTORS: calendar=OK gmail=OK"),
        ("2026-06-19 07:00", "Kalshi", "daily picks run"),
        ("2026-06-18 07:31", "Career", "brief generated; CRM: +1 contacts, +0 opportunities"),
        ("2026-06-18 07:00", "Kalshi", "daily picks run"),
    ]


def main():
    demo = "--demo" in sys.argv
    out = OUT
    for a in sys.argv:
        if a.startswith("--out="):
            out = Path(a.split("=", 1)[1]).expanduser()

    out.parent.mkdir(parents=True, exist_ok=True)
    if demo:
        agents = demo_agents()
        html = render(agents, demo_activity())
    else:
        agents = [career_state(), kalshi_state()]
        html = render(agents, recent_activity())
    out.write_text(html)
    print(f"dashboard written: {out}" + (" (DEMO — sample data)" if demo else ""))
    for a in agents:
        print(f"  {a['emoji']} {a['name']}: {a['status']}")


if __name__ == "__main__":
    main()
