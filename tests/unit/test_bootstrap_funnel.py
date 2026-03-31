import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import clawpilot_ops as ops


class BootstrapFunnelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        (self.root / ".env.example").write_text("OPENCLAW_PUBLIC_BASE_URL=\n", encoding="utf-8")
        (self.root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
        self.state_path = self.root / "data" / "bootstrap" / "latest.json"
        self.install_cli_patch = patch.object(
            ops,
            "install_global_cli",
            return_value={
                "ok": True,
                "status": "mocked",
                "command": "clawpilot",
                "install_path": str(self.root / "mocked-bin" / "clawpilot"),
                "source_path": str(self.root / "clawpilot"),
            },
        )
        self.bootstrap_notice_patch = patch.object(ops, "reveal_bootstrap_admin_for_bootstrap_notice", return_value=None)
        self.install_cli_patch.start()
        self.bootstrap_notice_patch.start()

    def tearDown(self) -> None:
        self.bootstrap_notice_patch.stop()
        self.install_cli_patch.stop()
        self.temp_dir.cleanup()

    def _ok_local(self) -> dict[str, object]:
        return {
            "api_health_url": "http://127.0.0.1:8088/healthz",
            "api_contract_url": "http://127.0.0.1:8088/openapi.json",
            "web_url": "http://127.0.0.1:3000/agents",
            "api_ok": True,
            "api_health_ok": True,
            "api_status_code": 200,
            "api_error": None,
            "api_contract_ok": True,
            "api_contract_status_code": 200,
            "api_contract_error": None,
            "web_ok": True,
            "web_status_code": 200,
            "web_error": None,
            "checked_at": "2026-03-18T10:00:00Z",
        }

    def test_bootstrap_aborts_on_preflight_failure(self) -> None:
        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "run_preflight", side_effect=ops.BootstrapFailure("preflight", "docker_missing", "缺少 docker")
        ):
            payload = ops.run_bootstrap(expose_mode="disabled", state_path=self.state_path, timeout_sec=1)

        self.assertEqual(payload["result"], "failed")
        self.assertEqual(payload["stage"], "preflight")
        self.assertEqual(payload["failure"]["code"], "docker_missing")
        written = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(written["failure"]["code"], "docker_missing")

    def test_bootstrap_persists_success_without_public_url_when_exposure_disabled(self) -> None:
        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "run_preflight", return_value={"compose_command": ["docker", "compose"]}
        ), patch.object(ops, "ensure_env_file", return_value="copied_from_example"), patch.object(
            ops, "run_command"
        ) as mock_run, patch.object(
            ops, "wait_for_local_services", return_value=self._ok_local()
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            payload = ops.run_bootstrap(expose_mode="disabled", state_path=self.state_path, timeout_sec=1)

        self.assertEqual(payload["result"], "success")
        self.assertEqual(payload["stage"], "completed")
        self.assertEqual(payload["public_url"]["status"], "unavailable")
        self.assertEqual(payload["public_url"]["reason"], "public_url_not_requested")

    def test_preflight_fails_fast_when_docker_proxy_is_unreachable(self) -> None:
        with patch.object(ops, "detect_compose_command", return_value=["docker", "compose"]), patch.object(
            ops,
            "inspect_docker_runtime",
            return_value={
                "available": True,
                "detail": "ok",
                "compose_command": ["docker", "compose"],
                "proxies": {"http": "http://192.168.5.2:10077"},
                "proxy_checks": {},
                "stale_proxies": [
                    {
                        "kind": "http",
                        "url": "http://192.168.5.2:10077",
                        "host": "192.168.5.2",
                        "port": 10077,
                        "error": "[Errno 61] Connection refused",
                    }
                ],
            },
        ):
            with self.assertRaises(ops.BootstrapFailure) as exc:
                ops.run_preflight(self.root)

        self.assertEqual(exc.exception.code, "docker_proxy_unreachable")
        self.assertIn("192.168.5.2:10077", exc.exception.message)

    def test_bootstrap_marks_failed_when_local_health_checks_fail(self) -> None:
        failed_local = self._ok_local()
        failed_local["api_ok"] = False
        failed_local["api_health_ok"] = False
        failed_local["api_error"] = "connection refused"

        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "run_preflight", return_value={"compose_command": ["docker", "compose"]}
        ), patch.object(ops, "ensure_env_file", return_value="existing"), patch.object(
            ops, "run_command"
        ) as mock_run, patch.object(
            ops, "wait_for_local_services", return_value=failed_local
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            payload = ops.run_bootstrap(expose_mode="disabled", state_path=self.state_path, timeout_sec=1)

        self.assertEqual(payload["result"], "failed")
        self.assertEqual(payload["stage"], "deploy")
        self.assertEqual(payload["failure"]["code"], "api_health_failed")

    def test_bootstrap_marks_failed_when_required_api_routes_are_missing(self) -> None:
        failed_local = self._ok_local()
        failed_local["api_ok"] = False
        failed_local["api_contract_ok"] = False
        failed_local["api_contract_error"] = "expected_marker_missing"
        failed_local["api_error"] = "expected_marker_missing"

        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "run_preflight", return_value={"compose_command": ["docker", "compose"]}
        ), patch.object(ops, "ensure_env_file", return_value="existing"), patch.object(
            ops, "run_command"
        ) as mock_run, patch.object(
            ops, "wait_for_local_services", return_value=failed_local
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            payload = ops.run_bootstrap(expose_mode="disabled", state_path=self.state_path, timeout_sec=1)

        self.assertEqual(payload["result"], "failed")
        self.assertEqual(payload["stage"], "deploy")
        self.assertEqual(payload["failure"]["code"], "api_contract_failed")

    def test_bootstrap_returns_snapshot_write_error_without_crashing(self) -> None:
        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "run_preflight", return_value={"compose_command": ["docker", "compose"]}
        ), patch.object(ops, "ensure_env_file", return_value="copied_from_example"), patch.object(
            ops, "run_command"
        ) as mock_run, patch.object(
            ops, "wait_for_local_services", return_value=self._ok_local()
        ), patch.object(
            ops, "write_snapshot", return_value="No space left on device"
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            payload = ops.run_bootstrap(expose_mode="disabled", state_path=self.state_path, timeout_sec=1)

        self.assertEqual(payload["result"], "success")
        self.assertEqual(payload["snapshot_write_error"], "No space left on device")

    def test_bootstrap_attaches_global_cli_install_result(self) -> None:
        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "run_preflight", return_value={"compose_command": ["docker", "compose"]}
        ), patch.object(ops, "ensure_env_file", return_value="copied_from_example"), patch.object(
            ops, "run_command"
        ) as mock_run, patch.object(
            ops, "wait_for_local_services", return_value=self._ok_local()
        ), patch.object(
            ops,
            "install_global_cli",
            return_value={
                "ok": True,
                "status": "installed",
                "command": "clawpilot",
                "install_path": "/usr/local/bin/clawpilot",
                "source_path": str(self.root / "clawpilot"),
            },
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            payload = ops.run_bootstrap(expose_mode="disabled", state_path=self.state_path, timeout_sec=1)

        self.assertEqual(payload["result"], "success")
        self.assertEqual(payload["global_cli"]["status"], "installed")
        self.assertEqual(payload["global_cli"]["install_path"], "/usr/local/bin/clawpilot")

    def test_bootstrap_attaches_first_reveal_bootstrap_admin_notice(self) -> None:
        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "run_preflight", return_value={"compose_command": ["docker", "compose"]}
        ), patch.object(ops, "ensure_env_file", return_value="copied_from_example"), patch.object(
            ops, "run_command"
        ) as mock_run, patch.object(
            ops, "wait_for_local_services", return_value=self._ok_local()
        ), patch.object(
            ops, "reveal_bootstrap_admin_for_bootstrap_notice",
            return_value={
                "username": "openclaw",
                "temp_password": "openclaw-demo-password",
                "created_at": "2026-03-20T08:00:00Z",
                "revealed_at": "2026-03-20T08:05:00Z",
                "first_reveal": True,
            },
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            payload = ops.run_bootstrap(expose_mode="disabled", state_path=self.state_path, timeout_sec=1)

        self.assertEqual(payload["result"], "success")
        self.assertEqual(payload["bootstrap_admin"]["username"], "openclaw")
        self.assertEqual(payload["bootstrap_admin"]["temp_password"], "openclaw-demo-password")

    def test_render_bootstrap_summary_includes_first_login_admin_credentials(self) -> None:
        summary = ops.render_bootstrap_summary(
            {
                "operation": "bootstrap",
                "result": "success",
                "stage": "completed",
                "updated_at": "2026-03-20T08:10:00Z",
                "local": self._ok_local(),
                "public_url": {"status": "unavailable", "reason": "public_url_not_requested"},
                "bootstrap_admin": {
                    "username": "openclaw",
                    "temp_password": "openclaw-demo-password",
                    "revealed_at": "2026-03-20T08:05:00Z",
                },
                "next_commands": [],
            }
        )

        self.assertIn("Admin Access:", summary)
        self.assertIn("管理员账号: openclaw", summary)
        self.assertIn("首次临时密码: openclaw-demo-password", summary)
        self.assertIn("展示时间: 2026年03月20日 16:05:00（北京时间）", summary)

    def test_render_bootstrap_summary_marks_already_revealed_bootstrap_password(self) -> None:
        summary = ops.render_bootstrap_summary(
            {
                "operation": "bootstrap",
                "result": "success",
                "stage": "completed",
                "updated_at": "2026-03-20T08:10:00Z",
                "local": self._ok_local(),
                "public_url": {"status": "unavailable", "reason": "public_url_not_requested"},
                "bootstrap_admin": {
                    "username": "openclaw",
                    "temp_password": None,
                    "revealed_at": "2026-03-20T08:05:00Z",
                },
                "next_commands": [],
            }
        )

        self.assertIn("管理员账号: openclaw", summary)
        self.assertIn("临时密码状态: 已于 2026年03月20日 16:05:00（北京时间） 展示过一次", summary)
        self.assertIn("clawpilot 8", summary)

    def test_expose_keeps_local_success_when_public_exposure_fails(self) -> None:
        public_failure = {
            "enabled": True,
            "provider": "cloudflared-quick",
            "status": "unavailable",
            "url": None,
            "candidate_url": None,
            "reason": "supported_provider_not_found",
            "verified_at": None,
            "pid": None,
            "log_path": None,
        }

        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "probe_local_services", return_value=self._ok_local()
        ), patch.object(
            ops, "attempt_public_exposure", return_value=public_failure
        ):
            payload = ops.run_expose("quick", state_path=self.state_path)

        self.assertEqual(payload["result"], "success")
        self.assertEqual(payload["operation"], "expose")
        self.assertEqual(payload["public_url"]["status"], "unavailable")
        self.assertEqual(payload["public_url"]["reason"], "supported_provider_not_found")

    def test_expose_records_verified_public_url(self) -> None:
        public_success = {
            "enabled": True,
            "provider": "cloudflared-quick",
            "status": "verified",
            "url": "https://demo.trycloudflare.com",
            "candidate_url": "https://demo.trycloudflare.com",
            "reason": None,
            "verified_at": "2026-03-18T10:05:00Z",
            "pid": 12345,
            "log_path": str(self.root / "data" / "bootstrap" / "logs" / "cloudflared-quick.log"),
        }

        with patch.object(ops, "project_root", return_value=self.root), patch.object(
            ops, "probe_local_services", return_value=self._ok_local()
        ), patch.object(
            ops, "attempt_public_exposure", return_value=public_success
        ):
            payload = ops.run_expose("quick", state_path=self.state_path)

        self.assertEqual(payload["result"], "success")
        self.assertEqual(payload["operation"], "expose")
        self.assertEqual(payload["public_url"]["status"], "verified")
        self.assertEqual(payload["public_url"]["url"], "https://demo.trycloudflare.com")

    def test_doctor_reports_stale_docker_proxy(self) -> None:
        report = ops.build_doctor_report(
            {
                "local": self._ok_local(),
                "public_url": {
                    "enabled": False,
                    "provider": None,
                    "status": "unavailable",
                    "url": None,
                    "reason": "public_url_not_requested",
                },
                "docker_runtime": {
                    "available": True,
                    "stale_proxies": [
                        {
                            "kind": "http",
                            "url": "http://192.168.5.2:10077",
                            "host": "192.168.5.2",
                            "port": 10077,
                            "error": "[Errno 61] Connection refused",
                        }
                    ],
                },
            }
        )

        self.assertFalse(report["healthy"])
        self.assertEqual(report["issues"][0]["category"], "docker_proxy")
        self.assertIn("192.168.5.2:10077", report["issues"][0]["detail"])

    def test_doctor_reports_missing_api_contract_routes(self) -> None:
        local = self._ok_local()
        local["api_ok"] = False
        local["api_contract_ok"] = False
        local["api_contract_error"] = "expected_marker_missing"
        local["api_error"] = "expected_marker_missing"

        report = ops.build_doctor_report(
            {
                "local": local,
                "public_url": {
                    "enabled": False,
                    "provider": None,
                    "status": "unavailable",
                    "url": None,
                    "reason": "public_url_not_requested",
                },
                "docker_runtime": {
                    "available": True,
                    "stale_proxies": [],
                },
            }
        )

        self.assertFalse(report["healthy"])
        self.assertEqual(report["issues"][0]["category"], "local_api_contract")
        self.assertIn("rescue-center 路由", report["issues"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
