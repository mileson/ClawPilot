import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db


class AgentScenePresetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.openclaw_root = self.base_path / "host-openclaw"
        self.openclaw_root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.base_path / "openclaw.json"
        self.db_path = self.base_path / "ops.db"

        self.host_root_patch = patch.object(db, "OPENCLAW_HOST_ROOT", self.openclaw_root)
        self.config_patch = patch.object(db, "OPENCLAW_CONFIG_PATH", self.config_path)
        self.db_patch = patch.object(db, "DB_PATH", self.db_path)
        self.cli_patch = patch.object(db, "OPENCLAW_CLI_BIN", "")
        self.host_root_patch.start()
        self.config_patch.start()
        self.db_patch.start()
        self.cli_patch.start()
        db.init_db()

    def tearDown(self) -> None:
        self.cli_patch.stop()
        self.db_patch.stop()
        self.config_patch.stop()
        self.host_root_patch.stop()
        self.temp_dir.cleanup()

    def _write_config(self) -> None:
        payload = {
            "agents": {
                "list": [
                    {"id": "blogger"},
                ]
            }
        }
        self.config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_list_agents_exposes_empty_scene_preset_before_selection(self) -> None:
        self._write_config()

        db.sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
        agents = db.list_agents(
            status=None,
            q=None,
            include_feishu_profiles=False,
            include_official_runtime_signal=False,
        )

        self.assertEqual(len(agents), 1)
        self.assertIsNone(agents[0]["scene_preset_id"])

    def test_update_agent_scene_preset_persists_selection(self) -> None:
        self._write_config()

        db.sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
        updated = db.update_agent_scene_preset("blogger", "preset-focus")

        self.assertEqual(updated["scene_preset_id"], "preset-focus")

        agents = db.list_agents(
            status=None,
            q=None,
            include_feishu_profiles=False,
            include_official_runtime_signal=False,
        )
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["scene_preset_id"], "preset-focus")

    def test_update_agent_scene_preset_rejects_unknown_preset(self) -> None:
        self._write_config()

        db.sync_agents_from_openclaw_config(refresh_feishu_profiles=False)

        with self.assertRaisesRegex(ValueError, "scene_preset_id_invalid"):
            db.update_agent_scene_preset("blogger", "preset-unknown")
