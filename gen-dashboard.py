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
COLORS = {
    "HEALTHY": "#3fb950", "STALE": "#d29922", "DEGRADED": "#d29922", "FAILED": "#f85149",
}
STATUS_GLYPH = {"HEALTHY": "✓", "STALE": "◷", "DEGRADED": "!", "FAILED": "✕"}


def card(a: dict) -> str:
    color = COLORS.get(a["status"], "#8b949e")
    pulse = " pulse" if a["status"] == "HEALTHY" else ""
    glyph = STATUS_GLYPH.get(a["status"], "•")
    facts = "".join(
        f'<div class="row"><span class="k">{k}</span><span class="v">{v}</span></div>'
        for k, v in a["facts"]
    )
    note = f'<div class="note">{a["note"]}</div>' if a.get("note") else ""
    return f"""
    <div class="card" style="--c:{color};">
      <div class="accent"></div>
      <div class="card-head">
        <span class="emoji">{a['emoji']}</span>
        <span class="title">{a['name']}</span>
        <span class="badge"><span class="dot{pulse}"></span>{glyph} {a['status']}</span>
      </div>
      <div class="sched">{a['schedule']}</div>
      <div class="facts">{facts}</div>
      <div class="delivery">📲 {a['delivery']}</div>
      {note}
    </div>"""


