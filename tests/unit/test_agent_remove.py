import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db


class AgentRemoveTests(unittest.TestCase):
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

    def test_remove_agent_prunes_config_bindings_and_deletes_local_row_when_unreferenced(self) -> None:
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
                            "channel": "feishu",
                        },
                        {
                            "id": "lobster-2",
                            "name": "第二只小龙虾",
                            "workspace": str(self.workspace_root.parent / "workspace-lobster-2"),
                            "channel": "feishu",
                        },
                    ],
                },
                "bindings": [
                    {
                        "name": "feishu-main-direct",
                        "agentId": "main",
                        "match": {
                            "channel": "feishu",
                            "accountId": "main",
                        },
                    },
                    {
                        "name": "feishu-lobster-2-direct",
                        "agentId": "lobster-2",
                        "match": {
                            "channel": "feishu",
                            "accountId": "lobster-2",
                        },
                    },
                ],
                "channels": {
                    "feishu": {
                        "defaultAccount": "main",
                        "accounts": {
                            "main": {
                                "appId": "cli_main",
                                "appSecret": "secret_main",
                            },
                            "lobster-2": {
                                "appId": "cli_lobster_2",
                                "appSecret": "secret_lobster_2",
                            },
                        },
                    }
                },
            }
        )

        db.sync_agents_from_openclaw_config(refresh_feishu_profiles=False)

        result = db.remove_agent("main")
        written = json.loads(self.config_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "removed")
        self.assertEqual(result["agent_id"], "main")
        self.assertTrue(result["database_row_removed"])
        self.assertFalse(result["retained_history"])
        self.assertEqual([item["id"] for item in written["agents"]["list"]], ["lobster-2"])
        self.assertEqual(len(written["bindings"]), 1)
        self.assertEqual(written["bindings"][0]["agentId"], "lobster-2")
        self.assertEqual(written["channels"]["feishu"]["defaultAccount"], "lobster-2")
        self.assertEqual([item["agent_id"] for item in db.list_agents(status=None, q=None)], ["lobster-2"])

        with db.get_conn() as conn:
            row = conn.execute("SELECT agent_id FROM agents WHERE agent_id = ?", ("main",)).fetchone()
        self.assertIsNone(row)

    def test_remove_agent_keeps_local_row_when_history_is_present(self) -> None:
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
                            "channel": "feishu",
                        }
                    ],
                },
                "bindings": [
                    {
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
        with db.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO score_ledger (
                    agent_id, source_type, source_id, delta_points, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("main", "task", "task_demo", 10, "history", db.now_iso()),
            )
            conn.commit()

        result = db.remove_agent("main")
        written = json.loads(self.config_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "removed")
        self.assertFalse(result["database_row_removed"])
        self.assertTrue(result["retained_history"])
        self.assertEqual(written["agents"]["list"], [])
        self.assertEqual(written["bindings"], [])
        self.assertEqual(db.list_agents(status=None, q=None), [])

        with db.get_conn() as conn:
            row = conn.execute("SELECT agent_id FROM agents WHERE agent_id = ?", ("main",)).fetchone()
        self.assertIsNotNone(row)
