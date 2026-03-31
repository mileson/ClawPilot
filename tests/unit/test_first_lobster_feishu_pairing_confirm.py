import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db


class FirstLobsterFeishuPairingConfirmTests(unittest.TestCase):
    def setUp(self) -> None:
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
        self.cli_patch = patch.object(db, "OPENCLAW_CLI_BIN", "/usr/local/bin/openclaw")

        self.home_patch.start()
        self.host_root_patch.start()
        self.config_patch.start()
        self.db_patch.start()
        self.roster_patch.start()
        self.profile_patch.start()
        self.cli_patch.start()
        db.init_db()

    def tearDown(self) -> None:
        self.cli_patch.stop()
        self.profile_patch.stop()
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

    def _seed_feishu_agent(self) -> None:
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
                "feishu": {"app_id": "cli_app", "app_secret": "cli_secret"},
            }
        )

    def test_confirm_first_lobster_feishu_pairing_parses_text_and_runs_cli(self) -> None:
        self._seed_feishu_agent()
        pairing_text = """OpenClaw: access not configured.
Your Feishu user id: ou_e70e90b5d6a24092d32291815085f0a1
Pairing code: PXE6J2Z7
Ask the bot owner to approve with:
openclaw pairing approve feishu PXE6J2Z7
"""

        with patch("app.db.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = "approved"
            run_mock.return_value.stderr = ""

            result = db.confirm_first_lobster_feishu_pairing(
                {"agent_id": "main", "pairing_text": pairing_text},
            )

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["agent_id"], "main")
        self.assertEqual(result["user_open_id"], "ou_e70e90b5d6a24092d32291815085f0a1")
        self.assertEqual(result["pairing_code"], "PXE6J2Z7")
        command = run_mock.call_args.args[0]
        self.assertEqual(
            command,
            [
                "/usr/local/bin/openclaw",
                "pairing",
                "approve",
                "feishu",
                "PXE6J2Z7",
                "--account",
                "main",
                "--notify",
            ],
        )
        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["OPENCLAW_STATE_DIR"], str(self.home_root / ".openclaw"))
        self.assertEqual(Path(env["OPENCLAW_CONFIG_PATH"]).resolve(), self.config_path.resolve())

    def test_confirm_first_lobster_feishu_pairing_rejects_invalid_text(self) -> None:
        self._seed_feishu_agent()

        with self.assertRaisesRegex(ValueError, "first_lobster_feishu_pairing_text_invalid"):
            db.confirm_first_lobster_feishu_pairing(
                {"agent_id": "main", "pairing_text": "OpenClaw: access not configured."},
            )

    def test_confirm_first_lobster_feishu_pairing_surfaces_cli_failure(self) -> None:
        self._seed_feishu_agent()
        pairing_text = """Your Feishu user id: ou_e70e90b5d6a24092d32291815085f0a1
Pairing code: PXE6J2Z7
"""

        with patch("app.db.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 1
            run_mock.return_value.stdout = ""
            run_mock.return_value.stderr = "invalid pairing code"

            with self.assertRaisesRegex(RuntimeError, "first_lobster_feishu_pairing_approve_failed:invalid pairing code"):
                db.confirm_first_lobster_feishu_pairing(
                    {"agent_id": "main", "pairing_text": pairing_text},
                )


if __name__ == "__main__":
    unittest.main()
