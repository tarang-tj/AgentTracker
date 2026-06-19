# 🛰️ AgentTracker

A lightweight, dependency-free **visual dashboard for tracking autonomous local agents** — the kind of always-on scripts you schedule with `launchd`/`cron` that quietly do work for you each day.

It reads each agent's **real on-disk state** (scheduler status, run logs, output artifacts) and renders a self-contained dark-theme HTML dashboard. No servers, no frameworks, no network calls — just Python stdlib and a single HTML file you open in a browser.

## Why

Background agents fail silently. A cron job that stops firing, a delivery step that no-ops, a connector that goes blind — you don't notice until you needed the output. AgentTracker turns "I hope my agents ran" into a glanceable status board, with honest states derived from ground truth rather than hardcoded green checkmarks.

## What it shows

- **Per-agent status cards** — `HEALTHY` / `STALE` / `DEGRADED` / `FAILED`, each derived from real signals (is the scheduled job loaded? did it run today? did delivery succeed?).
- **Key facts** per agent — last run, freshness, output counts, delivery channel.
- **Merged activity timeline** — recent runs across all agents in one feed.
- **Auto-refresh** every 5 minutes.

## Status model

| State | Meaning |
|-------|---------|
| `HEALTHY` | Scheduled job loaded **and** a clean run recorded today |
| `STALE` | Job loaded but no run yet today (e.g. before its fire time) |
| `DEGRADED` | Ran today but a downstream step (delivery/connector) failed |
| `FAILED` | Job not loaded, or today's run errored / produced nothing |

## Usage

```bash
python3 gen-dashboard.py && open index.html
```

The generator (`gen-dashboard.py`) is the whole tool. It's currently wired to two example agents (a "Career Engine" daily-brief job and a "Kalshi Engine" paper-trading picks job) by reading their launchd labels, run-logs, and output files. **Adapt the `*_state()` functions** to point at your own agents' logs and artifacts.

## Design principles

1. **Ground truth, not assumptions.** Every field traces to a file or a `launchctl` line. The dashboard's job is to surface real failures, not to look reassuring.
2. **Zero dependencies.** Python stdlib only; the output is one portable HTML file.
3. **Read-only.** It never mutates agent state — it only observes.

## License

MIT
