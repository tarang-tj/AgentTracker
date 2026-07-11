import importlib.util
import unittest
from datetime import datetime
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "gen-dashboard.py"
SPEC = importlib.util.spec_from_file_location("dashboard", MODULE_PATH)
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class DashboardPresentationTests(unittest.TestCase):
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

        self.assertIn("@media (max-width: 760px)", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)
        self.assertIn("overflow-x:hidden", html.replace(" ", ""))
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("<script", html.lower())

    def test_jarvis_face_is_an_inline_decorative_human_face(self):
        svg = dashboard.jarvis_face()

        self.assertIn('class="jarvis-face"', svg)
        self.assertIn('viewBox="0 0 260 330"', svg)
        self.assertIn('aria-hidden="true"', svg)
        self.assertIn("<path", svg)
        self.assertIn("<ellipse", svg)
        self.assertNotIn("<text", svg)
        self.assertNotIn("href=", svg)


if __name__ == "__main__":
    unittest.main()
