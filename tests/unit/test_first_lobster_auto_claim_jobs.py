import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app import first_lobster_jobs


class FirstLobsterAutoClaimJobTests(unittest.TestCase):
    def setUp(self) -> None:
        first_lobster_jobs._JOBS.clear()
        first_lobster_jobs._RUNNING_JOB_BY_ACCOUNT.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.home_root = self.base_path / "home"
        self.home_root.mkdir(parents=True, exist_ok=True)
        self.openclaw_root = self.base_path / "host-openclaw"
        self.openclaw_root.mkdir(parents=True, exist_ok=True)
        self.workspace_root = self.base_path / "workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.base_path / "openclaw.json"
        self.db_path = self.base_path / "ops.db"
        self.roster_path = self.base_path / "dispatch" / "agent-roster.json"

        self.home_patch = patch.dict(os.environ, {"HOME": str(self.home_root)}, clear=False)
        self.host_root_patch = patch.object(db, "OPENCLAW_HOST_ROOT", self.openclaw_root)
        self.config_patch = patch.object(db, "OPENCLAW_CONFIG_PATH", self.config_path)
        self.db_patch = patch.object(db, "DB_PATH", self.db_path)
        self.roster_patch = patch.object(db, "OPENCLAW_ROSTER_PATH", self.roster_path)
        self.profile_patch = patch("app.db._get_feishu_bot_profile_index", return_value={})
        self.cli_patch = patch.object(db, "OPENCLAW_CLI_BIN", "")

        self.home_patch.start()
        self.host_root_patch.start()
        self.config_patch.start()
        self.db_patch.start()
        self.roster_patch.start()
        self.profile_patch.start()
        self.cli_patch.start()
        db.init_db()

    def tearDown(self) -> None:
        self.profile_patch.stop()
        self.cli_patch.stop()
        self.roster_patch.stop()
        self.db_patch.stop()
        self.config_patch.stop()
        self.host_root_patch.stop()
        self.home_patch.stop()
        self.temp_dir.cleanup()

    def _write_config(self, payload: dict) -> None:
        self.config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_bootstrap_files(self) -> None:
        (self.workspace_root / "BOOTSTRAP.md").write_text("# BOOTSTRAP\nhello lobster\n", encoding="utf-8")
        (self.workspace_root / "IDENTITY.md").write_text("identity\n", encoding="utf-8")
        (self.workspace_root / "SOUL.md").write_text("soul\n", encoding="utf-8")
        (self.workspace_root / "USER.md").write_text("user\n", encoding="utf-8")
        (self.workspace_root / "AGENTS.md").write_text("agents\n", encoding="utf-8")
        (self.workspace_root / "TOOLS.md").write_text("tools\n", encoding="utf-8")
        (self.workspace_root / "HEARTBEAT.md").write_text("heartbeat\n", encoding="utf-8")

    def _wait_for_job(self, job_id: str) -> dict:
        deadline = time.time() + 3
        while time.time() < deadline:
            current = first_lobster_jobs.get_first_lobster_auto_claim_job(None, job_id)
            if current["status"] in {"completed", "failed"}:
                return current
            time.sleep(0.02)
        self.fail(f"job_timeout:{job_id}")

    def _wait_for_audit_actions(self, *expected_actions: str) -> list[dict]:
        deadline = time.time() + 3
        while time.time() < deadline:
            logs = db.list_audit_logs(limit=20)
            actions = [item["action"] for item in logs]
            if all(action in actions for action in expected_actions):
                return logs
            time.sleep(0.02)
        self.fail(f"audit_actions_timeout:{','.join(expected_actions)}")

    def _wait_for_diagnostic_events(self, trace_id: str, *expected_events: str) -> list[dict]:
        deadline = time.time() + 3
        while time.time() < deadline:
            logs = db.list_diagnostic_logs(limit=50, trace_id=trace_id)
            events = [item["event"] for item in logs]
            if all(event in events for event in expected_events):
                return logs
            time.sleep(0.02)
        self.fail(f"diagnostic_events_timeout:{trace_id}:{','.join(expected_events)}")

    def test_start_first_lobster_auto_claim_runs_automation_and_claims_agent(self) -> None:
        self._write_bootstrap_files()
        self._write_config(
            {
                "agents": {
                    "defaults": {
                        "workspace": str(self.workspace_root),
                    }
                }
            }
        )

        with patch(
            "app.first_lobster_jobs.db.run_feishu_app_ui_automation",
            return_value={
                "status": "success",
                "step": "done",
                "message": "ok",
                "app_id": "cli_app",
                "app_secret": "cli_secret",
                "chat_url": "https://applink.feishu.cn/client/bot/open?appId=cli_app",
                "execution_mode": "profile",
                "debugger_url": None,
            },
        ):
            job = first_lobster_jobs.start_first_lobster_auto_claim(
                None,
                {"app_name": "超级峰的小龙虾", "trace_id": "trace_success"},
            )
            result = self._wait_for_job(job["job_id"])

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["trace_id"], "trace_success")
        self.assertEqual(result["agent_id"], "main")
        self.assertEqual(result["primary_channel"], "feishu")
        written = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(written["agents"]["list"][0]["name"], "超级峰的小龙虾")
        self.assertEqual(written["channels"]["feishu"]["accounts"]["main"]["appId"], "cli_app")
        self.assertEqual(written["channels"]["feishu"]["accounts"]["main"]["appSecret"], "cli_secret")
        audit_logs = self._wait_for_audit_actions(
            "agents.claim_first_lobster_auto_run.started",
            "agents.claim_first_lobster_auto_run.completed",
        )
        actions = [item["action"] for item in audit_logs]
        self.assertIn("agents.claim_first_lobster_auto_run.started", actions)
        self.assertIn("agents.claim_first_lobster_auto_run.completed", actions)
        completed = next(item for item in audit_logs if item["action"] == "agents.claim_first_lobster_auto_run.completed")
        self.assertEqual(completed["detail"]["job_id"], job["job_id"])
        self.assertEqual(completed["detail"]["app_id"], "cli_app")
        self.assertEqual(completed["detail"]["agent_id"], "main")
        diagnostic_logs = self._wait_for_diagnostic_events(
            "trace_success",
            "job.started",
            "job.waiting_login",
            "automation.success",
            "claim.started",
            "claim.completed",
        )
        completed_diagnostic = next(item for item in diagnostic_logs if item["event"] == "claim.completed")
        self.assertEqual(completed_diagnostic["detail"]["job_id"], job["job_id"])
        self.assertEqual(completed_diagnostic["detail"]["app_id"], "cli_app")
        self.assertEqual(completed_diagnostic["detail"]["agent_id"], "main")

    def test_start_first_lobster_auto_claim_surfaces_login_timeout_error(self) -> None:
        self._write_bootstrap_files()
        self._write_config(
            {
                "agents": {
                    "defaults": {
                        "workspace": str(self.workspace_root),
                    }
                }
            }
        )

        with patch(
            "app.first_lobster_jobs.db.run_feishu_app_ui_automation",
            return_value={
                "status": "login_required",
                "step": "login_wait_timeout",
                "message": "在等待时间内未检测到飞书开放平台登录完成，请重试",
                "app_id": None,
                "app_secret": None,
                "chat_url": None,
                "execution_mode": "profile",
                "debugger_url": None,
            },
        ):
            job = first_lobster_jobs.start_first_lobster_auto_claim(
                None,
                {"app_name": "ClawPilot", "trace_id": "trace_failed"},
            )
            result = self._wait_for_job(job["job_id"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["trace_id"], "trace_failed")
        self.assertIn("未检测到飞书开放平台登录完成", result["error_message"])
        audit_logs = self._wait_for_audit_actions(
            "agents.claim_first_lobster_auto_run.started",
            "agents.claim_first_lobster_auto_run.failed",
        )
        actions = [item["action"] for item in audit_logs]
        self.assertIn("agents.claim_first_lobster_auto_run.started", actions)
        self.assertIn("agents.claim_first_lobster_auto_run.failed", actions)
        failed = next(item for item in audit_logs if item["action"] == "agents.claim_first_lobster_auto_run.failed")
        self.assertEqual(failed["detail"]["job_id"], job["job_id"])
        self.assertIn("未检测到飞书开放平台登录完成", failed["detail"]["error_message"])
        diagnostic_logs = self._wait_for_diagnostic_events(
            "trace_failed",
            "job.started",
            "job.waiting_login",
            "job.failed",
        )
        failed_diagnostic = next(item for item in diagnostic_logs if item["event"] == "job.failed")
        self.assertEqual(failed_diagnostic["detail"]["job_id"], job["job_id"])
        self.assertIn("未检测到飞书开放平台登录完成", failed_diagnostic["detail"]["error_message"])

    def test_start_first_lobster_auto_claim_adds_second_lobster_when_main_exists(self) -> None:
        self._write_bootstrap_files()
        self._write_config(
            {
                "agents": {
                    "defaults": {
                        "workspace": str(self.workspace_root),
                    }
                }
            }
        )
        db.claim_first_lobster(
            {
                "selected_channels": ["feishu"],
                "feishu": {"app_id": "cli_app_main", "app_secret": "cli_secret_main"},
            }
        )

        with patch(
            "app.first_lobster_jobs.db.run_feishu_app_ui_automation",
            return_value={
                "status": "success",
                "step": "done",
                "message": "ok",
                "app_id": "cli_app_second",
                "app_secret": "cli_secret_second",
                "chat_url": "https://applink.feishu.cn/client/bot/open?appId=cli_app_second",
                "execution_mode": "profile",
                "debugger_url": None,
            },
        ):
            job = first_lobster_jobs.start_first_lobster_auto_claim(None, {"app_name": "ClawPilot-2"})
            result = self._wait_for_job(job["job_id"])

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["agent_id"], "lobster-2")
        written = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(written["channels"]["feishu"]["accounts"]["main"]["appId"], "cli_app_main")
        self.assertEqual(written["channels"]["feishu"]["accounts"]["lobster-2"]["appId"], "cli_app_second")
        self.assertEqual(written["agents"]["list"][1]["id"], "lobster-2")


if __name__ == "__main__":
    unittest.main()