def render(agents: list[dict], activity: list[tuple[str, str, str]]) -> str:
    cards = "".join(card(a) for a in agents)
    n = len(agents)
    counts = {s: sum(1 for a in agents if a["status"] == s) for s in ("HEALTHY", "STALE", "DEGRADED", "FAILED")}
    n_healthy = counts["HEALTHY"]
    pct = round(100 * n_healthy / n) if n else 0
    # health-meter segments, ordered worst-last so green dominates visually
    seg = "".join(
        f'<span style="flex:{counts[s]};background:{COLORS[s]};"></span>'
        for s in ("HEALTHY", "STALE", "DEGRADED", "FAILED") if counts[s]
    ) or '<span style="flex:1;background:#30363d;"></span>'
    pills = "".join(
        f'<span class="pill" style="--p:{COLORS[s]};">{counts[s]} {s.lower()}</span>'
        for s in ("HEALTHY", "STALE", "DEGRADED", "FAILED") if counts[s]
    )
    timeline = "".join(
        f'<div class="t-row"><span class="t-dot t-{src.lower()}"></span>'
        f'<span class="t-time">{t or "·"}</span>'
        f'<span class="t-tag t-{src.lower()}">{src}</span>'
        f'<span class="t-msg">{msg}</span></div>'
        for t, src, msg in activity
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Agent Tracker</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; margin:0; padding:0; }}
  body {{ font: 15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif;
         color:#c9d1d9; padding:34px 28px 48px; max-width:1040px; margin:0 auto;
         background:#0a0d12;
         background-image:
           radial-gradient(900px 500px at 12% -8%, rgba(63,185,80,.10), transparent 60%),
           radial-gradient(800px 500px at 100% 0%, rgba(88,166,255,.10), transparent 55%),
           radial-gradient(700px 600px at 50% 120%, rgba(137,87,229,.08), transparent 60%);
         background-attachment:fixed; min-height:100vh; }}
  @keyframes rise {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:none; }} }}
  @keyframes glow {{ 0%,100% {{ box-shadow:0 0 0 0 rgba(63,185,80,.55); }} 70% {{ box-shadow:0 0 0 6px rgba(63,185,80,0); }} }}

  header {{ display:flex; align-items:flex-end; justify-content:space-between; gap:20px; flex-wrap:wrap;
            animation:rise .5s ease both; }}
  .brand h1 {{ font-size:26px; font-weight:700; letter-spacing:-.5px; display:flex; align-items:center; gap:10px; }}
  .brand .sub {{ color:#8b949e; font-size:13px; margin-top:6px; }}

  .gauge {{ text-align:right; }}
  .gauge .big {{ font-size:34px; font-weight:750; line-height:1;
                 background:linear-gradient(180deg,#e6edf3,#9aa7b4); -webkit-background-clip:text; background-clip:text; color:transparent; }}
  .gauge .big small {{ font-size:15px; color:#6e7681; -webkit-text-fill-color:#6e7681; font-weight:600; }}
  .gauge .lbl {{ font-size:11px; color:#8b949e; text-transform:uppercase; letter-spacing:.7px; margin-top:3px; }}

  .meter {{ display:flex; height:8px; border-radius:6px; overflow:hidden; margin:18px 0 8px;
            box-shadow:inset 0 0 0 1px #21262d; animation:rise .55s ease both; }}
  .meter span {{ transition:flex .4s; }}
  .pills {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:26px; animation:rise .6s ease both; }}
  .pill {{ font-size:11px; font-weight:650; color:#c9d1d9; padding:3px 10px 3px 8px; border-radius:20px;
           background:color-mix(in srgb, var(--p) 14%, transparent); border:1px solid color-mix(in srgb, var(--p) 45%, transparent);
           display:inline-flex; align-items:center; gap:6px; }}
  .pill::before {{ content:""; width:7px; height:7px; border-radius:50%; background:var(--p); box-shadow:0 0 7px var(--p); }}

  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:18px; margin-bottom:34px; }}
  .card {{ position:relative; background:linear-gradient(180deg,#161b22,#12161d); border:1px solid #2a3138;
           border-radius:16px; padding:20px 20px 18px; overflow:hidden;
           box-shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
           transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
           animation:rise .5s ease both; }}
  .card:hover {{ transform:translateY(-3px); border-color:color-mix(in srgb,var(--c) 50%, #2a3138);
                 box-shadow:0 1px 2px rgba(0,0,0,.4), 0 16px 40px -16px color-mix(in srgb,var(--c) 60%, transparent); }}
  .card .accent {{ position:absolute; top:0; left:0; right:0; height:3px;
                   background:linear-gradient(90deg, var(--c), color-mix(in srgb,var(--c) 25%, transparent)); }}
  .card-head {{ display:flex; align-items:center; gap:11px; margin-bottom:3px; }}
  .emoji {{ font-size:22px; filter:drop-shadow(0 1px 2px rgba(0,0,0,.4)); }}
  .title {{ font-size:16.5px; font-weight:650; flex:1; letter-spacing:-.2px; }}
  .badge {{ font-size:11px; font-weight:750; padding:4px 10px; border-radius:20px; letter-spacing:.4px;
            display:inline-flex; align-items:center; gap:6px; white-space:nowrap;
            color:var(--c); background:color-mix(in srgb,var(--c) 15%, transparent);
            border:1px solid color-mix(in srgb,var(--c) 50%, transparent); }}
  .dot {{ width:7px; height:7px; border-radius:50%; background:var(--c); }}
  .dot.pulse {{ animation:glow 2s infinite; }}
  .sched {{ color:#8b949e; font-size:12px; margin-bottom:14px; }}
  .facts {{ display:flex; flex-direction:column; gap:7px; }}
  .row {{ display:flex; justify-content:space-between; gap:12px; font-size:13px; border-bottom:1px solid #20262e; padding-bottom:6px; }}
  .row:last-child {{ border-bottom:none; }}
  .k {{ color:#8b949e; }} .v {{ color:#e6edf3; font-weight:550; text-align:right; }}
  .delivery {{ margin-top:14px; font-size:12px; color:#58a6ff;
               background:rgba(88,166,255,.08); border:1px solid rgba(88,166,255,.18); border-radius:8px; padding:7px 10px; }}
  .note {{ margin-top:9px; font-size:11px; color:#e3b341; background:rgba(210,153,34,.10);
           border:1px solid rgba(210,153,34,.25); border-radius:8px; padding:7px 10px; line-height:1.45; }}

  h2 {{ font-size:12px; color:#8b949e; text-transform:uppercase; letter-spacing:.8px; margin:0 0 14px 2px; font-weight:700; }}
  .timeline {{ background:linear-gradient(180deg,#161b22,#12161d); border:1px solid #2a3138; border-radius:16px;
               padding:6px 18px; box-shadow:0 8px 24px -14px rgba(0,0,0,.6); animation:rise .65s ease both; }}
  .t-row {{ display:flex; gap:12px; align-items:center; padding:9px 0; border-bottom:1px solid #1c2228; font-size:13px; }}
  .t-row:last-child {{ border-bottom:none; }}
  .t-dot {{ width:8px; height:8px; border-radius:50%; flex:none; }}
  .t-time {{ color:#6e7681; font-variant-numeric:tabular-nums; min-width:120px; font-size:12px; }}
  .t-tag {{ font-size:10px; font-weight:750; padding:2px 8px; border-radius:6px; letter-spacing:.3px; }}
  .t-career, .t-dot.t-career {{ background:rgba(88,166,255,.16); color:#58a6ff; }}
  .t-dot.t-career {{ background:#58a6ff; box-shadow:0 0 7px rgba(88,166,255,.7); }}
  .t-kalshi, .t-dot.t-kalshi {{ background:rgba(188,140,255,.16); color:#bc8cff; }}
  .t-dot.t-kalshi {{ background:#bc8cff; box-shadow:0 0 7px rgba(188,140,255,.7); }}
  .t-msg {{ color:#c9d1d9; flex:1; }}
  footer {{ margin-top:28px; color:#6e7681; font-size:12px; text-align:center; }}
  footer code {{ background:#161b22; border:1px solid #2a3138; border-radius:5px; padding:1px 6px; color:#9aa7b4; }}
</style></head>
<body>
  <header>
    <div class="brand">
      <h1>🛰️ Agent Tracker</h1>
      <div class="sub">live view of {n} autonomous {'agent' if n==1 else 'agents'} · auto-refresh 5 min · generated {NOW:%Y-%m-%d %H:%M}</div>
    </div>
    <div class="gauge">
      <div class="big">{pct}<small>%</small></div>
      <div class="lbl">{n_healthy}/{n} healthy</div>
    </div>
  </header>
  <div class="meter">{seg}</div>
  <div class="pills">{pills}</div>
  <div class="grid">{cards}</div>
  <h2>Recent activity</h2>
  <div class="timeline">{timeline or '<div class="t-row"><span class="t-msg">No recent activity.</span></div>'}</div>
  <footer>Read-only view of real on-disk state (launchd · run-log · output artifacts). Regenerate: <code>engine dashboard</code></footer>
</body></html>"""


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
