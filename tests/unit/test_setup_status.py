import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import db


class SetupStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "setup-status.db"
        self.config_path = Path(self.temp_dir.name) / "openclaw.json"
        self.bootstrap_state_path = Path(self.temp_dir.name) / "bootstrap" / "latest.json"
        self.home_patch = patch.dict(os.environ, {"HOME": self.temp_dir.name}, clear=False)
        self.db_patch = patch.object(db, "DB_PATH", self.db_path)
        self.config_patch = patch.object(db, "OPENCLAW_CONFIG_PATH", self.config_path)
        self.base_url_patch = patch.object(db, "OPENCLAW_PUBLIC_BASE_URL", "https://ops.example.com")
        self.bootstrap_state_patch = patch.object(db, "BOOTSTRAP_STATE_PATH", self.bootstrap_state_path)
        self.home_patch.start()
        self.db_patch.start()
        self.config_patch.start()
        self.base_url_patch.start()
        self.bootstrap_state_patch.start()
        db.init_db()

    def tearDown(self) -> None:
        self.bootstrap_state_patch.stop()
        self.base_url_patch.stop()
        self.config_patch.stop()
        self.db_patch.stop()
        self.home_patch.stop()
        self.temp_dir.cleanup()

    def test_setup_status_reports_unconfigured_without_openclaw_config(self) -> None:
        status = db.get_setup_status()

        self.assertFalse(status["has_openclaw_config"])
        self.assertEqual(status["node_total"], 0)
        self.assertTrue(status["bootstrap_ready"])
        self.assertEqual(status["install_result"], "unknown")
        self.assertEqual(status["public_url_status"], "unknown")

    def test_setup_status_reports_config_when_openclaw_json_exists(self) -> None:
        self.config_path.write_text('{"agents":{"list":[{"id":"main"}]}}', encoding="utf-8")

        status = db.get_setup_status()

        self.assertTrue(status["has_openclaw_config"])

    def test_setup_status_merges_bootstrap_snapshot_into_prompt_context(self) -> None:
        self.bootstrap_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.bootstrap_state_path.write_text(
            """
            {
              "operation": "bootstrap",
              "stage": "completed",
              "result": "success",
              "updated_at": "2026-03-18T10:00:00Z",
              "local": {
                "web_url": "http://127.0.0.1:3000/agents",
                "api_health_url": "http://127.0.0.1:8088/healthz",
                "web_ok": true,
                "api_ok": true
              },
              "public_url": {
                "enabled": true,
                "provider": "cloudflared-quick",
                "status": "verified",
                "url": "https://demo.trycloudflare.com"
              }
            }
            """,
            encoding="utf-8",
        )

        status = db.get_setup_status()

        self.assertEqual(status["install_stage"], "completed")
        self.assertEqual(status["install_result"], "success")
        self.assertEqual(status["public_url"], "https://demo.trycloudflare.com")
        self.assertEqual(status["public_url_status"], "verified")
        self.assertIn("./clawpilot status", status["bootstrap_prompt"])
        self.assertIn("https://demo.trycloudflare.com", status["bootstrap_prompt"])

    def test_setup_status_falls_back_to_local_openclaw_home(self) -> None:
        local_root = Path(self.temp_dir.name) / ".openclaw"
        local_root.mkdir(parents=True, exist_ok=True)
        (local_root / "openclaw.json").write_text('{"agents":{"defaults":{"workspace":"~/.openclaw/workspace"}}}', encoding="utf-8")

        with patch.dict(os.environ, {"HOME": self.temp_dir.name}, clear=False), patch.object(
            db, "OPENCLAW_HOST_ROOT", Path("/host-openclaw")
        ), patch.object(
            db, "OPENCLAW_CONFIG_PATH", Path("/host-openclaw/openclaw.json")
        ), patch.object(
            db, "OPENCLAW_ROSTER_PATH", Path("/host-openclaw/workspace/dispatch/agent-roster.json")
        ):
            status = db.get_setup_status()

        self.assertTrue(status["has_openclaw_config"])
        self.assertIn(str(local_root / "openclaw.json"), status["bootstrap_prompt"])

    def test_run_openclaw_cli_json_ignores_prefix_logs(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout='[plugins] feishu_doc: registered\n{"availability":{"available":true}}\n',
            stderr="",
        )
        with patch.object(db, "OPENCLAW_CLI_BIN", "/usr/local/bin/openclaw"), patch("app.db.subprocess.run", return_value=completed):
            payload = db._run_openclaw_cli_json(["/usr/local/bin/openclaw", "update", "status", "--json"])

        self.assertEqual(payload, {"availability": {"available": True}})

    def test_setup_status_reports_openclaw_version_summary(self) -> None:
        with patch.object(
            db,
            "_read_openclaw_cli_status_summary",
            return_value={
                "openclaw_cli_installed": True,
                "openclaw_cli_path": "/usr/local/bin/openclaw",
                "openclaw_current_version": "2026.3.13",
                "openclaw_latest_version": "2026.3.24",
                "openclaw_update_available": True,
            },
        ):
            status = db.get_setup_status()

        self.assertTrue(status["openclaw_cli_installed"])
        self.assertEqual(status["openclaw_current_version"], "2026.3.13")
        self.assertEqual(status["openclaw_latest_version"], "2026.3.24")
        self.assertTrue(status["openclaw_update_available"])

    def test_list_agents_returns_empty_without_configured_agent_list(self) -> None:
        with db.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO agents (
                    agent_id, display_name, role, status, open_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("main", "总管", "统筹与协调", "active", None, db.now_iso()),
            )
            conn.commit()

        agents = db.list_agents(status=None, q=None)
        self.assertEqual(agents, [])


if __name__ == "__main__":
    unittest.main()
