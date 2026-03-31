import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db


class FirstLobsterClaimTests(unittest.TestCase):
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

        self.home_patch.start()
        self.host_root_patch.start()
        self.config_patch.start()
        self.db_patch.start()
        self.roster_patch.start()
        self.profile_patch.start()
        db.init_db()

    def tearDown(self) -> None:
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

    def test_preview_reads_default_workspace_and_marks_missing_files(self) -> None:
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

        preview = db.get_first_lobster_bootstrap_preview()

        self.assertEqual(preview["workspace"]["path"], str(self.workspace_root))
        self.assertEqual(preview["workspace"]["source"], "config")
        self.assertTrue(preview["workspace"]["available"])
        self.assertEqual(preview["recommended_agent_id"], "main")
        self.assertEqual(preview["recommended_agent_name"], "第一只小龙虾")
        self.assertEqual(preview["recommended_app_name"], "ClawPilot")
        file_map = {item["path"]: item for item in preview["files"]}
        self.assertTrue(file_map["BOOTSTRAP.md"]["exists"])
        self.assertIn("hello lobster", file_map["BOOTSTRAP.md"]["preview"])
        self.assertFalse(file_map["MEMORY.md"]["exists"])

    def test_preview_falls_back_to_home_workspace_when_config_missing(self) -> None:
        fallback_workspace = self.home_root / ".openclaw" / "workspace"
        fallback_workspace.mkdir(parents=True, exist_ok=True)
        (fallback_workspace / "BOOTSTRAP.md").write_text("# fallback\n", encoding="utf-8")

        preview = db.get_first_lobster_bootstrap_preview()

        self.assertEqual(preview["workspace"]["source"], "fallback")
        self.assertEqual(preview["workspace"]["path"], str(fallback_workspace))
        self.assertTrue(preview["workspace"]["available"])
        self.assertEqual(preview["recommended_app_name"], "ClawPilot")

    def test_claim_first_lobster_writes_channels_bindings_and_agent_entry(self) -> None:
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

        result = db.claim_first_lobster(
            {
                "selected_channels": ["feishu", "telegram"],
                "primary_channel": "telegram",
                "feishu": {"app_id": "cli_app", "app_secret": "cli_secret"},
                "telegram": {"bot_token": "telegram-token"},
            }
        )

        written = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "claimed")
        self.assertEqual(result["primary_channel"], "telegram")
        self.assertEqual(result["agent"]["agent_id"], "main")
        self.assertEqual(result["agent"]["channel"], "telegram")
        self.assertEqual(written["agents"]["list"][0]["id"], "main")
        self.assertNotIn("channel", written["agents"]["list"][0])
        self.assertEqual(written["channels"]["feishu"]["accounts"]["main"]["appId"], "cli_app")
        self.assertEqual(written["channels"]["feishu"]["accounts"]["main"]["appSecret"], "cli_secret")
        self.assertEqual(written["channels"]["telegram"]["accounts"]["main"]["botToken"], "telegram-token")
        bindings = {(item["agentId"], item["match"]["channel"], item["match"]["accountId"]) for item in written["bindings"]}
        self.assertIn(("main", "feishu", "main"), bindings)
        self.assertIn(("main", "telegram", "main"), bindings)
        self.assertTrue(all(item.get("type") == "route" for item in written["bindings"]))
        self.assertTrue(all("name" not in item for item in written["bindings"]))
        self.assertTrue((self.openclaw_root / "agents" / "main" / "agent").exists())
        self.assertTrue((self.openclaw_root / "agents" / "main" / "sessions").exists())
        self.assertIsNotNone(result["backup_path"])

    def test_claim_first_lobster_supports_single_feishu_channel(self) -> None:
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

        result = db.claim_first_lobster(
            {
                "selected_channels": ["feishu"],
                "feishu": {"app_id": "feishu_app", "app_secret": "feishu_secret"},
            }
        )

        self.assertEqual(result["primary_channel"], "feishu")
        written = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertNotIn("channel", written["agents"]["list"][0])
        self.assertEqual(written["channels"]["feishu"]["accounts"]["main"]["appId"], "feishu_app")
        self.assertEqual(written["channels"]["feishu"]["accounts"]["main"]["appSecret"], "feishu_secret")

    def test_claim_first_lobster_appends_next_lobster_instead_of_overwriting_main(self) -> None:
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

        first = db.claim_first_lobster(
            {
                "selected_channels": ["feishu"],
                "feishu": {"app_id": "feishu_app_main", "app_secret": "feishu_secret_main"},
            }
        )
        second = db.claim_first_lobster(
            {
                "selected_channels": ["feishu"],
                "agent_name": "超级峰的小龙虾",
                "feishu": {"app_id": "feishu_app_second", "app_secret": "feishu_secret_second"},
            }
        )

        written = json.loads(self.config_path.read_text(encoding="utf-8"))
        agent_ids = [item["id"] for item in written["agents"]["list"]]
        self.assertEqual(first["agent"]["agent_id"], "main")
        self.assertEqual(second["agent"]["agent_id"], "lobster-2")
        self.assertEqual(second["agent"]["display_name"], "超级峰的小龙虾")
        self.assertEqual(agent_ids, ["main", "lobster-2"])
        self.assertEqual(written["agents"]["list"][1]["name"], "超级峰的小龙虾")
        self.assertEqual(written["channels"]["feishu"]["accounts"]["main"]["appId"], "feishu_app_main")
        self.assertEqual(written["channels"]["feishu"]["accounts"]["lobster-2"]["appId"], "feishu_app_second")
        self.assertEqual(written["channels"]["feishu"]["defaultAccount"], "main")
        bindings = {(item["agentId"], item["match"]["channel"], item["match"]["accountId"]) for item in written["bindings"]}
        self.assertIn(("lobster-2", "feishu", "lobster-2"), bindings)
        second_workspace = self.workspace_root.parent / "workspace-lobster-2"
        self.assertTrue(second_workspace.exists())
        self.assertTrue((second_workspace / "BOOTSTRAP.md").exists())

        preview = db.get_first_lobster_bootstrap_preview()
        self.assertEqual(preview["recommended_agent_id"], "lobster-3")
        self.assertEqual(preview["recommended_agent_name"], "第三只小龙虾")
        self.assertEqual(preview["recommended_app_name"], "ClawPilot-3")

    def test_claim_first_lobster_persists_feishu_profile_metadata_for_fast_list(self) -> None:
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
            "app.db._fetch_feishu_bot_profile",
            return_value={
                "name": "超级峰的小龙虾",
                "avatar_url": "https://example.com/avatar.png",
                "open_id": "ou_demo_123",
            },
        ):
            result = db.claim_first_lobster(
                {
                    "selected_channels": ["feishu"],
                    "feishu": {"app_id": "feishu_app_main", "app_secret": "feishu_secret_main"},
                }
            )

        written = json.loads(self.config_path.read_text(encoding="utf-8"))
        account = written["channels"]["feishu"]["accounts"]["main"]
        self.assertEqual(result["agent"]["display_name"], "超级峰的小龙虾")
        self.assertEqual(account["appName"], "超级峰的小龙虾")
        self.assertEqual(account["avatarUrl"], "https://example.com/avatar.png")
        self.assertEqual(account["openId"], "ou_demo_123")

    def test_list_agents_prefers_feishu_profile_name_for_placeholder_display_name(self) -> None:
        self._write_bootstrap_files()
        self._write_config(
            {
                "agents": {
                    "defaults": {
                        "workspace": str(self.workspace_root),
                    },
                    "list": [
                        {
                            "id": "lobster-2",
                            "name": "第二只小龙虾",
                            "workspace": str(self.workspace_root.parent / "workspace-lobster-2"),
                        }
                    ],
                },
                "bindings": [
                    {
                        "type": "route",
                        "name": "feishu-lobster-2-direct",
                        "agentId": "lobster-2",
                        "match": {
                            "channel": "feishu",
                            "accountId": "lobster-2",
                        },
                    }
                ],
                "channels": {
                    "feishu": {
                        "defaultAccount": "lobster-2",
                        "accounts": {
                            "lobster-2": {
                                "appId": "cli_lobster_2",
                                "appSecret": "secret_lobster_2",
                            }
                        },
                    }
                },
            }
        )

        with patch(
            "app.db._get_feishu_bot_profile_index",
            return_value={"lobster-2": {"name": "超级峰的小龙虾", "avatar_url": None, "open_id": None}},
        ):
            db.sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
            agents = db.list_agents(status=None, q=None)

        lobster = next(item for item in agents if item["agent_id"] == "lobster-2")
        self.assertEqual(lobster["display_name"], "超级峰的小龙虾")

    def test_list_agents_can_skip_official_runtime_signal_for_fast_ui_list(self) -> None:
        self._write_bootstrap_files()
        self._write_config(
            {
                "agents": {
                    "defaults": {
                        "workspace": str(self.workspace_root),
                    },
                    "list": [
                        {
                            "id": "main",
                            "name": "ClawPilot",
                            "workspace": str(self.workspace_root),
                        }
                    ],
                },
                "bindings": [
                    {
                        "type": "route",
                        "name": "feishu-main-direct",
                        "agentId": "main",
                        "match": {
                            "channel": "feishu",
                            "accountId": "main",
                        },
                    }
                ],
                "channels": {
                    "feishu": {
                        "defaultAccount": "main",
                        "accounts": {
                            "main": {
                                "appId": "cli_main",
                                "appSecret": "secret_main",
                            }
                        },
                    }
                },
            }
        )

        db.sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
        with patch("app.db._read_official_runtime_host_signal", side_effect=AssertionError("should not be called")):
            agents = db.list_agents(
                status=None,
                q=None,
                include_feishu_profiles=False,
                include_official_runtime_signal=False,
            )

        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["agent_id"], "main")

    def test_list_agents_uses_cached_feishu_avatar_without_remote_fetch(self) -> None:
        self._write_bootstrap_files()
        self._write_config(
            {
                "agents": {
                    "defaults": {
                        "workspace": str(self.workspace_root),
                    },
                    "list": [
                        {
                            "id": "main",
                            "name": "ClawPilot",
                            "workspace": str(self.workspace_root),
                        }
                    ],
                },
                "bindings": [
                    {
                        "type": "route",
                        "name": "feishu-main-direct",
                        "agentId": "main",
                        "match": {
                            "channel": "feishu",
                            "accountId": "main",
                        },
                    }
                ],
                "channels": {
                    "feishu": {
                        "defaultAccount": "main",
                        "accounts": {
                            "main": {
                                "appId": "cli_main",
                                "appSecret": "secret_main",
                                "appName": "ClawPilot",
                                "avatarUrl": "https://example.com/main-avatar.png",
                                "openId": "ou_main_demo",
                            }
                        },
                    }
                },
            }
        )

        db.sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
        with patch("app.db._get_feishu_bot_profile_index", side_effect=AssertionError("should not be called")):
            agents = db.list_agents(
                status=None,
                q=None,
                include_feishu_profiles=False,
                include_official_runtime_signal=False,
            )

        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["avatar_url"], "https://example.com/main-avatar.png")
        self.assertEqual(agents[0]["open_id"], "ou_main_demo")

    def test_claim_first_lobster_requires_primary_when_multiple_channels(self) -> None:
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

        with self.assertRaisesRegex(ValueError, "first_lobster_primary_channel_required"):
            db.claim_first_lobster(
                {
                    "selected_channels": ["feishu", "telegram"],
                    "feishu": {"app_id": "cli_app", "app_secret": "cli_secret"},
                    "telegram": {"bot_token": "telegram-token"},
                }
            )

    def test_claim_first_lobster_requires_channel_specific_credentials(self) -> None:
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

        with self.assertRaisesRegex(ValueError, "first_lobster_telegram_bot_token_required"):
            db.claim_first_lobster(
                {
                    "selected_channels": ["telegram"],
                    "primary_channel": "telegram",
                    "telegram": {"bot_token": ""},
                }
            )

        with self.assertRaisesRegex(ValueError, "first_lobster_discord_token_required"):
            db.claim_first_lobster(
                {
                    "selected_channels": ["discord"],
                    "primary_channel": "discord",
                    "discord": {"token": ""},
                }
            )

    def test_sync_agents_supports_non_feishu_binding_accounts(self) -> None:
        self._write_bootstrap_files()
        self._write_config(
            {
                "agents": {
                    "defaults": {
                        "workspace": str(self.workspace_root),
                    },
                    "list": [
                        {
                            "id": "main",
                            "name": "第一只小龙虾",
                            "workspace": str(self.workspace_root),
                        }
                    ],
                },
                "bindings": [
                    {
                        "type": "route",
                        "name": "telegram-main-direct",
                        "agentId": "main",
                        "match": {
                            "channel": "telegram",
                            "accountId": "main-telegram",
                        },
                    }
                ],
                "channels": {
                    "telegram": {
                        "defaultAccount": "main-telegram",
                        "accounts": {
                            "main-telegram": {
                                "botToken": "telegram-token",
                            }
                        },
                    }
                },
            }
        )

        synced = db.sync_agents_from_openclaw_config()

        self.assertEqual(synced, 1)
        agents = db.list_agents(status=None, q=None, include_feishu_profiles=False, include_official_runtime_signal=False)
        row = next((item for item in agents if item["agent_id"] == "main"), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["channel"], "telegram")
        self.assertEqual(row["account_id"], "main-telegram")
        self.assertTrue(row["identity_complete"])


if __name__ == "__main__":
    unittest.main()
