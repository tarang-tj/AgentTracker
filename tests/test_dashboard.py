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


if __name__ == "__main__":
    unittest.main()
