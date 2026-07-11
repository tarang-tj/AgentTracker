import importlib.util
import re
import unittest
from datetime import datetime
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "gen-dashboard.py"
README_PATH = MODULE_PATH.parent / "README.md"
SPEC = importlib.util.spec_from_file_location("dashboard", MODULE_PATH)
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class DashboardPresentationTests(unittest.TestCase):
    def assert_rem_font_size_at_least(self, html, selector, minimum):
        rule = re.search(rf"{re.escape(selector)}\s*\{{([^}}]+)\}}", html, re.S)
        self.assertIsNotNone(rule, f"missing CSS rule for {selector}")
        size = re.search(r"font-size:\s*([0-9.]+)rem", rule.group(1))
        self.assertIsNotNone(size, f"missing explicit rem font-size for {selector}")
        self.assertGreaterEqual(float(size.group(1)), minimum)

    def test_status_palette_uses_distinct_semantic_colors(self):
        primary_cyan = "#65e7f2"
        expected = {
            "HEALTHY": "#72c98b",
            "STALE": "#f2b661",
            "DEGRADED": "#f2b661",
            "FAILED": "#ff6673",
        }

        self.assertEqual(dashboard.COLORS, expected)
        self.assertNotEqual(dashboard.COLORS["HEALTHY"], primary_cyan)
        red, green, blue = (
            int(dashboard.COLORS["HEALTHY"][offset:offset + 2], 16)
            for offset in (1, 3, 5)
        )
        self.assertGreater(green, red)
        self.assertGreater(green, blue)
        self.assertEqual(
            len({
                dashboard.COLORS["HEALTHY"],
                dashboard.COLORS["STALE"],
                dashboard.COLORS["FAILED"],
            }),
            3,
        )

    def test_greeting_uses_local_hour(self):
        self.assertEqual(
            dashboard.greeting(datetime(2026, 7, 10, 9)),
            "Good morning",
        )
        self.assertEqual(
            dashboard.greeting(datetime(2026, 7, 10, 14)),
            "Good afternoon",
        )
        self.assertEqual(
            dashboard.greeting(datetime(2026, 7, 10, 20)),
            "Good evening",
        )

    def test_demo_output_contains_only_public_safe_fabricated_content(self):
        html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())
        forbidden = (
            str(Path.home()),
            "Documents/Obsidian Vault",
            ".career-engine",
            "kalshi-engine",
            "TJ Apple ID",
        )

        for value in forbidden:
            self.assertNotIn(value, html)

    def test_readme_identifies_jarvis_and_explains_agent_tracking(self):
        readme = README_PATH.read_text()
        lines = readme.splitlines()

        self.assertEqual(lines[0], "# Jarvis (AI Companion)")
        self.assertIn("tracks autonomous local agents", readme.lower())

    def test_companion_state_prioritizes_first_highest_severity_agent(self):
        agents = [
            {"name": "Brief", "status": "DEGRADED"},
            {"name": "Watcher", "status": "FAILED"},
            {"name": "Backup", "status": "FAILED"},
        ]

        result = dashboard.companion_state(agents)

        self.assertEqual(result["priority_label"], "Watcher")
        self.assertIn("failed", result["priority_detail"].lower())
        self.assertIn("1 system", result["summary"].lower())

    def test_companion_state_reports_nominal_when_all_healthy(self):
        result = dashboard.companion_state([
            {"name": "Brief", "status": "HEALTHY"},
            {"name": "Picks", "status": "HEALTHY"},
        ])

        self.assertEqual(result["priority_label"], "Systems nominal")
        self.assertIn("operating normally", result["summary"].lower())

    def test_render_contains_jarvis_identity_and_human_face(self):
        html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())

        self.assertIn("<title>Jarvis — AI Companion</title>", html)
        self.assertIn(">JARVIS<", html)
        self.assertIn("AI Companion", html)
        self.assertIn('class="jarvis-face"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertNotIn("orb", html.lower())

    def test_render_preserves_status_text_and_operational_details(self):
        agents = dashboard.demo_agents()
        html = dashboard.render(agents, dashboard.demo_activity())

        for status in ("HEALTHY", "STALE", "DEGRADED", "FAILED"):
            self.assertIn(status, html)
        self.assertIn("Daily Brief Agent", html)
        self.assertIn("Recent intelligence", html)
        self.assertIn("System readiness", html)
        for agent in agents:
            self.assertIn(agent["schedule"], html)
            self.assertIn(agent["delivery"], html)
            for label, value in agent["facts"]:
                self.assertIn(label, html)
                self.assertIn(value, html)
            if agent.get("note"):
                self.assertIn(agent["note"], html)

    def test_render_is_offline_responsive_and_reduced_motion_safe(self):
        html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())
        lower = html.lower()

        self.assertIn("@media (max-width: 760px)", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)
        self.assertIn("overflow-x:hidden", html.replace(" ", ""))
        self.assertNotIn("https://", lower)
        self.assertNotIn("http://", lower)
        self.assertNotIn("<script", lower)
        self.assertNotRegex(lower, r"""(?:src|href)\s*=\s*["']//""")
        self.assertNotRegex(lower, r"@import\b")
        self.assertNotRegex(lower, r"""url\(\s*["']?(?:https?:)?//""")
        self.assertNotRegex(lower, r"<(?:img|image)\b")
        self.assertNotRegex(lower, r"<use\b|(?:href|xlink:href)\s*=")

    def test_operational_typography_is_readable_at_desktop_and_mobile_sizes(self):
        html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())

        for selector, minimum in (
            (".agent-index", 0.75),
            (".status-label", 0.75),
            (".fact-row", 0.8),
            (".agent-note", 0.78),
        ):
            self.assert_rem_font_size_at_least(html, selector, minimum)
        self.assertRegex(
            html,
            r"@media \(max-width: 760px\)[\s\S]*?"
            r"\.agent-index,\.status-label,\.fact-row,\.agent-note\s*"
            r"\{[^}]*font-size:\s*\.8rem",
        )

    def test_operational_labels_and_values_have_accessible_text_separation(self):
        html = dashboard.render(dashboard.demo_agents(), dashboard.demo_activity())
        text = " ".join(re.sub(r"<[^>]+>", "", html).split())

        self.assertIn("Schedule daily 07:30", text)
        self.assertIn("Brief job loaded", text)
        self.assertIn("loaded Liveness job", text)
        self.assertIn("Delivery iMessage → primary handle", text)
        self.assertIn(
            "Diagnostic note PAPER ONLY — edge not yet proven",
            text,
        )
        self.assertIn("Kalshi ⚠️ send failed (delivery)", text)
        self.assertIn("send failed (delivery) 2026-06-19 07:30", text)

    def test_jarvis_face_is_an_inline_decorative_human_face(self):
        svg = dashboard.jarvis_face()
        lower = svg.lower()

        self.assertIn('class="jarvis-face"', svg)
        self.assertIn('viewBox="0 0 260 330"', svg)
        self.assertIn('aria-hidden="true"', svg)
        self.assertIn("<path", svg)
        self.assertIn("<ellipse", svg)
        self.assertNotIn("<text", lower)
        self.assertNotRegex(lower, r"<(?:img|image)\b")
        self.assertNotRegex(lower, r"<use\b|(?:href|xlink:href)\s*=")


if __name__ == "__main__":
    unittest.main()
