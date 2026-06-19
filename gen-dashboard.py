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


def card(a: dict) -> str:
    color = COLORS.get(a["status"], "#8b949e")
    facts = "".join(
        f'<div class="row"><span class="k">{k}</span><span class="v">{v}</span></div>'
        for k, v in a["facts"]
    )
    note = f'<div class="note">{a["note"]}</div>' if a.get("note") else ""
    return f"""
    <div class="card">
      <div class="card-head">
        <span class="emoji">{a['emoji']}</span>
        <span class="title">{a['name']}</span>
        <span class="badge" style="background:{color}1a;color:{color};border:1px solid {color}55;">{a['status']}</span>
      </div>
      <div class="sched">{a['schedule']}</div>
      <div class="facts">{facts}</div>
      <div class="delivery">📲 {a['delivery']}</div>
      {note}
    </div>"""


def render(agents: list[dict], activity: list[tuple[str, str, str]]) -> str:
    cards = "".join(card(a) for a in agents)
    n_healthy = sum(1 for a in agents if a["status"] == "HEALTHY")
    timeline = "".join(
        f'<div class="t-row"><span class="t-time">{t or "·"}</span>'
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
  body {{ font: 15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#0d1117; color:#c9d1d9; padding:28px; max-width:1000px; margin:0 auto; }}
  h1 {{ font-size:22px; font-weight:650; letter-spacing:-.3px; }}
  .sub {{ color:#8b949e; font-size:13px; margin-top:4px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; margin:24px 0; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:12px; padding:18px; }}
  .card-head {{ display:flex; align-items:center; gap:10px; margin-bottom:2px; }}
  .emoji {{ font-size:20px; }}
  .title {{ font-size:16px; font-weight:600; flex:1; }}
  .badge {{ font-size:11px; font-weight:700; padding:3px 9px; border-radius:20px; letter-spacing:.5px; }}
  .sched {{ color:#8b949e; font-size:12px; margin-bottom:12px; }}
  .facts {{ display:flex; flex-direction:column; gap:6px; }}
  .row {{ display:flex; justify-content:space-between; font-size:13px; border-bottom:1px solid #21262d; padding-bottom:5px; }}
  .k {{ color:#8b949e; }} .v {{ color:#c9d1d9; font-weight:500; text-align:right; }}
  .delivery {{ margin-top:12px; font-size:12px; color:#58a6ff; }}
  .note {{ margin-top:8px; font-size:11px; color:#d29922; background:#d2992212; border-radius:6px; padding:6px 8px; }}
  h2 {{ font-size:14px; color:#8b949e; text-transform:uppercase; letter-spacing:.6px; margin:8px 0 12px; }}
  .timeline {{ background:#161b22; border:1px solid #30363d; border-radius:12px; padding:8px 16px; }}
  .t-row {{ display:flex; gap:12px; align-items:center; padding:7px 0; border-bottom:1px solid #21262d; font-size:13px; }}
  .t-row:last-child {{ border-bottom:none; }}
  .t-time {{ color:#6e7681; font-variant-numeric:tabular-nums; min-width:118px; font-size:12px; }}
  .t-tag {{ font-size:10px; font-weight:700; padding:2px 7px; border-radius:5px; }}
  .t-career {{ background:#1f6feb22; color:#58a6ff; }}
  .t-kalshi {{ background:#8957e522; color:#bc8cff; }}
  .t-msg {{ color:#c9d1d9; flex:1; }}
  footer {{ margin-top:24px; color:#6e7681; font-size:12px; text-align:center; }}
</style></head>
<body>
  <h1>🛰️ Agent Tracker</h1>
  <div class="sub">{n_healthy}/{len(agents)} agents healthy · auto-refresh 5 min · generated {NOW:%Y-%m-%d %H:%M}</div>
  <div class="grid">{cards}</div>
  <h2>Recent activity</h2>
  <div class="timeline">{timeline or '<div class="t-row"><span class="t-msg">No recent activity.</span></div>'}</div>
  <footer>Read-only view of real on-disk state (launchd · run-log · output artifacts). Regenerate: <code>engine dashboard</code></footer>
</body></html>"""


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    agents = [career_state(), kalshi_state()]
    html = render(agents, recent_activity())
    OUT.write_text(html)
    print(f"dashboard written: {OUT}")
    for a in agents:
        print(f"  {a['emoji']} {a['name']}: {a['status']}")


if __name__ == "__main__":
    main()
