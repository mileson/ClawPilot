# Copyright (c) 2026 ClawPilot Contributors. All rights reserved.
# Licensed under the Business Source License 1.1 — see LICENSE file.
# NOTICE: Reverse engineering, decompilation, or disassembly is prohibited.

from __future__ import annotations

import hashlib
import ipaddress
import io
import json
import mimetypes
import os
import re
import secrets
import shlex
import shutil
import signal as signal_module
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
import xml.etree.ElementTree as ElementTree
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from . import local_runtime
from .scheduled_job_delivery import (
    apply_delivery_payload,
    build_delivery_bootstrap_operations,
    serialize_delivery_metadata,
    sync_delivery_bootstrap_files,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _detect_openclaw_cli_bin() -> str:
    configured = str(os.getenv("OPENCLAW_CLI_BIN") or "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())

    discovered = shutil.which("openclaw")
    if discovered:
        candidates.append(Path(discovered).expanduser())

    candidates.extend(
        [
            Path("/opt/homebrew/bin/openclaw"),
            Path("/usr/local/bin/openclaw"),
            Path.home() / ".local" / "bin" / "openclaw",
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return ""


def _resolve_runtime_data_path(
    raw_value: str | None,
    *,
    default_filename: str,
    repo_root: Path | None = None,
    container_data_root: Path = Path("/data"),
    container_data_available: bool | None = None,
) -> Path:
    resolved_repo_root = (repo_root or REPO_ROOT).resolve()
    host_data_root = resolved_repo_root / "data"
    container_available = container_data_root.exists() if container_data_available is None else container_data_available
    value = str(raw_value or "").strip()
    if not value:
        base_root = container_data_root if container_available else host_data_root
        return (base_root / default_filename).resolve()

    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        if not container_available:
            try:
                relative = candidate.relative_to(container_data_root)
            except ValueError:
                return candidate.resolve()
            return (host_data_root / relative).resolve()
        return candidate.resolve()
    return (resolved_repo_root / candidate).resolve()


DB_PATH = _resolve_runtime_data_path(os.getenv("OPENCLAW_OPS_DB"), default_filename="openclaw_ops.db")
OPENCLAW_CONFIG_PATH = Path(os.getenv("OPENCLAW_CONFIG_PATH", "/host-openclaw/openclaw.json"))
OPENCLAW_ROSTER_PATH = Path(
    os.getenv("OPENCLAW_ROSTER_PATH", "/host-openclaw/workspace/dispatch/agent-roster.json")
)
OPENCLAW_HOST_ROOT = Path(os.getenv("OPENCLAW_HOST_ROOT", "/host-openclaw"))
OPENCLAW_LOCAL_BASE_URL = os.getenv("OPENCLAW_LOCAL_BASE_URL", "http://127.0.0.1:8088").strip()
OPENCLAW_CRON_JOBS_PATH = Path(os.getenv("OPENCLAW_CRON_JOBS_PATH", str(OPENCLAW_HOST_ROOT / "cron" / "jobs.json")))
OPENCLAW_CRON_RUNS_ROOT = Path(os.getenv("OPENCLAW_CRON_RUNS_ROOT", str(OPENCLAW_HOST_ROOT / "cron" / "runs")))
FEISHU_TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_APP_ACCESS_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
FEISHU_BOT_INFO_URL = "https://open.feishu.cn/open-apis/bot/v3/info/"
FEISHU_MESSAGE_CREATE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
FEISHU_FILE_UPLOAD_URL = "https://open.feishu.cn/open-apis/im/v1/files"
FEISHU_USER_AUTH_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_USER_ACCESS_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/access_token"
FEISHU_USER_REFRESH_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/refresh_access_token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
FEISHU_BOT_CACHE_TTL_SEC = int(os.getenv("FEISHU_BOT_CACHE_TTL_SEC", "1800"))
FEISHU_SEND_FILE_MAX_BYTES = int(os.getenv("FEISHU_SEND_FILE_MAX_BYTES", str(20 * 1024 * 1024)))
FEISHU_USER_AUTH_SCOPE = os.getenv("FEISHU_USER_AUTH_SCOPE", "im:message.send_as_user")
CRON_RUN_ACTIVITY_TAIL_PER_JOB = int(os.getenv("CRON_RUN_ACTIVITY_TAIL_PER_JOB", "20"))
FEISHU_USER_AUTH_AGENT_IDS = {
    item.strip() for item in os.getenv("FEISHU_USER_AUTH_AGENT_IDS", "hr").split(",") if item.strip()
}
FEISHU_USER_AUTH_USER_KEY = os.getenv("FEISHU_USER_AUTH_USER_KEY", "default-human")
FEISHU_USER_AUTH_STATE_TTL_SEC = int(os.getenv("FEISHU_USER_AUTH_STATE_TTL_SEC", "900"))
FEISHU_USER_TOKEN_REFRESH_BUFFER_SEC = int(os.getenv("FEISHU_USER_TOKEN_REFRESH_BUFFER_SEC", "300"))
OPENCLAW_PUBLIC_BASE_URL = os.getenv("OPENCLAW_PUBLIC_BASE_URL", "").rstrip("/")
NODE_CONNECTOR_ONLINE_THRESHOLD_SEC = int(os.getenv("NODE_CONNECTOR_ONLINE_THRESHOLD_SEC", "90"))
OPENCLAW_CLI_BIN = _detect_openclaw_cli_bin()
AGENT_RUNTIME_WORKING_WINDOW_SEC = int(os.getenv("AGENT_RUNTIME_WORKING_WINDOW_SEC", "900"))
AGENT_RUNTIME_OFFLINE_STALE_WINDOW_SEC = int(os.getenv("AGENT_RUNTIME_OFFLINE_STALE_WINDOW_SEC", "86400"))
AGENT_RUNTIME_SESSION_TAIL_LINES = int(os.getenv("AGENT_RUNTIME_SESSION_TAIL_LINES", "200"))
AGENT_RUNTIME_OFFICIAL_SIGNAL_CACHE_TTL_SEC = int(
    os.getenv("AGENT_RUNTIME_OFFICIAL_SIGNAL_CACHE_TTL_SEC", "30")
)
TRAINING_RECENT_WINDOW_DAYS = int(os.getenv("TRAINING_RECENT_WINDOW_DAYS", "3"))
TRAINING_DEFAULT_OBSERVE_EVERY_HOURS = int(os.getenv("TRAINING_DEFAULT_OBSERVE_EVERY_HOURS", "6"))
TRAINING_STATUS_DOC_PATH = "training/status.md"
TRAINING_PROFILE_DOC_PATH = "training/trainee-profile.md"
TRAINING_RUN_DOCS_DIR = "training/runs"
TRAINING_SKILL_NAME = "agent-onboarding"
TRAINING_SKILL_SOURCE_OVERRIDE = os.getenv("AGENT_ONBOARDING_SKILL_PATH", "").strip()
ONBOARDING_SKILL_NAME = "agent-onboarding"
ONBOARDING_SKILL_SOURCE_OVERRIDE = os.getenv("AGENT_ONBOARDING_SKILL_PATH", "").strip()
ONBOARDING_RUN_STATUSES = {"draft", "running", "paused", "partial", "completed", "failed"}
ONBOARDING_STEP_STATUSES = {"todo", "running", "done", "warn", "failed", "skipped"}
ONBOARDING_STEP_DEFS = [
    {"key": "upsert", "label": "配置 upsert"},
    {"key": "scaffold_docs", "label": "文档脚手架"},
    {"key": "persona_writer", "label": "人设补写派发"},
    {"key": "group_join", "label": "自动加群"},
    {"key": "audit", "label": "审计 doctor / probe"},
    {"key": "restart", "label": "可选 restart"},
]
NODE_SYNC_SOURCE_SCHEDULED_JOB = "scheduled_job_delivery"
NODE_SYNC_OPERATION_KINDS = {"write_text_file", "upsert_json_value"}
NODE_SYNC_RESULT_STATUSES = {"applied", "failed"}
NODE_SYNC_BATCH_SIZE = int(os.getenv("NODE_SYNC_BATCH_SIZE", "50"))
SYSTEM_SETTINGS_SINGLETON = 1
SYSTEM_SETTINGS_DEFAULT_CURRENCY = "CNY"
SYSTEM_SETTINGS_DEFAULT_USD_CNY_RATE = float(os.getenv("OPENCLAW_DEFAULT_USD_CNY_RATE", "7.2"))
SYSTEM_SETTINGS_RATE_REFRESH_DAYS = int(os.getenv("OPENCLAW_EXCHANGE_RATE_REFRESH_DAYS", "7"))
SYSTEM_SETTINGS_FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=USD&to=CNY"
SYSTEM_SETTINGS_ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-xml.html"
SYSTEM_SETTINGS_RATE_SOURCES = {"frankfurter", "ecb", "fixed"}
SYSTEM_STATUS_ALIAS_DEFAULTS = {
    "working": "正在干活",
    "idle": "躺平中",
    "offline": "离线摸鱼",
    "crashed": "崩溃中",
}
AGENT_SCENE_PRESET_IDS = {
    "preset-standard",
    "preset-focus",
    "preset-cat-lobster",
    "preset-bear-lobster",
}
ACCOUNT_STATUS_VALUES = {"active", "disabled"}
ACCOUNT_PASSWORD_ITERATIONS = int(os.getenv("ACCOUNT_PASSWORD_ITERATIONS", "120000"))
ACCOUNT_SESSION_TTL_SEC = int(os.getenv("ACCOUNT_SESSION_TTL_SEC", str(7 * 24 * 3600)))
ACCOUNT_BOOTSTRAP_USERNAME = os.getenv("ACCOUNT_BOOTSTRAP_USERNAME", "openclaw").strip() or "openclaw"
ACCOUNT_BOOTSTRAP_PASSWORD_PREFIX = os.getenv("ACCOUNT_BOOTSTRAP_PASSWORD_PREFIX", "openclaw").strip() or "openclaw"
ACCOUNT_PASSWORD_MIN_LENGTH = int(os.getenv("ACCOUNT_PASSWORD_MIN_LENGTH", "10"))
ACCOUNT_PASSWORD_MAX_LENGTH = int(os.getenv("ACCOUNT_PASSWORD_MAX_LENGTH", "128"))
RESCUE_CENTER_THREAD_STATUSES = {"idle", "active", "archived", "failed", "blocked"}
RESCUE_CENTER_RUNTIME_STATUSES = {"idle", "awaiting_events", "recovering", "recovered", "failed", "blocked"}
RESCUE_CENTER_RECOVERY_STATES = {"none", "fresh_transport", "auto_recovered"}
_UNSET = object()
FEISHU_UI_AUTOMATION_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "feishu_app_ui_automation.py"
FEISHU_UI_AUTOMATION_DEFAULT_APP_NAME = "Clawpilot"
FEISHU_UI_AUTOMATION_DEFAULT_APP_DESCRIPTION = "第一只小龙虾，负责统管所有业务"
FEISHU_UI_AUTOMATION_DEFAULT_MENU_NAME = "/status 状态"
FIRST_LOBSTER_DEFAULT_AGENT_ID = "main"
FIRST_LOBSTER_DEFAULT_AGENT_NAME = "第一只小龙虾"
FIRST_LOBSTER_DEFAULT_ACCOUNT_ID = FIRST_LOBSTER_DEFAULT_AGENT_ID
FIRST_LOBSTER_BOOTSTRAP_FILES = (
    "BOOTSTRAP.md",
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "TOOLS.md",
    "HEARTBEAT.md",
    "MEMORY.md",
)
FIRST_LOBSTER_PREVIEW_MAX_CHARS = int(os.getenv("FIRST_LOBSTER_PREVIEW_MAX_CHARS", "4000"))
FIRST_LOBSTER_SUPPORTED_CHANNELS: tuple[dict[str, Any], ...] = (
    {
        "channel": "feishu",
        "label": "Feishu",
        "description": "Use appId / appSecret",
        "default_account_id": FIRST_LOBSTER_DEFAULT_ACCOUNT_ID,
        "fields": [
            {
                "key": "app_id",
                "label": "appId",
                "secret": False,
                "placeholder": "cli_xxx",
            },
            {
                "key": "app_secret",
                "label": "appSecret",
                "secret": True,
                "placeholder": "cli_secret_xxx",
            },
        ],
    },
    {
        "channel": "weixin",
        "label": "WeChat",
        "description": "QR code login",
        "default_account_id": FIRST_LOBSTER_DEFAULT_ACCOUNT_ID,
        "fields": [],
    },
)


def _local_openclaw_home() -> Path:
    return (Path.home() / ".openclaw").expanduser()


def _resolved_openclaw_host_root() -> Path:
    configured_root = OPENCLAW_HOST_ROOT.expanduser()
    if configured_root.exists():
        return configured_root.resolve()

    configured_config = OPENCLAW_CONFIG_PATH.expanduser()
    if configured_config.exists():
        return configured_config.parent.resolve()

    configured_roster = OPENCLAW_ROSTER_PATH.expanduser()
    if configured_roster.exists():
        try:
            return configured_roster.parents[2].resolve()
        except IndexError:
            pass

    local_home = _local_openclaw_home()
    if local_home.exists():
        return local_home.resolve()

    return configured_root


def _resolved_openclaw_config_path() -> Path:
    configured_path = OPENCLAW_CONFIG_PATH.expanduser()
    if configured_path.exists():
        return configured_path.resolve()

    fallback = _resolved_openclaw_host_root() / "openclaw.json"
    if fallback.exists():
        return fallback.resolve()

    return configured_path


def _resolved_openclaw_roster_path() -> Path:
    configured_path = OPENCLAW_ROSTER_PATH.expanduser()
    if configured_path.exists():
        return configured_path.resolve()

    fallback = _resolved_openclaw_host_root() / "workspace" / "dispatch" / "agent-roster.json"
    if fallback.exists():
        return fallback.resolve()

    return configured_path


def _resolved_openclaw_cron_jobs_path() -> Path:
    configured_path = OPENCLAW_CRON_JOBS_PATH.expanduser()
    if configured_path.exists():
        return configured_path.resolve()

    fallback = _resolved_openclaw_host_root() / "cron" / "jobs.json"
    if fallback.exists():
        return fallback.resolve()

    return configured_path


def _resolved_openclaw_cron_runs_root() -> Path:
    configured_path = OPENCLAW_CRON_RUNS_ROOT.expanduser()
    if configured_path.exists():
        return configured_path.resolve()

    fallback = _resolved_openclaw_host_root() / "cron" / "runs"
    if fallback.exists():
        return fallback.resolve()

    return configured_path

DEFAULT_ROLES = [
    {"role_id": "owner", "name": "Owner", "description": "全量权限", "is_system": 1},
    {"role_id": "admin", "name": "Admin", "description": "系统管理员", "is_system": 1},
    {"role_id": "operator", "name": "Operator", "description": "执行与运营", "is_system": 1},
    {"role_id": "viewer", "name": "Viewer", "description": "只读访问", "is_system": 1},
]

DEFAULT_PERMISSION_CATALOG = [
    {
        "module_key": "accounts",
        "module_label": "员工管理",
        "action_key": "view",
        "action_label": "查看",
        "description": "查看员工列表与员工授权信息",
    },
    {
        "module_key": "accounts",
        "module_label": "员工管理",
        "action_key": "invite",
        "action_label": "邀请",
        "description": "创建员工账号并下发临时密码",
    },
    {
        "module_key": "accounts",
        "module_label": "员工管理",
        "action_key": "disable",
        "action_label": "禁用",
        "description": "禁用或启用员工账号",
    },
    {
        "module_key": "accounts",
        "module_label": "员工管理",
        "action_key": "reset_password",
        "action_label": "重置密码",
        "description": "重置员工密码并强制修改",
    },
    {
        "module_key": "accounts",
        "module_label": "员工管理",
        "action_key": "force_logout",
        "action_label": "强制登出",
        "description": "强制清除员工会话",
    },
    {
        "module_key": "accounts",
        "module_label": "员工管理",
        "action_key": "delete",
        "action_label": "删除",
        "description": "删除员工账号",
    },
    {
        "module_key": "roles",
        "module_label": "角色管理",
        "action_key": "assign",
        "action_label": "分配角色",
        "description": "变更员工角色绑定与访问配置",
    },
    {
        "module_key": "roles",
        "module_label": "角色管理",
        "action_key": "manage",
        "action_label": "管理角色",
        "description": "更新角色权限矩阵",
    },
    {
        "module_key": "audit",
        "module_label": "审计日志",
        "action_key": "view",
        "action_label": "查看",
        "description": "查看审计日志",
    },
    {
        "module_key": "agents",
        "module_label": "Agent 工区",
        "action_key": "view",
        "action_label": "查看",
        "description": "查看 Agent 工区",
    },
    {
        "module_key": "agents",
        "module_label": "Agent 工区",
        "action_key": "manage",
        "action_label": "管理",
        "description": "管理 Agent 配置与状态",
    },
    {
        "module_key": "tasks",
        "module_label": "任务派单",
        "action_key": "view",
        "action_label": "查看",
        "description": "查看任务与派单数据",
    },
    {
        "module_key": "tasks",
        "module_label": "任务派单",
        "action_key": "manage",
        "action_label": "管理",
        "description": "创建与管理任务派单",
    },
    {
        "module_key": "system",
        "module_label": "系统设置",
        "action_key": "manage",
        "action_label": "管理",
        "description": "调整系统设置",
    },
]

DEFAULT_ROLE_PERMISSIONS = {
    "owner": ["*"],
    "admin": [
        "accounts.view",
        "accounts.invite",
        "accounts.disable",
        "accounts.reset_password",
        "accounts.force_logout",
        "roles.assign",
        "roles.manage",
        "audit.view",
        "agents.view",
        "agents.manage",
        "tasks.view",
        "tasks.manage",
        "system.manage",
    ],
    "operator": [
        "accounts.view",
        "roles.assign",
        "audit.view",
        "agents.view",
        "tasks.view",
    ],
    "viewer": [
        "accounts.view",
        "audit.view",
        "agents.view",
        "tasks.view",
    ],
}
SETUP_PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent / "data" / "setup_prompt.md"
BOOTSTRAP_STATE_PATH = Path(
    os.getenv(
        "OPENCLAW_BOOTSTRAP_STATE_PATH",
        Path(__file__).resolve().parent.parent / "data" / "bootstrap" / "latest.json",
    )
)

_FEISHU_BOT_PROFILE_CACHE: dict[str, dict[str, str | None]] = {}
_FEISHU_BOT_PROFILE_CACHE_AT = 0.0
_OFFICIAL_RUNTIME_SIGNAL_CACHE: dict[str, Any] = {"value": None, "loaded_at": 0.0}
_OPENCLAW_CONFIG_CACHE = local_runtime.VersionedValueCache("openclaw_config", max_entries=4)
_ROSTER_INDEX_CACHE = local_runtime.VersionedValueCache("agent_roster_index", max_entries=4)
_IDENTITY_INDEX_CACHE = local_runtime.VersionedValueCache("identity_index", max_entries=4)
_OPENCLAW_JOBS_CACHE = local_runtime.VersionedValueCache("openclaw_jobs", max_entries=4)
_SESSION_RECORDS_CACHE = local_runtime.VersionedValueCache("session_records", max_entries=128)
_TRANSCRIPT_SUMMARY_CACHE = local_runtime.VersionedValueCache("transcript_summary", max_entries=512)
_DIRECTORY_LISTING_CACHE = local_runtime.VersionedValueCache("directory_listing", max_entries=512)

ROLE_MAP = {
    "main": "总管与协调",
    "task": "项目管理与派单",
    "coding": "工程研发与联调",
    "image": "视觉设计与素材生成",
    "legal": "法务合规与合同审核",
    "evolution": "系统演进与能力优化",
    "reporter": "文档产出与材料整理",
    "blogger": "内容运营与分发",
    "product": "产品分析与增长策略",
    "coach": "培训考核与上岗门禁",
    "security": "安全监控与风险预警",
}

DISPLAY_NAME_MAP = {
    "main": "总管",
    "task": "项目经理",
    "coding": "工程师",
    "image": "画师",
    "legal": "法律专家",
    "evolution": "进化官",
    "reporter": "文员",
    "blogger": "博主",
    "product": "产品官",
    "coach": "教练",
    "security": "安全专家",
}

WORKSPACE_VISIBLE_ROOT = Path("/root/.openclaw")
WORKSPACE_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".log",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".scss",
    ".html",
    ".sh",
    ".sql",
    ".csv",
    ".ini",
    ".cfg",
    ".conf",
}
WORKSPACE_CODE_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".sh": "bash",
    ".sql": "sql",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".xml": "xml",
}
WORKSPACE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
WORKSPACE_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".ogg", ".ogv", ".mkv"}
WORKSPACE_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
WORKSPACE_PDF_EXTENSIONS = {".pdf"}
WORKSPACE_OFFICE_EXTENSIONS = {
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".odt",
    ".ods",
    ".odp",
    ".rtf",
}
WORKSPACE_MAX_PREVIEW_BYTES = int(os.getenv("WORKSPACE_MAX_PREVIEW_BYTES", "262144"))
WORKSPACE_MAX_SAVE_BYTES = int(os.getenv("WORKSPACE_MAX_SAVE_BYTES", "524288"))
WORKSPACE_PREVIEW_CACHE_DIR = Path(
    os.getenv("WORKSPACE_PREVIEW_CACHE_DIR", Path(__file__).resolve().parent / "data" / "workspace_preview_cache")
)
WORKSPACE_OFFICE_CONVERTER_BIN = os.getenv("WORKSPACE_OFFICE_CONVERTER_BIN", "").strip()
SKILL_IMPORT_MAX_BYTES = int(os.getenv("SKILL_IMPORT_MAX_BYTES", str(50 * 1024 * 1024)))
SESSION_LOG_LIMIT_MAX = 200
SCHEDULE_TIMELINE_DEFAULT_HOURS = 24
SCHEDULE_TIMELINE_MAX_DAYS = 31
SCHEDULE_TIMELINE_DEFAULT_DURATION_MINUTES = 30
SCHEDULE_TIMELINE_MIN_INTERVAL_DURATION_MINUTES = 5
SCHEDULE_TIMELINE_MAX_OCCURRENCES_PER_JOB = 2000
AGENT_PORTABLE_PACKAGE_SCHEMA_VERSION = "1.0.0"
AGENT_PORTABLE_PACKAGE_TYPE = "agent-portable-package"
AGENT_PORTABLE_PACKAGE_DOC_FILES = (
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "TOOLS.md",
    "HEARTBEAT.md",
    "MEMORY.md",
    "TASK_POLICY.md",
)
AGENT_PORTABLE_PACKAGE_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "sensitive_openai_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        "检测到疑似 API Key，请在迁移前确认是否需要替换。",
    ),
    (
        "sensitive_aws_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "检测到疑似 AWS Access Key，请在迁移前确认凭证安全。",
    ),
    (
        "sensitive_private_key",
        re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
        "检测到疑似私钥内容，请在迁移前确认是否需要重新签发。",
    ),
    (
        "sensitive_secret_keyword",
        re.compile(r"(?i)\b(token|secret|password|api[_-]?key)\b"),
        "检测到敏感字段关键词，请检查该文件是否适合直接迁移。",
    ),
)
AGENT_RUNTIME_FATAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"\bpanic:", re.IGNORECASE),
    re.compile(r"\bfatal:", re.IGNORECASE),
    re.compile(r"segmentation fault", re.IGNORECASE),
    re.compile(r"core dumped", re.IGNORECASE),
    re.compile(r"\bsignal sig(?:segv|abrt|bus|ill|fpe)\b", re.IGNORECASE),
    re.compile(r"\b(exit code|code)\s*(137|139)\b", re.IGNORECASE),
    re.compile(r"unhandledpromiserejection", re.IGNORECASE),
    re.compile(r"oomkilled", re.IGNORECASE),
)
AGENT_RUNTIME_HEARTBEAT_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"heartbeat[-_ ]only", re.IGNORECASE),
    re.compile(r"\bheartbeat ack(?:nowledg(?:e)?ment)?\b", re.IGNORECASE),
    re.compile(r"\bkeep[- ]?alive ack(?:nowledg(?:e)?ment)?\b", re.IGNORECASE),
    re.compile(r"\bsystem heartbeat\b", re.IGNORECASE),
    re.compile(r"\bmaintenance ack(?:nowledg(?:e)?ment)?\b", re.IGNORECASE),
)


def _resolve_display_name(agent_id: str, roster_row: dict[str, Any], config_row: dict[str, Any]) -> str:
    preferred = str(
        roster_row.get("name") or config_row.get("name") or DISPLAY_NAME_MAP.get(agent_id, agent_id)
    ).strip()
    if preferred == agent_id and agent_id in DISPLAY_NAME_MAP:
        return DISPLAY_NAME_MAP[agent_id]
    return preferred


def _default_lobster_agent_name(agent_id: str) -> str | None:
    normalized = str(agent_id or "").strip()
    if not normalized:
        return None
    sequence = _parse_lobster_sequence(normalized)
    if sequence == 1:
        return FIRST_LOBSTER_DEFAULT_AGENT_NAME
    if sequence and sequence >= 2:
        return f"第{_format_lobster_sequence_label(sequence)}只小龙虾"
    return None


def _is_default_lobster_placeholder_name(agent_id: str, name: Any) -> bool:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        return False
    expected = _default_lobster_agent_name(agent_id)
    return bool(expected) and normalized_name == expected


def _map_visible_openclaw_path(path: Path) -> Path:
    raw = path.expanduser()
    if raw == WORKSPACE_VISIBLE_ROOT or WORKSPACE_VISIBLE_ROOT in raw.parents:
        relative = raw.relative_to(WORKSPACE_VISIBLE_ROOT)
        return (_resolved_openclaw_host_root() / relative).resolve()
    host_root = _resolved_openclaw_host_root()
    if raw == host_root or host_root in raw.parents:
        return raw.resolve()
    raise PermissionError("workspace_outside_allowed_root")


def _workspace_shared_allowed_roots() -> tuple[Path, ...]:
    host_root = _resolved_openclaw_host_root()
    return (
        (host_root / "skills").resolve(),
        (host_root / ".agents" / "skills").resolve(),
    )


def _coerce_openclaw_host_path(path: Path) -> Path:
    try:
        return _map_visible_openclaw_path(path)
    except PermissionError:
        return path


def _is_under_allowed_root(path: Path, allowed_roots: tuple[Path, ...]) -> bool:
    return any(path == allowed_root or allowed_root in path.parents for allowed_root in allowed_roots)


def _workspace_allowed_roots(workspace_root: Path) -> tuple[Path, ...]:
    return (workspace_root.resolve(), *_workspace_shared_allowed_roots())


def _normalize_workspace_relative_path(relative_path: str | None) -> str:
    if not relative_path:
        return ""
    normalized = Path(relative_path).as_posix().strip("/")
    return "" if normalized == "." else normalized


def _join_workspace_relative_path(parent_relative_path: str, child_name: str) -> str:
    return f"{parent_relative_path}/{child_name}".strip("/")


def _is_skills_relative_path(relative_path: str) -> bool:
    return relative_path == "skills" or relative_path.startswith("skills/")


def _path_has_skills_symlink(workspace_root: Path, relative_path: str) -> bool:
    normalized = _normalize_workspace_relative_path(relative_path)
    if not normalized or not _is_skills_relative_path(normalized):
        return False
    current = workspace_root
    for segment in Path(normalized).parts:
        current = current / segment
        try:
            if current.is_symlink():
                return True
        except OSError:
            return False
    return False


def _ensure_child_path(
    root: Path,
    relative_path: str | None,
    extra_allowed_roots: tuple[Path, ...] = (),
    *,
    allow_skills_symlink: bool = False,
) -> Path:
    allowed_roots = (root.resolve(), *(item.resolve() for item in extra_allowed_roots))
    normalized = _normalize_workspace_relative_path(relative_path)
    candidate = _coerce_openclaw_host_path((root / (relative_path or "")).resolve())
    if not _is_under_allowed_root(candidate, allowed_roots):
        if not (allow_skills_symlink and _path_has_skills_symlink(root, normalized)):
            raise PermissionError("workspace_path_outside_root")
    return candidate


def _resolve_workspace_entry(
    entry: Path,
    allowed_roots: tuple[Path, ...],
    *,
    allow_outside_root: bool = False,
) -> tuple[Path, bool, os.stat_result]:
    resolved_entry = _coerce_openclaw_host_path(entry.resolve())
    if not allow_outside_root and not _is_under_allowed_root(resolved_entry, allowed_roots):
        raise PermissionError("workspace_path_outside_root")
    stat = resolved_entry.stat()
    return resolved_entry, resolved_entry.is_dir(), stat


def _is_text_like_file(path: Path) -> bool:
    if path.suffix.lower() in WORKSPACE_TEXT_EXTENSIONS:
        return True
    mime, _ = mimetypes.guess_type(path.name)
    return bool(mime and (mime.startswith("text/") or mime in {"application/json", "application/xml"}))


def _is_editable_text_file(path: Path) -> bool:
    return path.suffix.lower() in WORKSPACE_TEXT_EXTENSIONS


def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def _guess_code_language(path: Path) -> str | None:
    return WORKSPACE_CODE_LANGUAGE_BY_EXTENSION.get(path.suffix.lower())


def _office_converter_path() -> str | None:
    candidates = [
        WORKSPACE_OFFICE_CONVERTER_BIN,
        shutil.which("soffice") or "",
        shutil.which("libreoffice") or "",
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return None


def _workspace_preview_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = _guess_mime_type(path)
    if _is_text_like_file(path):
        return "code" if _guess_code_language(path) else "text"
    if suffix in WORKSPACE_IMAGE_EXTENSIONS or mime.startswith("image/"):
        return "image"
    if suffix in WORKSPACE_VIDEO_EXTENSIONS or mime.startswith("video/"):
        return "video"
    if suffix in WORKSPACE_AUDIO_EXTENSIONS or mime.startswith("audio/"):
        return "audio"
    if suffix in WORKSPACE_PDF_EXTENSIONS or mime == "application/pdf":
        return "pdf"
    if suffix in WORKSPACE_OFFICE_EXTENSIONS:
        return "office"
    return "binary"


def _workspace_asset_url(agent_id: str, relative_path: str, variant: str = "raw") -> str:
    encoded = quote(relative_path, safe="")
    return f"/api/agents/{agent_id}/workspace/asset?path={encoded}&variant={variant}"


def _serialize_workspace_file(
    *,
    agent_id: str,
    agent_name: str,
    workspace_display_path: str,
    relative_path: str,
    file_path: Path,
) -> dict[str, Any]:
    preview_kind = _workspace_preview_kind(file_path)
    mime_type = _guess_mime_type(file_path)
    previewable = preview_kind in {"text", "code", "image", "video", "audio", "pdf", "office"}
    editable = _is_editable_text_file(file_path)
    content = None
    truncated = False
    if preview_kind in {"text", "code"}:
        content, truncated = _read_text_preview(file_path)

    preview_url = None
    if preview_kind in {"image", "video", "audio", "pdf"}:
        preview_url = _workspace_asset_url(agent_id, relative_path, "raw")

    pdf_preview_url = None
    if preview_kind == "office" and _office_converter_path():
        pdf_preview_url = _workspace_asset_url(agent_id, relative_path, "pdf")

    stat = file_path.stat()
    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "root_path": workspace_display_path,
        "path": relative_path,
        "display_path": _workspace_visible_path(workspace_display_path, relative_path),
        "name": file_path.name,
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "editable": editable,
        "previewable": previewable,
        "preview_kind": preview_kind,
        "mime_type": mime_type,
        "code_language": _guess_code_language(file_path),
        "preview_url": preview_url,
        "pdf_preview_url": pdf_preview_url,
        "download_url": _workspace_asset_url(agent_id, relative_path, "raw"),
        "truncated": truncated,
        "content": content,
    }


def _read_text_preview(path: Path, max_bytes: int = WORKSPACE_MAX_PREVIEW_BYTES) -> tuple[str, bool]:
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace"), truncated


def _workspace_visible_path(root_display_path: str, relative_path: str) -> str:
    clean_root = root_display_path.rstrip("/")
    clean_rel = relative_path.strip("/")
    if not clean_rel:
        return clean_root
    return f"{clean_root}/{clean_rel}"


def _openclaw_root_asset_url(relative_path: str, variant: str = "raw") -> str:
    encoded = quote(relative_path, safe="")
    return f"/api/openclaw/explorer/asset?path={encoded}&variant={variant}"


def _get_openclaw_root() -> tuple[str, Path]:
    root_display_path = str(WORKSPACE_VISIBLE_ROOT)
    root_path = _map_visible_openclaw_path(WORKSPACE_VISIBLE_ROOT)
    if not root_path.exists() or not root_path.is_dir():
        raise LookupError("openclaw_root_not_found")
    return root_display_path, root_path


def _serialize_openclaw_root_file(
    *,
    root_display_path: str,
    relative_path: str,
    file_path: Path,
) -> dict[str, Any]:
    preview_kind = _workspace_preview_kind(file_path)
    mime_type = _guess_mime_type(file_path)
    previewable = preview_kind in {"text", "code", "image", "video", "audio", "pdf", "office"}
    editable = False
    content = None
    truncated = False
    if preview_kind in {"text", "code"}:
        content, truncated = _read_text_preview(file_path)

    preview_url = None
    if preview_kind in {"image", "video", "audio", "pdf"}:
        preview_url = _openclaw_root_asset_url(relative_path, "raw")

    pdf_preview_url = None
    if preview_kind == "office" and _office_converter_path():
        pdf_preview_url = _openclaw_root_asset_url(relative_path, "pdf")

    stat = file_path.stat()
    return {
        "root_path": root_display_path,
        "path": relative_path,
        "display_path": _workspace_visible_path(root_display_path, relative_path),
        "name": file_path.name,
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "editable": editable,
        "previewable": previewable,
        "preview_kind": preview_kind,
        "mime_type": mime_type,
        "code_language": _guess_code_language(file_path),
        "preview_url": preview_url,
        "pdf_preview_url": pdf_preview_url,
        "download_url": _openclaw_root_asset_url(relative_path, "raw"),
        "truncated": truncated,
        "content": content,
    }


def _get_agent_workspace_roots(agent_id: str) -> tuple[dict[str, Any], str, Path]:
    started = time.perf_counter()
    agent = _get_agent_lightweight_payload(agent_id)
    if not agent:
        raise LookupError("agent_not_found")

    workspace_display_path = str(agent.get("workspace_path") or "").strip()
    if not workspace_display_path:
        raise LookupError("workspace_not_configured")

    workspace_root = _map_visible_openclaw_path(Path(workspace_display_path))
    if not workspace_root.exists() or not workspace_root.is_dir():
        raise LookupError("workspace_not_found")
    local_runtime.RUNTIME_DIAGNOSTICS.record_latency(
        "agent_workspace_roots",
        (time.perf_counter() - started) * 1000,
        detail={"agent_id": agent_id},
    )
    return agent, workspace_display_path, workspace_root


def _resolve_agent_skills_root(agent_id: str) -> tuple[dict[str, Any], str, Path, Path]:
    agent, workspace_display_path, workspace_root = _get_agent_workspace_roots(agent_id)
    skills_root = (workspace_root / "skills").resolve()
    if skills_root != workspace_root and workspace_root not in skills_root.parents:
        raise PermissionError("workspace_path_outside_root")
    skills_root.mkdir(parents=True, exist_ok=True)
    return agent, workspace_display_path, workspace_root, skills_root


def _sanitize_skill_name(raw: str) -> str:
    candidate = raw.strip()
    candidate = re.sub(r"\.zip$", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.replace(" ", "-")
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate)
    candidate = candidate.strip("._-")
    if not candidate:
        raise ValueError("skill_name_invalid")
    return candidate


def _normalize_archive_relative_path(raw: str) -> str:
    path = raw.replace("\\", "/").strip("/")
    if not path:
        raise ValueError("skill_archive_path_invalid")
    parts = []
    for part in path.split("/"):
        if not part or part in {".", ".."}:
            raise ValueError("skill_archive_path_invalid")
        parts.append(part)
    return "/".join(parts)


def _prepare_skill_destination(skills_root: Path, skill_name: str) -> tuple[Path, bool]:
    destination = _ensure_child_path(skills_root, skill_name, _workspace_shared_allowed_roots())
    if destination.exists():
        raise ValueError("skill_already_exists")
    destination.mkdir(parents=True, exist_ok=True)
    return destination, False


def _iter_archive_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/").strip("/")
        if not name or name.startswith("__MACOSX/") or name.endswith("/.DS_Store") or name == ".DS_Store":
            continue
        members.append(info)
    return members


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _serialize_portable_warning(code: str, message: str, path: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "path": path}


def _dedupe_portable_warnings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (
            str(item.get("code") or "").strip(),
            str(item.get("message") or "").strip(),
            str(item.get("path") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _scan_sensitive_content(package_path: str, payload: bytes) -> list[dict[str, Any]]:
    if not package_path:
        return []
    suffix = Path(package_path).suffix.lower()
    if suffix not in WORKSPACE_TEXT_EXTENSIONS and suffix not in {".md", ".json"}:
        return []
    try:
        content = payload.decode("utf-8", errors="ignore")
    except Exception:
        return []
    if not content.strip():
        return []

    warnings: list[dict[str, Any]] = []
    for code, pattern, message in AGENT_PORTABLE_PACKAGE_SENSITIVE_PATTERNS:
        if pattern.search(content):
            warnings.append(_serialize_portable_warning(code=code, message=message, path=package_path))
    return warnings


def _build_agent_portable_package_filename(agent_id: str, exported_at: datetime) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(agent_id or "").strip()).strip("._-") or "agent"
    timestamp = exported_at.strftime("%Y%m%dT%H%M%SZ")
    return f"{normalized}-portable-package-{timestamp}.zip"


def _iter_directory_files(root: Path) -> list[Path]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _build_agent_portable_agent_payload(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": agent.get("agent_id"),
        "display_name": agent.get("display_name"),
        "role": agent.get("role"),
        "role_summary": agent.get("role_summary"),
        "status": agent.get("status"),
        "channel": agent.get("channel"),
        "account_id": agent.get("account_id"),
        "open_id": agent.get("open_id"),
        "scene_preset_id": agent.get("scene_preset_id"),
        "workspace_path": agent.get("workspace_path"),
        "identity_complete": bool(agent.get("identity_complete")),
        "skills": list(agent.get("skills") or []),
        "core_work": list(agent.get("core_work") or []),
        "capabilities": list(agent.get("capabilities") or []),
        "delegate_when": list(agent.get("delegate_when") or []),
        "do_not_delegate_when": list(agent.get("do_not_delegate_when") or []),
        "priority": agent.get("priority"),
        "enabled": agent.get("enabled"),
        "main_dispatch_allowed": agent.get("main_dispatch_allowed"),
        "emoji": agent.get("emoji"),
        "avatar_hint": agent.get("avatar_hint"),
        "avatar_url": agent.get("avatar_url"),
        "created_at": agent.get("created_at"),
    }


def _build_agent_portable_restore_readme(
    *,
    agent: dict[str, Any],
    missing_docs: list[str],
    skill_summaries: list[dict[str, Any]],
    scheduled_jobs: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    lines = [
        f"# {agent.get('display_name') or agent.get('agent_id') or 'Agent'} Portable Package",
        "",
        "## Summary",
        "",
        f"- Agent ID: `{agent.get('agent_id') or ''}`",
        f"- Display Name: `{agent.get('display_name') or ''}`",
        f"- Role: `{agent.get('role') or ''}`",
        f"- Channel: `{agent.get('channel') or ''}`",
        f"- Docs Included: `{len(AGENT_PORTABLE_PACKAGE_DOC_FILES) - len(missing_docs)}`",
        f"- Skills Included: `{len(skill_summaries)}`",
        f"- Scheduled Jobs Included: `{len(scheduled_jobs)}`",
        "",
        "## Package Layout",
        "",
        "```text",
        "manifest.json",
        "agent.json",
        "docs/",
        "skills/",
        "scheduled-jobs/jobs.json",
        "restore/README.md",
        "```",
        "",
        "## Restore Notes",
        "",
        "1. Import `agent.json` into the target platform as the base agent identity metadata.",
        "2. Copy files from `docs/` into the target platform's prompt or persona workspace.",
        "3. Copy directories under `skills/` into the target platform's skill/plugin registry as needed.",
        "4. Recreate tasks from `scheduled-jobs/jobs.json` according to the destination scheduler model.",
        "5. Review all warnings in `manifest.json` before activating the migrated agent.",
    ]

    if missing_docs:
        lines.extend(
            [
                "",
                "## Missing Standard Docs",
                "",
                *[f"- `{name}`" for name in missing_docs],
            ]
        )

    if warnings:
        lines.extend(
            [
                "",
                "## Warnings",
                "",
                *[
                    f"- {item['message']}" if not item.get("path") else f"- `{item['path']}`: {item['message']}"
                    for item in warnings
                ],
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _collect_agent_portable_package_context(agent_id: str) -> dict[str, Any]:
    agent, _workspace_display_path, workspace_root = _get_agent_workspace_roots(agent_id)
    exported_at = datetime.now(timezone.utc)
    warnings: list[dict[str, Any]] = []
    missing_docs: list[str] = []
    doc_files: list[dict[str, Any]] = []
    skill_files: list[dict[str, Any]] = []
    skill_summaries: list[dict[str, Any]] = []

    for doc_name in AGENT_PORTABLE_PACKAGE_DOC_FILES:
        source_path = _ensure_child_path(workspace_root, doc_name, _workspace_shared_allowed_roots())
        if not source_path.exists() or not source_path.is_file():
            missing_docs.append(doc_name)
            continue
        payload = source_path.read_bytes()
        package_path = f"docs/{doc_name}"
        doc_files.append(
            {
                "name": doc_name,
                "package_path": package_path,
                "source_path": source_path,
                "payload": payload,
                "size": len(payload),
                "sha256": _sha256_bytes(payload),
            }
        )
        warnings.extend(_scan_sensitive_content(package_path, payload))

    skills_root = (workspace_root / "skills").resolve()
    if skills_root.exists() and skills_root.is_dir():
        for entry in sorted(skills_root.iterdir(), key=lambda item: item.name.lower()):
            if not entry.is_dir():
                continue
            file_count = 0
            total_bytes = 0
            for file_path in _iter_directory_files(entry):
                relative_path = file_path.relative_to(skills_root).as_posix()
                package_path = f"skills/{relative_path}"
                payload = file_path.read_bytes()
                skill_files.append(
                    {
                        "name": file_path.name,
                        "package_path": package_path,
                        "source_path": file_path,
                        "payload": payload,
                        "size": len(payload),
                        "sha256": _sha256_bytes(payload),
                    }
                )
                file_count += 1
                total_bytes += len(payload)
                if _is_text_like_file(file_path):
                    warnings.extend(_scan_sensitive_content(package_path, payload))
            skill_summaries.append(
                {
                    "name": entry.name,
                    "package_path": f"skills/{entry.name}",
                    "file_count": file_count,
                    "total_bytes": total_bytes,
                }
            )

    filtered_jobs: list[dict[str, Any]] = []
    serialized_jobs: list[dict[str, Any]] = []
    document = _load_openclaw_jobs_document()
    for raw_job in document.get("jobs") or []:
        if not isinstance(raw_job, dict):
            continue
        if str(raw_job.get("agentId") or "").strip() != str(agent["agent_id"]):
            continue
        filtered_jobs.append(raw_job)
        try:
            serialized_jobs.append(_serialize_agent_scheduled_job(raw_job))
        except ValueError:
            warnings.append(
                _serialize_portable_warning(
                    code="scheduled_job_unsupported",
                    message="存在无法序列化的定时任务，已按原始结构导出，请在目标平台手工确认。",
                    path="scheduled-jobs/jobs.json",
                )
            )

    scheduled_jobs_payload = (json.dumps({"jobs": filtered_jobs}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    scheduled_jobs_file = {
        "name": "jobs.json",
        "package_path": "scheduled-jobs/jobs.json",
        "payload": scheduled_jobs_payload,
        "size": len(scheduled_jobs_payload),
        "sha256": _sha256_bytes(scheduled_jobs_payload),
    }
    warnings.extend(_scan_sensitive_content("scheduled-jobs/jobs.json", scheduled_jobs_payload))

    if agent.get("open_id"):
        warnings.append(
            _serialize_portable_warning(
                code="agent_open_id_rebind_required",
                message="当前 Agent 绑定了 open_id，迁移到其他平台后通常需要重新授权或重新绑定身份。",
                path="agent.json",
            )
        )

    generated_files: list[dict[str, Any]] = []
    agent_payload = _build_agent_portable_agent_payload(agent)
    agent_json_bytes = (json.dumps(agent_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    generated_files.append(
        {
            "name": "agent.json",
            "package_path": "agent.json",
            "payload": agent_json_bytes,
            "size": len(agent_json_bytes),
            "sha256": _sha256_bytes(agent_json_bytes),
        }
    )

    warnings = _dedupe_portable_warnings(warnings)
    restore_readme = _build_agent_portable_restore_readme(
        agent=agent,
        missing_docs=missing_docs,
        skill_summaries=skill_summaries,
        scheduled_jobs=serialized_jobs,
        warnings=warnings,
    )
    restore_bytes = restore_readme.encode("utf-8")
    generated_files.append(
        {
            "name": "README.md",
            "package_path": "restore/README.md",
            "payload": restore_bytes,
            "size": len(restore_bytes),
            "sha256": _sha256_bytes(restore_bytes),
        }
    )

    file_inventory = [
        {
            "path": item["package_path"],
            "sha256": item["sha256"],
            "size": item["size"],
        }
        for item in [*doc_files, *skill_files, scheduled_jobs_file, *generated_files]
    ]

    manifest = {
        "schema_version": AGENT_PORTABLE_PACKAGE_SCHEMA_VERSION,
        "package_type": AGENT_PORTABLE_PACKAGE_TYPE,
        "exported_at": exported_at.isoformat(),
        "source": {
            "product": "ClawPilot",
            "version": os.getenv("OPENCLAW_OPS_VERSION", "0.1.0"),
            "workspace_root": str(workspace_root),
        },
        "agent": {
            "agent_id": agent.get("agent_id"),
            "display_name": agent.get("display_name"),
            "role": agent.get("role"),
            "channel": agent.get("channel"),
        },
        "includes": {
            "docs": [item["name"] for item in doc_files],
            "skills": [item["name"] for item in skill_summaries],
            "scheduled_jobs": [item["id"] for item in serialized_jobs],
        },
        "missing_files": missing_docs,
        "warnings": warnings,
        "files": file_inventory,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    generated_files.append(
        {
            "name": "manifest.json",
            "package_path": "manifest.json",
            "payload": manifest_bytes,
            "size": len(manifest_bytes),
            "sha256": _sha256_bytes(manifest_bytes),
        }
    )

    total_files = len(doc_files) + len(skill_files) + len(generated_files) + 1
    total_bytes = (
        sum(item["size"] for item in doc_files)
        + sum(item["size"] for item in skill_files)
        + sum(item["size"] for item in generated_files)
        + scheduled_jobs_file["size"]
    )

    return {
        "agent": agent,
        "exported_at": exported_at,
        "package_name": _build_agent_portable_package_filename(str(agent["agent_id"]), exported_at),
        "doc_files": doc_files,
        "skill_files": skill_files,
        "skill_summaries": skill_summaries,
        "scheduled_jobs_file": scheduled_jobs_file,
        "scheduled_jobs": serialized_jobs,
        "missing_docs": missing_docs,
        "warnings": warnings,
        "generated_files": generated_files,
        "total_files": total_files,
        "total_bytes": total_bytes,
    }


def preview_agent_portable_package(agent_id: str) -> dict[str, Any]:
    context = _collect_agent_portable_package_context(agent_id)
    agent = context["agent"]
    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "package_name": context["package_name"],
        "docs": [
            {
                "name": item["name"],
                "package_path": item["package_path"],
                "size": item["size"],
                "sha256": item["sha256"],
            }
            for item in context["doc_files"]
        ],
        "skills": context["skill_summaries"],
        "scheduled_jobs": context["scheduled_jobs"],
        "missing_docs": context["missing_docs"],
        "warnings": context["warnings"],
        "total_files": context["total_files"],
        "total_bytes": context["total_bytes"],
        "docs_count": len(context["doc_files"]),
        "skill_count": len(context["skill_summaries"]),
        "scheduled_job_count": len(context["scheduled_jobs"]),
    }


def build_agent_portable_package_zip(agent_id: str) -> tuple[str, bytes]:
    context = _collect_agent_portable_package_context(agent_id)
    with tempfile.TemporaryDirectory(prefix="agent-portable-package-") as temp_dir:
        stage_root = Path(temp_dir)
        for item in [
            *context["doc_files"],
            *context["skill_files"],
            context["scheduled_jobs_file"],
            *context["generated_files"],
        ]:
            target = stage_root / item["package_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item["payload"])

        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in _iter_directory_files(stage_root):
                archive.write(file_path, arcname=file_path.relative_to(stage_root).as_posix())

        return context["package_name"], archive_buffer.getvalue()


def _extract_skill_archive(
    archive: zipfile.ZipFile,
    *,
    members: list[zipfile.ZipInfo],
    destination: Path,
    strip_prefix: str | None = None,
) -> int:
    extracted = 0
    for info in members:
        original_name = info.filename.replace("\\", "/").strip("/")
        relative_name = original_name
        if strip_prefix:
            if original_name == strip_prefix:
                continue
            prefix = f"{strip_prefix}/"
            if not original_name.startswith(prefix):
                continue
            relative_name = original_name[len(prefix) :]
        try:
            normalized = _normalize_archive_relative_path(relative_name)
        except ValueError:
            continue
        target_path = _ensure_child_path(destination, normalized, _workspace_shared_allowed_roots())
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info, "r") as source, target_path.open("wb") as handle:
            shutil.copyfileobj(source, handle)
        extracted += 1
    return extracted


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:10]}"


def generate_onboarding_job_id() -> str:
    return f"onb_{uuid.uuid4().hex[:10]}"


def generate_onboarding_run_id() -> str:
    return f"onbr_{uuid.uuid4().hex[:10]}"


def generate_training_run_id() -> str:
    return f"tr_{uuid.uuid4().hex[:10]}"


def generate_node_id() -> str:
    return f"node_{uuid.uuid4().hex[:10]}"


def generate_account_id() -> str:
    return f"acct_{uuid.uuid4().hex[:12]}"


def generate_role_id() -> str:
    return f"role_{uuid.uuid4().hex[:12]}"


def _hash_password(raw_password: str) -> tuple[str, str, int]:
    password = str(raw_password or "")
    if len(password) < ACCOUNT_PASSWORD_MIN_LENGTH:
        raise ValueError("password_too_short")
    if len(password) > ACCOUNT_PASSWORD_MAX_LENGTH:
        raise ValueError("password_too_long")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ACCOUNT_PASSWORD_ITERATIONS)
    return digest.hex(), salt.hex(), ACCOUNT_PASSWORD_ITERATIONS


def _verify_password(raw_password: str, password_hash: str, password_salt: str, password_iter: int) -> bool:
    password = str(raw_password or "")
    if not password or not password_hash or not password_salt:
        return False
    try:
        salt = bytes.fromhex(password_salt)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(password_iter))
    return secrets.compare_digest(digest.hex(), str(password_hash))


def _normalize_account_username(value: Any) -> str:
    username = str(value or "").strip().lower()
    if not username:
        raise ValueError("account_username_required")
    if len(username) > 64:
        raise ValueError("account_username_too_long")
    if not re.match(r"^[a-z0-9][a-z0-9_.-]{2,63}$", username):
        raise ValueError("account_username_invalid")
    return username


def _normalize_account_display_name(value: Any) -> str:
    display_name = str(value or "").strip()
    if not display_name:
        raise ValueError("account_display_name_required")
    if len(display_name) > 64:
        raise ValueError("account_display_name_too_long")
    return display_name


def _normalize_account_email(value: Any) -> str | None:
    email = str(value or "").strip().lower()
    if not email:
        return None
    if len(email) > 128:
        raise ValueError("account_email_too_long")
    return email


def _normalize_role_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    normalized: list[str] = []
    for item in items:
        role_id = str(item or "").strip()
        if not role_id:
            continue
        normalized.append(role_id)
    return list(dict.fromkeys(normalized))


def _normalize_permission_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    normalized: list[str] = []
    for item in items:
        permission_id = str(item or "").strip()
        if not permission_id:
            continue
        normalized.append(permission_id)
    return list(dict.fromkeys(normalized))


def _normalize_role_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("role_name_required")
    if len(name) > 64:
        raise ValueError("role_name_too_long")
    return name


def _normalize_role_description(value: Any) -> str | None:
    description = str(value or "").strip()
    if not description:
        return None
    if len(description) > 255:
        raise ValueError("role_description_too_long")
    return description


def _normalize_agent_scene_preset_id(value: Any) -> str:
    preset_id = str(value or "").strip()
    if not preset_id:
        raise ValueError("scene_preset_id_required")
    if preset_id not in AGENT_SCENE_PRESET_IDS:
        raise ValueError("scene_preset_id_invalid")
    return preset_id


def _path_cache_version(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return f"{path}:missing"
    kind = "dir" if path.is_dir() else "file"
    return f"{path.resolve()}:{kind}:{stat.st_mtime_ns}:{stat.st_size}"


def _paths_cache_version(paths: Iterable[Path]) -> str:
    chunks: list[str] = []
    for path in sorted({item.resolve() for item in paths}, key=lambda item: item.as_posix()):
        try:
            stat = path.stat()
        except OSError:
            continue
        kind = "dir" if path.is_dir() else "file"
        chunks.append(f"{path.as_posix()}:{kind}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(chunks) or "empty"

@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def _migrate_agents_table_drop_derived_columns(conn: sqlite3.Connection) -> None:
    """Migrate agents table: drop channel, account_id, workspace_path, identity_complete columns."""
    try:
        row = conn.execute("PRAGMA table_info(agents)").fetchall()
    except Exception:
        return
    col_names = {str(r["name"]) for r in row}
    if "channel" not in col_names:
        return
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        CREATE TABLE IF NOT EXISTS agents_new (
            agent_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','probation','suspended')),
            open_id TEXT,
            scene_preset_id TEXT,
            created_at TEXT NOT NULL
        );
        INSERT OR IGNORE INTO agents_new (agent_id, display_name, role, status, open_id, scene_preset_id, created_at)
            SELECT agent_id, display_name, role, status, open_id, NULL, created_at FROM agents;
        DROP TABLE agents;
        ALTER TABLE agents_new RENAME TO agents;
        PRAGMA foreign_keys = ON;
        """
    )


def _ensure_agents_scene_preset_column(conn: sqlite3.Connection) -> None:
    try:
        row = conn.execute("PRAGMA table_info(agents)").fetchall()
    except Exception:
        return
    if not row:
        return
    col_names = {str(r["name"]) for r in row}
    if "scene_preset_id" not in col_names:
        conn.execute("ALTER TABLE agents ADD COLUMN scene_preset_id TEXT")


def _ensure_rescue_center_thread_runtime_columns(conn: sqlite3.Connection) -> None:
    try:
        row = conn.execute("PRAGMA table_info(rescue_center_threads)").fetchall()
    except Exception:
        return
    if not row:
        return
    col_names = {str(r["name"]) for r in row}
    if "runtime_status" not in col_names:
        conn.execute(
            "ALTER TABLE rescue_center_threads ADD COLUMN runtime_status TEXT NOT NULL DEFAULT 'idle'"
        )
    if "runtime_turn_id" not in col_names:
        conn.execute(
            "ALTER TABLE rescue_center_threads ADD COLUMN runtime_turn_id TEXT"
        )
    if "last_event_at" not in col_names:
        conn.execute(
            "ALTER TABLE rescue_center_threads ADD COLUMN last_event_at TEXT"
        )
    if "recovery_state" not in col_names:
        conn.execute(
            "ALTER TABLE rescue_center_threads ADD COLUMN recovery_state TEXT NOT NULL DEFAULT 'none'"
        )


def init_db() -> None:
    with get_conn() as conn:
        from . import lobster_toolkit

        _migrate_agents_table_drop_derived_columns(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active','probation','suspended')),
                open_id TEXT,
                scene_preset_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                creator_type TEXT NOT NULL CHECK(creator_type IN ('human','agent')),
                creator_id TEXT NOT NULL,
                assignee_agent_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('todo','doing','review','done','rejected')),
                priority TEXT NOT NULL CHECK(priority IN ('low','medium','high','urgent')),
                expected_output TEXT NOT NULL,
                acceptance_criteria TEXT NOT NULL,
                deadline_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (assignee_agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            );

            CREATE TABLE IF NOT EXISTS score_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                delta_points INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS onboarding_jobs (
                job_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                role_summary TEXT NOT NULL,
                creator_type TEXT NOT NULL CHECK(creator_type IN ('human','agent')),
                creator_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','confirmed','failed')),
                trigger_training INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS agent_onboarding_runs (
                run_id TEXT PRIMARY KEY,
                owner_agent_id TEXT NOT NULL,
                target_agent_id TEXT NOT NULL,
                target_agent_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('draft','running','paused','partial','completed','failed')),
                pending_restart INTEGER NOT NULL DEFAULT 0,
                request_json TEXT,
                warnings_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (owner_agent_id) REFERENCES agents(agent_id),
                FOREIGN KEY (target_agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS agent_onboarding_run_steps (
                run_id TEXT NOT NULL,
                step_key TEXT NOT NULL,
                label TEXT NOT NULL,
                order_index INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('todo','running','done','warn','failed','skipped')),
                result_summary TEXT,
                result_payload_json TEXT,
                started_at TEXT,
                finished_at TEXT,
                PRIMARY KEY (run_id, step_key),
                FOREIGN KEY (run_id) REFERENCES agent_onboarding_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS training_runs (
                run_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                onboarding_job_id TEXT,
                phase TEXT NOT NULL CHECK(phase IN ('exam','observe','gate')),
                status TEXT NOT NULL CHECK(status IN ('planned','running','passed','failed')),
                score INTEGER,
                result TEXT CHECK(result IN ('GRADUATE','REMEDIATE')),
                report_url TEXT,
                observe_days INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
                FOREIGN KEY (onboarding_job_id) REFERENCES onboarding_jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS training_module_settings (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                coach_agent_id TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                skill_source_path TEXT NOT NULL,
                skill_target_path TEXT NOT NULL,
                configured_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (coach_agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS training_run_contexts (
                run_id TEXT PRIMARY KEY,
                coach_agent_id TEXT NOT NULL,
                status_doc_path TEXT NOT NULL,
                profile_doc_path TEXT NOT NULL,
                run_doc_path TEXT NOT NULL,
                observation_job_id TEXT,
                orchestration_state TEXT NOT NULL DEFAULT 'planned'
                    CHECK(orchestration_state IN ('planned','coach_prompted','observing','completed','failed')),
                orchestration_error TEXT,
                coach_prompt TEXT,
                generated_at TEXT,
                dispatched_at TEXT,
                observation_created_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES training_runs(run_id),
                FOREIGN KEY (coach_agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS system_settings (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                currency_preference TEXT NOT NULL CHECK(currency_preference IN ('CNY','USD')),
                usd_cny_rate REAL NOT NULL,
                rate_source TEXT NOT NULL CHECK(rate_source IN ('frankfurter','ecb','fixed')),
                rate_updated_at TEXT,
                rate_checked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS system_status_aliases (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                working_alias TEXT,
                idle_alias TEXT,
                offline_alias TEXT,
                crashed_alias TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gateway_settings (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                mode_preference TEXT NOT NULL
                    CHECK(mode_preference IN ('auto','existing-proxy','caddy','public-port')),
                domain TEXT,
                ssl_email TEXT,
                public_host_ip TEXT,
                public_web_port INTEGER NOT NULL DEFAULT 13000,
                auto_https INTEGER NOT NULL DEFAULT 1 CHECK(auto_https IN (0,1)),
                status TEXT NOT NULL DEFAULT 'idle'
                    CHECK(status IN ('idle','saved','error')),
                access_url TEXT,
                last_error TEXT,
                verified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_user_auth (
                agent_id TEXT NOT NULL,
                user_key TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                scope TEXT,
                user_name TEXT,
                user_open_id TEXT,
                user_union_id TEXT,
                authorized_at TEXT NOT NULL,
                expires_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (agent_id, user_key),
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS agent_user_oauth_states (
                state TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                user_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                node_type TEXT NOT NULL CHECK(node_type IN ('vps','linux','macos')),
                expected_openclaw_root TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                token_last4 TEXT NOT NULL,
                hostname TEXT,
                platform TEXT,
                connector_version TEXT,
                reported_openclaw_root TEXT,
                activated_at TEXT,
                last_seen_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS node_sync_jobs (
                sync_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                resource_key TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                operation_kind TEXT NOT NULL CHECK(operation_kind IN ('write_text_file','upsert_json_value')),
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','applied')),
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                last_attempt_at TEXT,
                applied_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(node_id, source_kind, source_id, resource_key),
                FOREIGN KEY (node_id) REFERENCES nodes(node_id)
            );

            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                email TEXT,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_iter INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active','disabled')),
                must_change_password INTEGER NOT NULL DEFAULT 1,
                force_logout_at TEXT,
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS roles (
                role_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                is_system INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS permissions (
                permission_id TEXT PRIMARY KEY,
                module_key TEXT NOT NULL,
                module_label TEXT NOT NULL,
                action_key TEXT NOT NULL,
                action_label TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(module_key, action_key)
            );

            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id TEXT NOT NULL,
                permission_id TEXT NOT NULL,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE,
                FOREIGN KEY (permission_id) REFERENCES permissions(permission_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS account_roles (
                account_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                PRIMARY KEY (account_id, role_id),
                FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS account_manual_permissions (
                account_id TEXT NOT NULL,
                permission_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (account_id, permission_id),
                FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
                FOREIGN KEY (permission_id) REFERENCES permissions(permission_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_account_manual_permissions_account
            ON account_manual_permissions(account_id);

            CREATE TABLE IF NOT EXISTS account_sessions (
                session_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                last_seen_at TEXT,
                FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS account_bootstrap (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                username TEXT NOT NULL,
                temp_password TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revealed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                audit_id TEXT PRIMARY KEY,
                actor_account_id TEXT,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                detail_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (actor_account_id) REFERENCES accounts(account_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS diagnostic_logs (
                diagnostic_id TEXT PRIMARY KEY,
                actor_account_id TEXT,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                event TEXT NOT NULL,
                level TEXT NOT NULL,
                trace_id TEXT,
                request_path TEXT,
                detail_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (actor_account_id) REFERENCES accounts(account_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS rescue_center_threads (
                account_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                thread_name TEXT,
                preview TEXT,
                message_count INTEGER NOT NULL DEFAULT 0,
                thread_status TEXT NOT NULL DEFAULT 'idle'
                    CHECK(thread_status IN ('idle','active','archived','failed','blocked')),
                codex_path TEXT,
                codex_version TEXT,
                cwd TEXT NOT NULL,
                last_error_code TEXT,
                last_error_message TEXT,
                runtime_status TEXT NOT NULL DEFAULT 'idle',
                runtime_turn_id TEXT,
                last_event_at TEXT,
                recovery_state TEXT NOT NULL DEFAULT 'none',
                last_message_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (account_id, thread_id),
                FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
            );
            """
        )
        _ensure_agents_scene_preset_column(conn)
        _ensure_rescue_center_thread_runtime_columns(conn)
        _ensure_system_settings_row(conn)
        _ensure_system_status_aliases_row(conn)
        _ensure_gateway_settings_row(conn)
        lobster_toolkit.ensure_schema(conn)
        _ensure_default_roles(conn)
        _ensure_default_permissions(conn)
        _ensure_bootstrap_owner(conn)
        conn.commit()


def _ensure_default_roles(conn: sqlite3.Connection) -> None:
    now = now_iso()
    existing = {row["role_id"] for row in conn.execute("SELECT role_id FROM roles").fetchall()}
    for role in DEFAULT_ROLES:
        if role["role_id"] in existing:
            continue
        conn.execute(
            """
            INSERT INTO roles (role_id, name, description, is_system, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                role["role_id"],
                role["name"],
                role.get("description"),
                int(role.get("is_system") or 0),
                now,
                now,
            ),
        )


def _ensure_default_permissions(conn: sqlite3.Connection) -> None:
    now = now_iso()
    existing = {
        row["permission_id"] for row in conn.execute("SELECT permission_id FROM permissions").fetchall()
    }
    for item in DEFAULT_PERMISSION_CATALOG:
        permission_id = f"{item['module_key']}.{item['action_key']}"
        if permission_id in existing:
            continue
        conn.execute(
            """
            INSERT INTO permissions (
                permission_id, module_key, module_label, action_key, action_label, description, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                permission_id,
                item["module_key"],
                item["module_label"],
                item["action_key"],
                item["action_label"],
                item.get("description"),
                now,
            ),
        )
        conn.execute(
            """
            UPDATE permissions
            SET module_label = ?, action_label = ?, description = ?
            WHERE permission_id = ?
            """,
            (
                item["module_label"],
                item["action_label"],
                item.get("description"),
                permission_id,
            ),
        )

    # Ensure default role-permission mapping
    permission_ids = {
        row["permission_id"] for row in conn.execute("SELECT permission_id FROM permissions").fetchall()
    }
    for role_id, perm_list in DEFAULT_ROLE_PERMISSIONS.items():
        if role_id not in {row["role_id"] for row in conn.execute("SELECT role_id FROM roles").fetchall()}:
            continue
        if "*" in perm_list:
            target_perms = permission_ids
        else:
            target_perms = {perm for perm in perm_list if perm in permission_ids}
        for perm in target_perms:
            conn.execute(
                """
                INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
                VALUES (?, ?)
                """,
                (role_id, perm),
            )


def _ensure_bootstrap_owner(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT account_id FROM accounts LIMIT 1").fetchone()
    if existing:
        return
    now = now_iso()
    temp_password = f"{ACCOUNT_BOOTSTRAP_PASSWORD_PREFIX}{uuid.uuid4()}"
    password_hash, password_salt, password_iter = _hash_password(temp_password)
    account_id = generate_account_id()
    conn.execute(
        """
        INSERT INTO accounts (
            account_id, username, display_name, email, password_hash, password_salt, password_iter,
            status, must_change_password, force_logout_at, last_login_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            ACCOUNT_BOOTSTRAP_USERNAME,
            "OpenClaw 管理员",
            None,
            password_hash,
            password_salt,
            password_iter,
            "active",
            1,
            None,
            None,
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO account_roles (account_id, role_id)
        VALUES (?, 'owner')
        """,
        (account_id,),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO account_bootstrap (singleton, username, temp_password, created_at, revealed_at)
        VALUES (1, ?, ?, ?, NULL)
        """,
        (ACCOUNT_BOOTSTRAP_USERNAME, temp_password, now),
    )


def _get_system_settings_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM system_settings WHERE singleton = 1").fetchone()


def _get_system_status_aliases_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM system_status_aliases WHERE singleton = 1").fetchone()


def _get_gateway_settings_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM gateway_settings WHERE singleton = 1").fetchone()


def _serialize_system_settings_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "currency_preference": str(payload.get("currency_preference") or SYSTEM_SETTINGS_DEFAULT_CURRENCY),
        "exchange_rate_usd_cny": float(payload.get("usd_cny_rate") or SYSTEM_SETTINGS_DEFAULT_USD_CNY_RATE),
        "exchange_rate_source": str(payload.get("rate_source") or "fixed"),
        "exchange_rate_updated_at": payload.get("rate_updated_at"),
        "exchange_rate_checked_at": payload.get("rate_checked_at"),
        "updated_at": payload.get("updated_at"),
    }


def _serialize_system_status_aliases_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "working": _clean_remote_value(payload.get("working_alias")),
        "idle": _clean_remote_value(payload.get("idle_alias")),
        "offline": _clean_remote_value(payload.get("offline_alias")),
        "crashed": _clean_remote_value(payload.get("crashed_alias")),
    }


def _serialize_gateway_settings_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    inferred_public_host_ip, inferred_public_web_port = _infer_gateway_public_entry_from_base_url()
    return {
        "mode_preference": str(payload.get("mode_preference") or "auto"),
        "domain": _clean_remote_value(payload.get("domain")),
        "ssl_email": _clean_remote_value(payload.get("ssl_email")),
        "public_host_ip": _clean_remote_value(payload.get("public_host_ip")) or inferred_public_host_ip,
        "public_web_port": int(payload.get("public_web_port") or inferred_public_web_port or 13000),
        "auto_https": bool(payload.get("auto_https")) if payload.get("auto_https") is not None else True,
        "status": str(payload.get("status") or "idle"),
        "access_url": _clean_remote_value(payload.get("access_url")),
        "last_error": _clean_remote_value(payload.get("last_error")),
        "verified_at": _clean_remote_value(payload.get("verified_at")),
        "updated_at": _clean_remote_value(payload.get("updated_at")),
    }


def _ensure_system_settings_row(conn: sqlite3.Connection) -> None:
    existing = _get_system_settings_row(conn)
    if existing:
        return
    now = now_iso()
    conn.execute(
        """
        INSERT INTO system_settings (
            singleton,
            currency_preference,
            usd_cny_rate,
            rate_source,
            rate_updated_at,
            rate_checked_at,
            created_at,
            updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SYSTEM_SETTINGS_DEFAULT_CURRENCY,
            SYSTEM_SETTINGS_DEFAULT_USD_CNY_RATE,
            "fixed",
            now,
            now,
            now,
            now,
        ),
    )


def _ensure_system_status_aliases_row(conn: sqlite3.Connection) -> None:
    existing = _get_system_status_aliases_row(conn)
    if existing:
        return
    now = now_iso()
    conn.execute(
        """
        INSERT INTO system_status_aliases (
            singleton,
            working_alias,
            idle_alias,
            offline_alias,
            crashed_alias,
            created_at,
            updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?)
        """,
        (None, None, None, None, now, now),
    )


def _ensure_gateway_settings_row(conn: sqlite3.Connection) -> None:
    existing = _get_gateway_settings_row(conn)
    if existing:
        return
    now = now_iso()
    conn.execute(
        """
        INSERT INTO gateway_settings (
            singleton,
            mode_preference,
            domain,
            ssl_email,
            public_host_ip,
            public_web_port,
            auto_https,
            status,
            access_url,
            last_error,
            verified_at,
            created_at,
            updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("auto", None, None, None, 13000, 1, "idle", None, None, None, now, now),
    )


def _normalize_gateway_mode_preference(value: Any) -> str:
    normalized = str(value or "").strip().lower() or "auto"
    if normalized not in {"auto", "existing-proxy", "caddy", "public-port"}:
        raise ValueError("gateway_mode_invalid")
    return normalized


def _normalize_gateway_domain(value: Any) -> str | None:
    domain = _clean_remote_value(value)
    if not domain:
        return None
    if len(domain) > 255:
        raise ValueError("gateway_domain_too_long")
    return domain.lower()


def _normalize_gateway_ssl_email(value: Any) -> str | None:
    email = _clean_remote_value(value)
    if not email:
        return None
    if len(email) > 255:
        raise ValueError("gateway_ssl_email_too_long")
    if "@" not in email:
        raise ValueError("gateway_ssl_email_invalid")
    return email


def _normalize_gateway_public_host_ip(value: Any) -> str | None:
    host_ip = _clean_remote_value(value)
    if not host_ip:
        return None
    if len(host_ip) > 255:
        raise ValueError("gateway_public_host_ip_too_long")
    return host_ip


def _normalize_gateway_public_web_port(value: Any) -> int:
    raw_value = str(value or "").strip() or "13000"
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError("gateway_public_web_port_invalid") from exc
    if port < 1 or port > 65535:
        raise ValueError("gateway_public_web_port_invalid")
    return port


def _infer_gateway_public_entry_from_base_url() -> tuple[str | None, int | None]:
    candidate_url = str(OPENCLAW_PUBLIC_BASE_URL or "").strip()
    if not candidate_url:
        return None, None
    try:
        parsed = urlparse(candidate_url)
    except ValueError:
        return None, None
    host = str(parsed.hostname or "").strip()
    if not host:
        return None, None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None, None
    if parsed.port is not None:
        return host, int(parsed.port)
    if parsed.scheme == "http":
        return host, 80
    if parsed.scheme == "https":
        return host, 443
    return host, None


def _build_gateway_access_url(
    *,
    domain: str | None,
    auto_https: bool,
    public_host_ip: str | None,
    public_web_port: int,
) -> str | None:
    if domain:
        scheme = "https" if auto_https else "http"
        return f"{scheme}://{domain}"
    if public_host_ip:
        return f"http://{public_host_ip}:{public_web_port}"
    if OPENCLAW_PUBLIC_BASE_URL:
        return OPENCLAW_PUBLIC_BASE_URL
    return None


def _is_exchange_rate_stale(value: str | None) -> bool:
    if not value:
        return True
    try:
        parsed = _parse_iso_utc(value, "exchange_rate_checked_at")
    except ValueError:
        return True
    if not parsed:
        return True
    return datetime.now(timezone.utc) - parsed >= timedelta(days=SYSTEM_SETTINGS_RATE_REFRESH_DAYS)


def _fetch_frankfurter_usd_cny() -> tuple[float | None, str | None]:
    payload = _http_json(SYSTEM_SETTINGS_FRANKFURTER_URL, timeout=8)
    if not payload:
        return None, None
    rates = payload.get("rates") if isinstance(payload, dict) else None
    if not isinstance(rates, dict):
        return None, None
    rate_value = rates.get("CNY")
    if rate_value is None:
        return None, None
    try:
        rate = float(rate_value)
    except (TypeError, ValueError):
        return None, None
    rate_date = str(payload.get("date") or "").strip() or None
    return rate, rate_date


def _fetch_ecb_usd_cny() -> tuple[float | None, str | None]:
    try:
        with urlopen(SYSTEM_SETTINGS_ECB_URL, timeout=8) as resp:
            raw = resp.read()
    except (URLError, TimeoutError, ValueError):
        return None, None
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None, None
    rates: dict[str, float] = {}
    for cube in root.findall(".//{*}Cube[@currency]"):
        currency = cube.attrib.get("currency")
        rate_str = cube.attrib.get("rate")
        if not currency or not rate_str:
            continue
        try:
            rates[currency] = float(rate_str)
        except ValueError:
            continue
    usd_rate = rates.get("USD")
    cny_rate = rates.get("CNY")
    if not usd_rate or not cny_rate:
        return None, None
    rate = cny_rate / usd_rate
    rate_date = None
    time_node = root.find(".//{*}Cube[@time]")
    if time_node is not None:
        rate_date = time_node.attrib.get("time")
    return rate, rate_date


def _build_system_settings_payload(
    conn: sqlite3.Connection,
    *,
    settings_row: sqlite3.Row | dict[str, Any] | None = None,
    aliases_row: sqlite3.Row | dict[str, Any] | None = None,
    gateway_row: sqlite3.Row | dict[str, Any] | None = None,
) -> dict[str, Any]:
    if settings_row is None:
        settings_row = _get_system_settings_row(conn)
    if aliases_row is None:
        aliases_row = _get_system_status_aliases_row(conn)
    if gateway_row is None:
        gateway_row = _get_gateway_settings_row(conn)
    settings_payload = _serialize_system_settings_row(settings_row or {})
    aliases_payload = _serialize_system_status_aliases_row(aliases_row or {})
    gateway_payload = _serialize_gateway_settings_row(gateway_row or {})
    settings_payload["status_aliases"] = aliases_payload
    settings_payload["gateway_settings"] = gateway_payload
    return settings_payload


def refresh_exchange_rate_if_due(*, force: bool = False) -> dict[str, Any]:
    with get_conn() as conn:
        _ensure_system_settings_row(conn)
        _ensure_system_status_aliases_row(conn)
        _ensure_gateway_settings_row(conn)
        row = _get_system_settings_row(conn)
        settings = _serialize_system_settings_row(row) if row else None
        if not settings:
            return _build_system_settings_payload(conn)
        if not force and not _is_exchange_rate_stale(settings.get("exchange_rate_checked_at")):
            return _build_system_settings_payload(conn, settings_row=row)

        now = now_iso()
        source = "fixed"
        rate = SYSTEM_SETTINGS_DEFAULT_USD_CNY_RATE
        updated_at = now
        rate_checked_at = now

        frankfurter_rate, frankfurter_date = _fetch_frankfurter_usd_cny()
        if frankfurter_rate is not None:
            source = "frankfurter"
            rate = frankfurter_rate
            updated_at = frankfurter_date or now
        else:
            ecb_rate, ecb_date = _fetch_ecb_usd_cny()
            if ecb_rate is not None:
                source = "ecb"
                rate = ecb_rate
                updated_at = ecb_date or now

        conn.execute(
            """
            UPDATE system_settings
            SET usd_cny_rate = ?,
                rate_source = ?,
                rate_updated_at = ?,
                rate_checked_at = ?,
                updated_at = ?
            WHERE singleton = 1
            """,
            (
                float(rate),
                source,
                updated_at,
                rate_checked_at,
                now,
            ),
        )
        conn.commit()
        row = _get_system_settings_row(conn)
        return _build_system_settings_payload(conn, settings_row=row)


def get_system_settings() -> dict[str, Any]:
    refresh_exchange_rate_if_due(force=False)
    with get_conn() as conn:
        _ensure_system_settings_row(conn)
        _ensure_system_status_aliases_row(conn)
        _ensure_gateway_settings_row(conn)
        row = _get_system_settings_row(conn)
        alias_row = _get_system_status_aliases_row(conn)
        gateway_row = _get_gateway_settings_row(conn)
    return _build_system_settings_payload(conn, settings_row=row, aliases_row=alias_row, gateway_row=gateway_row)


def update_system_currency(payload: dict[str, Any]) -> dict[str, Any]:
    currency = str(payload.get("currency_preference") or "").strip().upper()
    if currency not in {"CNY", "USD"}:
        raise ValueError("currency_preference_invalid")
    now = now_iso()
    with get_conn() as conn:
        _ensure_system_settings_row(conn)
        _ensure_system_status_aliases_row(conn)
        _ensure_gateway_settings_row(conn)
        conn.execute(
            """
            UPDATE system_settings
            SET currency_preference = ?,
                updated_at = ?
            WHERE singleton = 1
            """,
            (currency, now),
        )
        conn.commit()
        row = _get_system_settings_row(conn)
        alias_row = _get_system_status_aliases_row(conn)
        gateway_row = _get_gateway_settings_row(conn)
    return _build_system_settings_payload(conn, settings_row=row, aliases_row=alias_row, gateway_row=gateway_row)


def update_system_status_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    with get_conn() as conn:
        _ensure_system_settings_row(conn)
        _ensure_system_status_aliases_row(conn)
        _ensure_gateway_settings_row(conn)
        row = _get_system_status_aliases_row(conn)
        current = _serialize_system_status_aliases_row(row or {})

        def next_value(key: str) -> str | None:
            if key not in payload:
                return current.get(key)
            raw = payload.get(key)
            cleaned = _clean_remote_value(raw)
            return cleaned

        working = next_value("working")
        idle = next_value("idle")
        offline = next_value("offline")
        crashed = next_value("crashed")

        conn.execute(
            """
            UPDATE system_status_aliases
            SET working_alias = ?,
                idle_alias = ?,
                offline_alias = ?,
                crashed_alias = ?,
                updated_at = ?
            WHERE singleton = 1
            """,
            (working, idle, offline, crashed, now),
        )
        conn.commit()
        settings_row = _get_system_settings_row(conn)
        alias_row = _get_system_status_aliases_row(conn)
        gateway_row = _get_gateway_settings_row(conn)
    return _build_system_settings_payload(conn, settings_row=settings_row, aliases_row=alias_row, gateway_row=gateway_row)


def get_gateway_settings() -> dict[str, Any]:
    with get_conn() as conn:
        _ensure_gateway_settings_row(conn)
        row = _get_gateway_settings_row(conn)
    return _serialize_gateway_settings_row(row or {})


def update_gateway_settings(payload: dict[str, Any]) -> dict[str, Any]:
    mode_preference = _normalize_gateway_mode_preference(payload.get("mode_preference"))
    domain = _normalize_gateway_domain(payload.get("domain"))
    ssl_email = _normalize_gateway_ssl_email(payload.get("ssl_email"))
    public_host_ip = _normalize_gateway_public_host_ip(payload.get("public_host_ip"))
    public_web_port = _normalize_gateway_public_web_port(payload.get("public_web_port"))
    auto_https = bool(payload.get("auto_https", True))
    access_url = _build_gateway_access_url(
        domain=domain,
        auto_https=auto_https,
        public_host_ip=public_host_ip,
        public_web_port=public_web_port,
    )
    status = "saved" if access_url else "idle"
    now = now_iso()

    with get_conn() as conn:
        _ensure_gateway_settings_row(conn)
        conn.execute(
            """
            UPDATE gateway_settings
            SET mode_preference = ?,
                domain = ?,
                ssl_email = ?,
                public_host_ip = ?,
                public_web_port = ?,
                auto_https = ?,
                status = ?,
                access_url = ?,
                last_error = NULL,
                updated_at = ?
            WHERE singleton = 1
            """,
            (
                mode_preference,
                domain,
                ssl_email,
                public_host_ip,
                int(public_web_port),
                1 if auto_https else 0,
                status,
                access_url,
                now,
            ),
        )
        conn.commit()
        row = _get_gateway_settings_row(conn)
    return _serialize_gateway_settings_row(row or {})


def record_gateway_execution_result(
    *,
    status: str,
    access_url: str | None = None,
    last_error: str | None = None,
    verified_at: str | None = None,
) -> dict[str, Any]:
    normalized_status = str(status or "error").strip().lower() or "error"
    if normalized_status not in {"idle", "saved", "error"}:
        normalized_status = "error"
    now = now_iso()
    with get_conn() as conn:
        _ensure_gateway_settings_row(conn)
        current = _serialize_gateway_settings_row(_get_gateway_settings_row(conn) or {})
        conn.execute(
            """
            UPDATE gateway_settings
            SET status = ?,
                access_url = ?,
                last_error = ?,
                verified_at = ?,
                updated_at = ?
            WHERE singleton = 1
            """,
            (
                normalized_status,
                access_url if access_url is not None else current.get("access_url"),
                last_error,
                verified_at,
                now,
            ),
        )
        conn.commit()
        row = _get_gateway_settings_row(conn)
    return _serialize_gateway_settings_row(row or {})


def _serialize_account_row(row: sqlite3.Row | dict[str, Any], roles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = dict(row)
    return {
        "account_id": payload["account_id"],
        "username": payload["username"],
        "display_name": payload["display_name"],
        "email": payload.get("email"),
        "status": payload["status"],
        "must_change_password": bool(payload.get("must_change_password")),
        "force_logout_at": payload.get("force_logout_at"),
        "last_login_at": payload.get("last_login_at"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "roles": roles or [],
    }


def _serialize_role_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "role_id": payload["role_id"],
        "name": payload["name"],
        "description": payload.get("description"),
        "is_system": bool(payload.get("is_system")),
        "permission_count": int(payload.get("permission_count") or 0),
        "member_count": int(payload.get("member_count") or 0),
    }


def _serialize_permission_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "permission_id": payload["permission_id"],
        "module_key": payload["module_key"],
        "module_label": payload["module_label"],
        "action_key": payload["action_key"],
        "action_label": payload["action_label"],
        "description": payload.get("description"),
    }


def _serialize_audit_log_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    try:
        detail = json.loads(payload.get("detail_json") or "{}")
    except Exception:
        detail = {}
    return {
        "audit_id": payload["audit_id"],
        "actor_account_id": payload.get("actor_account_id"),
        "action": payload["action"],
        "target_type": payload["target_type"],
        "target_id": payload.get("target_id"),
        "detail": detail,
        "created_at": payload["created_at"],
    }


def _serialize_diagnostic_log_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    try:
        detail = json.loads(payload.get("detail_json") or "{}")
    except Exception:
        detail = {}
    source = str(payload.get("source") or "server")
    if source not in {"client", "server"}:
        source = "server"
    level = str(payload.get("level") or "info")
    if level not in {"info", "warn", "error"}:
        level = "info"
    return {
        "diagnostic_id": payload["diagnostic_id"],
        "actor_account_id": payload.get("actor_account_id"),
        "source": source,
        "category": payload["category"],
        "event": payload["event"],
        "level": level,
        "trace_id": payload.get("trace_id"),
        "request_path": payload.get("request_path"),
        "detail": detail,
        "created_at": payload["created_at"],
    }


def _account_roles(conn: sqlite3.Connection, account_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.role_id, r.name, r.description, r.is_system
        FROM account_roles ar
        JOIN roles r ON r.role_id = ar.role_id
        WHERE ar.account_id = ?
        ORDER BY r.role_id ASC
        """,
        (account_id,),
    ).fetchall()
    return [_serialize_role_row(row) for row in rows]


def _all_permission_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT permission_id FROM permissions").fetchall()
    return {row["permission_id"] for row in rows}


def _manual_permission_ids(conn: sqlite3.Connection, account_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT permission_id FROM account_manual_permissions WHERE account_id = ?",
        (account_id,),
    ).fetchall()
    return {row["permission_id"] for row in rows}


def _inherited_permission_ids(conn: sqlite3.Connection, role_ids: list[str]) -> set[str]:
    if "owner" in role_ids:
        return _all_permission_ids(conn)
    return _get_permission_ids_for_roles(conn, role_ids)


def _build_account_access_payload(conn: sqlite3.Connection, account_id: str) -> dict[str, Any]:
    account_row = _get_account_by_id(conn, account_id)
    if not account_row:
        raise LookupError("account_not_found")
    role_ids = _get_role_ids(conn, account_id)
    roles = _account_roles(conn, account_id)
    inherited_permission_ids = _inherited_permission_ids(conn, role_ids)
    all_permission_ids = _all_permission_ids(conn)
    manual_permission_ids = _manual_permission_ids(conn, account_id) - inherited_permission_ids
    effective_permission_ids = inherited_permission_ids | manual_permission_ids
    editable_permission_ids = all_permission_ids - inherited_permission_ids
    return {
        "account": _serialize_account_row(account_row, roles),
        "role_ids": role_ids,
        "roles": roles,
        "inherited_permission_ids": sorted(inherited_permission_ids),
        "manual_permission_ids": sorted(manual_permission_ids),
        "effective_permission_ids": sorted(effective_permission_ids),
        "editable_permission_ids": sorted(editable_permission_ids),
    }


def _record_audit_log(
    conn: sqlite3.Connection,
    *,
    actor_account_id: str | None,
    action: str,
    target_type: str,
    target_id: str | None,
    detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_logs (audit_id, actor_account_id, action, target_type, target_id, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"audit_{uuid.uuid4().hex[:12]}",
            actor_account_id,
            action,
            target_type,
            target_id,
            json.dumps(detail or {}, ensure_ascii=False, sort_keys=True),
            now_iso(),
        ),
    )


def _record_diagnostic_log(
    conn: sqlite3.Connection,
    *,
    actor_account_id: str | None,
    source: str,
    category: str,
    event: str,
    level: str = "info",
    trace_id: str | None = None,
    request_path: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_source = source if source in {"client", "server"} else "server"
    normalized_level = level if level in {"info", "warn", "error"} else "info"
    diagnostic = {
        "diagnostic_id": f"diag_{uuid.uuid4().hex[:12]}",
        "actor_account_id": actor_account_id,
        "source": normalized_source,
        "category": str(category or "").strip() or "general",
        "event": str(event or "").strip() or "unknown",
        "level": normalized_level,
        "trace_id": (str(trace_id or "").strip() or None),
        "request_path": (str(request_path or "").strip() or None),
        "detail": detail or {},
        "created_at": now_iso(),
    }
    conn.execute(
        """
        INSERT INTO diagnostic_logs (
            diagnostic_id, actor_account_id, source, category, event, level,
            trace_id, request_path, detail_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            diagnostic["diagnostic_id"],
            diagnostic["actor_account_id"],
            diagnostic["source"],
            diagnostic["category"],
            diagnostic["event"],
            diagnostic["level"],
            diagnostic["trace_id"],
            diagnostic["request_path"],
            json.dumps(diagnostic["detail"], ensure_ascii=False, sort_keys=True),
            diagnostic["created_at"],
        ),
    )
    return diagnostic


def record_diagnostic_log(
    *,
    actor_account_id: str | None,
    source: str,
    category: str,
    event: str,
    level: str = "info",
    trace_id: str | None = None,
    request_path: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with get_conn() as conn:
        diagnostic = _record_diagnostic_log(
            conn,
            actor_account_id=actor_account_id,
            source=source,
            category=category,
            event=event,
            level=level,
            trace_id=trace_id,
            request_path=request_path,
            detail=detail,
        )
        conn.commit()
        return diagnostic


def _serialize_rescue_center_thread_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = dict(row)
    return {
        "thread_id": str(payload.get("thread_id") or ""),
        "title": str(payload.get("thread_name") or "").strip() or None,
        "preview": str(payload.get("preview") or "").strip() or None,
        "message_count": int(payload.get("message_count") or 0),
        "status": str(payload.get("thread_status") or "idle"),
        "codex_path": str(payload.get("codex_path") or "").strip() or None,
        "codex_version": str(payload.get("codex_version") or "").strip() or None,
        "cwd": str(payload.get("cwd") or "").strip(),
        "last_error_code": str(payload.get("last_error_code") or "").strip() or None,
        "last_error_message": str(payload.get("last_error_message") or "").strip() or None,
        "runtime_status": str(payload.get("runtime_status") or "idle").strip() or "idle",
        "runtime_turn_id": str(payload.get("runtime_turn_id") or "").strip() or None,
        "last_event_at": str(payload.get("last_event_at") or "").strip() or None,
        "recovery_state": str(payload.get("recovery_state") or "none").strip() or "none",
        "last_message_at": str(payload.get("last_message_at") or "").strip() or None,
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
        "is_active": bool(payload.get("is_active")),
    }


def upsert_rescue_center_thread(account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized_account_id = str(account_id or "").strip()
    thread_id = str(payload.get("thread_id") or "").strip()
    if not normalized_account_id:
        raise ValueError("account_id_required")
    if not thread_id:
        raise ValueError("rescue_center_thread_id_required")

    title = str(payload.get("title") or "").strip() or None
    preview = str(payload.get("preview") or "").strip() or None
    message_count = max(0, int(payload.get("message_count") or 0))
    status = str(payload.get("status") or "idle").strip() or "idle"
    if status not in RESCUE_CENTER_THREAD_STATUSES:
        status = "idle"
    cwd = str(payload.get("cwd") or "").strip()
    if not cwd:
        raise ValueError("rescue_center_cwd_required")

    codex_path = str(payload.get("codex_path") or "").strip() or None
    codex_version = str(payload.get("codex_version") or "").strip() or None
    last_error_code = str(payload.get("last_error_code") or "").strip() or None
    last_error_message = str(payload.get("last_error_message") or "").strip() or None
    runtime_status = str(payload.get("runtime_status") or "idle").strip() or "idle"
    if runtime_status not in RESCUE_CENTER_RUNTIME_STATUSES:
        runtime_status = "idle"
    runtime_turn_id = str(payload.get("runtime_turn_id") or "").strip() or None
    last_event_at = str(payload.get("last_event_at") or "").strip() or None
    recovery_state = str(payload.get("recovery_state") or "none").strip() or "none"
    if recovery_state not in RESCUE_CENTER_RECOVERY_STATES:
        recovery_state = "none"
    last_message_at = str(payload.get("last_message_at") or "").strip() or None
    created_at = str(payload.get("created_at") or "").strip() or now_iso()
    updated_at = str(payload.get("updated_at") or "").strip() or now_iso()
    is_active = bool(payload.get("is_active"))

    with get_conn() as conn:
        if is_active:
            conn.execute(
                "UPDATE rescue_center_threads SET is_active = 0 WHERE account_id = ?",
                (normalized_account_id,),
            )
        conn.execute(
            """
            INSERT INTO rescue_center_threads (
                account_id, thread_id, thread_name, preview, message_count, thread_status,
                codex_path, codex_version, cwd, last_error_code, last_error_message,
                runtime_status, runtime_turn_id, last_event_at, recovery_state,
                last_message_at, created_at, updated_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, thread_id) DO UPDATE SET
                thread_name = excluded.thread_name,
                preview = excluded.preview,
                message_count = excluded.message_count,
                thread_status = excluded.thread_status,
                codex_path = excluded.codex_path,
                codex_version = excluded.codex_version,
                cwd = excluded.cwd,
                last_error_code = excluded.last_error_code,
                last_error_message = excluded.last_error_message,
                runtime_status = excluded.runtime_status,
                runtime_turn_id = excluded.runtime_turn_id,
                last_event_at = excluded.last_event_at,
                recovery_state = excluded.recovery_state,
                last_message_at = excluded.last_message_at,
                updated_at = excluded.updated_at,
                is_active = excluded.is_active
            """,
            (
                normalized_account_id,
                thread_id,
                title,
                preview,
                message_count,
                status,
                codex_path,
                codex_version,
                cwd,
                last_error_code,
                last_error_message,
                runtime_status,
                runtime_turn_id,
                last_event_at,
                recovery_state,
                last_message_at,
                created_at,
                updated_at,
                int(is_active),
            ),
        )
        row = conn.execute(
            """
            SELECT *
            FROM rescue_center_threads
            WHERE account_id = ? AND thread_id = ?
            """,
            (normalized_account_id, thread_id),
        ).fetchone()
        conn.commit()
    serialized = _serialize_rescue_center_thread_row(row)
    if not serialized:
        raise RuntimeError("rescue_center_thread_not_found_after_upsert")
    return serialized


def list_rescue_center_thread_records(account_id: str) -> list[dict[str, Any]]:
    normalized_account_id = str(account_id or "").strip()
    if not normalized_account_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM rescue_center_threads
            WHERE account_id = ?
            ORDER BY is_active DESC, COALESCE(last_message_at, updated_at) DESC, created_at DESC
            """,
            (normalized_account_id,),
        ).fetchall()
    return [item for item in (_serialize_rescue_center_thread_row(row) for row in rows) if item]


def get_rescue_center_thread_record(account_id: str, thread_id: str) -> dict[str, Any] | None:
    normalized_account_id = str(account_id or "").strip()
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_account_id or not normalized_thread_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM rescue_center_threads
            WHERE account_id = ? AND thread_id = ?
            """,
            (normalized_account_id, normalized_thread_id),
        ).fetchone()
    return _serialize_rescue_center_thread_row(row)


def get_active_rescue_center_thread_record(account_id: str) -> dict[str, Any] | None:
    normalized_account_id = str(account_id or "").strip()
    if not normalized_account_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM rescue_center_threads
            WHERE account_id = ? AND is_active = 1
            ORDER BY COALESCE(last_message_at, updated_at) DESC
            LIMIT 1
            """,
            (normalized_account_id,),
        ).fetchone()
    return _serialize_rescue_center_thread_row(row)


def mark_rescue_center_thread_error(
    account_id: str,
    thread_id: str,
    *,
    error_code: str | None,
    error_message: str | None,
    status: str = "failed",
    runtime_status: str | None = None,
    runtime_turn_id: str | None | object = _UNSET,
    last_event_at: str | None | object = _UNSET,
    recovery_state: str | None | object = _UNSET,
) -> dict[str, Any] | None:
    normalized_account_id = str(account_id or "").strip()
    normalized_thread_id = str(thread_id or "").strip()
    normalized_status = str(status or "failed").strip() or "failed"
    if normalized_status not in RESCUE_CENTER_THREAD_STATUSES:
        normalized_status = "failed"
    normalized_runtime_status = str(runtime_status or "").strip() or (
        "blocked" if normalized_status == "blocked" else "failed"
    )
    if normalized_runtime_status not in RESCUE_CENTER_RUNTIME_STATUSES:
        normalized_runtime_status = "failed"
    if not normalized_account_id or not normalized_thread_id:
        return None
    updated_at = now_iso()
    set_clauses = [
        "thread_status = ?",
        "last_error_code = ?",
        "last_error_message = ?",
        "runtime_status = ?",
        "updated_at = ?",
    ]
    values: list[Any] = [
        str(normalized_status),
        str(error_code or "").strip() or None,
        str(error_message or "").strip() or None,
        normalized_runtime_status,
        updated_at,
    ]
    if runtime_turn_id is not _UNSET:
        set_clauses.append("runtime_turn_id = ?")
        values.append(str(runtime_turn_id or "").strip() or None)
    if last_event_at is not _UNSET:
        set_clauses.append("last_event_at = ?")
        values.append(str(last_event_at or "").strip() or None)
    if recovery_state is not _UNSET:
        normalized_recovery_state = str(recovery_state or "none").strip() or "none"
        if normalized_recovery_state not in RESCUE_CENTER_RECOVERY_STATES:
            normalized_recovery_state = "none"
        set_clauses.append("recovery_state = ?")
        values.append(normalized_recovery_state)
    with get_conn() as conn:
        conn.execute(
            f"""
            UPDATE rescue_center_threads
            SET {", ".join(set_clauses)}
            WHERE account_id = ? AND thread_id = ?
            """,
            (
                *values,
                normalized_account_id,
                normalized_thread_id,
            ),
        )
        row = conn.execute(
            """
            SELECT *
            FROM rescue_center_threads
            WHERE account_id = ? AND thread_id = ?
            """,
            (normalized_account_id, normalized_thread_id),
        ).fetchone()
        conn.commit()
    return _serialize_rescue_center_thread_row(row)


def update_rescue_center_thread_runtime(
    account_id: str,
    thread_id: str,
    *,
    runtime_status: str | None | object = _UNSET,
    runtime_turn_id: str | None | object = _UNSET,
    last_event_at: str | None | object = _UNSET,
    recovery_state: str | None | object = _UNSET,
    last_error_code: str | None | object = _UNSET,
    last_error_message: str | None | object = _UNSET,
    status: str | None | object = _UNSET,
    is_active: bool | object = _UNSET,
    updated_at: str | None = None,
) -> dict[str, Any] | None:
    normalized_account_id = str(account_id or "").strip()
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_account_id or not normalized_thread_id:
        return None

    set_clauses: list[str] = []
    values: list[Any] = []

    if runtime_status is not _UNSET:
        normalized_runtime_status = str(runtime_status or "idle").strip() or "idle"
        if normalized_runtime_status not in RESCUE_CENTER_RUNTIME_STATUSES:
            normalized_runtime_status = "idle"
        set_clauses.append("runtime_status = ?")
        values.append(normalized_runtime_status)
    if runtime_turn_id is not _UNSET:
        set_clauses.append("runtime_turn_id = ?")
        values.append(str(runtime_turn_id or "").strip() or None)
    if last_event_at is not _UNSET:
        set_clauses.append("last_event_at = ?")
        values.append(str(last_event_at or "").strip() or None)
    if recovery_state is not _UNSET:
        normalized_recovery_state = str(recovery_state or "none").strip() or "none"
        if normalized_recovery_state not in RESCUE_CENTER_RECOVERY_STATES:
            normalized_recovery_state = "none"
        set_clauses.append("recovery_state = ?")
        values.append(normalized_recovery_state)
    if last_error_code is not _UNSET:
        set_clauses.append("last_error_code = ?")
        values.append(str(last_error_code or "").strip() or None)
    if last_error_message is not _UNSET:
        set_clauses.append("last_error_message = ?")
        values.append(str(last_error_message or "").strip() or None)
    if status is not _UNSET:
        normalized_status = str(status or "idle").strip() or "idle"
        if normalized_status not in RESCUE_CENTER_THREAD_STATUSES:
            normalized_status = "idle"
        set_clauses.append("thread_status = ?")
        values.append(normalized_status)
    if is_active is not _UNSET:
        set_clauses.append("is_active = ?")
        values.append(int(bool(is_active)))

    set_clauses.append("updated_at = ?")
    values.append(str(updated_at or "").strip() or now_iso())

    with get_conn() as conn:
        conn.execute(
            f"""
            UPDATE rescue_center_threads
            SET {", ".join(set_clauses)}
            WHERE account_id = ? AND thread_id = ?
            """,
            (
                *values,
                normalized_account_id,
                normalized_thread_id,
            ),
        )
        row = conn.execute(
            """
            SELECT *
            FROM rescue_center_threads
            WHERE account_id = ? AND thread_id = ?
            """,
            (normalized_account_id, normalized_thread_id),
        ).fetchone()
        conn.commit()
    return _serialize_rescue_center_thread_row(row)


def clear_rescue_center_threads(account_id: str) -> int:
    normalized_account_id = str(account_id or "").strip()
    if not normalized_account_id:
        return 0
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM rescue_center_threads WHERE account_id = ?",
            (normalized_account_id,),
        )
        conn.commit()
        return int(cursor.rowcount or 0)


def get_bootstrap_account() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM account_bootstrap WHERE singleton = 1").fetchone()
        if not row:
            return None
        payload = dict(row)
        return {
            "username": payload.get("username"),
            "temp_password": payload.get("temp_password"),
            "created_at": payload.get("created_at"),
            "revealed_at": payload.get("revealed_at"),
        }


def reveal_bootstrap_account() -> dict[str, Any]:
    now = now_iso()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM account_bootstrap WHERE singleton = 1").fetchone()
        if not row:
            raise LookupError("bootstrap_not_found")
        if row["revealed_at"]:
            return {
                "username": row["username"],
                "temp_password": None,
                "created_at": row["created_at"],
                "revealed_at": row["revealed_at"],
            }
        conn.execute("UPDATE account_bootstrap SET revealed_at = ? WHERE singleton = 1", (now,))
        conn.commit()
        return {
            "username": row["username"],
            "temp_password": row["temp_password"],
            "created_at": row["created_at"],
            "revealed_at": now,
        }


def reset_bootstrap_account_password() -> dict[str, Any]:
    now = now_iso()
    temp_password = f"{ACCOUNT_BOOTSTRAP_PASSWORD_PREFIX}{uuid.uuid4()}"
    password_hash, password_salt, password_iter = _hash_password(temp_password)
    with get_conn() as conn:
        bootstrap_row = conn.execute("SELECT * FROM account_bootstrap WHERE singleton = 1").fetchone()
        account_row = conn.execute(
            "SELECT account_id FROM accounts WHERE username = ?",
            (ACCOUNT_BOOTSTRAP_USERNAME,),
        ).fetchone()
        if not account_row:
            raise LookupError("bootstrap_not_found")
        account_id = str(account_row["account_id"])
        conn.execute(
            """
            UPDATE accounts
            SET password_hash = ?, password_salt = ?, password_iter = ?,
                must_change_password = 1,
                force_logout_at = ?,
                updated_at = ?
            WHERE account_id = ?
            """,
            (password_hash, password_salt, password_iter, now, now, account_id),
        )
        conn.execute(
            "UPDATE account_sessions SET revoked_at = ? WHERE account_id = ? AND revoked_at IS NULL",
            (now, account_id),
        )
        created_at = (bootstrap_row["created_at"] if bootstrap_row and bootstrap_row["created_at"] else now)
        conn.execute(
            """
            INSERT OR REPLACE INTO account_bootstrap (singleton, username, temp_password, created_at, revealed_at)
            VALUES (1, ?, ?, ?, NULL)
            """,
            (ACCOUNT_BOOTSTRAP_USERNAME, temp_password, created_at),
        )
        _record_audit_log(
            conn,
            actor_account_id=account_id,
            action="account.bootstrap_reset_password",
            target_type="account",
            target_id=account_id,
            detail={"reset_at": now, "username": ACCOUNT_BOOTSTRAP_USERNAME},
        )
        conn.commit()
        return {
            "username": ACCOUNT_BOOTSTRAP_USERNAME,
            "temp_password": temp_password,
            "created_at": created_at,
            "revealed_at": None,
            "reset_at": now,
        }


def list_accounts() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT account_id, username, display_name, email, status, must_change_password,
                   force_logout_at, last_login_at, created_at, updated_at
            FROM accounts
            ORDER BY created_at DESC
            """
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            roles = _account_roles(conn, row["account_id"])
            items.append(_serialize_account_row(row, roles))
        return items


def list_roles() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                r.role_id,
                r.name,
                r.description,
                r.is_system,
                COUNT(DISTINCT rp.permission_id) AS permission_count,
                COUNT(DISTINCT ar.account_id) AS member_count
            FROM roles r
            LEFT JOIN role_permissions rp ON rp.role_id = r.role_id
            LEFT JOIN account_roles ar ON ar.role_id = r.role_id
            GROUP BY r.role_id, r.name, r.description, r.is_system
            ORDER BY r.is_system DESC, r.name COLLATE NOCASE ASC
            """
        ).fetchall()
        return [_serialize_role_row(row) for row in rows]


def list_permissions() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT permission_id, module_key, module_label, action_key, action_label, description
            FROM permissions
            ORDER BY module_key ASC, action_key ASC
            """
        ).fetchall()
        return [_serialize_permission_row(row) for row in rows]


def list_role_permissions() -> dict[str, list[str]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT role_id, permission_id
            FROM role_permissions
            ORDER BY role_id ASC
            """
        ).fetchall()
        mapping: dict[str, list[str]] = {}
        for row in rows:
            mapping.setdefault(row["role_id"], []).append(row["permission_id"])
        for role_id in list(mapping):
            mapping[role_id] = sorted(set(mapping[role_id]))
        return mapping


def create_role(payload: dict[str, Any], *, actor_account_id: str) -> dict[str, Any]:
    name = _normalize_role_name(payload.get("name"))
    description = _normalize_role_description(payload.get("description"))
    permission_ids = _normalize_permission_ids(payload.get("permission_ids"))
    now = now_iso()
    role_id = generate_role_id()

    with get_conn() as conn:
        valid_permissions = _all_permission_ids(conn)
        for permission_id in permission_ids:
            if permission_id not in valid_permissions:
                raise ValueError("permission_not_found")
        existing = conn.execute("SELECT role_id FROM roles WHERE lower(name) = lower(?)", (name,)).fetchone()
        if existing:
            raise ValueError("role_name_conflict")
        conn.execute(
            """
            INSERT INTO roles (role_id, name, description, is_system, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (role_id, name, description, now, now),
        )
        for permission_id in permission_ids:
            conn.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (?, ?)
                """,
                (role_id, permission_id),
            )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="role.create",
            target_type="role",
            target_id=role_id,
            detail={"name": name, "description": description, "permission_ids": sorted(permission_ids)},
        )
        conn.commit()
        role_row = conn.execute(
            """
            SELECT role_id, name, description, is_system, ? AS permission_count, 0 AS member_count
            FROM roles
            WHERE role_id = ?
            """,
            (len(set(permission_ids)), role_id),
        ).fetchone()
        return {"role": _serialize_role_row(role_row), "permission_ids": sorted(set(permission_ids))}


def update_role(role_id: str, payload: dict[str, Any], *, actor_account_id: str) -> dict[str, Any]:
    name = _normalize_role_name(payload.get("name"))
    description = _normalize_role_description(payload.get("description"))
    now = now_iso()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT role_id, name, description, is_system FROM roles WHERE role_id = ?",
            (role_id,),
        ).fetchone()
        if not existing:
            raise LookupError("role_not_found")
        conflict = conn.execute(
            "SELECT role_id FROM roles WHERE lower(name) = lower(?) AND role_id != ?",
            (name, role_id),
        ).fetchone()
        if conflict:
            raise ValueError("role_name_conflict")
        conn.execute(
            """
            UPDATE roles
            SET name = ?, description = ?, updated_at = ?
            WHERE role_id = ?
            """,
            (name, description, now, role_id),
        )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="role.update",
            target_type="role",
            target_id=role_id,
            detail={"name": name, "description": description, "updated_at": now},
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT
                r.role_id,
                r.name,
                r.description,
                r.is_system,
                COUNT(DISTINCT rp.permission_id) AS permission_count,
                COUNT(DISTINCT ar.account_id) AS member_count
            FROM roles r
            LEFT JOIN role_permissions rp ON rp.role_id = r.role_id
            LEFT JOIN account_roles ar ON ar.role_id = r.role_id
            WHERE r.role_id = ?
            GROUP BY r.role_id, r.name, r.description, r.is_system
            """,
            (role_id,),
        ).fetchone()
        return _serialize_role_row(row)


def delete_role(role_id: str, *, actor_account_id: str) -> None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT role_id, name, is_system
            FROM roles
            WHERE role_id = ?
            """,
            (role_id,),
        ).fetchone()
        if not row:
            raise LookupError("role_not_found")
        if bool(row["is_system"]):
            raise ValueError("role_delete_system_forbidden")
        binding = conn.execute(
            "SELECT COUNT(1) AS cnt FROM account_roles WHERE role_id = ?",
            (role_id,),
        ).fetchone()
        if binding and int(binding["cnt"] or 0) > 0:
            raise ValueError("role_delete_in_use")
        conn.execute("DELETE FROM roles WHERE role_id = ?", (role_id,))
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="role.delete",
            target_type="role",
            target_id=role_id,
            detail={"name": row["name"]},
        )
        conn.commit()


def update_role_permissions(*, role_id: str, permission_ids: list[str], actor_account_id: str) -> dict[str, Any]:
    permission_ids = _normalize_permission_ids(permission_ids)
    now = now_iso()
    with get_conn() as conn:
        role = conn.execute("SELECT role_id FROM roles WHERE role_id = ?", (role_id,)).fetchone()
        if not role:
            raise LookupError("role_not_found")
        valid_permissions = {
            row["permission_id"] for row in conn.execute("SELECT permission_id FROM permissions").fetchall()
        }
        for perm_id in permission_ids:
            if perm_id not in valid_permissions:
                raise ValueError("permission_not_found")
        conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        for perm_id in permission_ids:
            conn.execute(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                (role_id, perm_id),
            )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="role.permissions.update",
            target_type="role",
            target_id=role_id,
            detail={"permission_ids": sorted(permission_ids), "updated_at": now},
        )
        conn.commit()
    return {"role_id": role_id, "permission_ids": sorted(permission_ids)}


def create_account(payload: dict[str, Any], *, actor_account_id: str) -> dict[str, Any]:
    username = _normalize_account_username(payload.get("username"))
    display_name = _normalize_account_display_name(payload.get("display_name"))
    email = _normalize_account_email(payload.get("email"))
    role_ids = _normalize_role_ids(payload.get("role_ids") or [])
    temp_password = f"{ACCOUNT_BOOTSTRAP_PASSWORD_PREFIX}{uuid.uuid4()}"
    password_hash, password_salt, password_iter = _hash_password(temp_password)
    now = now_iso()
    account_id = generate_account_id()

    with get_conn() as conn:
        valid_roles = {row["role_id"] for row in conn.execute("SELECT role_id FROM roles").fetchall()}
        for role_id in role_ids:
            if role_id not in valid_roles:
                raise ValueError("role_not_found")
        existing = conn.execute("SELECT 1 FROM accounts WHERE username = ?", (username,)).fetchone()
        if existing:
            raise ValueError("account_username_conflict")
        conn.execute(
            """
            INSERT INTO accounts (
                account_id, username, display_name, email, password_hash, password_salt, password_iter,
                status, must_change_password, force_logout_at, last_login_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1, NULL, NULL, ?, ?)
            """,
            (
                account_id,
                username,
                display_name,
                email,
                password_hash,
                password_salt,
                password_iter,
                now,
                now,
            ),
        )
        for role_id in role_ids:
            conn.execute(
                "INSERT OR IGNORE INTO account_roles (account_id, role_id) VALUES (?, ?)",
                (account_id, role_id),
            )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="account.create",
            target_type="account",
            target_id=account_id,
            detail={"username": username, "role_ids": role_ids},
        )
        conn.commit()
        roles = _account_roles(conn, account_id)
        account = _serialize_account_row(
            conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone(), roles
        )
    return {"account": account, "temp_password": temp_password}


def update_account_roles(account_id: str, role_ids: list[str], *, actor_account_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT account_id FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if not row:
            raise LookupError("account_not_found")
        existing_manual_permission_ids = sorted(_manual_permission_ids(conn, account_id))
    return update_account_access(
        account_id,
        role_ids=role_ids,
        manual_permission_ids=existing_manual_permission_ids,
        actor_account_id=actor_account_id,
    )["account"]


def get_account_access(account_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        return _build_account_access_payload(conn, account_id)


def update_account_access(
    account_id: str,
    *,
    role_ids: list[str],
    manual_permission_ids: list[str],
    actor_account_id: str,
) -> dict[str, Any]:
    role_ids = _normalize_role_ids(role_ids)
    manual_permission_ids = _normalize_permission_ids(manual_permission_ids)
    now = now_iso()
    with get_conn() as conn:
        row = conn.execute("SELECT account_id FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if not row:
            raise LookupError("account_not_found")
        valid_roles = {row["role_id"] for row in conn.execute("SELECT role_id FROM roles").fetchall()}
        for role_id in role_ids:
            if role_id not in valid_roles:
                raise ValueError("role_not_found")
        valid_permissions = _all_permission_ids(conn)
        for permission_id in manual_permission_ids:
            if permission_id not in valid_permissions:
                raise ValueError("permission_not_found")

        inherited_permission_ids = _inherited_permission_ids(conn, role_ids)
        normalized_manual_permission_ids = sorted(set(manual_permission_ids) - inherited_permission_ids)

        conn.execute("DELETE FROM account_roles WHERE account_id = ?", (account_id,))
        for role_id in role_ids:
            conn.execute(
                "INSERT OR IGNORE INTO account_roles (account_id, role_id) VALUES (?, ?)",
                (account_id, role_id),
            )

        conn.execute("DELETE FROM account_manual_permissions WHERE account_id = ?", (account_id,))
        for permission_id in normalized_manual_permission_ids:
            conn.execute(
                """
                INSERT INTO account_manual_permissions (account_id, permission_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (account_id, permission_id, now, now),
            )

        effective_permission_ids = sorted(inherited_permission_ids | set(normalized_manual_permission_ids))
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="account.access.update",
            target_type="account",
            target_id=account_id,
            detail={
                "role_ids": role_ids,
                "manual_permission_ids": normalized_manual_permission_ids,
                "effective_permission_ids": effective_permission_ids,
                "updated_at": now,
            },
        )
        conn.commit()
        return _build_account_access_payload(conn, account_id)


def disable_account(account_id: str, *, actor_account_id: str) -> dict[str, Any]:
    now = now_iso()
    with get_conn() as conn:
        row = conn.execute("SELECT account_id FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if not row:
            raise LookupError("account_not_found")
        conn.execute(
            "UPDATE accounts SET status = 'disabled', force_logout_at = ?, updated_at = ? WHERE account_id = ?",
            (now, now, account_id),
        )
        conn.execute(
            "UPDATE account_sessions SET revoked_at = ? WHERE account_id = ? AND revoked_at IS NULL",
            (now, account_id),
        )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="account.disable",
            target_type="account",
            target_id=account_id,
            detail={"disabled_at": now},
        )
        conn.commit()
        roles = _account_roles(conn, account_id)
        account = _serialize_account_row(
            conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone(), roles
        )
    return account


def enable_account(account_id: str, *, actor_account_id: str) -> dict[str, Any]:
    now = now_iso()
    with get_conn() as conn:
        row = conn.execute("SELECT account_id FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if not row:
            raise LookupError("account_not_found")
        conn.execute(
            "UPDATE accounts SET status = 'active', updated_at = ? WHERE account_id = ?",
            (now, account_id),
        )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="account.enable",
            target_type="account",
            target_id=account_id,
            detail={"enabled_at": now},
        )
        conn.commit()
        roles = _account_roles(conn, account_id)
        account = _serialize_account_row(
            conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone(), roles
        )
    return account


def reset_account_password(account_id: str, *, actor_account_id: str) -> dict[str, Any]:
    now = now_iso()
    temp_password = f"{ACCOUNT_BOOTSTRAP_PASSWORD_PREFIX}{uuid.uuid4()}"
    password_hash, password_salt, password_iter = _hash_password(temp_password)
    with get_conn() as conn:
        row = conn.execute("SELECT account_id FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if not row:
            raise LookupError("account_not_found")
        conn.execute(
            """
            UPDATE accounts
            SET password_hash = ?, password_salt = ?, password_iter = ?,
                must_change_password = 1,
                force_logout_at = ?,
                updated_at = ?
            WHERE account_id = ?
            """,
            (password_hash, password_salt, password_iter, now, now, account_id),
        )
        conn.execute(
            "UPDATE account_sessions SET revoked_at = ? WHERE account_id = ? AND revoked_at IS NULL",
            (now, account_id),
        )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="account.reset_password",
            target_type="account",
            target_id=account_id,
            detail={"reset_at": now},
        )
        conn.commit()
        roles = _account_roles(conn, account_id)
        account = _serialize_account_row(
            conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone(), roles
        )
    return {"account": account, "temp_password": temp_password}


def force_logout_account(account_id: str, *, actor_account_id: str) -> dict[str, Any]:
    now = now_iso()
    with get_conn() as conn:
        row = conn.execute("SELECT account_id FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if not row:
            raise LookupError("account_not_found")
        conn.execute(
            "UPDATE accounts SET force_logout_at = ?, updated_at = ? WHERE account_id = ?",
            (now, now, account_id),
        )
        conn.execute(
            "UPDATE account_sessions SET revoked_at = ? WHERE account_id = ? AND revoked_at IS NULL",
            (now, account_id),
        )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="account.force_logout",
            target_type="account",
            target_id=account_id,
            detail={"forced_at": now},
        )
        conn.commit()
        roles = _account_roles(conn, account_id)
        account = _serialize_account_row(
            conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone(), roles
        )
    return account


def delete_account(account_id: str, *, actor_account_id: str) -> None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT account_id, username FROM accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if not row:
            raise LookupError("account_not_found")
        conn.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="account.delete",
            target_type="account",
            target_id=account_id,
            detail={"username": row["username"]},
        )
        conn.commit()


def list_audit_logs(limit: int = 200) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT audit_id, actor_account_id, action, target_type, target_id, detail_json, created_at
            FROM audit_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [_serialize_audit_log_row(row) for row in rows]


def list_diagnostic_logs(
    limit: int = 200,
    *,
    source: str | None = None,
    category: str | None = None,
    trace_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if trace_id:
        clauses.append("trace_id = ?")
        params.append(trace_id)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT diagnostic_id, actor_account_id, source, category, event, level,
               trace_id, request_path, detail_json, created_at
        FROM diagnostic_logs
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ?
    """
    params.append(max(1, min(int(limit), 500)))
    with get_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [_serialize_diagnostic_log_row(row) for row in rows]


def _get_account_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT account_id, username, display_name, email, password_hash, password_salt, password_iter,
               status, must_change_password, force_logout_at, last_login_at, created_at, updated_at
        FROM accounts
        WHERE username = ?
        """,
        (username,),
    ).fetchone()


def _get_account_by_id(conn: sqlite3.Connection, account_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT account_id, username, display_name, email, password_hash, password_salt, password_iter,
               status, must_change_password, force_logout_at, last_login_at, created_at, updated_at
        FROM accounts
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()


def _get_role_ids(conn: sqlite3.Connection, account_id: str) -> list[str]:
    rows = conn.execute("SELECT role_id FROM account_roles WHERE account_id = ?", (account_id,)).fetchall()
    return [row["role_id"] for row in rows]


def _get_permission_ids_for_roles(conn: sqlite3.Connection, role_ids: list[str]) -> set[str]:
    if not role_ids:
        return set()
    query = f"""
        SELECT permission_id
        FROM role_permissions
        WHERE role_id IN ({",".join("?" for _ in role_ids)})
    """
    rows = conn.execute(query, tuple(role_ids)).fetchall()
    return {row["permission_id"] for row in rows}


def list_account_permissions(account_id: str) -> set[str]:
    with get_conn() as conn:
        role_ids = _get_role_ids(conn, account_id)
        inherited_permission_ids = _inherited_permission_ids(conn, role_ids)
        manual_permission_ids = _manual_permission_ids(conn, account_id) - inherited_permission_ids
        return inherited_permission_ids | manual_permission_ids


def create_session(account_id: str) -> dict[str, Any]:
    now = now_iso()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ACCOUNT_SESSION_TTL_SEC)).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO account_sessions (
                session_id, account_id, token_hash, created_at, expires_at, revoked_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                f"sess_{uuid.uuid4().hex[:12]}",
                account_id,
                token_hash,
                now,
                expires_at,
                now,
            ),
        )
        conn.execute(
            "UPDATE accounts SET last_login_at = ?, updated_at = ? WHERE account_id = ?",
            (now, now, account_id),
        )
        _record_audit_log(
            conn,
            actor_account_id=account_id,
            action="account.login",
            target_type="account",
            target_id=account_id,
            detail={"login_at": now},
        )
        conn.commit()
    return {"token": token, "expires_at": expires_at}


def revoke_session(raw_token: str) -> None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = now_iso()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT account_id FROM account_sessions WHERE token_hash = ? AND revoked_at IS NULL",
            (token_hash,),
        ).fetchone()
        conn.execute(
            "UPDATE account_sessions SET revoked_at = ? WHERE token_hash = ?",
            (now, token_hash),
        )
        if row:
            _record_audit_log(
                conn,
                actor_account_id=row["account_id"],
                action="account.logout",
                target_type="account",
                target_id=row["account_id"],
                detail={"logout_at": now},
            )
        conn.commit()


def authenticate_account(username: str, password: str) -> dict[str, Any]:
    normalized_username = _normalize_account_username(username)
    with get_conn() as conn:
        row = _get_account_by_username(conn, normalized_username)
        if not row:
            raise LookupError("account_not_found")
        if row["status"] != "active":
            raise PermissionError("account_disabled")
        if not _verify_password(password, row["password_hash"], row["password_salt"], row["password_iter"]):
            raise PermissionError("account_password_invalid")
        roles = _account_roles(conn, row["account_id"])
        account = _serialize_account_row(row, roles)
    session = create_session(account["account_id"])
    return {"account": account, "token": session["token"], "expires_at": session["expires_at"]}


def get_account_by_session(raw_token: str) -> dict[str, Any]:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT s.session_id, s.account_id, s.token_hash, s.created_at, s.expires_at, s.revoked_at,
                   a.username, a.display_name, a.email, a.status, a.must_change_password, a.force_logout_at,
                   a.last_login_at, a.created_at, a.updated_at
            FROM account_sessions s
            JOIN accounts a ON a.account_id = s.account_id
            WHERE s.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if not row:
            raise PermissionError("session_invalid")
        if row["revoked_at"]:
            raise PermissionError("session_revoked")
        try:
            expires_at = datetime.fromisoformat(row["expires_at"])
        except ValueError:
            raise PermissionError("session_invalid") from None
        if expires_at < now:
            raise PermissionError("session_expired")
        if row["status"] != "active":
            raise PermissionError("account_disabled")
        if row["force_logout_at"]:
            try:
                forced_at = datetime.fromisoformat(row["force_logout_at"])
                created_at = datetime.fromisoformat(row["created_at"])
            except ValueError:
                forced_at = None
                created_at = None
            if forced_at and created_at and created_at < forced_at:
                raise PermissionError("session_forced_logout")
        roles = _account_roles(conn, row["account_id"])
        account = _serialize_account_row(row, roles)
        conn.execute(
            "UPDATE account_sessions SET last_seen_at = ? WHERE session_id = ?",
            (now_iso(), row["session_id"]),
        )
        conn.commit()
    return account


def change_account_password(
    account_id: str, current_password: str | None, new_password: str, *, actor_account_id: str
) -> dict[str, Any]:
    new_hash, new_salt, new_iter = _hash_password(new_password)
    now = now_iso()
    with get_conn() as conn:
        row = _get_account_by_id(conn, account_id)
        if not row:
            raise LookupError("account_not_found")
        if current_password:
            if not _verify_password(current_password, row["password_hash"], row["password_salt"], row["password_iter"]):
                raise PermissionError("account_password_invalid")
        elif not bool(row["must_change_password"]):
            raise PermissionError("account_password_required")
        conn.execute(
            """
            UPDATE accounts
            SET password_hash = ?, password_salt = ?, password_iter = ?,
                must_change_password = 0,
                updated_at = ?
            WHERE account_id = ?
            """,
            (new_hash, new_salt, new_iter, now, account_id),
        )
        _record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action="account.password.change",
            target_type="account",
            target_id=account_id,
            detail={"changed_at": now},
        )
        conn.commit()
        roles = _account_roles(conn, account_id)
        account = _serialize_account_row(_get_account_by_id(conn, account_id), roles)
    return account


def _normalize_node_type(value: Any) -> str:
    node_type = str(value or "").strip().lower()
    if node_type not in {"vps", "linux", "macos"}:
        raise ValueError("node_type_invalid")
    return node_type


def _normalize_node_display_name(value: Any) -> str:
    display_name = str(value or "").strip()
    if not display_name:
        raise ValueError("node_display_name_required")
    if len(display_name) > 80:
        raise ValueError("node_display_name_too_long")
    return display_name


def _normalize_openclaw_root_value(value: Any) -> str:
    openclaw_root = str(value or "").strip()
    if not openclaw_root:
        raise ValueError("node_openclaw_root_required")
    if len(openclaw_root) > 500:
        raise ValueError("node_openclaw_root_too_long")
    return openclaw_root


def _generate_node_token() -> str:
    return secrets.token_urlsafe(24)


def _hash_node_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _bootstrap_context() -> dict[str, Any]:
    if OPENCLAW_PUBLIC_BASE_URL:
        return {
            "bootstrap_ready": True,
            "bootstrap_reason": None,
            "bootstrap_mode": "public",
            "bootstrap_base": OPENCLAW_PUBLIC_BASE_URL,
        }
    if OPENCLAW_LOCAL_BASE_URL:
        return {
            "bootstrap_ready": True,
            "bootstrap_reason": None,
            "bootstrap_mode": "local",
            "bootstrap_base": OPENCLAW_LOCAL_BASE_URL,
        }
    return {
        "bootstrap_ready": False,
        "bootstrap_reason": "未配置可用的接入地址，请设置 OPENCLAW_PUBLIC_BASE_URL。",
        "bootstrap_mode": "unavailable",
        "bootstrap_base": None,
    }


def _build_node_bootstrap_script_url(node_id: str, raw_token: str) -> tuple[str | None, bool, str | None, str | None]:
    context = _bootstrap_context()
    ready = bool(context["bootstrap_ready"])
    reason = context["bootstrap_reason"]
    base_url = context["bootstrap_base"]
    if not ready or not base_url:
        return None, False, reason, context["bootstrap_mode"]
    script_url = (
        f"{base_url}/api/nodes/bootstrap.sh"
        f"?node_id={quote(node_id, safe='')}&token={quote(raw_token, safe='')}"
    )
    return script_url, True, None, context["bootstrap_mode"]


def _build_node_bootstrap_command(node_id: str, raw_token: str) -> tuple[str | None, bool, str | None]:
    script_url, ready, reason, _ = _build_node_bootstrap_script_url(node_id, raw_token)
    if not ready or not script_url:
        return None, ready, reason
    return f"curl -fsSL {shlex.quote(script_url)} | bash", True, None


def _node_status_from_row(row: dict[str, Any]) -> str:
    activated_at = row.get("activated_at")
    if not activated_at:
        return "pending"
    last_seen_at = row.get("last_seen_at")
    if not last_seen_at:
        return "offline"
    last_seen_dt = _parse_iso_utc(str(last_seen_at), "node_last_seen_at")
    if not last_seen_dt:
        return "offline"
    delta = datetime.now(timezone.utc) - last_seen_dt
    if delta.total_seconds() <= NODE_CONNECTOR_ONLINE_THRESHOLD_SEC:
        return "online"
    return "offline"


def _serialize_node(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "node_id": payload["node_id"],
        "display_name": payload["display_name"],
        "node_type": payload["node_type"],
        "expected_openclaw_root": payload["expected_openclaw_root"],
        "reported_openclaw_root": payload.get("reported_openclaw_root"),
        "hostname": payload.get("hostname"),
        "platform": payload.get("platform"),
        "connector_version": payload.get("connector_version"),
        "status": _node_status_from_row(payload),
        "token_last4": payload.get("token_last4"),
        "activated_at": payload.get("activated_at"),
        "last_seen_at": payload.get("last_seen_at"),
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }


def _normalize_runtime_root_candidates(*values: str | None) -> set[str]:
    normalized: set[str] = set()
    for raw in values:
        if not raw:
            continue
        text = str(raw).strip()
        if not text:
            continue
        normalized.add(text.rstrip("/"))
        normalized.add(Path(text).name)
    return normalized


def _match_runtime_node_snapshot(rows: list[sqlite3.Row | dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    host_candidates = _normalize_runtime_root_candidates(str(_resolved_openclaw_host_root()), str(WORKSPACE_VISIBLE_ROOT))
    matched: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        node_candidates = _normalize_runtime_root_candidates(
            payload.get("reported_openclaw_root"),
            payload.get("expected_openclaw_root"),
        )
        if host_candidates & node_candidates:
            matched.append(_serialize_node(payload))

    if len(matched) == 1:
        return matched[0]
    return None


def _get_node_row(conn: sqlite3.Connection, node_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT node_id, display_name, node_type, expected_openclaw_root, token_hash, token_last4,
               hostname, platform, connector_version, reported_openclaw_root, activated_at,
               last_seen_at, created_at, updated_at
        FROM nodes
        WHERE node_id = ?
        """,
        (node_id,),
    ).fetchone()


def _normalize_node_sync_relative_path(value: Any) -> str:
    relative_path = str(value or "").strip()
    if not relative_path:
        raise ValueError("node_sync_relative_path_required")
    path = Path(relative_path)
    if path.is_absolute() or relative_path.startswith("/"):
        raise ValueError("node_sync_relative_path_absolute")
    if any(part == ".." for part in path.parts):
        raise ValueError("node_sync_relative_path_parent_traversal")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ValueError("node_sync_relative_path_invalid")
    return normalized


def _normalize_node_sync_operation_kind(value: Any) -> str:
    operation_kind = str(value or "").strip()
    if operation_kind not in NODE_SYNC_OPERATION_KINDS:
        raise ValueError("node_sync_operation_kind_invalid")
    return operation_kind


def _serialize_node_sync_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ValueError("node_sync_payload_required")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _upsert_node_sync_job(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    source_kind: str,
    source_id: str,
    resource_key: str,
    relative_path: str,
    operation_kind: str,
    payload: dict[str, Any],
    created_at: str,
) -> None:
    normalized_source_kind = str(source_kind or "").strip()
    normalized_source_id = str(source_id or "").strip()
    normalized_resource_key = str(resource_key or "").strip()
    if not normalized_source_kind:
        raise ValueError("node_sync_source_kind_required")
    if not normalized_source_id:
        raise ValueError("node_sync_source_id_required")
    if not normalized_resource_key:
        raise ValueError("node_sync_resource_key_required")

    conn.execute(
        """
        INSERT INTO node_sync_jobs (
            sync_id, node_id, source_kind, source_id, resource_key, relative_path,
            operation_kind, payload_json, status, attempt_count, last_error,
            last_attempt_at, applied_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, NULL, NULL, NULL, ?, ?)
        ON CONFLICT(node_id, source_kind, source_id, resource_key)
        DO UPDATE SET
            relative_path = excluded.relative_path,
            operation_kind = excluded.operation_kind,
            payload_json = excluded.payload_json,
            status = CASE
                WHEN node_sync_jobs.relative_path != excluded.relative_path
                  OR node_sync_jobs.operation_kind != excluded.operation_kind
                  OR node_sync_jobs.payload_json != excluded.payload_json
                THEN 'pending'
                ELSE node_sync_jobs.status
            END,
            attempt_count = CASE
                WHEN node_sync_jobs.relative_path != excluded.relative_path
                  OR node_sync_jobs.operation_kind != excluded.operation_kind
                  OR node_sync_jobs.payload_json != excluded.payload_json
                THEN 0
                ELSE node_sync_jobs.attempt_count
            END,
            last_error = CASE
                WHEN node_sync_jobs.relative_path != excluded.relative_path
                  OR node_sync_jobs.operation_kind != excluded.operation_kind
                  OR node_sync_jobs.payload_json != excluded.payload_json
                THEN NULL
                ELSE node_sync_jobs.last_error
            END,
            last_attempt_at = CASE
                WHEN node_sync_jobs.relative_path != excluded.relative_path
                  OR node_sync_jobs.operation_kind != excluded.operation_kind
                  OR node_sync_jobs.payload_json != excluded.payload_json
                THEN NULL
                ELSE node_sync_jobs.last_attempt_at
            END,
            applied_at = CASE
                WHEN node_sync_jobs.relative_path != excluded.relative_path
                  OR node_sync_jobs.operation_kind != excluded.operation_kind
                  OR node_sync_jobs.payload_json != excluded.payload_json
                THEN NULL
                ELSE node_sync_jobs.applied_at
            END,
            updated_at = excluded.updated_at
        """,
        (
            f"sync_{uuid.uuid4().hex[:12]}",
            node_id,
            normalized_source_kind,
            normalized_source_id,
            normalized_resource_key,
            _normalize_node_sync_relative_path(relative_path),
            _normalize_node_sync_operation_kind(operation_kind),
            _serialize_node_sync_payload(payload),
            created_at,
            created_at,
        ),
    )


def _list_node_sync_jobs(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    status: str = "pending",
    limit: int = NODE_SYNC_BATCH_SIZE,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT sync_id, node_id, source_kind, source_id, resource_key, relative_path,
               operation_kind, payload_json, status, attempt_count, last_error,
               last_attempt_at, applied_at, created_at, updated_at
        FROM node_sync_jobs
        WHERE node_id = ? AND status = ?
        ORDER BY created_at ASC, sync_id ASC
        LIMIT ?
        """,
        (node_id, status, max(1, int(limit))),
    ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            payload = {}
        items.append(
            {
                "sync_id": row["sync_id"],
                "source_kind": row["source_kind"],
                "source_id": row["source_id"],
                "resource_key": row["resource_key"],
                "relative_path": row["relative_path"],
                "operation_kind": row["operation_kind"],
                "payload": payload if isinstance(payload, dict) else {},
            }
        )
    return items


def _build_remote_scheduled_job_sync_plan(job: dict[str, Any]) -> dict[str, Any] | None:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    _content_field, content = _resolve_scheduled_job_content(payload)
    normalized = serialize_delivery_metadata(job, content=content)
    if normalized["delivery_channel"] == "internal":
        return None
    if not normalized["delivery_bootstrap_enabled"]:
        return None
    if normalized["delivery_bootstrap_scope"] != "remote":
        return None
    stable_synced_at = _ts_ms_to_iso(job.get("updatedAtMs")) or _ts_ms_to_iso(job.get("createdAtMs")) or now_iso()
    return build_delivery_bootstrap_operations(job, synced_at=stable_synced_at, content=content)


def _queue_scheduled_job_remote_sync_for_nodes(
    conn: sqlite3.Connection,
    job: dict[str, Any],
    *,
    node_ids: list[str],
) -> dict[str, Any]:
    plan = _build_remote_scheduled_job_sync_plan(job)
    if not plan:
        return {
            "node_count": 0,
            "queued_operation_count": 0,
            "synced_files": [],
        }

    job_id = str(job.get("id") or "").strip()
    if not job_id:
        raise ValueError("scheduled_job_id_required")

    normalized_node_ids = sorted({str(node_id or "").strip() for node_id in node_ids if str(node_id or "").strip()})
    if not normalized_node_ids:
        return {
            "node_count": 0,
            "queued_operation_count": 0,
            "synced_files": list(plan["synced_files"]),
        }

    created_at = now_iso()
    operation_count = 0
    for node_id in normalized_node_ids:
        for operation in plan["operations"]:
            _upsert_node_sync_job(
                conn,
                node_id=node_id,
                source_kind=NODE_SYNC_SOURCE_SCHEDULED_JOB,
                source_id=job_id,
                resource_key=str(operation.get("resource_key") or ""),
                relative_path=str(operation.get("relative_path") or ""),
                operation_kind=str(operation.get("operation_kind") or ""),
                payload=operation.get("payload") if isinstance(operation.get("payload"), dict) else {},
                created_at=created_at,
            )
            operation_count += 1

    return {
        "node_count": len(normalized_node_ids),
        "queued_operation_count": operation_count,
        "synced_files": list(plan["synced_files"]),
    }


def _queue_all_remote_scheduled_job_sync_for_node(conn: sqlite3.Connection, *, node_id: str) -> None:
    document = _load_openclaw_jobs_document()
    jobs = document.get("jobs") or []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        _queue_scheduled_job_remote_sync_for_nodes(conn, job, node_ids=[node_id])


def _get_remote_scheduled_job_sync_snapshot(job_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(1) AS total_count,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                   SUM(CASE WHEN status = 'pending' AND last_error IS NOT NULL THEN 1 ELSE 0 END) AS failed_count,
                   COUNT(DISTINCT node_id) AS node_count,
                   MAX(applied_at) AS latest_applied_at
            FROM node_sync_jobs
            WHERE source_kind = ? AND source_id = ?
            """,
            (NODE_SYNC_SOURCE_SCHEDULED_JOB, job_id),
        ).fetchone()
        if not row or int(row["total_count"] or 0) <= 0:
            return None
        path_rows = conn.execute(
            """
            SELECT DISTINCT relative_path
            FROM node_sync_jobs
            WHERE source_kind = ? AND source_id = ?
            ORDER BY relative_path ASC
            """,
            (NODE_SYNC_SOURCE_SCHEDULED_JOB, job_id),
        ).fetchall()

    total_count = int(row["total_count"] or 0)
    pending_count = int(row["pending_count"] or 0)
    failed_count = int(row["failed_count"] or 0)
    node_count = int(row["node_count"] or 0)
    synced_files = [str(path_row["relative_path"]) for path_row in path_rows if path_row["relative_path"]]
    if pending_count <= 0:
        message = f"已同步到 {node_count} 个远程节点"
        status = "synced"
        synced_at = str(row["latest_applied_at"] or "") or None
        synced_root = f"remote:{node_count}-nodes"
    else:
        status = "pending"
        if failed_count > 0:
            message = f"远程同步正在重试，最近一次有 {failed_count} 项失败；目标节点 {node_count} 个。"
        else:
            message = f"已加入 {node_count} 个节点的远程同步队列，等待节点 heartbeat 执行。"
        synced_at = None
        synced_root = None

    return {
        "status": status,
        "message": message,
        "synced_at": synced_at,
        "synced_root": synced_root,
        "synced_files": synced_files,
        "total_count": total_count,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "node_count": node_count,
    }


def list_nodes() -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT node_id, display_name, node_type, expected_openclaw_root, token_hash, token_last4,
                   hostname, platform, connector_version, reported_openclaw_root, activated_at,
                   last_seen_at, created_at, updated_at
            FROM nodes
            ORDER BY created_at DESC, display_name ASC
            """
        ).fetchall()

    items = [_serialize_node(row) for row in rows]
    context = _bootstrap_context()
    return {
        "items": items,
        "total": len(items),
        "bootstrap_ready": context["bootstrap_ready"],
        "bootstrap_reason": context["bootstrap_reason"],
        "bootstrap_mode": context["bootstrap_mode"],
        "bootstrap_base": context["bootstrap_base"],
    }


def _load_bootstrap_snapshot() -> dict[str, Any]:
    try:
        return json.loads(BOOTSTRAP_STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def _extract_bootstrap_snapshot_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    local = snapshot.get("local") if isinstance(snapshot.get("local"), dict) else {}
    public = snapshot.get("public_url") if isinstance(snapshot.get("public_url"), dict) else {}
    return {
        "install_operation": str(snapshot.get("operation") or "unknown"),
        "install_stage": str(snapshot.get("stage") or "unknown"),
        "install_result": str(snapshot.get("result") or "unknown"),
        "install_updated_at": str(snapshot.get("updated_at") or "") or None,
        "local_web_url": str(local.get("web_url") or "") or None,
        "local_api_health_url": str(local.get("api_health_url") or "") or None,
        "local_web_ok": bool(local.get("web_ok")) if local else None,
        "local_api_ok": bool(local.get("api_ok")) if local else None,
        "public_url": str(public.get("url") or "") or None,
        "public_url_status": str(public.get("status") or "unknown"),
        "public_url_reason": str(public.get("reason") or "") or None,
        "public_url_provider": str(public.get("provider") or "") or None,
        "public_url_enabled": bool(public.get("enabled")) if public else False,
    }


_DEFAULT_SETUP_PROMPT_TEMPLATE = """你是 OpenClaw 本地部署代理，目标是完成 ClawPilot 本地接入与节点上线。

当前环境：
- api_base: {{api_base}}
- openclaw_config_path: {{openclaw_config_path}}
- has_openclaw_config: {{has_openclaw_config}}
- node_total: {{node_total}}
- install_stage: {{install_stage}}
- install_result: {{install_result}}
- install_updated_at: {{install_updated_at}}
- local_web_url: {{local_web_url}}
- public_url_status: {{public_url_status}}
- public_url: {{public_url}}
- public_url_reason: {{public_url_reason}}
- bootstrap_ready: {{bootstrap_ready}}
- bootstrap_reason: {{bootstrap_reason}}

阻断项：
{{blocking_items}}

执行步骤：
1. 先确认控制面已启动：
   ./clawpilot status
   ./clawpilot doctor
   ./clawpilot url
2. 如果 install_result 不是 success，优先执行：
   ./clawpilot bootstrap
   如仍失败，再按 doctor 输出执行：
   ./clawpilot repair local
3. 如果需要给用户一个临时公网入口，再执行：
   ./clawpilot expose quick
4. 如果 openclaw.json 不存在，先生成或拷贝到 {{openclaw_config_path}}
5. 创建本地节点 (node_type={{node_type_hint}}):
   curl -fsSL -X POST {{api_base}}/api/nodes \
     -H 'Content-Type: application/json' \
     -d '{"display_name":"本地节点","node_type":"{{node_type_hint}}","expected_openclaw_root":"{{openclaw_root_hint}}"}'
6. 读取响应中的 bootstrap_script_url，并执行：
   export OPENCLAW_ROOT="{{openclaw_root_hint}}"; curl -fsSL "<bootstrap_script_url>" | bash
7. 轮询节点状态：
   curl -fsSL {{api_base}}/api/nodes
8. 节点 online 后返回 /agents；如果 {{public_url}} 已可用就回传给用户，否则说明当前只有本地入口。
"""


def _load_setup_prompt_template() -> str:
    try:
        return SETUP_PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _DEFAULT_SETUP_PROMPT_TEMPLATE


def _render_setup_prompt(template: str, payload: dict[str, str]) -> str:
    rendered = template
    for key, value in payload.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _build_local_setup_prompt(setup: dict[str, Any]) -> str:
    base_url = (OPENCLAW_LOCAL_BASE_URL or setup.get("bootstrap_base") or "http://127.0.0.1:8088").rstrip("/")
    node_type_hint = "macos" if sys.platform == "darwin" else "linux"
    openclaw_root_hint = "~/.openclaw"
    issues: list[str] = []

    if not setup.get("has_openclaw_config"):
        issues.append(f"openclaw 配置缺失: {_resolved_openclaw_config_path()}")
    if int(setup.get("node_total") or 0) == 0:
        issues.append("未注册本地节点")
    if not setup.get("bootstrap_ready") and setup.get("bootstrap_reason"):
        issues.append(f"bootstrap 不可用: {setup.get('bootstrap_reason')}")
    if setup.get("install_result") != "success":
        issues.append(f"控制面 bootstrap 未完成: stage={setup.get('install_stage')} result={setup.get('install_result')}")
    if setup.get("public_url_enabled") and setup.get("public_url_status") != "verified":
        issues.append(
            f"公网入口不可用: {setup.get('public_url_status')} / {setup.get('public_url_reason') or '可尝试 clawpilot expose quick'}"
        )

    if not issues:
        issues.append("未发现明显阻断项")

    payload = {
        "api_base": base_url,
        "openclaw_config_path": str(_resolved_openclaw_config_path()),
        "has_openclaw_config": str(bool(setup.get("has_openclaw_config"))).lower(),
        "node_total": str(int(setup.get("node_total") or 0)),
        "install_stage": str(setup.get("install_stage") or "unknown"),
        "install_result": str(setup.get("install_result") or "unknown"),
        "install_updated_at": str(setup.get("install_updated_at") or "unknown"),
        "local_web_url": str(setup.get("local_web_url") or "http://127.0.0.1:3000/agents"),
        "public_url_status": str(setup.get("public_url_status") or "unknown"),
        "public_url": str(setup.get("public_url") or "未生成"),
        "public_url_reason": str(setup.get("public_url_reason") or "无"),
        "bootstrap_ready": str(bool(setup.get("bootstrap_ready"))).lower(),
        "bootstrap_reason": str(setup.get("bootstrap_reason") or "无"),
        "blocking_items": "\n".join([f"- {item}" for item in issues]),
        "node_type_hint": node_type_hint,
        "openclaw_root_hint": openclaw_root_hint,
    }
    template = _load_setup_prompt_template()
    return _render_setup_prompt(template, payload)


def get_setup_status() -> dict[str, Any]:
    with get_conn() as conn:
        node_total = int(conn.execute("SELECT COUNT(1) AS cnt FROM nodes").fetchone()["cnt"])
    context = _bootstrap_context()
    snapshot_fields = _extract_bootstrap_snapshot_fields(_load_bootstrap_snapshot())
    openclaw_fields = _read_openclaw_cli_status_summary()
    payload = {
        "has_openclaw_config": bool(_load_openclaw_config()),
        "node_total": node_total,
        "bootstrap_ready": context["bootstrap_ready"],
        "bootstrap_reason": context["bootstrap_reason"],
        "bootstrap_mode": context["bootstrap_mode"],
        "bootstrap_base": context["bootstrap_base"],
    }
    payload.update(snapshot_fields)
    payload.update(openclaw_fields)
    payload["bootstrap_prompt"] = _build_local_setup_prompt(payload)
    return payload


def create_node(payload: dict[str, Any]) -> dict[str, Any]:
    display_name = _normalize_node_display_name(payload.get("display_name"))
    node_type = _normalize_node_type(payload.get("node_type"))
    expected_openclaw_root = _normalize_openclaw_root_value(payload.get("expected_openclaw_root"))

    node_id = generate_node_id()
    raw_token = _generate_node_token()
    token_hash = _hash_node_token(raw_token)
    token_last4 = raw_token[-4:]
    created_at = now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO nodes (
                node_id, display_name, node_type, expected_openclaw_root, token_hash, token_last4,
                hostname, platform, connector_version, reported_openclaw_root,
                activated_at, last_seen_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?)
            """,
            (
                node_id,
                display_name,
                node_type,
                expected_openclaw_root,
                token_hash,
                token_last4,
                created_at,
                created_at,
            ),
        )
        conn.commit()
        row = _get_node_row(conn, node_id)

    bootstrap_script_url, bootstrap_ready, bootstrap_reason, bootstrap_mode = _build_node_bootstrap_script_url(
        node_id, raw_token
    )
    bootstrap_command, _, _ = _build_node_bootstrap_command(node_id, raw_token)
    context = _bootstrap_context()
    return {
        "node": _serialize_node(row or {}),
        "raw_token": raw_token,
        "bootstrap_script_url": bootstrap_script_url,
        "bootstrap_command": bootstrap_command,
        "bootstrap_ready": bootstrap_ready,
        "bootstrap_reason": bootstrap_reason,
        "bootstrap_mode": bootstrap_mode,
        "bootstrap_base": context["bootstrap_base"],
    }


def rotate_node_token(node_id: str) -> dict[str, Any]:
    raw_token = _generate_node_token()
    token_hash = _hash_node_token(raw_token)
    token_last4 = raw_token[-4:]
    updated_at = now_iso()

    with get_conn() as conn:
        existing = _get_node_row(conn, node_id)
        if not existing:
            raise LookupError("node_not_found")
        conn.execute(
            """
            UPDATE nodes
            SET token_hash = ?, token_last4 = ?, updated_at = ?
            WHERE node_id = ?
            """,
            (token_hash, token_last4, updated_at, node_id),
        )
        conn.commit()
        row = _get_node_row(conn, node_id)

    bootstrap_script_url, bootstrap_ready, bootstrap_reason, bootstrap_mode = _build_node_bootstrap_script_url(
        node_id, raw_token
    )
    bootstrap_command, _, _ = _build_node_bootstrap_command(node_id, raw_token)
    context = _bootstrap_context()
    return {
        "node": _serialize_node(row or {}),
        "raw_token": raw_token,
        "bootstrap_script_url": bootstrap_script_url,
        "bootstrap_command": bootstrap_command,
        "bootstrap_ready": bootstrap_ready,
        "bootstrap_reason": bootstrap_reason,
        "bootstrap_mode": bootstrap_mode,
        "bootstrap_base": context["bootstrap_base"],
    }


def record_node_heartbeat(payload: dict[str, Any]) -> dict[str, Any]:
    node_id = str(payload.get("node_id") or "").strip()
    raw_token = str(payload.get("token") or "").strip()
    connector_version = str(payload.get("connector_version") or "").strip()
    hostname = str(payload.get("hostname") or "").strip()
    platform = str(payload.get("platform") or "").strip().lower()
    openclaw_root = _normalize_openclaw_root_value(payload.get("openclaw_root"))

    if not node_id:
        raise ValueError("node_id_required")
    if not raw_token:
        raise ValueError("node_token_required")
    if not connector_version:
        raise ValueError("node_connector_version_required")
    if not hostname:
        raise ValueError("node_hostname_required")
    if not platform:
        raise ValueError("node_platform_required")

    now = now_iso()

    with get_conn() as conn:
        row = _get_node_row(conn, node_id)
        if not row:
            raise LookupError("node_not_found")
        if row["token_hash"] != _hash_node_token(raw_token):
            raise PermissionError("node_token_invalid")

        activated_at = row["activated_at"] or now
        conn.execute(
            """
            UPDATE nodes
            SET connector_version = ?, hostname = ?, platform = ?, reported_openclaw_root = ?,
                activated_at = ?, last_seen_at = ?, updated_at = ?
            WHERE node_id = ?
            """,
            (connector_version, hostname, platform, openclaw_root, activated_at, now, now, node_id),
        )
        try:
            _queue_all_remote_scheduled_job_sync_for_node(conn, node_id=node_id)
        except RuntimeError:
            pass
        conn.commit()
        updated_row = _get_node_row(conn, node_id)
        sync_jobs = _list_node_sync_jobs(conn, node_id=node_id)

    serialized = _serialize_node(updated_row or {})
    return {
        "node_id": node_id,
        "status": serialized["status"],
        "accepted_at": now,
        "activated_at": serialized["activated_at"],
        "last_seen_at": serialized["last_seen_at"],
        "sync_jobs": sync_jobs,
    }


def record_node_sync_results(payload: dict[str, Any]) -> dict[str, Any]:
    node_id = str(payload.get("node_id") or "").strip()
    raw_token = str(payload.get("token") or "").strip()
    results = payload.get("results")
    if not node_id:
        raise ValueError("node_id_required")
    if not raw_token:
        raise ValueError("node_token_required")
    if results is None:
        results = []
    if not isinstance(results, list):
        raise ValueError("node_sync_results_invalid")

    accepted_at = now_iso()
    applied_count = 0
    failed_count = 0
    ignored_count = 0

    with get_conn() as conn:
        row = _get_node_row(conn, node_id)
        if not row:
            raise LookupError("node_not_found")
        if row["token_hash"] != _hash_node_token(raw_token):
            raise PermissionError("node_token_invalid")

        for item in results:
            if not isinstance(item, dict):
                raise ValueError("node_sync_result_item_invalid")
            sync_id = str(item.get("sync_id") or "").strip()
            status = str(item.get("status") or "").strip()
            error_message = str(item.get("error_message") or "").strip() or None
            if not sync_id:
                raise ValueError("node_sync_result_sync_id_required")
            if status not in NODE_SYNC_RESULT_STATUSES:
                raise ValueError("node_sync_result_status_invalid")

            existing = conn.execute(
                "SELECT sync_id FROM node_sync_jobs WHERE sync_id = ? AND node_id = ?",
                (sync_id, node_id),
            ).fetchone()
            if not existing:
                ignored_count += 1
                continue

            if status == "applied":
                conn.execute(
                    """
                    UPDATE node_sync_jobs
                    SET status = 'applied',
                        attempt_count = attempt_count + 1,
                        last_error = NULL,
                        last_attempt_at = ?,
                        applied_at = ?,
                        updated_at = ?
                    WHERE sync_id = ? AND node_id = ?
                    """,
                    (accepted_at, accepted_at, accepted_at, sync_id, node_id),
                )
                applied_count += 1
                continue

            conn.execute(
                """
                UPDATE node_sync_jobs
                SET status = 'pending',
                    attempt_count = attempt_count + 1,
                    last_error = ?,
                    last_attempt_at = ?,
                    applied_at = NULL,
                    updated_at = ?
                WHERE sync_id = ? AND node_id = ?
                """,
                (error_message, accepted_at, accepted_at, sync_id, node_id),
            )
            failed_count += 1

        conn.commit()

    return {
        "node_id": node_id,
        "accepted_at": accepted_at,
        "applied_count": applied_count,
        "failed_count": failed_count,
        "ignored_count": ignored_count,
    }


def build_node_bootstrap_script(node_id: str, raw_token: str) -> str:
    node_id = str(node_id or "").strip()
    raw_token = str(raw_token or "").strip()
    if not node_id:
        raise ValueError("node_id_required")
    if not raw_token:
        raise ValueError("node_token_required")
    context = _bootstrap_context()
    if not context["bootstrap_ready"] or not context["bootstrap_base"]:
        raise ValueError("public_base_url_not_configured")

    with get_conn() as conn:
        row = _get_node_row(conn, node_id)
        if not row:
            raise LookupError("node_not_found")
        if row["token_hash"] != _hash_node_token(raw_token):
            raise PermissionError("node_token_invalid")

    base_url = shlex.quote(context["bootstrap_base"])
    safe_node_id = shlex.quote(node_id)
    safe_raw_token = shlex.quote(raw_token)
    return f"""#!/usr/bin/env bash
set -euo pipefail

BASE_URL={base_url}
NODE_ID={safe_node_id}
NODE_TOKEN={safe_raw_token}
CONNECTOR_DIR="${{HOME}}/.clawpilot-node-connector"
OPENCLAW_ROOT="${{OPENCLAW_ROOT:-/root/.openclaw}}"
POLL_INTERVAL="${{CLAWPILOT_POLL_INTERVAL:-60}}"

mkdir -p "${{CONNECTOR_DIR}}"

cat > "${{CONNECTOR_DIR}}/heartbeat.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
BASE_URL={base_url}
NODE_ID={safe_node_id}
NODE_TOKEN={safe_raw_token}
OPENCLAW_ROOT="${{OPENCLAW_ROOT:-/root/.openclaw}}"
CONNECTOR_DIR="${{HOME}}/.clawpilot-node-connector"
CONNECTOR_VERSION="${{CLAWPILOT_CONNECTOR_VERSION:-bootstrap-v2}}"
HOSTNAME_VALUE="$(hostname)"
PLATFORM_VALUE="$(uname -s | tr '[:upper:]' '[:lower:]')"
response_file="$(mktemp "${{CONNECTOR_DIR}}/heartbeat-response-XXXXXX.json")"
results_file="$(mktemp "${{CONNECTOR_DIR}}/heartbeat-results-XXXXXX.json")"

cleanup() {{
  rm -f "${{response_file}}" "${{results_file}}"
}}

trap cleanup EXIT

payload=$(NODE_ID="${{NODE_ID}}" NODE_TOKEN="${{NODE_TOKEN}}" CONNECTOR_VERSION="${{CONNECTOR_VERSION}}" \
  HOSTNAME_VALUE="${{HOSTNAME_VALUE}}" PLATFORM_VALUE="${{PLATFORM_VALUE}}" OPENCLAW_ROOT="${{OPENCLAW_ROOT}}" \
  python3 - <<'PY'
import json
import os

print(
    json.dumps(
        {{
            "node_id": os.environ["NODE_ID"],
            "token": os.environ["NODE_TOKEN"],
            "connector_version": os.environ["CONNECTOR_VERSION"],
            "hostname": os.environ["HOSTNAME_VALUE"],
            "platform": os.environ["PLATFORM_VALUE"],
            "openclaw_root": os.environ["OPENCLAW_ROOT"],
        }},
        ensure_ascii=False,
    )
)
PY
)
curl -fsS "${{BASE_URL}}/api/nodes/heartbeat" \
  -H 'Content-Type: application/json' \
  -d "${{payload}}" \
  -o "${{response_file}}"

python3 - "${{response_file}}" "${{OPENCLAW_ROOT}}" "${{results_file}}" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path, PurePosixPath

response_path = Path(sys.argv[1])
openclaw_root = Path(sys.argv[2]).resolve()
results_path = Path(sys.argv[3])


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{{path.stem}}-", suffix=path.suffix or ".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        Path(temp_name).replace(path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def resolve_target(relative_path: str) -> Path:
    relative = PurePosixPath(str(relative_path or "").strip())
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("relative_path_invalid")
    target = (openclaw_root / Path(*relative.parts)).resolve()
    if os.path.commonpath([str(openclaw_root), str(target)]) != str(openclaw_root):
        raise ValueError("relative_path_escapes_root")
    return target


def upsert_json_value(target_path: Path, payload: dict) -> None:
    root_default = payload.get("root_default")
    key_path = payload.get("key_path")
    value = payload.get("value")
    if not isinstance(root_default, dict):
        raise ValueError("root_default_required")
    if not isinstance(key_path, list) or not key_path:
        raise ValueError("key_path_required")

    if target_path.exists():
        with target_path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
        if not isinstance(document, dict):
            document = dict(root_default)
    else:
        document = dict(root_default)

    cursor = document
    for segment in key_path[:-1]:
        key = str(segment or "").strip()
        if not key:
            raise ValueError("key_path_invalid")
        child = cursor.get(key)
        if not isinstance(child, dict):
            child = {{}}
            cursor[key] = child
        cursor = child

    last_key = str(key_path[-1] or "").strip()
    if not last_key:
        raise ValueError("key_path_invalid")
    cursor[last_key] = value
    atomic_write_text(target_path, json.dumps(document, ensure_ascii=False, indent=2) + "\\n")


with response_path.open("r", encoding="utf-8") as handle:
    response = json.load(handle)

sync_jobs = response.get("sync_jobs") or []
results = []
for item in sync_jobs:
    sync_id = str((item or {{}}).get("sync_id") or "").strip()
    if not sync_id:
        continue
    try:
        relative_path = str(item.get("relative_path") or "").strip()
        operation_kind = str(item.get("operation_kind") or "").strip()
        payload = item.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload_required")
        target_path = resolve_target(relative_path)
        if operation_kind == "write_text_file":
            content = payload.get("content")
            if not isinstance(content, str):
                raise ValueError("content_required")
            atomic_write_text(target_path, content)
        elif operation_kind == "upsert_json_value":
            upsert_json_value(target_path, payload)
        else:
            raise ValueError(f"unsupported_operation:{{operation_kind}}")
        results.append({{"sync_id": sync_id, "status": "applied"}})
    except Exception as exc:
        results.append(
            {{
                "sync_id": sync_id,
                "status": "failed",
                "error_message": str(exc)[:500],
            }}
        )

with results_path.open("w", encoding="utf-8") as handle:
    json.dump({{"results": results}}, handle, ensure_ascii=False)
PY

results_payload=$(RESULTS_FILE="${{results_file}}" NODE_ID="${{NODE_ID}}" NODE_TOKEN="${{NODE_TOKEN}}" \
  python3 - <<'PY'
import json
import os

with open(os.environ["RESULTS_FILE"], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

print(
    json.dumps(
        {{
            "node_id": os.environ["NODE_ID"],
            "token": os.environ["NODE_TOKEN"],
            "results": payload.get("results") or [],
        }},
        ensure_ascii=False,
    )
)
PY
)

curl -fsS "${{BASE_URL}}/api/nodes/sync-results" \
  -H 'Content-Type: application/json' \
  -d "${{results_payload}}" >/dev/null
EOF

chmod +x "${{CONNECTOR_DIR}}/heartbeat.sh"

if [[ -f "${{CONNECTOR_DIR}}/connector.pid" ]] && kill -0 "$(cat "${{CONNECTOR_DIR}}/connector.pid")" >/dev/null 2>&1; then
  kill "$(cat "${{CONNECTOR_DIR}}/connector.pid")" >/dev/null 2>&1 || true
fi

nohup bash -lc 'while true; do "${{HOME}}/.clawpilot-node-connector/heartbeat.sh"; sleep "${{CLAWPILOT_POLL_INTERVAL:-60}}"; done' \
  > "${{CONNECTOR_DIR}}/connector.log" 2>&1 &
echo $! > "${{CONNECTOR_DIR}}/connector.pid"

"${{CONNECTOR_DIR}}/heartbeat.sh"

echo "ClawPilot Connector 已启动"
echo "node_id=${{NODE_ID}}"
echo "log=${{CONNECTOR_DIR}}/connector.log"
"""


def _executemany(conn: sqlite3.Connection, sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
    for row in rows:
        conn.execute(sql, row)


def _get_agent_open_id(feishu_config: dict[str, Any], agent_id: str) -> str | None:
    identities = (feishu_config.get("userIdentities") or {})
    for _key, row in identities.items():
        if not isinstance(row, dict):
            continue
        open_id = row.get(agent_id)
        if open_id:
            return str(open_id)
    return None


def _load_agent_roster_index() -> dict[str, dict[str, Any]]:
    """加载结构化 roster，并按 agentId 建索引。"""
    roster_path = _resolved_openclaw_roster_path()
    version = _path_cache_version(roster_path)

    def _loader() -> dict[str, dict[str, Any]]:
        if not roster_path.exists():
            return {}

        try:
            data = json.loads(roster_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        agents = data.get("agents") if isinstance(data, dict) else None
        if not isinstance(agents, list):
            return {}

        index: dict[str, dict[str, Any]] = {}
        for item in agents:
            if not isinstance(item, dict):
                continue
            agent_id = item.get("agentId")
            if not agent_id:
                continue
            index[str(agent_id)] = item
        return index

    return _ROSTER_INDEX_CACHE.get(f"roster:{roster_path.resolve()}", version, _loader)


def _first_channel_account_id(roster_row: dict[str, Any], preferred_channel: str | None = None) -> str | None:
    channels = roster_row.get("channels")
    if not isinstance(channels, list):
        return None
    for row in channels:
        if not isinstance(row, dict):
            continue
        channel = _clean_remote_value(row.get("channel"))
        if preferred_channel and channel != preferred_channel:
            continue
        account_id = row.get("accountId")
        if account_id:
            return str(account_id)
    if preferred_channel:
        return _first_channel_account_id(roster_row, preferred_channel=None)
    return None


def _binding_account_ids_by_agent(bindings: Any) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    if not isinstance(bindings, list):
        return index
    for row in bindings:
        if not isinstance(row, dict):
            continue
        agent_id = _clean_remote_value(row.get("agentId"))
        match = row.get("match")
        if not agent_id or not isinstance(match, dict):
            continue
        channel = _clean_remote_value(match.get("channel"))
        account_id = _clean_remote_value(match.get("accountId"))
        if not channel or not account_id:
            continue
        index.setdefault(agent_id, {}).setdefault(channel, account_id)
    return index


def _normalize_agent_channel_name(channel: str | None) -> str | None:
    normalized = _clean_remote_value(channel)
    if not normalized:
        return None
    if normalized == "openclaw-weixin":
        return "weixin"
    return normalized


def _derive_agent_channel_state(
    agent_id: str,
    config: dict[str, Any],
    *,
    open_id: str | None = None,
) -> dict[str, Any]:
    agents_config = config.get("agents") if isinstance(config, dict) else {}
    if not isinstance(agents_config, dict):
        agents_config = {}
    agent_rows = agents_config.get("list") or []

    agent_row: dict[str, Any] = {}
    for row in agent_rows:
        if isinstance(row, dict) and str(row.get("id") or "").strip() == agent_id:
            agent_row = row
            break

    bindings = config.get("bindings") or []
    binding_channels = _binding_account_ids_by_agent(bindings).get(agent_id, {})
    feishu_config = ((config.get("channels") or {}).get("feishu") or {})
    feishu_accounts = feishu_config.get("accounts") if isinstance(feishu_config, dict) else {}
    if not isinstance(feishu_accounts, dict):
        feishu_accounts = {}

    raw_primary = _normalize_agent_channel_name(str(agent_row.get("channel") or "").strip())
    ordered_channels: list[tuple[str, str]] = []
    seen_channels: set[str] = set()

    if raw_primary:
        account_id = binding_channels.get(raw_primary)
        if account_id:
            ordered_channels.append((raw_primary, account_id))
            seen_channels.add(raw_primary)

    for raw_channel, account_id in binding_channels.items():
        normalized_channel = _normalize_agent_channel_name(raw_channel)
        if not normalized_channel or normalized_channel in seen_channels:
            continue
        ordered_channels.append((normalized_channel, account_id))
        seen_channels.add(normalized_channel)

    primary_channel = raw_primary or (ordered_channels[0][0] if ordered_channels else None)
    resolved_open_id = open_id or _get_agent_open_id(feishu_config, agent_id)

    connected_channels: list[dict[str, Any]] = []
    for channel, account_id in ordered_channels:
        status = "configured"
        reason = None
        if channel == "feishu":
            account_payload = feishu_accounts.get(account_id) or feishu_accounts.get(agent_id)
            if not isinstance(account_payload, dict):
                status = "warning"
                reason = "feishu_credentials_missing"
            elif not resolved_open_id:
                status = "warning"
                reason = "feishu_identity_missing"
        elif channel == "weixin" and not account_id:
            status = "warning"
            reason = "weixin_account_missing"

        connected_channels.append(
            {
                "channel": channel,
                "account_id": account_id,
                "primary": channel == primary_channel,
                "status": status,
                "reason": reason,
            }
        )

    channel_status = "missing"
    channel_status_reason = "channel_missing"
    if connected_channels:
        warning = next((item for item in connected_channels if item["status"] == "warning"), None)
        if warning:
            channel_status = "warning"
            channel_status_reason = warning.get("reason") or "channel_warning"
        else:
            channel_status = "configured"
            channel_status_reason = "channel_connected"

    primary_account_id = next(
        (item.get("account_id") for item in connected_channels if item.get("primary") and item.get("account_id")),
        None,
    )

    return {
        "primary_channel": primary_channel,
        "connected_channels": connected_channels,
        "channel_status": channel_status,
        "channel_status_reason": channel_status_reason,
        "primary_account_id": primary_account_id,
    }


def _agent_id_from_workspace_name(name: str) -> str | None:
    if name == "workspace":
        return "main"
    if name.startswith("workspace-"):
        return name.removeprefix("workspace-")
    return None


def _clean_identity_value(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip().strip("`").strip()
    if not text:
        return None
    if "待设置" in text or text.upper() == "N/A":
        return None
    return text


def _parse_identity_md(path: Path) -> dict[str, str | None]:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return {"emoji": None, "avatar_hint": None, "avatar_url": None}

    emoji: str | None = None
    avatar_hint: str | None = None
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if emoji is None:
            m = re.match(r"^-\s*\*\*Emoji\*\*\s*[:：]\s*(.+)$", line, flags=re.IGNORECASE)
            if m:
                emoji = _clean_identity_value(m.group(1))
                continue
        if avatar_hint is None:
            m = re.match(r"^-\s*\*\*Avatar\*\*\s*[:：]\s*(.+)$", line, flags=re.IGNORECASE)
            if m:
                avatar_hint = _clean_identity_value(m.group(1))

    avatar_url = None
    if avatar_hint and avatar_hint.startswith(("http://", "https://")):
        avatar_url = avatar_hint

    return {"emoji": emoji, "avatar_hint": avatar_hint, "avatar_url": avatar_url}


def _load_identity_index() -> dict[str, dict[str, str | None]]:
    try:
        host_root = _resolved_openclaw_host_root()
        candidates = list(host_root.glob("workspace*/IDENTITY.md"))
    except Exception:
        return {}

    version = _paths_cache_version([host_root, *candidates])

    def _loader() -> dict[str, dict[str, str | None]]:
        index: dict[str, dict[str, str | None]] = {}
        for id_file in candidates:
            agent_id = _agent_id_from_workspace_name(id_file.parent.name)
            if not agent_id:
                continue
            index[agent_id] = _parse_identity_md(id_file)
        return index

    return _IDENTITY_INDEX_CACHE.get(f"identity:{host_root.resolve()}", version, _loader)


def _load_openclaw_config() -> dict[str, Any]:
    config_path = _resolved_openclaw_config_path()
    version = _path_cache_version(config_path)

    def _loader() -> dict[str, Any]:
        if not config_path.exists():
            return {}
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return config if isinstance(config, dict) else {}

    return _OPENCLAW_CONFIG_CACHE.get(f"config:{config_path.resolve()}", version, _loader)


def _load_openclaw_config_document_for_write() -> dict[str, Any]:
    config_path = _resolved_openclaw_config_path()
    if not config_path.exists():
        return {}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("openclaw_config_invalid_json") from exc
    if not isinstance(config, dict):
        raise ValueError("openclaw_config_root_invalid")
    return config


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=path.suffix or ".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        Path(temp_name).replace(path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _get_agent_db_row(agent_id: str) -> sqlite3.Row | None:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return None

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
    if row is not None:
        return row

    config = _load_openclaw_config()
    configured_rows = ((config.get("agents") or {}).get("list") or []) if isinstance(config, dict) else []
    if any(isinstance(item, dict) and str(item.get("id") or "").strip() == normalized_agent_id for item in configured_rows):
        sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
        with get_conn() as conn:
            return conn.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
    return None


def _feishu_accounts_from_config(config: dict[str, Any]) -> dict[str, Any]:
    feishu_config = ((config.get("channels") or {}).get("feishu") or {})
    accounts = feishu_config.get("accounts") if isinstance(feishu_config, dict) else {}
    return accounts if isinstance(accounts, dict) else {}


def _get_agent_lightweight_payload(
    agent_id: str,
    *,
    config: dict[str, Any] | None = None,
    roster_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    active_config = config if isinstance(config, dict) else _load_openclaw_config()
    active_roster_index = roster_index if isinstance(roster_index, dict) else _load_agent_roster_index()
    row = _get_agent_db_row(agent_id)
    if row is None:
        return None

    item = dict(row)
    item.update(_derive_agent_runtime_fields(item["agent_id"], active_config, open_id=item.get("open_id")))
    roster = active_roster_index.get(item["agent_id"]) or {}
    if roster:
        role_summary = roster.get("roleSummary")
        if role_summary:
            item["role"] = str(role_summary)
        item["display_name"] = _resolve_display_name(item["agent_id"], roster, item)
        item["role_summary"] = str(role_summary) if role_summary else None
        item["skills"] = [str(value) for value in (roster.get("skills") or [])]
        item["core_work"] = [str(value) for value in (roster.get("coreWork") or [])]
    else:
        item["role_summary"] = None
        item["skills"] = []
        item["core_work"] = []

    if item.get("channel") == "feishu":
        feishu_accounts = _feishu_accounts_from_config(active_config)
        account_id = str(item.get("account_id") or item["agent_id"])
        cached_profile = _extract_cached_feishu_account_profile(
            feishu_accounts.get(account_id) or feishu_accounts.get(item["agent_id"])
        )
        if cached_profile.get("name") and _is_default_lobster_placeholder_name(item["agent_id"], item.get("display_name")):
            item["display_name"] = str(cached_profile["name"]).strip()
        if not item.get("open_id") and cached_profile.get("open_id"):
            item["open_id"] = cached_profile.get("open_id")
        if cached_profile.get("avatar_url"):
            item["avatar_url"] = cached_profile.get("avatar_url")
    return item


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _normalize_model_ref(provider: Any, model_id: Any) -> tuple[str | None, str | None]:
    provider_text = _clean_remote_value(provider)
    model_text = _clean_remote_value(model_id)
    if model_text and "/" in model_text and not provider_text:
        maybe_provider, maybe_model = model_text.split("/", 1)
        if maybe_provider and maybe_model:
            return maybe_provider, maybe_model
    return provider_text, model_text


def _model_label(provider: str | None, model_id: str | None) -> str | None:
    if provider and model_id:
        return f"{provider}/{model_id}"
    return model_id or provider


def _parse_timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = int(value)
        if raw <= 0:
            return None
        return raw if raw >= 1_000_000_000_000 else raw * 1000

    text = str(value).strip()
    if not text:
        return None
    parsed_int = _safe_int(text)
    if parsed_int is not None and parsed_int > 0:
        return parsed_int if parsed_int >= 1_000_000_000_000 else parsed_int * 1000
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def _model_sort_key(timestamp_ms: int | None, order: int = 0) -> tuple[int, int]:
    return (int(timestamp_ms or 0), order)


def _extract_model_candidate(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, str):
        return _normalize_model_ref(None, value)

    if isinstance(value, list):
        for item in value:
            provider, model_id = _extract_model_candidate(item)
            if provider or model_id:
                return provider, model_id
        return None, None

    if not isinstance(value, dict):
        return None, None

    provider = value.get("provider") or value.get("vendor")
    model_ref = (
        value.get("modelRef")
        or value.get("ref")
        or value.get("model_id")
        or value.get("modelId")
        or value.get("model")
    )
    if model_ref is None and provider:
        model_ref = value.get("id")

    if isinstance(model_ref, dict):
        return _extract_model_candidate(model_ref)
    if isinstance(model_ref, list):
        return _extract_model_candidate(model_ref)

    provider_text, model_text = _normalize_model_ref(provider, model_ref)
    if provider_text or model_text:
        return provider_text, model_text

    primary = value.get("primary")
    if primary is not None:
        return _extract_model_candidate(primary)

    models = value.get("models")
    if models is not None:
        return _extract_model_candidate(models)

    return None, None


def _resolve_agent_config_model(config: dict[str, Any], agent_id: str) -> tuple[str | None, str | None]:
    agents_config = config.get("agents") if isinstance(config, dict) else None
    if not isinstance(agents_config, dict):
        return None, None

    agent_rows = agents_config.get("list")
    if isinstance(agent_rows, list):
        for row in agent_rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("id") or "") != agent_id:
                continue
            provider, model_id = _extract_model_candidate(row.get("models") or row)
            if provider or model_id:
                return provider, model_id

    defaults = agents_config.get("defaults")
    if isinstance(defaults, dict):
        return _extract_model_candidate(defaults.get("models") or defaults)

    return None, None


def _agent_sessions_root(agent_id: str) -> Path:
    return (_resolved_openclaw_host_root() / "agents" / agent_id / "sessions").resolve()


def _load_agent_session_records(agent_id: str) -> list[dict[str, Any]]:
    sessions_root = _agent_sessions_root(agent_id)
    if not sessions_root.exists() or not sessions_root.is_dir():
        return []

    manifest_path = sessions_root / "sessions.json"
    related_paths: list[Path] = [sessions_root]
    if manifest_path.exists():
        related_paths.append(manifest_path)
    else:
        related_paths.extend(sessions_root.glob("*.jsonl"))
    version = _paths_cache_version(related_paths)

    def _loader() -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                for row in payload.values():
                    if not isinstance(row, dict):
                        continue
                    session_id = _clean_remote_value(row.get("sessionId"))
                    session_file = row.get("sessionFile")
                    resolved_file: Path | None = None
                    if session_file:
                        try:
                            resolved_file = _map_visible_openclaw_path(Path(str(session_file)))
                        except Exception:
                            resolved_file = None
                    if resolved_file is None and session_id:
                        candidate = sessions_root / f"{session_id}.jsonl"
                        if candidate.exists():
                            resolved_file = candidate
                    records.append(
                        {
                            "session_id": session_id,
                            "updated_at_ms": _safe_int(row.get("updatedAt")) or 0,
                            "session_file": resolved_file,
                            "row": row,
                        }
                    )

        if not records:
            for item in sorted(sessions_root.glob("*.jsonl")):
                try:
                    updated_at_ms = int(item.stat().st_mtime * 1000)
                except OSError:
                    updated_at_ms = 0
                records.append(
                    {
                        "session_id": item.stem,
                        "updated_at_ms": updated_at_ms,
                        "session_file": item,
                        "row": {},
                    }
                )

        records.sort(key=lambda item: (item.get("updated_at_ms") or 0, str(item.get("session_id") or "")))
        return records

    return _SESSION_RECORDS_CACHE.get(f"sessions:{agent_id}:{sessions_root.resolve()}", version, _loader)


def _find_usage_blob(value: Any, *, depth: int = 0) -> dict[str, Any] | None:
    if depth > 4:
        return None
    if isinstance(value, dict):
        usage_keys = {
            "inputTokens",
            "outputTokens",
            "totalTokens",
            "contextTokens",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimatedCostUsd",
            "costUsd",
        }
        if any(key in value for key in usage_keys):
            return value

        for key in ("responseUsage", "usage", "message", "data", "payload", "metadata", "meta"):
            if key in value:
                found = _find_usage_blob(value[key], depth=depth + 1)
                if found:
                    return found
    elif isinstance(value, list):
        for item in value[:8]:
            found = _find_usage_blob(item, depth=depth + 1)
            if found:
                return found
    return None


def _usage_blob_to_metrics(blob: dict[str, Any]) -> dict[str, float | int | None]:
    input_tokens = _safe_int(blob.get("inputTokens") or blob.get("promptTokens") or blob.get("input_tokens"))
    output_tokens = _safe_int(
        blob.get("outputTokens") or blob.get("completionTokens") or blob.get("output_tokens")
    )
    total_tokens = _safe_int(blob.get("totalTokens") or blob.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "context_tokens": _safe_int(blob.get("contextTokens") or blob.get("context_tokens")),
        "estimated_cost_usd": _safe_float(
            blob.get("estimatedCostUsd")
            or blob.get("estimated_cost_usd")
            or blob.get("costUsd")
            or blob.get("cost_usd")
            or blob.get("cost")
        ),
    }


def _scan_session_transcript(session_file: Path) -> dict[str, Any]:
    version = _path_cache_version(session_file)

    def _loader() -> dict[str, Any]:
        summary = {
            "usage_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "context_tokens": 0,
            "estimated_cost_usd": 0.0,
            "has_input_tokens": False,
            "has_output_tokens": False,
            "has_total_tokens": False,
            "has_context_tokens": False,
            "has_cost": False,
            "latest_model_provider": None,
            "latest_model_id": None,
            "latest_model_sort_key": _model_sort_key(None, -1),
        }
        try:
            handle = session_file.open(encoding="utf-8", errors="replace")
        except Exception:
            return summary

        with handle:
            for line_number, line in enumerate(handle):
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue

                marker = _model_sort_key(_parse_timestamp_ms(row.get("timestamp")), line_number)
                if row.get("type") == "model_change":
                    provider, model_id = _extract_model_candidate(row)
                    if (provider or model_id) and marker >= tuple(summary["latest_model_sort_key"]):
                        summary["latest_model_provider"] = provider
                        summary["latest_model_id"] = model_id
                        summary["latest_model_sort_key"] = marker

                usage_blob = _find_usage_blob(row)
                if not usage_blob:
                    continue

                metrics = _usage_blob_to_metrics(usage_blob)
                summary["usage_count"] = int(summary["usage_count"]) + 1
                for key in ("input_tokens", "output_tokens", "total_tokens", "context_tokens"):
                    value = metrics[key]
                    if value is None:
                        continue
                    summary[key] = int(summary[key]) + int(value)
                    summary[f"has_{key}"] = True
                cost_value = metrics["estimated_cost_usd"]
                if cost_value is not None:
                    summary["estimated_cost_usd"] = float(summary["estimated_cost_usd"]) + float(cost_value)
                    summary["has_cost"] = True

                provider, model_id = _extract_model_candidate(
                    usage_blob.get("model")
                    or {
                        "provider": usage_blob.get("provider"),
                        "modelId": usage_blob.get("modelId") or usage_blob.get("model_id"),
                    }
                )
                if (provider or model_id) and marker >= tuple(summary["latest_model_sort_key"]):
                    summary["latest_model_provider"] = provider
                    summary["latest_model_id"] = model_id
                    summary["latest_model_sort_key"] = marker

        return summary

    return _TRANSCRIPT_SUMMARY_CACHE.get(f"transcript:{session_file.resolve()}", version, _loader)


def _resolve_agent_local_usage_summary(agent_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    active_config = config if isinstance(config, dict) else _load_openclaw_config()
    config_provider, config_model_id = _resolve_agent_config_model(active_config, agent_id)
    records = _load_agent_session_records(agent_id)

    recent_model_provider: str | None = None
    recent_model_id: str | None = None
    recent_model_sort_key = _model_sort_key(None, -1)

    input_tokens_total = 0
    output_tokens_total = 0
    total_tokens_total = 0
    context_tokens_total = 0
    estimated_cost_total = 0.0
    has_input_tokens = False
    has_output_tokens = False
    has_total_tokens = False
    has_context_tokens = False
    has_cost = False

    for record in records:
        manifest_row = record.get("row") if isinstance(record.get("row"), dict) else {}
        updated_marker = _model_sort_key(record.get("updated_at_ms"), 0)

        provider, model_id = _extract_model_candidate(manifest_row)
        if (provider or model_id) and updated_marker >= recent_model_sort_key:
            recent_model_provider = provider
            recent_model_id = model_id
            recent_model_sort_key = updated_marker

        transcript = None
        session_file = record.get("session_file")
        if isinstance(session_file, Path) and session_file.exists() and session_file.is_file():
            transcript = _scan_session_transcript(session_file)
            transcript_provider = transcript.get("latest_model_provider")
            transcript_model_id = transcript.get("latest_model_id")
            transcript_marker = tuple(transcript.get("latest_model_sort_key") or _model_sort_key(None, -1))
            if (transcript_provider or transcript_model_id) and transcript_marker >= recent_model_sort_key:
                recent_model_provider = transcript_provider
                recent_model_id = transcript_model_id
                recent_model_sort_key = transcript_marker

        used_transcript_metrics = bool(transcript and int(transcript.get("usage_count") or 0) > 0)
        if used_transcript_metrics:
            if transcript.get("has_input_tokens"):
                input_tokens_total += int(transcript.get("input_tokens") or 0)
                has_input_tokens = True
            if transcript.get("has_output_tokens"):
                output_tokens_total += int(transcript.get("output_tokens") or 0)
                has_output_tokens = True
            if transcript.get("has_total_tokens"):
                total_tokens_total += int(transcript.get("total_tokens") or 0)
                has_total_tokens = True
            if transcript.get("has_context_tokens"):
                context_tokens_total += int(transcript.get("context_tokens") or 0)
                has_context_tokens = True
            if transcript.get("has_cost"):
                estimated_cost_total += float(transcript.get("estimated_cost_usd") or 0.0)
                has_cost = True
            continue

        manifest_input = _safe_int(manifest_row.get("inputTokens") or manifest_row.get("input_tokens"))
        manifest_output = _safe_int(manifest_row.get("outputTokens") or manifest_row.get("output_tokens"))
        manifest_total = _safe_int(manifest_row.get("totalTokens") or manifest_row.get("total_tokens"))
        manifest_context = _safe_int(manifest_row.get("contextTokens") or manifest_row.get("context_tokens"))
        manifest_cost = _safe_float(
            manifest_row.get("estimatedCostUsd")
            or manifest_row.get("estimated_cost_usd")
            or manifest_row.get("costUsd")
            or manifest_row.get("cost")
        )

        if manifest_input is not None:
            input_tokens_total += manifest_input
            has_input_tokens = True
        if manifest_output is not None:
            output_tokens_total += manifest_output
            has_output_tokens = True
        if manifest_total is not None:
            total_tokens_total += manifest_total
            has_total_tokens = True
        elif manifest_input is not None and manifest_output is not None:
            total_tokens_total += manifest_input + manifest_output
            has_total_tokens = True
        if manifest_context is not None:
            context_tokens_total += manifest_context
            has_context_tokens = True
        if manifest_cost is not None:
            estimated_cost_total += manifest_cost
            has_cost = True

    if not has_total_tokens and has_input_tokens and has_output_tokens:
        total_tokens_total = input_tokens_total + output_tokens_total
        has_total_tokens = True

    display_provider = config_provider or recent_model_provider
    display_model_id = config_model_id or recent_model_id

    return {
        "model_provider": display_provider,
        "model_id": display_model_id,
        "model_label": _model_label(display_provider, display_model_id),
        "config_model_provider": config_provider,
        "config_model_id": config_model_id,
        "config_model_label": _model_label(config_provider, config_model_id),
        "recent_model_provider": recent_model_provider,
        "recent_model_id": recent_model_id,
        "recent_model_label": _model_label(recent_model_provider, recent_model_id),
        "usage_input_tokens": input_tokens_total if has_input_tokens else None,
        "usage_output_tokens": output_tokens_total if has_output_tokens else None,
        "usage_total_tokens": total_tokens_total if has_total_tokens else None,
        "usage_context_tokens": context_tokens_total if has_context_tokens else None,
        "estimated_cost_usd": round(estimated_cost_total, 6) if has_cost else None,
    }


def _clean_remote_value(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _http_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 8) -> dict[str, Any] | None:
    body = None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = Request(url, data=body, headers=req_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except (TimeoutError, URLError, ValueError):
        return None

    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _run_openclaw_cli_json(args: list[str], *, timeout: int = 8) -> dict[str, Any] | None:
    if not OPENCLAW_CLI_BIN:
        return None
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return _extract_json_object_from_text(completed.stdout or "")


def _extract_json_object_from_text(raw: str | None) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    candidates = [text]
    first_object_index = text.find("{")
    if first_object_index > 0:
        candidates.append(text[first_object_index:].strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _extract_openclaw_version(raw: str | None) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    match = re.search(r"OpenClaw\s+([^\s]+)", text)
    if match:
        return str(match.group(1)).strip() or None
    fallback = text.splitlines()[0].strip()
    return fallback or None


def _refresh_openclaw_cli_bin() -> str:
    global OPENCLAW_CLI_BIN
    OPENCLAW_CLI_BIN = _detect_openclaw_cli_bin()
    return OPENCLAW_CLI_BIN


def _read_openclaw_cli_status_summary() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "openclaw_cli_installed": bool(OPENCLAW_CLI_BIN),
        "openclaw_cli_path": OPENCLAW_CLI_BIN or None,
        "openclaw_current_version": None,
        "openclaw_latest_version": None,
        "openclaw_update_available": False,
    }
    if not OPENCLAW_CLI_BIN:
        return payload

    try:
        version_text = _run_openclaw_cli_text([OPENCLAW_CLI_BIN, "--version"], timeout=8)
        payload["openclaw_current_version"] = _extract_openclaw_version(version_text)
    except RuntimeError:
        pass

    update_status = _run_openclaw_cli_json([OPENCLAW_CLI_BIN, "update", "status", "--json"], timeout=12)
    if not update_status:
        return payload

    availability = update_status.get("availability") if isinstance(update_status.get("availability"), dict) else {}
    update = update_status.get("update") if isinstance(update_status.get("update"), dict) else {}
    registry = update.get("registry") if isinstance(update.get("registry"), dict) else {}
    latest_version = str(availability.get("latestVersion") or registry.get("latestVersion") or "").strip() or None
    payload["openclaw_latest_version"] = latest_version
    payload["openclaw_update_available"] = bool(
        availability.get("hasRegistryUpdate") or availability.get("hasGitUpdate") or False
    )
    return payload


def _resolve_openclaw_install_command() -> list[str]:
    if shutil.which("pnpm"):
        return ["pnpm", "add", "-g", "openclaw@latest"]
    if shutil.which("npm"):
        return ["npm", "install", "-g", "openclaw@latest"]
    raise RuntimeError("node_package_manager_unavailable")


def run_openclaw_update_status() -> dict[str, Any]:
    summary = _read_openclaw_cli_status_summary()
    if not summary.get("openclaw_cli_installed"):
        raise RuntimeError("openclaw_cli_unavailable")
    return {"summary": summary}


def run_openclaw_install_latest() -> dict[str, Any]:
    before = _read_openclaw_cli_status_summary()
    command = _resolve_openclaw_install_command()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("openclaw_install_failed:install_command_unavailable") from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip() or f"exit_code_{completed.returncode}"
        raise RuntimeError(f"openclaw_install_failed:{message}")
    cli_path = _refresh_openclaw_cli_bin()
    if not cli_path:
        raise RuntimeError("openclaw_install_failed:cli_not_detected_after_install")
    after = _read_openclaw_cli_status_summary()
    return {
        "command": command,
        "stdout": (completed.stdout or "").strip() or None,
        "stderr": (completed.stderr or "").strip() or None,
        "before": before,
        "after": after,
    }


def run_openclaw_update_install() -> dict[str, Any]:
    if not OPENCLAW_CLI_BIN:
        raise RuntimeError("openclaw_cli_unavailable")
    before = _read_openclaw_cli_status_summary()
    output = _run_openclaw_cli_text([OPENCLAW_CLI_BIN, "update", "--yes", "--json"], timeout=900)
    update_payload = _extract_json_object_from_text(output)
    after = _read_openclaw_cli_status_summary()
    return {
        "before": before,
        "update": update_payload or {"stdout": output},
        "after": after,
    }


def _run_openclaw_cli_text(args: list[str], *, timeout: int = 20) -> str:
    if not OPENCLAW_CLI_BIN:
        raise RuntimeError("openclaw_cli_unavailable")
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("openclaw_cli_unavailable") from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip() or f"exit_code_{completed.returncode}"
        raise RuntimeError(f"openclaw_cli_failed:{message}")
    return (completed.stdout or "").strip()


def _run_openclaw_cli_text_with_env(args: list[str], *, timeout: int = 20, env_overrides: dict[str, str] | None = None) -> str:
    if not OPENCLAW_CLI_BIN:
        raise RuntimeError("openclaw_cli_unavailable")
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("openclaw_cli_unavailable") from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip() or f"exit_code_{completed.returncode}"
        raise RuntimeError(f"openclaw_cli_failed:{message}")
    return (completed.stdout or "").strip()


def _iter_json_scalar_strings(payload: Any) -> Iterable[str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield str(key)
            yield from _iter_json_scalar_strings(value)
        return
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_json_scalar_strings(item)
        return
    if isinstance(payload, (str, int, float, bool)):
        text = str(payload).strip()
        if text:
            yield text


def _extract_official_runtime_host_signal(payload: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    scalar_text = " ".join(text.lower() for text in _iter_json_scalar_strings(payload))
    if not scalar_text:
        return None

    host_online: bool | None = None
    work_state: str | None = None
    reason = "官方信号可用，但未识别出明确运行态。"

    if "workingmain" in scalar_text or "workingother" in scalar_text or " working " in f" {scalar_text} ":
        work_state = "working"
        host_online = True
        reason = "官方 work state 显示当前存在活跃工作。"
    elif " idle " in f" {scalar_text} ":
        host_online = True
        reason = "官方信号显示当前宿主可达，但没有活跃工作。"

    offline_tokens = (" offline ", " unreachable ", " disconnected ", " stale ", " timeout ")
    online_tokens = (" online ", " connected ", " reachable ", " active ", " healthy ", " ok ")

    if any(token in f" {scalar_text} " for token in offline_tokens):
        host_online = False
        reason = "官方 liveness / health 信号显示宿主不可达或已 stale。"
    elif host_online is None and any(token in f" {scalar_text} " for token in online_tokens):
        host_online = True
        reason = "官方 liveness / health 信号显示宿主可达。"

    if host_online is None and work_state is None:
        return None

    return {
        "host_online": host_online,
        "work_state": work_state,
        "source": source,
        "reason": reason,
        "observed_at": now_iso(),
    }


def _read_official_runtime_host_signal(force_refresh: bool = False) -> dict[str, Any] | None:
    now = time.time()
    if (
        not force_refresh
        and _OFFICIAL_RUNTIME_SIGNAL_CACHE.get("loaded_at")
        and now - float(_OFFICIAL_RUNTIME_SIGNAL_CACHE["loaded_at"]) < AGENT_RUNTIME_OFFICIAL_SIGNAL_CACHE_TTL_SEC
    ):
        cached = _OFFICIAL_RUNTIME_SIGNAL_CACHE.get("value")
        return cached if isinstance(cached, dict) else None

    signal: dict[str, Any] | None = None
    if OPENCLAW_CLI_BIN:
        status_payload = _run_openclaw_cli_json([OPENCLAW_CLI_BIN, "status", "--json"], timeout=6)
        if isinstance(status_payload, dict):
            signal = _extract_official_runtime_host_signal(status_payload, source="official_status")
        if signal is None:
            health_payload = _run_openclaw_cli_json([OPENCLAW_CLI_BIN, "health", "--json"], timeout=8)
            if isinstance(health_payload, dict):
                signal = _extract_official_runtime_host_signal(health_payload, source="official_health")

    _OFFICIAL_RUNTIME_SIGNAL_CACHE["value"] = signal
    _OFFICIAL_RUNTIME_SIGNAL_CACHE["loaded_at"] = now
    return signal


def _fetch_feishu_bot_profile(app_id: str, app_secret: str) -> dict[str, str | None] | None:
    token = _fetch_feishu_tenant_token(app_id, app_secret)
    if not token:
        return None

    bot_resp = _http_json(
        FEISHU_BOT_INFO_URL,
        headers={"Authorization": f"Bearer {token}"},
    )
    if not bot_resp:
        return None
    bot = bot_resp.get("bot")
    if not isinstance(bot, dict):
        return None
    return {
        "avatar_url": _clean_remote_value(bot.get("avatar_url")),
        "open_id": _clean_remote_value(bot.get("open_id")),
        "name": _clean_remote_value(bot.get("app_name")),
    }


def _fetch_feishu_tenant_token(app_id: str, app_secret: str) -> str | None:
    token_resp = _http_json(
        FEISHU_TENANT_TOKEN_URL,
        method="POST",
        payload={"app_id": app_id, "app_secret": app_secret},
    )
    if not token_resp:
        return None
    return _clean_remote_value(token_resp.get("tenant_access_token"))


def _extract_cached_feishu_account_profile(account: Any) -> dict[str, str | None]:
    if not isinstance(account, dict):
        return {"name": None, "avatar_url": None, "open_id": None}
    return {
        "name": _clean_remote_value(account.get("appName") or account.get("displayName") or account.get("name")),
        "avatar_url": _clean_remote_value(account.get("avatarUrl") or account.get("avatar_url")),
        "open_id": _clean_remote_value(account.get("openId") or account.get("open_id")),
    }


def _get_feishu_account_credentials(account_id: str) -> tuple[str, str] | None:
    config = _load_openclaw_config()
    feishu = ((config.get("channels") or {}).get("feishu") or {})
    accounts = feishu.get("accounts")
    if not isinstance(accounts, dict):
        return None

    account = accounts.get(account_id)
    if not isinstance(account, dict):
        return None
    app_id = _clean_remote_value(account.get("appId"))
    app_secret = _clean_remote_value(account.get("appSecret"))
    if not app_id or not app_secret:
        return None
    return app_id, app_secret


def _get_feishu_app_access_token(app_id: str, app_secret: str) -> str | None:
    token_resp = _http_json(
        FEISHU_APP_ACCESS_TOKEN_URL,
        method="POST",
        payload={"app_id": app_id, "app_secret": app_secret},
    )
    if not token_resp:
        return None
    return _clean_remote_value(token_resp.get("app_access_token"))


def _feishu_json_request(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"feishu_http_failed:{resp.status_code}:{resp.text[:300]}")
    data = resp.json()
    if int(data.get("code", -1)) != 0:
        raise RuntimeError(f"feishu_http_failed:{data.get('code')}:{data.get('msg')}")
    payload_data = data.get("data")
    return payload_data if isinstance(payload_data, dict) else {}


def _is_user_auth_supported(agent_id: str) -> bool:
    return agent_id in FEISHU_USER_AUTH_AGENT_IDS


def _get_feishu_user_auth_redirect_uri(agent_id: str) -> str | None:
    if not OPENCLAW_PUBLIC_BASE_URL:
        return None
    return f"{OPENCLAW_PUBLIC_BASE_URL}/api/agents/{agent_id}/user-auth/callback"


def _serialize_scope(scope: Any) -> str | None:
    if isinstance(scope, list):
        parts = [str(item).strip() for item in scope if str(item).strip()]
        return " ".join(parts) if parts else None
    if scope is None:
        return None
    text = str(scope).strip()
    return text or None


def _get_stored_agent_user_auth(agent_id: str, user_key: str = FEISHU_USER_AUTH_USER_KEY) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT agent_id, user_key, access_token, refresh_token, scope, user_name,
                   user_open_id, user_union_id, authorized_at, expires_at, updated_at
            FROM agent_user_auth
            WHERE agent_id = ? AND user_key = ?
            """,
            (agent_id, user_key),
        ).fetchone()
    return dict(row) if row else None


def get_agent_user_auth_state(agent_id: str, user_key: str = FEISHU_USER_AUTH_USER_KEY) -> dict[str, Any]:
    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")

    supported = _is_user_auth_supported(agent_id)
    callback_ready = bool(_get_feishu_user_auth_redirect_uri(agent_id))
    stored = _get_stored_agent_user_auth(agent_id, user_key=user_key)
    message = None
    if supported and not callback_ready:
        message = "未配置公网回调地址，暂时无法发起用户授权。"
    elif not supported:
        message = "当前仅对已接入用户凭证的 Agent 开放。"

    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "supported": supported,
        "callback_ready": callback_ready,
        "authorized": bool(stored and stored.get("access_token")),
        "user_label": stored.get("user_name") if stored else None,
        "user_open_id": stored.get("user_open_id") if stored else None,
        "scope": stored.get("scope") if stored else None,
        "authorized_at": stored.get("authorized_at") if stored else None,
        "expires_at": stored.get("expires_at") if stored else None,
        "message": message,
    }


def start_agent_user_auth(agent_id: str, user_key: str = FEISHU_USER_AUTH_USER_KEY) -> dict[str, Any]:
    state_info = get_agent_user_auth_state(agent_id, user_key=user_key)
    if not state_info["supported"]:
        raise ValueError("agent_user_auth_not_enabled")

    redirect_uri = _get_feishu_user_auth_redirect_uri(agent_id)
    if not redirect_uri:
        raise ValueError("public_base_url_not_configured")

    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")

    credentials = _get_feishu_account_credentials(str(agent.get("account_id") or agent_id))
    if not credentials:
        raise RuntimeError("target_feishu_credentials_missing")
    app_id, _app_secret = credentials

    state = f"fau_{uuid.uuid4().hex}"
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(seconds=FEISHU_USER_AUTH_STATE_TTL_SEC)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_user_oauth_states (state, agent_id, user_key, created_at, expires_at, used_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (state, agent_id, user_key, created_at.isoformat(), expires_at.isoformat()),
        )
        conn.commit()

    from urllib.parse import urlencode

    authorize_url = (
        f"{FEISHU_USER_AUTH_AUTHORIZE_URL}?"
        + urlencode(
            {
                "app_id": app_id,
                "redirect_uri": redirect_uri,
                "scope": FEISHU_USER_AUTH_SCOPE,
                "state": state,
            }
        )
    )
    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "authorize_url": authorize_url,
        "state": state,
        "expires_at": expires_at.isoformat(),
    }


def _consume_agent_user_oauth_state(state: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT state, agent_id, user_key, created_at, expires_at, used_at
            FROM agent_user_oauth_states
            WHERE state = ?
            """,
            (state,),
        ).fetchone()
        if not row:
            raise ValueError("oauth_state_not_found")
        payload = dict(row)
        if payload.get("used_at"):
            raise ValueError("oauth_state_already_used")
        expires_at = payload.get("expires_at")
        if expires_at:
            expires_at_dt = datetime.fromisoformat(str(expires_at))
            if expires_at_dt <= datetime.now(timezone.utc):
                raise ValueError("oauth_state_expired")
        conn.execute(
            "UPDATE agent_user_oauth_states SET used_at = ? WHERE state = ?",
            (now_iso(), state),
        )
        conn.commit()
    return payload


def _store_agent_user_auth(
    *,
    agent_id: str,
    user_key: str,
    access_token: str,
    refresh_token: str | None,
    scope: str | None,
    user_name: str | None,
    user_open_id: str | None,
    user_union_id: str | None,
    expires_in: int | None,
) -> dict[str, Any]:
    authorized_at = now_iso()
    expires_at = None
    if expires_in and expires_in > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_user_auth (
                agent_id, user_key, access_token, refresh_token, scope, user_name,
                user_open_id, user_union_id, authorized_at, expires_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, user_key) DO UPDATE SET
                access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,
                scope=excluded.scope,
                user_name=excluded.user_name,
                user_open_id=excluded.user_open_id,
                user_union_id=excluded.user_union_id,
                authorized_at=excluded.authorized_at,
                expires_at=excluded.expires_at,
                updated_at=excluded.updated_at
            """,
            (
                agent_id,
                user_key,
                access_token,
                refresh_token,
                scope,
                user_name,
                user_open_id,
                user_union_id,
                authorized_at,
                expires_at,
                authorized_at,
            ),
        )
        conn.commit()
    return get_agent_user_auth_state(agent_id, user_key=user_key)


def _fetch_feishu_user_info(user_access_token: str) -> dict[str, Any]:
    try:
        return _feishu_json_request(FEISHU_USER_INFO_URL, token=user_access_token)
    except Exception:
        return {}


def complete_agent_user_auth(
    *,
    agent_id: str,
    code: str,
    state: str,
) -> dict[str, Any]:
    state_row = _consume_agent_user_oauth_state(state)
    if state_row["agent_id"] != agent_id:
        raise ValueError("oauth_state_agent_mismatch")

    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")
    credentials = _get_feishu_account_credentials(str(agent.get("account_id") or agent_id))
    if not credentials:
        raise RuntimeError("target_feishu_credentials_missing")
    app_id, app_secret = credentials
    app_access_token = _get_feishu_app_access_token(app_id, app_secret)
    if not app_access_token:
        raise RuntimeError("feishu_app_access_token_fetch_failed")

    data = _feishu_json_request(
        FEISHU_USER_ACCESS_TOKEN_URL,
        method="POST",
        token=app_access_token,
        payload={"grant_type": "authorization_code", "code": code},
    )
    access_token = _clean_remote_value(data.get("access_token"))
    if not access_token:
        raise RuntimeError("feishu_user_access_token_missing")
    refresh_token = _clean_remote_value(data.get("refresh_token"))
    scope = _serialize_scope(data.get("scope"))
    expires_in = data.get("expires_in")
    user_name = _clean_remote_value(data.get("name"))
    user_open_id = _clean_remote_value(data.get("open_id"))
    user_union_id = _clean_remote_value(data.get("union_id"))

    if not user_name or not user_open_id:
        user_info = _fetch_feishu_user_info(access_token)
        user_name = user_name or _clean_remote_value(user_info.get("name"))
        user_open_id = user_open_id or _clean_remote_value(user_info.get("open_id"))
        user_union_id = user_union_id or _clean_remote_value(user_info.get("union_id"))

    return _store_agent_user_auth(
        agent_id=agent_id,
        user_key=state_row["user_key"],
        access_token=access_token,
        refresh_token=refresh_token,
        scope=scope,
        user_name=user_name,
        user_open_id=user_open_id,
        user_union_id=user_union_id,
        expires_in=int(expires_in) if isinstance(expires_in, int) else None,
    )


def _refresh_agent_user_auth(agent_id: str, user_key: str = FEISHU_USER_AUTH_USER_KEY) -> dict[str, Any]:
    stored = _get_stored_agent_user_auth(agent_id, user_key=user_key)
    if not stored:
        raise RuntimeError("agent_user_auth_missing")
    refresh_token = _clean_remote_value(stored.get("refresh_token"))
    if not refresh_token:
        raise RuntimeError("agent_user_refresh_token_missing")

    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")
    credentials = _get_feishu_account_credentials(str(agent.get("account_id") or agent_id))
    if not credentials:
        raise RuntimeError("target_feishu_credentials_missing")
    app_id, app_secret = credentials
    app_access_token = _get_feishu_app_access_token(app_id, app_secret)
    if not app_access_token:
        raise RuntimeError("feishu_app_access_token_fetch_failed")

    data = _feishu_json_request(
        FEISHU_USER_REFRESH_TOKEN_URL,
        method="POST",
        token=app_access_token,
        payload={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    access_token = _clean_remote_value(data.get("access_token"))
    if not access_token:
        raise RuntimeError("feishu_user_access_token_missing")
    next_refresh_token = _clean_remote_value(data.get("refresh_token")) or refresh_token
    scope = _serialize_scope(data.get("scope")) or stored.get("scope")
    expires_in = data.get("expires_in")
    user_name = _clean_remote_value(data.get("name")) or stored.get("user_name")
    user_open_id = _clean_remote_value(data.get("open_id")) or stored.get("user_open_id")
    user_union_id = _clean_remote_value(data.get("union_id")) or stored.get("user_union_id")

    return _store_agent_user_auth(
        agent_id=agent_id,
        user_key=user_key,
        access_token=access_token,
        refresh_token=next_refresh_token,
        scope=scope,
        user_name=user_name,
        user_open_id=user_open_id,
        user_union_id=user_union_id,
        expires_in=int(expires_in) if isinstance(expires_in, int) else None,
    )


def _get_valid_agent_user_access_token(agent_id: str, user_key: str = FEISHU_USER_AUTH_USER_KEY) -> str:
    stored = _get_stored_agent_user_auth(agent_id, user_key=user_key)
    if not stored:
        raise RuntimeError("agent_user_auth_missing")

    expires_at = stored.get("expires_at")
    should_refresh = False
    if expires_at:
        try:
            expires_dt = datetime.fromisoformat(str(expires_at))
            should_refresh = expires_dt <= (
                datetime.now(timezone.utc) + timedelta(seconds=FEISHU_USER_TOKEN_REFRESH_BUFFER_SEC)
            )
        except ValueError:
            should_refresh = False

    if should_refresh:
        _refresh_agent_user_auth(agent_id, user_key=user_key)
        access_token = _clean_remote_value(
            (_get_stored_agent_user_auth(agent_id, user_key=user_key) or {}).get("access_token")
        )
        if access_token:
            return access_token
        raise RuntimeError("agent_user_auth_refresh_failed")

    access_token = _clean_remote_value(stored.get("access_token"))
    if not access_token:
        raise RuntimeError("agent_user_auth_missing")
    return access_token


def _send_feishu_message(token: str, *, receive_open_id: str, msg_type: str, content: dict[str, Any]) -> str | None:
    resp = requests.post(
        FEISHU_MESSAGE_CREATE_URL,
        params={"receive_id_type": "open_id"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "receive_id": receive_open_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"feishu_send_failed:{resp.status_code}:{resp.text[:300]}")
    data = resp.json()
    if int(data.get("code", -1)) != 0:
        raise RuntimeError(f"feishu_send_failed:{data.get('code')}:{data.get('msg')}")
    message_id = (((data.get("data") or {}).get("message_id")) or "")
    return str(message_id) if message_id else None


def _upload_feishu_file(token: str, *, file_name: str, file_bytes: bytes) -> str:
    resp = requests.post(
        FEISHU_FILE_UPLOAD_URL,
        headers={"Authorization": f"Bearer {token}"},
        data={"file_type": "stream", "file_name": file_name},
        files={"file": (file_name, file_bytes, mimetypes.guess_type(file_name)[0] or "application/octet-stream")},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"feishu_upload_failed:{resp.status_code}:{resp.text[:300]}")
    data = resp.json()
    if int(data.get("code", -1)) != 0:
        raise RuntimeError(f"feishu_upload_failed:{data.get('code')}:{data.get('msg')}")
    file_key = (((data.get("data") or {}).get("file_key")) or "")
    if not file_key:
        raise RuntimeError("feishu_upload_failed:file_key_missing")
    return str(file_key)


def _get_feishu_bot_profile_index(force_refresh: bool = False) -> dict[str, dict[str, str | None]]:
    global _FEISHU_BOT_PROFILE_CACHE, _FEISHU_BOT_PROFILE_CACHE_AT
    now = time.time()
    if (
        not force_refresh
        and _FEISHU_BOT_PROFILE_CACHE
        and (now - _FEISHU_BOT_PROFILE_CACHE_AT) < FEISHU_BOT_CACHE_TTL_SEC
    ):
        return _FEISHU_BOT_PROFILE_CACHE

    config = _load_openclaw_config()
    feishu = ((config.get("channels") or {}).get("feishu") or {})
    accounts = feishu.get("accounts")
    if not isinstance(accounts, dict):
        return _FEISHU_BOT_PROFILE_CACHE

    profile_index: dict[str, dict[str, str | None]] = {}
    for account_id, account in accounts.items():
        if not isinstance(account, dict):
            continue
        app_id = _clean_remote_value(account.get("appId"))
        app_secret = _clean_remote_value(account.get("appSecret"))
        if not app_id or not app_secret:
            continue
        profile = _fetch_feishu_bot_profile(app_id, app_secret)
        if profile:
            profile_index[str(account_id)] = profile

    if profile_index:
        _FEISHU_BOT_PROFILE_CACHE = profile_index
        _FEISHU_BOT_PROFILE_CACHE_AT = now
    return _FEISHU_BOT_PROFILE_CACHE


def _default_workspace_path_for_agent(agent_id: str, config: dict[str, Any]) -> str:
    defaults = ((config.get("agents") or {}).get("defaults") or {}) if isinstance(config, dict) else {}
    default_workspace = defaults.get("workspace")
    if isinstance(default_workspace, str) and default_workspace.strip():
        if agent_id == "main":
            return default_workspace.strip()
        workspace_root = Path(default_workspace.strip())
        return str((workspace_root.parent / f"{workspace_root.name}-{agent_id}"))

    host_root = _resolved_openclaw_host_root()
    if agent_id == "main":
        return str((host_root / "workspace").resolve())
    return str((host_root / f"workspace-{agent_id}").resolve())


def _resolve_first_lobster_workspace(config: dict[str, Any]) -> tuple[Path, str]:
    defaults = ((config.get("agents") or {}).get("defaults") or {}) if isinstance(config, dict) else {}
    default_workspace = defaults.get("workspace")
    if isinstance(default_workspace, str) and default_workspace.strip():
        return _coerce_openclaw_host_path(Path(default_workspace.strip()).expanduser()), "config"
    return _coerce_openclaw_host_path((_local_openclaw_home() / "workspace").expanduser()), "fallback"


def _read_first_lobster_file_preview(workspace_root: Path, relative_path: str) -> dict[str, Any]:
    target = workspace_root / relative_path
    result: dict[str, Any] = {
        "path": relative_path,
        "exists": False,
        "size": None,
        "modified_at": None,
        "preview": None,
        "preview_truncated": False,
        "error": None,
    }
    if not target.exists():
        return result
    if not target.is_file():
        result["error"] = "not_a_file"
        return result

    result["exists"] = True
    try:
        stat = target.stat()
        result["size"] = stat.st_size
        result["modified_at"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    except OSError as exc:
        result["error"] = f"stat_failed:{exc}"
        return result

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["error"] = f"read_failed:{exc}"
        return result

    preview = content[:FIRST_LOBSTER_PREVIEW_MAX_CHARS]
    result["preview"] = preview
    result["preview_truncated"] = len(content) > len(preview)
    return result


def _first_lobster_supported_channels_payload() -> list[dict[str, Any]]:
    return json.loads(json.dumps(FIRST_LOBSTER_SUPPORTED_CHANNELS, ensure_ascii=False))


def _parse_lobster_sequence(agent_id: Any) -> int | None:
    normalized = str(agent_id or "").strip()
    if not normalized:
        return None
    if normalized == FIRST_LOBSTER_DEFAULT_AGENT_ID:
        return 1
    match = re.fullmatch(r"lobster-(\d+)", normalized)
    if not match:
        return None
    sequence = int(match.group(1))
    return sequence if sequence >= 2 else None


def _format_lobster_sequence_label(sequence: int) -> str:
    if sequence <= 0:
        return "0"
    numerals = "零一二三四五六七八九"
    if sequence < 10:
        return numerals[sequence]
    if sequence < 20:
        suffix = numerals[sequence % 10] if sequence % 10 else ""
        return f"十{suffix}"
    if sequence < 100:
        tens = numerals[sequence // 10]
        ones = numerals[sequence % 10] if sequence % 10 else ""
        return f"{tens}十{ones}"
    return str(sequence)


def _build_next_lobster_target(config: dict[str, Any]) -> dict[str, Any]:
    configured_rows = ((config.get("agents") or {}).get("list") or []) if isinstance(config, dict) else []
    highest_sequence = 0
    for row in configured_rows:
        if not isinstance(row, dict):
            continue
        sequence = _parse_lobster_sequence(row.get("id"))
        if sequence:
            highest_sequence = max(highest_sequence, sequence)

    next_sequence = highest_sequence + 1 if highest_sequence > 0 else 1
    if next_sequence == 1:
        agent_id = FIRST_LOBSTER_DEFAULT_AGENT_ID
        agent_name = FIRST_LOBSTER_DEFAULT_AGENT_NAME
        app_name = "ClawPilot"
    else:
        agent_id = f"lobster-{next_sequence}"
        agent_name = f"第{_format_lobster_sequence_label(next_sequence)}只小龙虾"
        app_name = f"ClawPilot-{next_sequence}"

    return {
        "sequence": next_sequence,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "account_id": agent_id,
        "app_name": app_name,
    }


def get_first_lobster_bootstrap_preview() -> dict[str, Any]:
    config = _load_openclaw_config()
    workspace_root, workspace_source = _resolve_first_lobster_workspace(config)
    available = workspace_root.exists() and workspace_root.is_dir()
    workspace_error = None
    if not available:
        workspace_error = "workspace_not_found"
    recommended = _build_next_lobster_target(config)

    files = []
    for relative_path in FIRST_LOBSTER_BOOTSTRAP_FILES:
        if available:
            files.append(_read_first_lobster_file_preview(workspace_root, relative_path))
        else:
            files.append(
                {
                    "path": relative_path,
                    "exists": False,
                    "size": None,
                    "modified_at": None,
                    "preview": None,
                    "preview_truncated": False,
                    "error": workspace_error,
                }
            )

    return {
        "workspace": {
            "path": str(workspace_root),
            "source": workspace_source,
            "available": available,
            "error": workspace_error,
        },
        "recommended_agent_id": recommended["agent_id"],
        "recommended_agent_name": recommended["agent_name"],
        "recommended_app_name": recommended["app_name"],
        "supported_channels": _first_lobster_supported_channels_payload(),
        "files": files,
    }


def _ensure_first_lobster_config_shape(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    agents_config = config.get("agents")
    if agents_config is None:
        agents_config = {}
        config["agents"] = agents_config
    if not isinstance(agents_config, dict):
        raise ValueError("openclaw_agents_config_invalid")

    defaults = agents_config.get("defaults")
    if defaults is None:
        defaults = {}
        agents_config["defaults"] = defaults
    if not isinstance(defaults, dict):
        raise ValueError("openclaw_agents_defaults_invalid")

    agent_list = agents_config.get("list")
    if agent_list is None:
        agent_list = []
        agents_config["list"] = agent_list
    if not isinstance(agent_list, list):
        raise ValueError("openclaw_agents_list_invalid")

    bindings = config.get("bindings")
    if bindings is None:
        bindings = []
        config["bindings"] = bindings
    if not isinstance(bindings, list):
        raise ValueError("openclaw_bindings_invalid")

    channels = config.get("channels")
    if channels is None:
        channels = {}
        config["channels"] = channels
    if not isinstance(channels, dict):
        raise ValueError("openclaw_channels_invalid")

    return agents_config, defaults, agent_list, channels


def _migrate_gateway_config(config: dict[str, Any]) -> None:
    """Migrate legacy gatewayToken/gatewayPort to gateway.auth.token / gateway.port (CLI v2026.3.13+)."""
    legacy_token = config.pop("gatewayToken", None)
    legacy_port = config.pop("gatewayPort", None)
    gateway = config.get("gateway")
    if gateway is None:
        gateway = {}
        config["gateway"] = gateway
    if not isinstance(gateway, dict):
        return
    if legacy_token and not (gateway.get("auth") or {}).get("token"):
        auth = gateway.setdefault("auth", {})
        auth["token"] = legacy_token
    if legacy_port and not gateway.get("port"):
        gateway["port"] = legacy_port


def _ensure_weixin_plugin_enabled(config: dict[str, Any], *, enabled: bool = True) -> None:
    """Ensure plugins.entries.openclaw-weixin.enabled is set."""
    plugins = config.get("plugins")
    if plugins is None:
        plugins = {}
        config["plugins"] = plugins
    if not isinstance(plugins, dict):
        return
    entries = plugins.get("entries")
    if entries is None:
        entries = {}
        plugins["entries"] = entries
    if not isinstance(entries, dict):
        return
    weixin_entry = entries.get("openclaw-weixin")
    if weixin_entry is None:
        weixin_entry = {}
        entries["openclaw-weixin"] = weixin_entry
    if not isinstance(weixin_entry, dict):
        return
    weixin_entry["enabled"] = enabled


def _first_lobster_agent_dir(agent_id: str = FIRST_LOBSTER_DEFAULT_AGENT_ID) -> Path:
    return (_resolved_openclaw_host_root() / "agents" / agent_id / "agent").resolve()


def _resolve_model_ref_from_agent_models_json(agent_id: str) -> str | None:
    """Read the agent's models.json and return an OpenClaw model ref (e.g. 'ollama/qwen3:8b')."""
    models_file = _first_lobster_agent_dir(agent_id) / "models.json"
    if not models_file.exists():
        return None
    try:
        data = json.loads(models_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, dict):
        return None
    for provider_name, provider_conf in providers.items():
        if not isinstance(provider_conf, dict):
            continue
        models = provider_conf.get("models")
        if not isinstance(models, list) or not models:
            continue
        first_model = models[0]
        model_id = first_model.get("id") if isinstance(first_model, dict) else None
        if isinstance(model_id, str) and model_id.strip():
            return f"{provider_name}/{model_id.strip()}"
    return None


def _ensure_defaults_model(defaults: dict[str, Any], agent_list: list[dict[str, Any]]) -> None:
    """Ensure agents.defaults.model is set; bootstrap from existing agents if needed."""
    if defaults.get("model"):
        return
    for row in agent_list:
        if not isinstance(row, dict):
            continue
        agent_model = row.get("model")
        if agent_model:
            defaults["model"] = agent_model
            return
    for row in agent_list:
        if not isinstance(row, dict):
            continue
        agent_id = str(row.get("id") or "").strip()
        if not agent_id:
            continue
        ref = _resolve_model_ref_from_agent_models_json(agent_id)
        if ref:
            defaults["model"] = ref
            return


def _derive_agent_runtime_fields(
    agent_id: str,
    config: dict[str, Any],
    *,
    open_id: str | None = None,
) -> dict[str, Any]:
    """Derive channel, account_id, workspace_path, identity_complete from openclaw.json at runtime."""
    agents_config = config.get("agents") if isinstance(config, dict) else {}
    if not isinstance(agents_config, dict):
        agents_config = {}
    agent_rows = agents_config.get("list") or []

    agent_row: dict[str, Any] = {}
    for row in agent_rows:
        if isinstance(row, dict) and str(row.get("id") or "").strip() == agent_id:
            agent_row = row
            break

    bindings = config.get("bindings") or []
    account_by_agent_channel = _binding_account_ids_by_agent(bindings)
    binding_channels = account_by_agent_channel.get(agent_id, {})
    channel_state = _derive_agent_channel_state(agent_id, config, open_id=open_id)
    channel = str(channel_state.get("primary_channel") or "").strip()
    roster_index = _load_agent_roster_index()
    roster_row = roster_index.get(agent_id, {})
    roster_account_id = (
        _first_channel_account_id(roster_row, preferred_channel=channel) if roster_row else None
    )
    account_id = (
        channel_state.get("primary_account_id")
        or binding_channels.get(channel)
        or roster_account_id
        or agent_id
    )

    workspace_path = str(
        roster_row.get("workspace")
        or agent_row.get("workspace")
        or _default_workspace_path_for_agent(agent_id, config)
    )

    identity_complete = bool(channel and (open_id or channel != "feishu"))

    return {
        "channel": channel,
        "primary_channel": channel_state.get("primary_channel"),
        "connected_channels": channel_state.get("connected_channels") or [],
        "channel_status": channel_state.get("channel_status") or "missing",
        "channel_status_reason": channel_state.get("channel_status_reason"),
        "account_id": account_id,
        "workspace_path": workspace_path,
        "identity_complete": identity_complete,
    }


def _ensure_first_lobster_agent_layout(agent_id: str = FIRST_LOBSTER_DEFAULT_AGENT_ID) -> None:
    agent_dir = _first_lobster_agent_dir(agent_id)
    sessions_dir = agent_dir.parent / "sessions"
    agent_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)


def _upsert_agent_entry(agent_list: list[dict[str, Any]], *, agent_id: str, agent_name: str, workspace: str, agent_dir: str) -> None:
    existing = None
    for row in agent_list:
        if isinstance(row, dict) and str(row.get("id") or "").strip() == agent_id:
            existing = row
            break
    desired = {
        "id": agent_id,
        "name": agent_name,
        "workspace": workspace,
        "agentDir": agent_dir,
    }
    if existing is None:
        agent_list.append(desired)
        return
    existing.update({key: value for key, value in desired.items() if value})


def _resolve_claimed_agent_name(
    payload: dict[str, Any],
    *,
    fallback_name: str,
    primary_channel: str,
    feishu_profile: dict[str, str | None] | None = None,
) -> str:
    explicit_name = _clean_remote_value(payload.get("agent_name"))
    if explicit_name:
        return explicit_name
    if primary_channel == "feishu":
        profile_name = _clean_remote_value((feishu_profile or {}).get("name"))
        if profile_name:
            return profile_name
        feishu = payload.get("feishu") or {}
        if isinstance(feishu, dict):
            app_id = _clean_remote_value(feishu.get("app_id"))
            app_secret = _clean_remote_value(feishu.get("app_secret"))
            if app_id and app_secret:
                profile = _fetch_feishu_bot_profile(app_id, app_secret) or {}
                profile_name = _clean_remote_value(profile.get("name"))
                if profile_name:
                    return profile_name
    return fallback_name


def _ensure_channel_accounts_container(channels: dict[str, Any], channel: str) -> dict[str, Any]:
    provider_config = channels.get(channel)
    if provider_config is None:
        provider_config = {}
        channels[channel] = provider_config
    if not isinstance(provider_config, dict):
        raise ValueError(f"openclaw_channel_{channel}_invalid")

    accounts = provider_config.get("accounts")
    if accounts is None:
        accounts = {}
        provider_config["accounts"] = accounts
    if not isinstance(accounts, dict):
        raise ValueError(f"openclaw_channel_{channel}_accounts_invalid")

    return provider_config


def _upsert_channel_account(channels: dict[str, Any], channel: str, account_id: str, payload: dict[str, str]) -> None:
    provider_config = _ensure_channel_accounts_container(channels, channel)
    accounts = provider_config["accounts"]
    existing = accounts.get(account_id)
    if existing is None:
        existing = {}
        accounts[account_id] = existing
    if not isinstance(existing, dict):
        existing = {}
        accounts[account_id] = existing
    existing.update({key: value for key, value in payload.items() if value})
    default_account = _clean_remote_value(provider_config.get("defaultAccount"))
    if not default_account:
        provider_config["defaultAccount"] = account_id


def _ensure_lobster_workspace(agent_id: str, config: dict[str, Any], template_workspace_root: Path) -> Path:
    if agent_id == FIRST_LOBSTER_DEFAULT_AGENT_ID:
        return template_workspace_root.resolve()

    target_root = Path(_default_workspace_path_for_agent(agent_id, config)).expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    for relative_path in FIRST_LOBSTER_BOOTSTRAP_FILES:
        source = template_workspace_root / relative_path
        target = target_root / relative_path
        if target.exists() or not source.exists() or not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return target_root


def _upsert_agent_binding(bindings: list[dict[str, Any]], *, agent_id: str, channel: str, account_id: str) -> None:
    existing = None
    for row in bindings:
        if not isinstance(row, dict):
            continue
        match = row.get("match")
        if not isinstance(match, dict):
            continue
        if (
            str(row.get("agentId") or "").strip() == agent_id
            and str(match.get("channel") or "").strip() == channel
            and str(match.get("accountId") or "").strip() == account_id
        ):
            existing = row
            break

    desired = {
        "type": "route",
        "agentId": agent_id,
        "match": {
            "channel": channel,
            "accountId": account_id,
        },
    }
    if existing is None:
        bindings.append(desired)
        return
    existing.update(desired)


def remove_agent(agent_id: str, *, actor_account_id: str | None = None) -> dict[str, Any]:
    target_agent_id = _clean_remote_value(agent_id)
    if not target_agent_id:
        raise ValueError("agent_id_required")

    config = _load_openclaw_config_document_for_write()
    _agents_config, _defaults, agent_list, _channels = _ensure_first_lobster_config_shape(config)
    bindings = config["bindings"]

    removed_runtime = _derive_agent_runtime_fields(target_agent_id, config)
    removed_agent_name = target_agent_id
    next_agent_list: list[dict[str, Any]] = []
    removed_agent_found = False

    for row in agent_list:
        if not isinstance(row, dict):
            next_agent_list.append(row)
            continue
        current_agent_id = _clean_remote_value(row.get("id"))
        if current_agent_id != target_agent_id:
            next_agent_list.append(row)
            continue
        removed_agent_found = True
        removed_agent_name = _clean_remote_value(row.get("name")) or removed_agent_name

    if not removed_agent_found:
        raise LookupError("agent_not_found")

    agent_list[:] = next_agent_list

    removed_binding_rows: list[dict[str, Any]] = []
    next_bindings: list[dict[str, Any]] = []
    removed_accounts_by_channel: dict[str, set[str]] = {}
    remaining_accounts_by_channel: dict[str, set[str]] = {}

    removed_channel = _clean_remote_value(removed_runtime.get("channel"))
    removed_account_id = _clean_remote_value(removed_runtime.get("account_id"))
    if removed_channel and removed_account_id:
        removed_accounts_by_channel.setdefault(removed_channel, set()).add(removed_account_id)

    for row in bindings:
        if not isinstance(row, dict):
            next_bindings.append(row)
            continue
        current_agent_id = _clean_remote_value(row.get("agentId"))
        match = row.get("match")
        channel = _clean_remote_value(match.get("channel")) if isinstance(match, dict) else None
        account_id = _clean_remote_value(match.get("accountId")) if isinstance(match, dict) else None
        if current_agent_id == target_agent_id:
            removed_binding_rows.append(row)
            if channel and account_id:
                removed_accounts_by_channel.setdefault(channel, set()).add(account_id)
            continue
        next_bindings.append(row)
        if channel and account_id:
            remaining_accounts_by_channel.setdefault(channel, set()).add(account_id)

    bindings[:] = next_bindings

    channels = config.get("channels")
    if isinstance(channels, dict):
        for channel, removed_accounts in removed_accounts_by_channel.items():
            provider_config = channels.get(channel)
            if not isinstance(provider_config, dict):
                continue
            default_account = _clean_remote_value(provider_config.get("defaultAccount"))
            if not default_account or default_account not in removed_accounts:
                continue
            remaining_accounts = sorted(remaining_accounts_by_channel.get(channel) or [])
            if remaining_accounts:
                provider_config["defaultAccount"] = remaining_accounts[0]
            else:
                provider_config.pop("defaultAccount", None)

    write_result = _write_openclaw_config_document(config)

    database_row_removed = False
    retained_history = False
    blocker_queries = [
        ("tasks", "assignee_agent_id"),
        ("score_ledger", "agent_id"),
        ("onboarding_jobs", "agent_id"),
        ("agent_onboarding_runs", "owner_agent_id"),
        ("agent_onboarding_runs", "target_agent_id"),
        ("training_runs", "agent_id"),
        ("training_module_settings", "coach_agent_id"),
        ("training_run_contexts", "coach_agent_id"),
    ]

    with get_conn() as conn:
        history_ref_count = 0
        for table_name, column_name in blocker_queries:
            try:
                row = conn.execute(
                    f"SELECT COUNT(1) AS cnt FROM {table_name} WHERE {column_name} = ?",
                    (target_agent_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                continue
            history_ref_count += int(row["cnt"]) if row else 0

        conn.execute("DELETE FROM agent_user_oauth_states WHERE agent_id = ?", (target_agent_id,))
        conn.execute("DELETE FROM agent_user_auth WHERE agent_id = ?", (target_agent_id,))

        if history_ref_count == 0:
            deleted = conn.execute("DELETE FROM agents WHERE agent_id = ?", (target_agent_id,))
            database_row_removed = deleted.rowcount > 0
        else:
            retained_history = True

        if actor_account_id:
            _record_audit_log(
                conn,
                actor_account_id=actor_account_id,
                action="agents.remove",
                target_type="agent",
                target_id=target_agent_id,
                detail={
                    "agent_id": target_agent_id,
                    "display_name": removed_agent_name,
                    "removed_bindings": len(removed_binding_rows),
                    "database_row_removed": database_row_removed,
                    "retained_history": retained_history,
                    "config_path": write_result["config_path"],
                },
            )
        conn.commit()

    return {
        "status": "removed",
        "agent_id": target_agent_id,
        "display_name": removed_agent_name,
        "removed_bindings": len(removed_binding_rows),
        "database_row_removed": database_row_removed,
        "retained_history": retained_history,
        "config_path": write_result["config_path"],
        "backup_path": write_result["backup_path"],
    }


def _write_openclaw_config_document(document: dict[str, Any]) -> dict[str, str | None]:
    _migrate_gateway_config(document)
    config_path = _resolved_openclaw_config_path()
    backup_path: Path | None = None
    if config_path.exists():
        backup_path = config_path.with_name(
            f"{config_path.stem}.backup-first-lobster-{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')}{config_path.suffix}"
        )
        shutil.copy2(config_path, backup_path)
    _atomic_write_text(config_path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    _OPENCLAW_CONFIG_CACHE.invalidate("config:")
    return {"config_path": str(config_path), "backup_path": str(backup_path) if backup_path else None}


def _build_claimed_agent_result(
    *,
    agent_id: str,
    fallback_display_name: str,
    fallback_role: str,
    fallback_channel: str,
    fallback_account_id: str,
    fallback_workspace_path: str,
) -> dict[str, Any]:
    config = _load_openclaw_config()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    if not row:
        raise RuntimeError("first_lobster_sync_failed")
    payload = dict(row)
    derived = _derive_agent_runtime_fields(agent_id, config, open_id=payload.get("open_id"))
    return {
        "agent_id": str(payload.get("agent_id") or agent_id),
        "display_name": str(payload.get("display_name") or fallback_display_name),
        "role": str(payload.get("role") or fallback_role),
        "status": str(payload.get("status") or "active"),
        "channel": str(derived.get("channel") or fallback_channel),
        "account_id": str(derived.get("account_id") or fallback_account_id),
        "open_id": _clean_remote_value(payload.get("open_id")),
        "workspace_path": str(derived.get("workspace_path") or fallback_workspace_path),
        "identity_complete": bool(derived.get("identity_complete")),
        "role_summary": None,
        "core_work": [],
        "capabilities": [],
        "skills": [],
        "delegate_when": [],
        "do_not_delegate_when": [],
        "priority": None,
        "enabled": None,
        "main_dispatch_allowed": None,
        "last_known_active": None,
        "latest_activity_at": None,
        "runtime_status": None,
        "runtime_status_reason": None,
        "runtime_status_at": None,
        "runtime_signal_source": None,
        "runtime_node_status": None,
        "runtime_crash_excerpt": None,
        "emoji": None,
        "avatar_hint": None,
        "avatar_url": None,
        "scene_preset_id": _clean_remote_value(payload.get("scene_preset_id")),
        "model_provider": None,
        "model_id": None,
        "model_label": None,
        "config_model_provider": None,
        "config_model_id": None,
        "config_model_label": None,
        "recent_model_provider": None,
        "recent_model_id": None,
        "recent_model_label": None,
        "usage_input_tokens": None,
        "usage_output_tokens": None,
        "usage_total_tokens": None,
        "usage_context_tokens": None,
        "estimated_cost_usd": None,
        "created_at": str(payload.get("created_at") or now_iso()),
    }


def _parse_first_lobster_feishu_pairing_text(pairing_text: str) -> dict[str, str]:
    text = str(pairing_text or "").strip()
    if not text:
        raise ValueError("first_lobster_feishu_pairing_text_required")

    open_id_match = re.search(r"Your\s+Feishu\s+user\s+id:\s*(ou_[A-Za-z0-9]+)", text, flags=re.IGNORECASE)
    code_match = re.search(r"Pairing\s+code:\s*([A-Z0-9]+)", text, flags=re.IGNORECASE)
    if not code_match:
        code_match = re.search(
            r"openclaw\s+pairing\s+approve\s+feishu\s+([A-Z0-9]+)",
            text,
            flags=re.IGNORECASE,
        )

    user_open_id = open_id_match.group(1).strip() if open_id_match else ""
    pairing_code = code_match.group(1).strip().upper() if code_match else ""
    if not user_open_id or not pairing_code:
        raise ValueError("first_lobster_feishu_pairing_text_invalid")

    return {
        "user_open_id": user_open_id,
        "pairing_code": pairing_code,
    }


def confirm_first_lobster_feishu_pairing(payload: dict[str, Any], *, actor_account_id: str | None = None) -> dict[str, Any]:
    agent_id = _clean_remote_value(payload.get("agent_id"))
    if not agent_id:
        raise ValueError("agent_id_required")

    pairing = _parse_first_lobster_feishu_pairing_text(str(payload.get("pairing_text") or ""))
    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")
    if str(agent.get("channel") or "").strip() != "feishu":
        raise ValueError("first_lobster_feishu_pairing_channel_invalid")

    env_overrides = {
        "OPENCLAW_STATE_DIR": str(_local_openclaw_home()),
        "OPENCLAW_CONFIG_PATH": str(_resolved_openclaw_config_path()),
    }
    command = [
        OPENCLAW_CLI_BIN,
        "pairing",
        "approve",
        "feishu",
        pairing["pairing_code"],
        "--account",
        agent_id,
        "--notify",
    ]
    try:
        _run_openclaw_cli_text_with_env(command, timeout=30, env_overrides=env_overrides)
    except RuntimeError as exc:
        message = str(exc)
        if message == "openclaw_cli_unavailable":
            raise RuntimeError("openclaw_cli_unavailable") from exc
        if message.startswith("openclaw_cli_failed:"):
            raise RuntimeError(f"first_lobster_feishu_pairing_approve_failed:{message.removeprefix('openclaw_cli_failed:')}") from exc
        raise RuntimeError("first_lobster_feishu_pairing_approve_failed") from exc

    now = now_iso()
    if actor_account_id:
        with get_conn() as conn:
            _record_audit_log(
                conn,
                actor_account_id=actor_account_id,
                action="agents.claim_first_lobster_feishu_pairing_confirmed",
                target_type="agent",
                target_id=agent_id,
                detail={
                    "agent_id": agent_id,
                    "agent_name": agent.get("display_name"),
                    "user_open_id": pairing["user_open_id"],
                    "pairing_code": pairing["pairing_code"],
                },
            )
            conn.commit()

    return {
        "status": "confirmed",
        "agent_id": agent_id,
        "agent_name": str(agent.get("display_name") or agent_id),
        "user_open_id": pairing["user_open_id"],
        "pairing_code": pairing["pairing_code"],
        "completed_at": now,
    }


def confirm_agent_feishu_pairing(payload: dict[str, Any], *, actor_account_id: str | None = None) -> dict[str, Any]:
    agent_id = _clean_remote_value(payload.get("agent_id"))
    if not agent_id:
        raise ValueError("agent_id_required")

    pairing = _parse_first_lobster_feishu_pairing_text(str(payload.get("pairing_text") or ""))
    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")
    if str(agent.get("channel") or "").strip() != "feishu":
        raise ValueError("agent_feishu_pairing_channel_invalid")

    env_overrides = {
        "OPENCLAW_STATE_DIR": str(_local_openclaw_home()),
        "OPENCLAW_CONFIG_PATH": str(_resolved_openclaw_config_path()),
    }
    command = [
        OPENCLAW_CLI_BIN,
        "pairing",
        "approve",
        "feishu",
        pairing["pairing_code"],
        "--account",
        agent_id,
        "--notify",
    ]
    try:
        _run_openclaw_cli_text_with_env(command, timeout=30, env_overrides=env_overrides)
    except RuntimeError as exc:
        message = str(exc)
        if message == "openclaw_cli_unavailable":
            raise RuntimeError("openclaw_cli_unavailable") from exc
        if message.startswith("openclaw_cli_failed:"):
            raise RuntimeError(f"agent_feishu_pairing_approve_failed:{message.removeprefix('openclaw_cli_failed:')}") from exc
        raise RuntimeError("agent_feishu_pairing_approve_failed") from exc

    sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
    now = now_iso()
    if actor_account_id:
        with get_conn() as conn:
            _record_audit_log(
                conn,
                actor_account_id=actor_account_id,
                action="agents.feishu_pairing_confirmed",
                target_type="agent",
                target_id=agent_id,
                detail={
                    "agent_id": agent_id,
                    "agent_name": agent.get("display_name"),
                    "user_open_id": pairing["user_open_id"],
                    "pairing_code": pairing["pairing_code"],
                },
            )
            conn.commit()

    return {
        "status": "confirmed",
        "agent_id": agent_id,
        "agent_name": str(agent.get("display_name") or agent_id),
        "user_open_id": pairing["user_open_id"],
        "pairing_code": pairing["pairing_code"],
        "completed_at": now,
    }


_WEIXIN_QR_SESSIONS: dict[str, dict[str, Any]] = {}
WEIXIN_QR_WORKER_SCRIPT_PATH = REPO_ROOT / "bridge" / "weixin" / "qr-login-worker.ts"
WEIXIN_QR_WORKER_TSX_PATH = REPO_ROOT / "bridge" / "weixin" / "node_modules" / ".bin" / "tsx"


def _weixin_qr_sessions_dir() -> Path:
    return (_local_openclaw_home() / "openclaw-weixin" / "qr-sessions").resolve()


def _weixin_qr_status_path(session_id: str) -> Path:
    return _weixin_qr_sessions_dir() / f"{session_id}.json"


def _read_weixin_qr_state(session_id: str) -> dict[str, Any] | None:
    status_path = _weixin_qr_status_path(session_id)
    if not status_path.exists():
        return None
    try:
        payload = json.loads(status_path.read_text("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def start_weixin_qr_login() -> dict[str, Any]:
    """Start a WeChat QR login flow and return a real QR URL."""
    if not WEIXIN_QR_WORKER_SCRIPT_PATH.exists() or not WEIXIN_QR_WORKER_TSX_PATH.exists():
        raise ValueError("weixin_qr_worker_not_found")

    session_id = secrets.token_hex(16)
    status_path = _weixin_qr_status_path(session_id)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        status_path.unlink(missing_ok=True)
    except Exception:
        pass
    log_dir = (_local_openclaw_home() / "logs").resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"weixin-qr-{session_id}.log"
    env = {
        **os.environ,
        "OPENCLAW_STATE_DIR": str(_local_openclaw_home()),
        "OPENCLAW_CONFIG_PATH": str(_resolved_openclaw_config_path()),
        "OPENCLAW_CONFIG": str(_resolved_openclaw_config_path()),
    }

    try:
        log_handle = open(log_path, "a", encoding="utf-8")
        process = subprocess.Popen(
            [
                str(WEIXIN_QR_WORKER_TSX_PATH),
                str(WEIXIN_QR_WORKER_SCRIPT_PATH),
                "--session-id",
                session_id,
                "--status-file",
                str(status_path),
                "--timeout-ms",
                "480000",
            ],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        log_handle.close()
    except FileNotFoundError as exc:
        raise ValueError("weixin_qr_worker_not_found") from exc

    _WEIXIN_QR_SESSIONS[session_id] = {
        "status_path": str(status_path),
        "log_path": str(log_path),
        "process": process,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    deadline = time.time() + 12
    while time.time() < deadline:
        state = _read_weixin_qr_state(session_id)
        if state and state.get("qr_url"):
            return {
                "session_id": session_id,
                "qr_url": str(state.get("qr_url")),
                "expires_at": str(state.get("expires_at") or (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()),
            }
        if process.poll() is not None:
            state_message = state.get("message") if isinstance(state, dict) else None
            raise ValueError(str(state_message or "weixin_qr_login_failed"))
        time.sleep(0.1)

    raise ValueError("weixin_qr_login_timeout")


def poll_weixin_qr_login(session_id: str) -> dict[str, Any]:
    """Poll the status of a WeChat QR login session."""
    session = _WEIXIN_QR_SESSIONS.get(session_id)
    state = _read_weixin_qr_state(session_id)
    if not session and not state:
        return {"status": "expired", "account_id": None, "message": "Session not found or expired"}

    if not state:
        process = session.get("process") if isinstance(session, dict) else None
        if isinstance(process, subprocess.Popen) and process.poll() is not None:
            return {"status": "error", "account_id": None, "message": "微信二维码登录任务已退出，请重新生成。"}
        return {"status": "waiting", "account_id": None, "message": None}

    normalized_status = str(state.get("status") or "waiting").strip().lower()
    if normalized_status not in {"waiting", "scanned", "confirmed", "expired", "error"}:
        normalized_status = "waiting"

    expires_at = str(state.get("expires_at") or "").strip()
    if normalized_status in {"waiting", "scanned"} and expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if datetime.now(timezone.utc) > expiry:
                normalized_status = "expired"
        except (ValueError, TypeError):
            pass

    return {
        "status": normalized_status,
        "account_id": _clean_remote_value(state.get("account_id")),
        "message": _clean_remote_value(state.get("message")),
    }


WEIXIN_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "bridge" / "weixin"
WEIXIN_BRIDGE_PID_FILE = _local_openclaw_home() / "bridge-weixin.pid"
_WEIXIN_BRIDGE_PROCESS: subprocess.Popen[str] | None = None


def _read_bridge_pid() -> int | None:
    try:
        if WEIXIN_BRIDGE_PID_FILE.exists():
            pid = int(WEIXIN_BRIDGE_PID_FILE.read_text("utf-8").strip())
            return pid if pid > 0 else None
    except (ValueError, OSError):
        pass
    return None


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def start_weixin_bridge() -> dict[str, Any]:
    """Start the WeChat bridge Node.js process."""
    global _WEIXIN_BRIDGE_PROCESS

    existing_pid = _read_bridge_pid()
    if existing_pid and _is_process_alive(existing_pid):
        return {"status": "already_running", "pid": existing_pid, "message": "Bridge is already running"}

    config = _load_openclaw_config_document_for_write()
    _ensure_weixin_plugin_enabled(config, enabled=False)
    _write_openclaw_config_document(config)

    if OPENCLAW_CLI_BIN:
        try:
            subprocess.run(
                [OPENCLAW_CLI_BIN, "gateway", "restart"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "OPENCLAW_STATE_DIR": str(_local_openclaw_home()),
                     "OPENCLAW_CONFIG_PATH": str(_resolved_openclaw_config_path())},
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if not WEIXIN_BRIDGE_DIR.exists():
        raise ValueError("weixin_bridge_not_installed")

    tsx_bin = shutil.which("tsx") or "npx"
    cmd: list[str]
    if tsx_bin == "npx":
        cmd = ["npx", "tsx", "index.ts", "start"]
    else:
        cmd = [tsx_bin, "index.ts", "start"]

    log_dir = _local_openclaw_home() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "bridge-weixin.log"

    with open(log_file, "a", encoding="utf-8") as log_fh:
        proc = subprocess.Popen(
            cmd,
            cwd=str(WEIXIN_BRIDGE_DIR),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "CLAWPILOT_API_BASE": os.getenv("CLAWPILOT_API_BASE", "http://127.0.0.1:8000"),
                "BRIDGE_PID_FILE": str(WEIXIN_BRIDGE_PID_FILE),
            },
            start_new_session=True,
        )

    _WEIXIN_BRIDGE_PROCESS = proc
    return {"status": "started", "pid": proc.pid, "message": None}


def stop_weixin_bridge() -> dict[str, Any]:
    """Stop the WeChat bridge process and re-enable the openclaw-weixin plugin."""
    global _WEIXIN_BRIDGE_PROCESS

    pid = _read_bridge_pid()
    if not pid:
        if _WEIXIN_BRIDGE_PROCESS and _WEIXIN_BRIDGE_PROCESS.poll() is None:
            pid = _WEIXIN_BRIDGE_PROCESS.pid
        else:
            return {"status": "not_running", "message": "Bridge is not running"}

    try:
        os.kill(pid, signal_module.SIGTERM)
        for _ in range(20):
            if not _is_process_alive(pid):
                break
            import time
            time.sleep(0.5)
    except (OSError, ProcessLookupError):
        pass

    try:
        if WEIXIN_BRIDGE_PID_FILE.exists():
            WEIXIN_BRIDGE_PID_FILE.unlink()
    except OSError:
        pass

    _WEIXIN_BRIDGE_PROCESS = None

    config = _load_openclaw_config_document_for_write()
    _ensure_weixin_plugin_enabled(config, enabled=True)
    _write_openclaw_config_document(config)

    if OPENCLAW_CLI_BIN:
        try:
            subprocess.run(
                [OPENCLAW_CLI_BIN, "gateway", "restart"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "OPENCLAW_STATE_DIR": str(_local_openclaw_home()),
                     "OPENCLAW_CONFIG_PATH": str(_resolved_openclaw_config_path())},
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return {"status": "stopped", "message": None}


def get_weixin_bridge_status() -> dict[str, Any]:
    """Check the WeChat bridge process status."""
    pid = _read_bridge_pid()
    if not pid or not _is_process_alive(pid):
        return {"running": False, "pid": None, "uptime_seconds": None, "message": None}

    uptime: int | None = None
    try:
        stat = WEIXIN_BRIDGE_PID_FILE.stat()
        uptime = int(datetime.now(timezone.utc).timestamp() - stat.st_mtime)
    except OSError:
        pass

    return {"running": True, "pid": pid, "uptime_seconds": uptime, "message": None}


def claim_first_lobster(payload: dict[str, Any], *, actor_account_id: str | None = None) -> dict[str, Any]:
    config = _load_openclaw_config_document_for_write()
    workspace_root, _workspace_source = _resolve_first_lobster_workspace(config)
    if not workspace_root.exists() or not workspace_root.is_dir():
        raise ValueError("first_lobster_workspace_unavailable")

    selected_channels = []
    for item in payload.get("selected_channels") or []:
        value = _clean_remote_value(item)
        if value and value not in selected_channels:
            selected_channels.append(value)
    if not selected_channels:
        raise ValueError("first_lobster_channel_required")

    primary_channel = _clean_remote_value(payload.get("primary_channel"))
    if primary_channel is None and len(selected_channels) == 1:
        primary_channel = selected_channels[0]
    if primary_channel is None:
        raise ValueError("first_lobster_primary_channel_required")
    if primary_channel not in selected_channels:
        raise ValueError("first_lobster_primary_channel_invalid")

    channel_payloads: dict[str, dict[str, str]] = {}
    feishu_profile: dict[str, str | None] | None = None
    if "feishu" in selected_channels:
        feishu = payload.get("feishu") or {}
        app_id = _clean_remote_value((feishu or {}).get("app_id"))
        app_secret = _clean_remote_value((feishu or {}).get("app_secret"))
        if not app_id:
            raise ValueError("first_lobster_feishu_app_id_required")
        if not app_secret:
            raise ValueError("first_lobster_feishu_app_secret_required")
        feishu_profile = _fetch_feishu_bot_profile(app_id, app_secret)
        channel_payloads["feishu"] = {
            "appId": app_id,
            "appSecret": app_secret,
            "appName": _clean_remote_value((feishu_profile or {}).get("name")) or "",
            "avatarUrl": _clean_remote_value((feishu_profile or {}).get("avatar_url")) or "",
            "openId": _clean_remote_value((feishu_profile or {}).get("open_id")) or "",
        }
    if "telegram" in selected_channels:
        telegram = payload.get("telegram") or {}
        bot_token = _clean_remote_value((telegram or {}).get("bot_token"))
        if not bot_token:
            raise ValueError("first_lobster_telegram_bot_token_required")
        channel_payloads["telegram"] = {"botToken": bot_token}
    if "discord" in selected_channels:
        discord = payload.get("discord") or {}
        token = _clean_remote_value((discord or {}).get("token"))
        if not token:
            raise ValueError("first_lobster_discord_token_required")
        channel_payloads["discord"] = {"token": token}
    weixin_account_id: str | None = None
    if "weixin" in selected_channels:
        weixin = payload.get("weixin") or {}
        weixin_account_id = _clean_remote_value((weixin or {}).get("account_id"))
        if not weixin_account_id:
            raise ValueError("first_lobster_weixin_account_id_required")

    target = _build_next_lobster_target(config)
    target_agent_id = str(target["agent_id"])
    target_agent_name = _resolve_claimed_agent_name(
        payload,
        fallback_name=str(target["agent_name"]),
        primary_channel=primary_channel,
        feishu_profile=feishu_profile,
    )
    target_account_id = str(target["account_id"])
    target_workspace = _ensure_lobster_workspace(target_agent_id, config, workspace_root)

    _ensure_first_lobster_agent_layout(target_agent_id)
    _agents_config, _defaults, agent_list, channels = _ensure_first_lobster_config_shape(config)
    _ensure_defaults_model(_defaults, agent_list)
    bindings = config["bindings"]

    _upsert_agent_entry(
        agent_list,
        agent_id=target_agent_id,
        agent_name=target_agent_name,
        workspace=str(target_workspace),
        agent_dir=str(_first_lobster_agent_dir(target_agent_id)),
    )
    ordered_channels = [primary_channel, *[item for item in channel_payloads.keys() if item != primary_channel]]
    for channel in ordered_channels:
        account_payload = channel_payloads[channel]
        _upsert_channel_account(channels, channel, target_account_id, account_payload)
        _upsert_agent_binding(
            bindings,
            agent_id=target_agent_id,
            channel=channel,
            account_id=target_account_id,
        )
    if weixin_account_id:
        _ensure_weixin_plugin_enabled(config, enabled=True)
        _upsert_agent_binding(
            bindings,
            agent_id=target_agent_id,
            channel="openclaw-weixin",
            account_id=weixin_account_id,
        )

    write_result = _write_openclaw_config_document(config)
    sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
    agent = _build_claimed_agent_result(
        agent_id=target_agent_id,
        fallback_display_name=target_agent_name,
        fallback_role=ROLE_MAP.get(target_agent_id, "待补充"),
        fallback_channel=primary_channel,
        fallback_account_id=target_account_id,
        fallback_workspace_path=str(target_workspace),
    )

    if actor_account_id:
        with get_conn() as conn:
            _record_audit_log(
                conn,
                actor_account_id=actor_account_id,
                action="agents.claim_first_lobster",
                target_type="agent",
                target_id=target_agent_id,
                detail={
                    "agent_id": target_agent_id,
                    "agent_name": target_agent_name,
                    "selected_channels": selected_channels,
                    "primary_channel": primary_channel,
                    "workspace_path": str(target_workspace),
                    "config_path": write_result["config_path"],
                },
            )
            conn.commit()

    return {
        "status": "claimed",
        "selected_channels": selected_channels,
        "primary_channel": primary_channel,
        "config_path": write_result["config_path"],
        "backup_path": write_result["backup_path"],
        "agent": agent,
    }


def create_basic_agent(payload: dict[str, Any]) -> dict[str, Any]:
    agent_id = _clean_remote_value(payload.get("agent_id"))
    agent_name = _clean_remote_value(payload.get("agent_name"))
    role_summary = _clean_remote_value(payload.get("role_summary"))
    core_work = [
        str(item).strip()
        for item in (payload.get("core_work") or [])
        if isinstance(item, str) and item.strip()
    ]
    if not agent_id:
        raise ValueError("agent_id_required")
    if not agent_name:
        raise ValueError("agent_name_required")
    if not role_summary:
        raise ValueError("role_summary_required")

    config = _load_openclaw_config_document_for_write()
    workspace_preview, _workspace_source = _resolve_first_lobster_workspace(config)
    template_workspace_root = workspace_preview if workspace_preview.exists() else Path(
        _default_workspace_path_for_agent(agent_id, config)
    ).expanduser().resolve()
    template_workspace_root.mkdir(parents=True, exist_ok=True)

    _ensure_first_lobster_agent_layout(agent_id)
    _agents_config, defaults, agent_list, _channels = _ensure_first_lobster_config_shape(config)
    _ensure_defaults_model(defaults, agent_list)
    target_workspace = _ensure_lobster_workspace(agent_id, config, template_workspace_root)
    _upsert_agent_entry(
        agent_list,
        agent_id=agent_id,
        agent_name=agent_name,
        workspace=str(target_workspace),
        agent_dir=str(_first_lobster_agent_dir(agent_id)),
    )
    _write_openclaw_config_document(config)
    sync_agents_from_openclaw_config(refresh_feishu_profiles=False)

    warnings: list[str] = []
    try:
        scripts = _resolve_onboarding_scripts()
        _run_skill_script_json(
            scripts["scaffold_docs"],
            [
                "--agent-id",
                agent_id,
                "--agent-name",
                agent_name,
                "--workspace-dir",
                str(target_workspace),
                "--role-summary",
                role_summary,
                *sum([["--core-work", item] for item in core_work], []),
            ],
            timeout=90,
        )
    except Exception as exc:
        warnings.append(f"scaffold_docs_failed:{exc}")

    with get_conn() as conn:
        conn.execute(
            "UPDATE agents SET display_name = ?, role = ? WHERE agent_id = ?",
            (agent_name, role_summary, agent_id),
        )
        conn.commit()

    agent = get_agent_by_id(
        agent_id,
        include_feishu_profiles=False,
        include_official_runtime_signal=False,
    )
    if not agent:
        raise RuntimeError("agent_create_sync_failed")
    return {"status": "created", "agent": agent, "warnings": warnings}


def connect_agent_feishu_channel(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized_agent_id = _clean_remote_value(agent_id)
    if not normalized_agent_id:
        raise ValueError("agent_id_required")

    existing = get_agent_by_id(
        normalized_agent_id,
        include_feishu_profiles=False,
        include_official_runtime_signal=False,
    )
    if not existing:
        raise LookupError("agent_not_found")

    app_id = _clean_remote_value(payload.get("app_id"))
    app_secret = _clean_remote_value(payload.get("app_secret"))
    operator_open_id = _clean_remote_value(payload.get("operator_open_id"))
    if not app_id:
        raise ValueError("feishu_app_id_missing")
    if not app_secret:
        raise ValueError("feishu_app_secret_missing")
    warnings: list[str] = []

    config = _load_openclaw_config()
    identity_key = _clean_remote_value(payload.get("identity_key")) or _resolve_default_identity_key(config) or "default"
    scripts = _resolve_onboarding_scripts()
    sync_args = [
        "upsert",
        "--agent-id",
        normalized_agent_id,
        "--agent-name",
        str(existing.get("display_name") or normalized_agent_id),
        "--app-id",
        app_id,
        "--app-secret",
        app_secret,
        "--identity-key",
        identity_key,
    ]
    if operator_open_id:
        sync_args.extend(["--operator-open-id", operator_open_id])
    _run_skill_script_json(
        scripts["ensure_feishu_agent"],
        sync_args,
        timeout=90,
    )
    sync_agents_from_openclaw_config(refresh_feishu_profiles=False)

    updated = get_agent_by_id(
        normalized_agent_id,
        include_feishu_profiles=False,
        include_official_runtime_signal=False,
    )
    if not updated:
        raise RuntimeError("agent_channel_sync_failed")
    if not operator_open_id:
        warnings.append("feishu_identity_pending_pairing")
    return {"status": "connected", "channel": "feishu", "agent": updated, "warnings": warnings}


def sync_agents_from_openclaw_config(*, refresh_feishu_profiles: bool = True) -> int:
    """从 openclaw.json 同步 agent 到本地 agents 表。

    Returns:
        同步成功写入（upsert）条数；0 表示未同步。
    """
    config = _load_openclaw_config()
    agents = ((config.get("agents") or {}).get("list") or []) if isinstance(config, dict) else []
    if not agents:
        return 0

    feishu_config = ((config.get("channels") or {}).get("feishu") or {})
    feishu_accounts = feishu_config.get("accounts") if isinstance(feishu_config, dict) else {}
    if not isinstance(feishu_accounts, dict):
        feishu_accounts = {}
    roster_index = _load_agent_roster_index()

    upsert_count = 0
    now = now_iso()

    with get_conn() as conn:
        for row in agents:
            if not isinstance(row, dict):
                continue
            agent_id_raw = row.get("id")
            if not agent_id_raw:
                continue
            agent_id = str(agent_id_raw)

            existing = conn.execute(
                "SELECT status, created_at FROM agents WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            status = str(existing["status"]) if existing and existing["status"] else ("probation" if agent_id == "security" else "active")
            created_at = str(existing["created_at"]) if existing and existing["created_at"] else now

            derived = _derive_agent_runtime_fields(agent_id, config)
            channel = derived["channel"]
            account_id = derived["account_id"]

            cached_feishu_profile = (
                _extract_cached_feishu_account_profile(feishu_accounts.get(account_id) or feishu_accounts.get(agent_id))
                if channel == "feishu"
                else {"name": None, "avatar_url": None, "open_id": None}
            )

            open_id = _get_agent_open_id(feishu_config, agent_id)
            if not open_id and channel == "feishu":
                open_id = cached_feishu_profile.get("open_id")

            roster_row = roster_index.get(agent_id, {})
            display_name = _resolve_display_name(agent_id, roster_row, row)
            if (
                channel == "feishu"
                and cached_feishu_profile.get("name")
                and _is_default_lobster_placeholder_name(agent_id, display_name)
            ):
                display_name = str(cached_feishu_profile["name"]).strip()
            role = str(roster_row.get("roleSummary") or ROLE_MAP.get(agent_id, "待补充"))

            conn.execute(
                """
                INSERT INTO agents (
                    agent_id, display_name, role, status, open_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    role=excluded.role,
                    status=excluded.status,
                    open_id=excluded.open_id
                """,
                (
                    agent_id,
                    display_name,
                    role,
                    status,
                    open_id,
                    created_at,
                ),
            )
            upsert_count += 1
        conn.commit()

    if refresh_feishu_profiles:
        _get_feishu_bot_profile_index(force_refresh=True)
    return upsert_count


def list_agents(
    status: str | None,
    q: str | None,
    *,
    include_feishu_profiles: bool = True,
    include_official_runtime_signal: bool = True,
) -> list[dict[str, Any]]:
    config = _load_openclaw_config()
    configured_rows = ((config.get("agents") or {}).get("list") or []) if isinstance(config, dict) else []
    configured_agent_ids = [
        str(item.get("id")).strip()
        for item in configured_rows
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if not configured_agent_ids:
        return []

    roster_index = _load_agent_roster_index()
    identity_index = _load_identity_index()
    feishu_config = ((config.get("channels") or {}).get("feishu") or {})
    feishu_accounts = feishu_config.get("accounts") if isinstance(feishu_config, dict) else {}
    if not isinstance(feishu_accounts, dict):
        feishu_accounts = {}
    feishu_bot_profiles = _get_feishu_bot_profile_index() if include_feishu_profiles else {}
    official_runtime_signal = _read_official_runtime_host_signal() if include_official_runtime_signal else None

    with get_conn() as conn:
        existing_total = int(conn.execute("SELECT COUNT(1) AS cnt FROM agents").fetchone()["cnt"])
    if existing_total == 0:
        sync_agents_from_openclaw_config()

    with get_conn() as conn:
        sql = "SELECT * FROM agents WHERE 1=1"
        params: list[Any] = [*configured_agent_ids]
        placeholders = ",".join("?" for _ in configured_agent_ids)
        sql += f" AND agent_id IN ({placeholders})"
        if status:
            sql += " AND status = ?"
            params.append(status)
        if q:
            sql += " AND (agent_id LIKE ? OR display_name LIKE ?)"
            fuzzy = f"%{q}%"
            params.extend([fuzzy, fuzzy])
        sql += " ORDER BY created_at DESC, agent_id ASC"

        rows = conn.execute(sql, params).fetchall()
        try:
            node_rows = conn.execute(
                """
                SELECT node_id, display_name, node_type, expected_openclaw_root, token_hash, token_last4,
                       hostname, platform, connector_version, reported_openclaw_root, activated_at,
                       last_seen_at, created_at, updated_at
                FROM nodes
                ORDER BY created_at DESC, display_name ASC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            node_rows = []
        runtime_node_snapshot = _match_runtime_node_snapshot(node_rows)
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            derived = _derive_agent_runtime_fields(
                item["agent_id"], config, open_id=item.get("open_id"),
            )
            item.update(derived)
            roster = roster_index.get(item["agent_id"])
            if roster:
                role_summary = roster.get("roleSummary")
                if role_summary:
                    item["role"] = str(role_summary)
                item["display_name"] = _resolve_display_name(item["agent_id"], roster, item)
                item["role_summary"] = str(role_summary) if role_summary else None
                item["core_work"] = [str(x) for x in (roster.get("coreWork") or [])]
                item["capabilities"] = [str(x) for x in (roster.get("capabilities") or [])]
                item["skills"] = [str(x) for x in (roster.get("skills") or [])]
                item["delegate_when"] = [str(x) for x in (roster.get("delegateWhen") or [])]
                item["do_not_delegate_when"] = [str(x) for x in (roster.get("doNotDelegateWhen") or [])]
                item["priority"] = int(roster.get("priority")) if isinstance(roster.get("priority"), int) else None
                item["enabled"] = bool(roster.get("enabled")) if roster.get("enabled") is not None else None
                item["main_dispatch_allowed"] = (
                    bool(roster.get("mainDispatchAllowed"))
                    if roster.get("mainDispatchAllowed") is not None
                    else None
                )
                item["last_known_active"] = (
                    str(roster.get("lastKnownActive")) if roster.get("lastKnownActive") else None
                )
            else:
                item["role_summary"] = None
                item["core_work"] = []
                item["capabilities"] = []
                item["skills"] = []
                item["delegate_when"] = []
                item["do_not_delegate_when"] = []
                item["priority"] = None
                item["enabled"] = None
                item["main_dispatch_allowed"] = None

            runtime_snapshot = _derive_agent_runtime_snapshot(
                item,
                official_signal=official_runtime_signal,
                node_snapshot=runtime_node_snapshot,
            )
            item.update(runtime_snapshot)

            # Frontend is migrating from `last_known_active` to `latest_activity_at`.
            # For active/probation agents, expose the log-derived timestamp through both
            # fields so older bundles still render the correct relative active time.
            if item.get("latest_activity_at") and item.get("status") in {"active", "probation"}:
                item["last_known_active"] = item["latest_activity_at"]

            identity = identity_index.get(item["agent_id"]) or {}
            item["emoji"] = identity.get("emoji")
            item["avatar_hint"] = identity.get("avatar_hint")
            item["avatar_url"] = identity.get("avatar_url")
            profile = None
            if item.get("channel") == "feishu":
                account_id = str(item.get("account_id") or item["agent_id"])
                cached_profile = _extract_cached_feishu_account_profile(
                    feishu_accounts.get(account_id) or feishu_accounts.get(item["agent_id"])
                )
                profile = feishu_bot_profiles.get(account_id) or feishu_bot_profiles.get(item["agent_id"]) or cached_profile
                if profile and profile.get("name") and _is_default_lobster_placeholder_name(item["agent_id"], item.get("display_name")):
                    item["display_name"] = str(profile["name"]).strip()
                if not item.get("open_id") and profile and profile.get("open_id"):
                    item["open_id"] = profile.get("open_id")
            if not item.get("avatar_url") and item.get("channel") == "feishu":
                if profile and profile.get("avatar_url"):
                    item["avatar_url"] = profile.get("avatar_url")

            usage_summary = _resolve_agent_local_usage_summary(item["agent_id"], config=config)
            item.update(usage_summary)
            items.append(item)
        return items


def get_agent_by_id(
    agent_id: str,
    *,
    include_feishu_profiles: bool = True,
    include_official_runtime_signal: bool = True,
) -> dict[str, Any] | None:
    items = list_agents(
        status=None,
        q=None,
        include_feishu_profiles=include_feishu_profiles,
        include_official_runtime_signal=include_official_runtime_signal,
    )
    for item in items:
        if item.get("agent_id") == agent_id:
            return item
    return None


def update_agent_scene_preset(agent_id: str, preset_id: str) -> dict[str, Any]:
    normalized_preset_id = _normalize_agent_scene_preset_id(preset_id)
    with get_conn() as conn:
        row = conn.execute("SELECT agent_id FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        if row is None:
            raise LookupError("agent_not_found")
        conn.execute(
            "UPDATE agents SET scene_preset_id = ? WHERE agent_id = ?",
            (normalized_preset_id, agent_id),
        )
        conn.commit()

    updated = get_agent_by_id(
        agent_id,
        include_feishu_profiles=False,
        include_official_runtime_signal=False,
    )
    if updated is None:
        raise LookupError("agent_not_found")
    return updated


def list_agent_workspace_entries(agent_id: str, relative_path: str | None = None) -> dict[str, Any]:
    agent, workspace_display_path, workspace_root = _get_agent_workspace_roots(agent_id)
    relative_current = _normalize_workspace_relative_path(relative_path)
    allowed_roots = _workspace_allowed_roots(workspace_root)
    allow_skills_symlink = _path_has_skills_symlink(workspace_root, relative_current)
    current_dir = _ensure_child_path(
        workspace_root,
        relative_current,
        _workspace_shared_allowed_roots(),
        allow_skills_symlink=allow_skills_symlink,
    )
    if not current_dir.exists():
        raise LookupError("workspace_path_not_found")
    if not current_dir.is_dir():
        raise ValueError("workspace_path_not_directory")

    version = _path_cache_version(current_dir)

    def _loader() -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []

        def _entry_sort_key(item: Path) -> tuple[bool, str]:
            try:
                return (not item.is_dir(), item.name.lower())
            except FileNotFoundError:
                return (True, item.name.lower())

        for entry in sorted(current_dir.iterdir(), key=_entry_sort_key):
            try:
                entry_is_symlink = entry.is_symlink()
                allow_outside_root = allow_skills_symlink or (
                    entry_is_symlink and _is_skills_relative_path(relative_current)
                )
                resolved_entry, is_directory, stat = _resolve_workspace_entry(
                    entry,
                    allowed_roots,
                    allow_outside_root=allow_outside_root,
                )
            except FileNotFoundError:
                continue
            except PermissionError:
                continue

            relative_entry = _join_workspace_relative_path(relative_current, entry.name)
            preview_kind = "directory" if is_directory else _workspace_preview_kind(resolved_entry)
            entries.append(
                {
                    "name": entry.name,
                    "path": relative_entry,
                    "display_path": _workspace_visible_path(workspace_display_path, relative_entry),
                    "kind": "directory" if is_directory else "file",
                    "size": None if is_directory else stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "editable": False if is_directory else _is_editable_text_file(resolved_entry),
                    "previewable": False if is_directory else preview_kind != "binary",
                    "preview_kind": preview_kind,
                    "mime_type": None if is_directory else _guess_mime_type(resolved_entry),
                    "code_language": None if is_directory else _guess_code_language(resolved_entry),
                    "is_symlink": entry_is_symlink,
                    "symlink_target": str(entry.resolve()) if entry_is_symlink else None,
                    "preview_url": None
                    if is_directory or preview_kind not in {"image", "video", "audio", "pdf"}
                    else _workspace_asset_url(agent["agent_id"], relative_entry, "raw"),
                    "pdf_preview_url": None
                    if is_directory or preview_kind != "office"
                    else _workspace_asset_url(agent["agent_id"], relative_entry, "pdf"),
                    "download_url": None
                    if is_directory
                    else _workspace_asset_url(agent["agent_id"], relative_entry, "raw"),
                }
            )
        return entries

    started = time.perf_counter()
    entries = _DIRECTORY_LISTING_CACHE.get(
        f"workspace:{agent['agent_id']}:{current_dir.resolve()}",
        version,
        _loader,
    )
    local_runtime.RUNTIME_DIAGNOSTICS.record_latency(
        "workspace_directory_listing",
        (time.perf_counter() - started) * 1000,
        detail={"agent_id": agent["agent_id"], "path": relative_current},
    )

    parent_path = None
    if relative_current:
        parent_path = str(Path(relative_current).parent.as_posix())
        if parent_path == ".":
            parent_path = ""

    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "root_path": workspace_display_path,
        "current_path": relative_current,
        "current_display_path": _workspace_visible_path(workspace_display_path, relative_current),
        "parent_path": parent_path,
        "entries": entries,
    }


def list_openclaw_root_entries(relative_path: str | None = None) -> dict[str, Any]:
    root_display_path, root_path = _get_openclaw_root()
    relative_current = _normalize_workspace_relative_path(relative_path)
    current_dir = _ensure_child_path(root_path, relative_current)
    if not current_dir.exists():
        raise LookupError("workspace_path_not_found")
    if not current_dir.is_dir():
        raise ValueError("workspace_path_not_directory")

    allowed_roots = (root_path.resolve(),)
    version = _path_cache_version(current_dir)

    def _loader() -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []

        def _entry_sort_key(item: Path) -> tuple[bool, str]:
            try:
                return (not item.is_dir(), item.name.lower())
            except FileNotFoundError:
                return (True, item.name.lower())

        for entry in sorted(current_dir.iterdir(), key=_entry_sort_key):
            try:
                resolved_entry, is_directory, stat = _resolve_workspace_entry(entry, allowed_roots)
            except FileNotFoundError:
                continue
            except PermissionError:
                continue

            relative_entry = _join_workspace_relative_path(relative_current, entry.name)
            preview_kind = "directory" if is_directory else _workspace_preview_kind(resolved_entry)
            entries.append(
                {
                    "name": entry.name,
                    "path": relative_entry,
                    "display_path": _workspace_visible_path(root_display_path, relative_entry),
                    "kind": "directory" if is_directory else "file",
                    "size": None if is_directory else stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "editable": False,
                    "previewable": False if is_directory else preview_kind != "binary",
                    "preview_kind": preview_kind,
                    "mime_type": None if is_directory else _guess_mime_type(resolved_entry),
                    "code_language": None if is_directory else _guess_code_language(resolved_entry),
                    "preview_url": None
                    if is_directory or preview_kind not in {"image", "video", "audio", "pdf"}
                    else _openclaw_root_asset_url(relative_entry, "raw"),
                    "pdf_preview_url": None
                    if is_directory or preview_kind != "office"
                    else _openclaw_root_asset_url(relative_entry, "pdf"),
                    "download_url": None if is_directory else _openclaw_root_asset_url(relative_entry, "raw"),
                }
            )
        return entries

    started = time.perf_counter()
    entries = _DIRECTORY_LISTING_CACHE.get(
        f"openclaw-root:{current_dir.resolve()}",
        version,
        _loader,
    )
    local_runtime.RUNTIME_DIAGNOSTICS.record_latency(
        "openclaw_directory_listing",
        (time.perf_counter() - started) * 1000,
        detail={"path": relative_current},
    )

    parent_path = None
    if relative_current:
        parent_path = str(Path(relative_current).parent.as_posix())
        if parent_path == ".":
            parent_path = ""

    return {
        "root_path": root_display_path,
        "current_path": relative_current,
        "current_display_path": _workspace_visible_path(root_display_path, relative_current),
        "parent_path": parent_path,
        "entries": entries,
    }


def read_agent_workspace_file(agent_id: str, relative_path: str) -> dict[str, Any]:
    agent, workspace_display_path, workspace_root = _get_agent_workspace_roots(agent_id)
    normalized_relative_path = _normalize_workspace_relative_path(relative_path)
    file_path = _ensure_child_path(
        workspace_root,
        normalized_relative_path,
        _workspace_shared_allowed_roots(),
        allow_skills_symlink=True,
    )
    if not file_path.exists():
        raise LookupError("workspace_file_not_found")
    if not file_path.is_file():
        raise ValueError("workspace_path_not_file")
    return _serialize_workspace_file(
        agent_id=agent["agent_id"],
        agent_name=agent["display_name"],
        workspace_display_path=workspace_display_path,
        relative_path=normalized_relative_path,
        file_path=file_path,
    )


def read_openclaw_root_file(relative_path: str) -> dict[str, Any]:
    root_display_path, root_path = _get_openclaw_root()
    normalized_relative_path = _normalize_workspace_relative_path(relative_path)
    file_path = _ensure_child_path(root_path, normalized_relative_path)
    if not file_path.exists():
        raise LookupError("workspace_file_not_found")
    if not file_path.is_file():
        raise ValueError("workspace_path_not_file")
    return _serialize_openclaw_root_file(
        root_display_path=root_display_path,
        relative_path=normalized_relative_path,
        file_path=file_path,
    )


def resolve_agent_workspace_asset(
    agent_id: str,
    relative_path: str,
    variant: str = "raw",
) -> tuple[Path, str, str]:
    agent, _, workspace_root = _get_agent_workspace_roots(agent_id)
    normalized_relative_path = _normalize_workspace_relative_path(relative_path)
    file_path = _ensure_child_path(
        workspace_root,
        normalized_relative_path,
        _workspace_shared_allowed_roots(),
        allow_skills_symlink=True,
    )
    if not file_path.exists():
        raise LookupError("workspace_file_not_found")
    if not file_path.is_file():
        raise ValueError("workspace_path_not_file")

    if variant == "raw":
        return file_path, _guess_mime_type(file_path), file_path.name

    if variant != "pdf":
        raise ValueError("workspace_asset_variant_invalid")

    if _workspace_preview_kind(file_path) != "office":
        raise ValueError("workspace_asset_variant_not_supported")

    converter = _office_converter_path()
    if not converter:
        raise RuntimeError("office_preview_converter_missing")

    file_stat = file_path.stat()
    cache_key = hashlib.sha1(
        f"{agent['agent_id']}::{normalized_relative_path}::{file_stat.st_mtime_ns}::{file_stat.st_size}".encode("utf-8")
    ).hexdigest()
    cache_dir = WORKSPACE_PREVIEW_CACHE_DIR / agent["agent_id"] / cache_key
    output_name = f"{file_path.stem}.pdf"
    output_path = cache_dir / output_name
    if output_path.exists():
        return output_path, "application/pdf", output_name

    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="office-preview-") as temp_dir:
        temp_path = Path(temp_dir)
        command = [
            converter,
            "--headless",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(temp_path),
            str(file_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if completed.returncode != 0:
            raise RuntimeError(
                f"office_preview_convert_failed:{completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
            )

        generated = temp_path / output_name
        if not generated.exists():
            raise RuntimeError("office_preview_pdf_missing")
        shutil.copy2(generated, output_path)

    return output_path, "application/pdf", output_name


def resolve_openclaw_root_asset(relative_path: str, variant: str = "raw") -> tuple[Path, str, str]:
    root_path_display, root_path = _get_openclaw_root()
    normalized_relative_path = _normalize_workspace_relative_path(relative_path)
    file_path = _ensure_child_path(root_path, normalized_relative_path)
    if not file_path.exists():
        raise LookupError("workspace_file_not_found")
    if not file_path.is_file():
        raise ValueError("workspace_path_not_file")

    if variant == "raw":
        return file_path, _guess_mime_type(file_path), file_path.name

    if variant != "pdf":
        raise ValueError("workspace_asset_variant_invalid")

    if _workspace_preview_kind(file_path) != "office":
        raise ValueError("workspace_asset_variant_not_supported")

    converter = _office_converter_path()
    if not converter:
        raise RuntimeError("office_preview_converter_missing")

    file_stat = file_path.stat()
    cache_key = hashlib.sha1(
        f"openclaw-root::{normalized_relative_path}::{file_stat.st_mtime_ns}::{file_stat.st_size}".encode("utf-8")
    ).hexdigest()
    cache_dir = WORKSPACE_PREVIEW_CACHE_DIR / "openclaw-root" / cache_key
    output_name = f"{file_path.stem}.pdf"
    output_path = cache_dir / output_name
    if output_path.exists():
        return output_path, "application/pdf", output_name

    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="office-preview-") as temp_dir:
        temp_path = Path(temp_dir)
        command = [
            converter,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(temp_path),
            str(file_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"office_preview_conversion_failed: {(result.stderr or result.stdout or 'unknown_error').strip()}"
            )

        generated = temp_path / output_name
        if not generated.exists():
            raise RuntimeError("office_preview_conversion_missing_output")
        generated.replace(output_path)

    return output_path, "application/pdf", output_name


def send_workspace_instruction_to_agent(
    *,
    source_agent_id: str,
    relative_path: str,
    target_agent_id: str,
    instruction: str,
    sender_agent_id: str = "main",
) -> dict[str, Any]:
    config = _load_openclaw_config()
    roster_index = _load_agent_roster_index()
    source_agent, workspace_display_path, workspace_root = _get_agent_workspace_roots(source_agent_id)
    target_agent = _get_agent_lightweight_payload(target_agent_id, config=config, roster_index=roster_index)
    if not target_agent:
        raise LookupError("target_agent_not_found")

    sender_agent = _get_agent_lightweight_payload(sender_agent_id, config=config, roster_index=roster_index)
    if not sender_agent:
        raise LookupError("sender_agent_not_found")

    target_open_id = _clean_remote_value(target_agent.get("open_id"))
    if not target_open_id:
        raise ValueError("target_agent_open_id_missing")

    normalized_relative_path = _normalize_workspace_relative_path(relative_path)
    file_path = _ensure_child_path(
        workspace_root,
        normalized_relative_path,
        _workspace_shared_allowed_roots(),
        allow_skills_symlink=True,
    )
    if not file_path.exists():
        raise LookupError("workspace_file_not_found")
    if not file_path.is_file():
        raise ValueError("workspace_path_not_file")

    file_bytes = file_path.read_bytes()
    if len(file_bytes) > FEISHU_SEND_FILE_MAX_BYTES:
        raise ValueError("workspace_file_too_large")

    visible_path = _workspace_visible_path(workspace_display_path, normalized_relative_path)
    instruction_text = (
        "来自 OpenClaw 工区协作派发。\n"
        f"来源 Agent：{source_agent['display_name']} ({source_agent['agent_id']})\n"
        f"文件：{file_path.name}\n"
        f"路径：{visible_path}\n\n"
        "处理要求：\n"
        f"{instruction.strip()}"
    )

    if not _is_user_auth_supported(target_agent_id):
        raise ValueError("target_agent_user_auth_not_enabled")

    token = _get_valid_agent_user_access_token(target_agent_id)

    text_message_id = _send_feishu_message(
        token,
        receive_open_id=target_open_id,
        msg_type="text",
        content={"text": instruction_text},
    )
    file_key = _upload_feishu_file(token, file_name=file_path.name, file_bytes=file_bytes)
    file_message_id = _send_feishu_message(
        token,
        receive_open_id=target_open_id,
        msg_type="file",
        content={"file_key": file_key},
    )

    return {
        "source_agent_id": source_agent["agent_id"],
        "source_agent_name": source_agent["display_name"],
        "target_agent_id": target_agent["agent_id"],
        "target_agent_name": target_agent["display_name"],
        "sender_agent_id": sender_agent["agent_id"],
        "sender_agent_name": sender_agent["display_name"],
        "file_name": file_path.name,
        "transport": "human_user_feishu_dm",
        "text_message_id": text_message_id,
        "file_message_id": file_message_id,
        "sent_at": now_iso(),
    }


def update_agent_workspace_file(agent_id: str, relative_path: str, content: str) -> dict[str, Any]:
    _agent, _workspace_display_path, workspace_root = _get_agent_workspace_roots(agent_id)
    normalized_relative_path = _normalize_workspace_relative_path(relative_path)
    file_path = _ensure_child_path(
        workspace_root,
        normalized_relative_path,
        _workspace_shared_allowed_roots(),
        allow_skills_symlink=True,
    )
    if not file_path.exists():
        raise LookupError("workspace_file_not_found")
    if not file_path.is_file():
        raise ValueError("workspace_path_not_file")
    if not _is_editable_text_file(file_path):
        raise PermissionError("workspace_file_not_editable")
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > WORKSPACE_MAX_SAVE_BYTES:
        raise ValueError("workspace_file_too_large")

    file_path.write_text(content, encoding="utf-8")
    _DIRECTORY_LISTING_CACHE.invalidate("workspace:")
    _SESSION_RECORDS_CACHE.invalidate(f"sessions:{agent_id}:")
    _TRANSCRIPT_SUMMARY_CACHE.invalidate(f"transcript:{file_path.resolve()}")
    return read_agent_workspace_file(agent_id, normalized_relative_path)


def create_agent_workspace_file(agent_id: str, relative_path: str, content: str = "") -> dict[str, Any]:
    _agent, _workspace_display_path, workspace_root = _get_agent_workspace_roots(agent_id)
    normalized_relative_path = _normalize_workspace_relative_path(relative_path)
    file_path = _ensure_child_path(
        workspace_root,
        normalized_relative_path,
        _workspace_shared_allowed_roots(),
        allow_skills_symlink=True,
    )
    if file_path.exists():
        if not file_path.is_file():
            raise ValueError("workspace_path_not_file")
        return read_agent_workspace_file(agent_id, normalized_relative_path)

    parent_dir = file_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    if not _is_editable_text_file(file_path):
        raise PermissionError("workspace_file_not_editable")

    content_bytes = content.encode("utf-8")
    if len(content_bytes) > WORKSPACE_MAX_SAVE_BYTES:
        raise ValueError("workspace_file_too_large")

    file_path.write_text(content, encoding="utf-8")
    _DIRECTORY_LISTING_CACHE.invalidate("workspace:")
    return read_agent_workspace_file(agent_id, normalized_relative_path)


def import_agent_skill_zip(agent_id: str, file_name: str, file_bytes: bytes) -> dict[str, Any]:
    if not file_name.lower().endswith(".zip"):
        raise ValueError("skill_zip_only_supported")
    if not file_bytes:
        raise ValueError("skill_zip_empty")
    if len(file_bytes) > SKILL_IMPORT_MAX_BYTES:
        raise ValueError("skill_import_too_large")

    agent, workspace_display_path, workspace_root, skills_root = _resolve_agent_skills_root(agent_id)
    skill_name = _sanitize_skill_name(Path(file_name).stem)
    destination, overwritten = _prepare_skill_destination(skills_root, skill_name)

    try:
        with tempfile.NamedTemporaryFile(prefix="skill-import-", suffix=".zip", delete=False) as temp_file:
            temp_file.write(file_bytes)
            temp_zip_path = Path(temp_file.name)

        with zipfile.ZipFile(temp_zip_path) as archive:
            members = _iter_archive_members(archive)
            if not members:
                raise ValueError("skill_archive_empty")

            normalized_names = [info.filename.replace("\\", "/").strip("/") for info in members]
            top_level = {name.split("/", 1)[0] for name in normalized_names}
            strip_prefix = (
                next(iter(top_level))
                if len(top_level) == 1 and all("/" in name for name in normalized_names)
                else None
            )
            extracted = _extract_skill_archive(
                archive,
                members=members,
                destination=destination,
                strip_prefix=strip_prefix,
            )
            if extracted == 0:
                raise ValueError("skill_archive_empty")
    except zipfile.BadZipFile as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise ValueError("skill_zip_invalid") from exc
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        if "temp_zip_path" in locals():
            temp_zip_path.unlink(missing_ok=True)

    relative_path = str(destination.relative_to(workspace_root))
    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "skill_name": skill_name,
        "skill_path": relative_path,
        "display_path": _workspace_visible_path(workspace_display_path, relative_path),
        "imported_from": "zip",
        "overwritten": overwritten,
    }


def _parse_github_skill_url(source_url: str) -> tuple[str, str, str | None, str | None]:
    parsed = urlparse(source_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("skill_github_url_invalid")
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError("skill_github_only_supported")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("skill_github_url_invalid")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    ref: str | None = None
    subdir: str | None = None
    if len(parts) >= 4 and parts[2] == "tree":
        ref = parts[3]
        subdir = "/".join(parts[4:]) or None
    elif len(parts) > 2:
        raise ValueError("skill_github_url_unsupported")
    return owner, repo, ref, subdir


def _resolve_github_default_branch(owner: str, repo: str) -> str:
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ClawPilot"},
        timeout=30,
    )
    if response.status_code == 404:
        raise LookupError("skill_github_repo_not_found")
    if response.status_code >= 400:
        raise RuntimeError(f"skill_github_repo_lookup_failed:{response.status_code}")

    data = response.json()
    default_branch = str(data.get("default_branch") or "").strip()
    if not default_branch:
        raise RuntimeError("skill_github_default_branch_missing")
    return default_branch


def _download_github_archive(owner: str, repo: str, ref: str) -> bytes:
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ClawPilot"},
        timeout=60,
        stream=True,
    )
    if response.status_code == 404:
        raise LookupError("skill_github_ref_not_found")
    if response.status_code >= 400:
        raise RuntimeError(f"skill_github_download_failed:{response.status_code}")

    collected = bytearray()
    for chunk in response.iter_content(chunk_size=1024 * 256):
        if not chunk:
            continue
        collected.extend(chunk)
        if len(collected) > SKILL_IMPORT_MAX_BYTES:
            raise ValueError("skill_import_too_large")
    if not collected:
        raise RuntimeError("skill_github_archive_empty")
    return bytes(collected)


def import_agent_skill_from_github(
    agent_id: str,
    source_url: str,
    target_name: str | None = None,
) -> dict[str, Any]:
    owner, repo, ref, subdir = _parse_github_skill_url(source_url)
    ref = ref or _resolve_github_default_branch(owner, repo)
    archive_bytes = _download_github_archive(owner, repo, ref)

    agent, workspace_display_path, workspace_root, skills_root = _resolve_agent_skills_root(agent_id)
    inferred_name = Path(subdir).name if subdir else repo
    skill_name = _sanitize_skill_name(target_name or inferred_name)
    destination, overwritten = _prepare_skill_destination(skills_root, skill_name)

    try:
        with tempfile.NamedTemporaryFile(prefix="skill-github-", suffix=".zip", delete=False) as temp_file:
            temp_file.write(archive_bytes)
            temp_zip_path = Path(temp_file.name)

        with zipfile.ZipFile(temp_zip_path) as archive:
            members = _iter_archive_members(archive)
            if not members:
                raise ValueError("skill_archive_empty")

            root_prefix = members[0].filename.replace("\\", "/").strip("/").split("/", 1)[0]
            normalized_subdir = _normalize_archive_relative_path(subdir) if subdir else None
            extracted = 0
            for info in members:
                original_name = info.filename.replace("\\", "/").strip("/")
                if not original_name.startswith(f"{root_prefix}/"):
                    continue
                repo_relative = original_name[len(root_prefix) + 1 :]
                if not repo_relative:
                    continue
                if normalized_subdir:
                    if repo_relative == normalized_subdir:
                        continue
                    prefix = f"{normalized_subdir}/"
                    if not repo_relative.startswith(prefix):
                        continue
                    repo_relative = repo_relative[len(prefix) :]
                try:
                    normalized = _normalize_archive_relative_path(repo_relative)
                except ValueError:
                    continue
                target_path = _ensure_child_path(destination, normalized, _workspace_shared_allowed_roots())
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target_path.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
                extracted += 1

            if extracted == 0:
                raise LookupError("skill_github_path_not_found")
    except zipfile.BadZipFile as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise ValueError("skill_zip_invalid") from exc
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        if "temp_zip_path" in locals():
            temp_zip_path.unlink(missing_ok=True)

    relative_path = str(destination.relative_to(workspace_root))
    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "skill_name": skill_name,
        "skill_path": relative_path,
        "display_path": _workspace_visible_path(workspace_display_path, relative_path),
        "imported_from": "github",
        "overwritten": overwritten,
    }


def delete_agent_skill(agent_id: str, skill_name: str) -> dict[str, Any]:
    raw_name = str(skill_name or "").strip()
    if not raw_name:
        raise ValueError("skill_name_required")

    agent, _workspace_display_path, workspace_root, skills_root = _resolve_agent_skills_root(agent_id)
    normalized_name = _sanitize_skill_name(raw_name)
    target_path = _ensure_child_path(skills_root, normalized_name, _workspace_shared_allowed_roots())
    if target_path == skills_root:
        raise PermissionError("skill_delete_root_forbidden")
    if len(target_path.relative_to(skills_root).parts) != 1:
        raise PermissionError("skill_delete_only_top_level_supported")
    if not target_path.exists():
        raise LookupError("skill_not_found")
    if not target_path.is_dir():
        raise ValueError("skill_path_not_directory")
    if target_path.is_symlink():
        raise PermissionError("skill_delete_symlink_forbidden")

    shutil.rmtree(target_path)
    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "skill_name": normalized_name,
        "deleted_path": str(target_path.relative_to(workspace_root)),
    }


def _load_openclaw_jobs_document() -> dict[str, Any]:
    cron_jobs_path = _resolved_openclaw_cron_jobs_path()
    version = _path_cache_version(cron_jobs_path)

    def _loader() -> dict[str, Any]:
        if not cron_jobs_path.exists() or not cron_jobs_path.is_file():
            raise RuntimeError("scheduled_jobs_registry_missing")
        try:
            payload = json.loads(cron_jobs_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("scheduled_jobs_registry_invalid") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("scheduled_jobs_registry_invalid")
        jobs = payload.get("jobs")
        if jobs is None:
            payload["jobs"] = []
            jobs = payload["jobs"]
        if not isinstance(jobs, list):
            raise RuntimeError("scheduled_jobs_registry_invalid")
        return payload

    return _OPENCLAW_JOBS_CACHE.get(f"jobs:{cron_jobs_path.resolve()}", version, _loader)


def _write_openclaw_jobs_document(payload: dict[str, Any]) -> None:
    cron_jobs_path = _resolved_openclaw_cron_jobs_path()
    cron_jobs_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="cron-jobs-",
        suffix=".json",
        dir=str(cron_jobs_path.parent),
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        handle.write(b"\n")
    temp_path.replace(cron_jobs_path)
    _OPENCLAW_JOBS_CACHE.invalidate("jobs:")


def _ts_ms_to_iso(value: Any) -> str | None:
    if value in (None, "", 0):
        return None
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp_ms <= 0:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def _normalize_cron_expr(value: Any) -> str:
    expr = str(value or "").strip()
    if not expr:
        raise ValueError("scheduled_job_cron_required")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("scheduled_job_cron_invalid")
    return " ".join(parts)


def _normalize_every_ms(value: Any) -> int:
    try:
        every_ms = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("scheduled_job_every_invalid") from exc
    if every_ms < 1:
        raise ValueError("scheduled_job_every_invalid")
    return every_ms


def _normalize_at_iso(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("scheduled_job_at_required")
    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("scheduled_job_at_invalid") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _isoformat_utc(dt: datetime) -> str:
    normalized = dt.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name}_invalid") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_timeline_window(from_at: str | None, to_at: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    window_start = _parse_iso_utc(from_at, "timeline_from_at") or now
    window_end = _parse_iso_utc(to_at, "timeline_to_at") or (window_start + timedelta(hours=SCHEDULE_TIMELINE_DEFAULT_HOURS))
    if window_end <= window_start:
        raise ValueError("timeline_window_invalid")
    if window_end - window_start > timedelta(days=SCHEDULE_TIMELINE_MAX_DAYS):
        raise ValueError("timeline_window_too_large")
    return window_start, window_end


def _resolve_schedule_timezone(value: Any) -> ZoneInfo:
    raw = str(value or "").strip() or "Asia/Shanghai"
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai")


def _coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _resolve_job_duration_minutes(job: dict[str, Any], serialized_job: dict[str, Any]) -> tuple[int, bool]:
    explicit_sources = [
        job.get("durationMinutes"),
        job.get("estimatedDurationMinutes"),
        job.get("coverageMinutes"),
        (job.get("schedule") or {}).get("durationMinutes") if isinstance(job.get("schedule"), dict) else None,
        (job.get("payload") or {}).get("durationMinutes") if isinstance(job.get("payload"), dict) else None,
    ]
    for source in explicit_sources:
        minutes = _coerce_positive_int(source)
        if minutes:
            return minutes, False

    if serialized_job.get("schedule_kind") == "every" and serialized_job.get("every_ms"):
        interval_minutes = max(1, int(int(serialized_job["every_ms"]) / 60000))
        return max(SCHEDULE_TIMELINE_MIN_INTERVAL_DURATION_MINUTES, min(SCHEDULE_TIMELINE_DEFAULT_DURATION_MINUTES, interval_minutes)), True

    return SCHEDULE_TIMELINE_DEFAULT_DURATION_MINUTES, True


def _parse_cron_part(part: str, min_value: int, max_value: int) -> set[int]:
    raw = str(part or "").strip()
    if not raw:
        raise ValueError("scheduled_job_cron_invalid")
    values: set[int] = set()
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            raise ValueError("scheduled_job_cron_invalid")

        step = 1
        if "/" in token:
            base, step_raw = token.split("/", 1)
            try:
                step = int(step_raw)
            except ValueError as exc:
                raise ValueError("scheduled_job_cron_invalid") from exc
            if step <= 0:
                raise ValueError("scheduled_job_cron_invalid")
        else:
            base = token

        if base == "*":
            start, end = min_value, max_value
        elif "-" in base:
            start_raw, end_raw = base.split("-", 1)
            try:
                start = int(start_raw)
                end = int(end_raw)
            except ValueError as exc:
                raise ValueError("scheduled_job_cron_invalid") from exc
        else:
            try:
                value = int(base)
            except ValueError as exc:
                raise ValueError("scheduled_job_cron_invalid") from exc
            if min_value == 0 and max_value == 6 and value == 7:
                value = 0
            if value < min_value or value > max_value:
                raise ValueError("scheduled_job_cron_invalid")
            values.add(value)
            continue

        if min_value == 0 and max_value == 6:
            if start == 7:
                start = 0
            if end == 7:
                end = 0
            if start == 0 and end == 6 and base == "*":
                pass
            elif start > end:
                raise ValueError("scheduled_job_cron_invalid")
        elif start > end:
            raise ValueError("scheduled_job_cron_invalid")

        if start < min_value or end > max_value:
            raise ValueError("scheduled_job_cron_invalid")
        values.update(range(start, end + 1, step))

    if not values:
        raise ValueError("scheduled_job_cron_invalid")
    return values


def _cron_matches(local_dt: datetime, expr: str) -> bool:
    parts = _normalize_cron_expr(expr).split()
    minute_match = local_dt.minute in _parse_cron_part(parts[0], 0, 59)
    hour_match = local_dt.hour in _parse_cron_part(parts[1], 0, 23)
    month_match = local_dt.month in _parse_cron_part(parts[3], 1, 12)
    if not (minute_match and hour_match and month_match):
        return False

    dom_any = parts[2] == "*"
    dow_any = parts[4] == "*"
    dom_match = local_dt.day in _parse_cron_part(parts[2], 1, 31)
    cron_weekday = (local_dt.weekday() + 1) % 7
    dow_match = cron_weekday in _parse_cron_part(parts[4], 0, 6)

    if dom_any and dow_any:
        return True
    if dom_any:
        return dow_match
    if dow_any:
        return dom_match
    return dom_match or dow_match


def _expand_cron_occurrences(
    expr: str,
    tz_name: Any,
    window_start: datetime,
    window_end: datetime,
) -> list[datetime]:
    tz = _resolve_schedule_timezone(tz_name)
    local_start = window_start.astimezone(tz).replace(second=0, microsecond=0)
    if local_start.astimezone(timezone.utc) < window_start:
        local_start += timedelta(minutes=1)

    occurrences: list[datetime] = []
    cursor = local_start
    while cursor.astimezone(timezone.utc) <= window_end and len(occurrences) < SCHEDULE_TIMELINE_MAX_OCCURRENCES_PER_JOB:
        current_utc = cursor.astimezone(timezone.utc)
        if current_utc >= window_start and _cron_matches(cursor, expr):
            occurrences.append(current_utc)
        cursor += timedelta(minutes=1)
    return occurrences


def _first_valid_anchor_ms(job: dict[str, Any]) -> int | None:
    state = job.get("state") if isinstance(job.get("state"), dict) else {}
    candidates = [
        state.get("nextRunAtMs"),
        state.get("lastRunAtMs"),
        job.get("createdAtMs"),
        job.get("updatedAtMs"),
    ]
    for candidate in candidates:
        anchor_ms = _coerce_positive_int(candidate)
        if anchor_ms:
            return anchor_ms
    return None


def _expand_every_occurrences(job: dict[str, Any], every_ms: int, window_start: datetime, window_end: datetime) -> list[datetime]:
    start_ms = int(window_start.timestamp() * 1000)
    end_ms = int(window_end.timestamp() * 1000)
    anchor_ms = _first_valid_anchor_ms(job) or start_ms

    if start_ms <= anchor_ms:
        first_ms = anchor_ms - ((anchor_ms - start_ms) // every_ms) * every_ms
    else:
        first_ms = anchor_ms + ((start_ms - anchor_ms + every_ms - 1) // every_ms) * every_ms

    occurrences: list[datetime] = []
    cursor_ms = first_ms
    while cursor_ms <= end_ms and len(occurrences) < SCHEDULE_TIMELINE_MAX_OCCURRENCES_PER_JOB:
        if cursor_ms >= start_ms:
            occurrences.append(datetime.fromtimestamp(cursor_ms / 1000, tz=timezone.utc))
        cursor_ms += every_ms
    return occurrences


def _expand_at_occurrence(at_value: str, window_start: datetime, window_end: datetime) -> list[datetime]:
    at_dt = _parse_iso_utc(at_value, "timeline_at")
    if not at_dt:
        return []
    if window_start <= at_dt <= window_end:
        return [at_dt]
    return []


def _merge_ranges(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    normalized = sorted((start, end) for start, end in ranges if end > start)
    if not normalized:
        return []
    merged: list[tuple[datetime, datetime]] = [normalized[0]]
    for start, end in normalized[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _calculate_conflict_ranges(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    events: list[tuple[datetime, int]] = []
    for start, end in ranges:
        if end <= start:
            continue
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda item: (item[0], item[1]))

    conflict_ranges: list[tuple[datetime, datetime]] = []
    active = 0
    conflict_start: datetime | None = None
    for point, delta in events:
        previous = active
        active += delta
        if previous < 2 and active >= 2:
            conflict_start = point
        elif previous >= 2 and active < 2 and conflict_start and point > conflict_start:
            conflict_ranges.append((conflict_start, point))
            conflict_start = None
    return conflict_ranges


def _range_to_payload(start: datetime, end: datetime) -> dict[str, Any]:
    minutes = max(0, int((end - start).total_seconds() / 60))
    return {
        "start_at": _isoformat_utc(start),
        "end_at": _isoformat_utc(end),
        "minutes": minutes,
    }


def _resolve_scheduled_job_content(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    kind = str(payload.get("kind") or "").strip() or None
    if "message" in payload and isinstance(payload.get("message"), str):
        return "message", str(payload.get("message") or "")
    if "text" in payload and isinstance(payload.get("text"), str):
        return "text", str(payload.get("text") or "")
    return None, None


def _resolve_scheduled_job_bootstrap_root() -> tuple[str, Path]:
    display_root = str(WORKSPACE_VISIBLE_ROOT)
    candidates: list[Path] = []
    try:
        candidates.append(_map_visible_openclaw_path(WORKSPACE_VISIBLE_ROOT))
    except PermissionError:
        pass
    candidates.append(_resolved_openclaw_host_root())

    seen: set[str] = set()
    for raw_candidate in candidates:
        candidate = raw_candidate.resolve()
        marker = str(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        if candidate.exists() and candidate.is_dir():
            return display_root, candidate
    raise LookupError("openclaw_root_not_found")


def _refresh_scheduled_job_bootstrap(job: dict[str, Any], *, content: str | None) -> None:
    delivery = job.get("delivery") if isinstance(job.get("delivery"), dict) else {}
    bootstrap = delivery.get("bootstrap") if isinstance(delivery.get("bootstrap"), dict) else {}
    if not bool(bootstrap.get("enabled")):
        return
    if str(bootstrap.get("scope") or "auto").strip().lower() == "remote":
        try:
            with get_conn() as conn:
                node_rows = conn.execute("SELECT node_id FROM nodes ORDER BY created_at ASC, node_id ASC").fetchall()
                queued = _queue_scheduled_job_remote_sync_for_nodes(
                    conn,
                    job,
                    node_ids=[str(row["node_id"]) for row in node_rows if row["node_id"]],
                )
                conn.commit()
        except Exception as exc:
            bootstrap["status"] = "failed"
            bootstrap["message"] = f"远程同步队列写入失败：{exc}"
            bootstrap["syncedAt"] = None
            bootstrap["syncedRoot"] = None
            bootstrap["syncedFiles"] = []
            delivery["bootstrap"] = bootstrap
            job["delivery"] = delivery
            return

        bootstrap["status"] = "pending"
        if queued["node_count"] > 0:
            bootstrap["message"] = f"已加入 {queued['node_count']} 个节点的远程同步队列，等待节点 heartbeat 执行。"
            bootstrap["syncedFiles"] = list(queued["synced_files"])
        else:
            bootstrap["message"] = "当前没有已注册节点，远程同步会在节点接入后入队。"
            bootstrap["syncedFiles"] = []
        bootstrap["syncedAt"] = None
        bootstrap["syncedRoot"] = None
        delivery["bootstrap"] = bootstrap
        job["delivery"] = delivery
        return

    try:
        display_root, resolved_root = _resolve_scheduled_job_bootstrap_root()
    except LookupError:
        bootstrap["status"] = "pending"
        bootstrap["message"] = "未找到 .openclaw 根目录，已保存渠道配置，待环境就绪后再次保存即可自动同步。"
        bootstrap["syncedAt"] = None
        bootstrap["syncedRoot"] = None
        bootstrap["syncedFiles"] = []
        delivery["bootstrap"] = bootstrap
        job["delivery"] = delivery
        return

    sync_delivery_bootstrap_files(
        job,
        openclaw_root=resolved_root,
        openclaw_display_root=display_root,
        synced_at=now_iso(),
        content=content,
    )


def _serialize_agent_scheduled_job(job: dict[str, Any]) -> dict[str, Any]:
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    content_field, content = _resolve_scheduled_job_content(payload)
    schedule_kind = str(schedule.get("kind") or "cron").strip() or "cron"
    if schedule_kind not in {"cron", "every", "at"}:
        raise ValueError("scheduled_job_schedule_kind_unsupported")
    every_ms = None
    every_minutes = None
    if schedule_kind == "every":
        raw_every_ms = schedule.get("everyMs")
        if raw_every_ms not in (None, ""):
            try:
                every_ms = int(raw_every_ms)
                every_minutes = max(1, int(every_ms / 60000))
            except (TypeError, ValueError):
                every_ms = None
                every_minutes = None
    serialized = {
        "id": str(job.get("id") or ""),
        "agent_id": str(job.get("agentId") or "") or None,
        "name": str(job.get("name") or "未命名任务").strip() or "未命名任务",
        "description": str(job.get("description") or "").strip() or None,
        "enabled": bool(job.get("enabled", True)),
        "schedule_kind": schedule_kind,
        "cron_expr": str(schedule.get("expr") or "").strip() or None,
        "timezone": str(schedule.get("tz") or "").strip() or None,
        "every_ms": every_ms,
        "every_minutes": every_minutes,
        "at": str(schedule.get("at") or "").strip() or None,
        "payload_kind": str(payload.get("kind") or "").strip() or None,
        "content_field": content_field,
        "content": content,
        "next_run_at": _ts_ms_to_iso((job.get("state") or {}).get("nextRunAtMs") if isinstance(job.get("state"), dict) else None),
        "last_run_at": _ts_ms_to_iso((job.get("state") or {}).get("lastRunAtMs") if isinstance(job.get("state"), dict) else None),
        "last_status": str(((job.get("state") or {}).get("lastStatus") if isinstance(job.get("state"), dict) else None) or "").strip() or None,
        "updated_at": _ts_ms_to_iso(job.get("updatedAtMs")),
        **serialize_delivery_metadata(job, content=content),
    }
    if serialized["delivery_bootstrap_enabled"] and serialized["delivery_bootstrap_scope"] == "remote":
        snapshot = _get_remote_scheduled_job_sync_snapshot(serialized["id"])
        if snapshot:
            serialized["delivery_bootstrap_status"] = snapshot["status"]
            serialized["delivery_bootstrap_message"] = snapshot["message"]
            serialized["delivery_bootstrap_synced_at"] = snapshot["synced_at"]
            serialized["delivery_bootstrap_synced_root"] = snapshot["synced_root"]
            serialized["delivery_synced_files"] = snapshot["synced_files"]
    return serialized


def list_agent_scheduled_jobs(agent_id: str) -> dict[str, Any]:
    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")
    payload = _load_openclaw_jobs_document()
    jobs = payload.get("jobs") or []
    items: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if str(job.get("agentId") or "").strip() != agent_id:
            continue
        try:
            items.append(_serialize_agent_scheduled_job(job))
        except ValueError:
            continue
    items.sort(key=lambda item: ((item.get("name") or "").lower(), item.get("id") or ""))
    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "jobs": items,
    }


def update_agent_scheduled_job(agent_id: str, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")

    raw_job_id = str(job_id or "").strip()
    if not raw_job_id:
        raise ValueError("scheduled_job_id_required")

    document = _load_openclaw_jobs_document()
    jobs = document.get("jobs") or []
    matched_job: dict[str, Any] | None = None
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if str(job.get("id") or "").strip() != raw_job_id:
            continue
        if str(job.get("agentId") or "").strip() != agent_id:
            raise PermissionError("scheduled_job_agent_mismatch")
        matched_job = job
        break

    if not matched_job:
        raise LookupError("scheduled_job_not_found")

    schedule = matched_job.get("schedule")
    if not isinstance(schedule, dict):
        raise ValueError("scheduled_job_schedule_missing")

    schedule_kind = str(schedule.get("kind") or "").strip()
    requested_kind = str(payload.get("schedule_kind") or "").strip()
    if schedule_kind not in {"cron", "every", "at"}:
        raise ValueError("scheduled_job_schedule_kind_unsupported")
    if requested_kind not in {"cron", "every", "at"}:
        raise ValueError("scheduled_job_schedule_kind_unsupported")

    content_field, _existing_content = _resolve_scheduled_job_content(
        matched_job.get("payload") if isinstance(matched_job.get("payload"), dict) else {}
    )
    if not content_field:
        raise ValueError("scheduled_job_content_not_editable")

    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("scheduled_job_content_required")

    if "name" in payload:
        next_name = str(payload.get("name") or "").strip()
        if not next_name:
            raise ValueError("scheduled_job_name_required")
        matched_job["name"] = next_name

    if "description" in payload:
        matched_job["description"] = str(payload.get("description") or "").strip() or None

    next_schedule: dict[str, Any] = {"kind": requested_kind}
    if requested_kind == "cron":
        next_schedule["expr"] = _normalize_cron_expr(payload.get("cron_expr"))
        next_schedule["tz"] = str(schedule.get("tz") or "Asia/Shanghai").strip() or "Asia/Shanghai"
    elif requested_kind == "every":
        next_schedule["everyMs"] = _normalize_every_ms(payload.get("every_ms"))
    elif requested_kind == "at":
        next_schedule["at"] = _normalize_at_iso(payload.get("at"))

    if not isinstance(matched_job.get("payload"), dict):
        matched_job["payload"] = {}
    matched_job["enabled"] = bool(payload.get("enabled", matched_job.get("enabled", True)))
    matched_job["schedule"] = next_schedule
    matched_job["payload"][content_field] = content
    apply_delivery_payload(matched_job, payload, content=content)
    _refresh_scheduled_job_bootstrap(matched_job, content=content)
    matched_job["updatedAtMs"] = int(time.time() * 1000)

    _write_openclaw_jobs_document(document)
    return _serialize_agent_scheduled_job(matched_job)


def create_agent_scheduled_job(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")

    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("scheduled_job_name_required")

    description = str(payload.get("description") or "").strip() or None
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("scheduled_job_content_required")

    requested_kind = str(payload.get("schedule_kind") or "").strip()
    if requested_kind not in {"cron", "every", "at"}:
        raise ValueError("scheduled_job_schedule_kind_unsupported")

    schedule: dict[str, Any] = {"kind": requested_kind}
    if requested_kind == "cron":
        schedule["expr"] = _normalize_cron_expr(payload.get("cron_expr"))
        schedule["tz"] = "Asia/Shanghai"
    elif requested_kind == "every":
        schedule["everyMs"] = _normalize_every_ms(payload.get("every_ms"))
    else:
        schedule["at"] = _normalize_at_iso(payload.get("at"))

    now_ms = int(time.time() * 1000)
    job = {
        "id": str(uuid.uuid4()),
        "name": name,
        "description": description,
        "enabled": bool(payload.get("enabled", True)),
        "createdAtMs": now_ms,
        "updatedAtMs": now_ms,
        "schedule": schedule,
        "sessionTarget": "isolated",
        "wakeMode": "next-heartbeat",
        "payload": {
            "kind": "agentTurn",
            "message": content,
        },
        "delivery": {
            "mode": "none",
            "channel": "last",
        },
        "state": {},
        "agentId": agent_id,
    }
    apply_delivery_payload(job, payload, content=content)
    _refresh_scheduled_job_bootstrap(job, content=content)

    document = _load_openclaw_jobs_document()
    jobs = document.get("jobs")
    if not isinstance(jobs, list):
        document["jobs"] = []
        jobs = document["jobs"]
    jobs.append(job)
    _write_openclaw_jobs_document(document)
    return _serialize_agent_scheduled_job(job)


def get_scheduled_jobs_timeline(
    from_at: str | None = None,
    to_at: str | None = None,
    agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    window_start, window_end = _parse_timeline_window(from_at, to_at)
    requested_agent_ids = {str(item).strip() for item in (agent_ids or []) if str(item).strip()}

    all_agents = list_agents(status=None, q=None)
    if requested_agent_ids:
        agents = [item for item in all_agents if item.get("agent_id") in requested_agent_ids]
    else:
        agents = all_agents

    agent_map = {str(item["agent_id"]): item for item in agents if item.get("agent_id")}
    document = _load_openclaw_jobs_document()
    raw_jobs = document.get("jobs") or []
    jobs_by_agent: dict[str, list[dict[str, Any]]] = {agent_id: [] for agent_id in agent_map}
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue
        agent_id = str(raw_job.get("agentId") or "").strip()
        if not agent_id or agent_id not in jobs_by_agent:
            continue
        jobs_by_agent[agent_id].append(raw_job)

    window_minutes = max(1, int((window_end - window_start).total_seconds() / 60))
    rows: list[dict[str, Any]] = []

    for agent in agents:
        agent_id = str(agent["agent_id"])
        occurrences: list[dict[str, Any]] = []
        raw_coverage_ranges: list[tuple[datetime, datetime]] = []
        enabled_job_count = 0

        for raw_job in jobs_by_agent.get(agent_id, []):
            try:
                serialized_job = _serialize_agent_scheduled_job(raw_job)
            except ValueError:
                continue

            if serialized_job.get("enabled"):
                enabled_job_count += 1
            else:
                continue

            duration_minutes, estimated = _resolve_job_duration_minutes(raw_job, serialized_job)
            duration_delta = timedelta(minutes=duration_minutes)
            schedule = raw_job.get("schedule") if isinstance(raw_job.get("schedule"), dict) else {}
            schedule_kind = str(schedule.get("kind") or "").strip()

            if schedule_kind == "cron":
                occurrence_starts = _expand_cron_occurrences(
                    str(schedule.get("expr") or ""),
                    schedule.get("tz"),
                    window_start,
                    window_end,
                )
            elif schedule_kind == "every":
                every_ms = _coerce_positive_int(schedule.get("everyMs"))
                occurrence_starts = (
                    _expand_every_occurrences(raw_job, every_ms, window_start, window_end) if every_ms else []
                )
            elif schedule_kind == "at":
                occurrence_starts = _expand_at_occurrence(str(schedule.get("at") or ""), window_start, window_end)
            else:
                occurrence_starts = []

            for start_at in occurrence_starts:
                end_at = start_at + duration_delta
                clipped_start = max(start_at, window_start)
                clipped_end = min(end_at, window_end)
                if clipped_end > clipped_start:
                    raw_coverage_ranges.append((clipped_start, clipped_end))

                occurrences.append(
                    {
                        "occurrence_id": f"{serialized_job['id']}:{int(start_at.timestamp() * 1000)}",
                        "job": serialized_job,
                        "start_at": _isoformat_utc(start_at),
                        "end_at": _isoformat_utc(end_at),
                        "minutes": duration_minutes,
                        "estimated": estimated,
                    }
                )

        coverage_ranges = _merge_ranges(raw_coverage_ranges)
        conflict_ranges = _calculate_conflict_ranges(raw_coverage_ranges)

        idle_ranges: list[tuple[datetime, datetime]] = []
        cursor = window_start
        for start_at, end_at in coverage_ranges:
            if start_at > cursor:
                idle_ranges.append((cursor, start_at))
            cursor = max(cursor, end_at)
        if cursor < window_end:
            idle_ranges.append((cursor, window_end))

        occupied_minutes = sum(max(0, int((end - start).total_seconds() / 60)) for start, end in coverage_ranges)
        conflict_minutes = sum(max(0, int((end - start).total_seconds() / 60)) for start, end in conflict_ranges)
        coverage_ratio = min(1.0, occupied_minutes / window_minutes) if window_minutes else 0

        rows.append(
            {
                "agent_id": agent_id,
                "agent_name": str(agent.get("display_name") or agent_id),
                "coverage_ratio": round(coverage_ratio, 4),
                "occupied_minutes": occupied_minutes,
                "conflict_minutes": conflict_minutes,
                "enabled_job_count": enabled_job_count,
                "occurrence_count": len(occurrences),
                "occurrences": sorted(occurrences, key=lambda item: (item["start_at"], item["job"]["name"])),
                "conflict_ranges": [_range_to_payload(start, end) for start, end in conflict_ranges],
                "idle_ranges": [_range_to_payload(start, end) for start, end in idle_ranges],
            }
        )

    rows.sort(key=lambda item: (item["agent_name"], item["agent_id"]))
    return {
        "from_at": _isoformat_utc(window_start),
        "to_at": _isoformat_utc(window_end),
        "generated_at": _isoformat_utc(datetime.now(timezone.utc)),
        "rows": rows,
    }


def _resolve_agent_session_file(agent_id: str) -> tuple[str | None, str | None, Path | None]:
    sessions_root = (_resolved_openclaw_host_root() / "agents" / agent_id / "sessions").resolve()
    if not sessions_root.exists() or not sessions_root.is_dir():
        return None, None, None

    sessions_manifest = sessions_root / "sessions.json"
    best_session_id: str | None = None
    best_session_file: str | None = None
    best_updated_at: int = -1
    if sessions_manifest.exists():
        try:
            data = json.loads(sessions_manifest.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            for row in data.values():
                if not isinstance(row, dict):
                    continue
                updated_at = int(row.get("updatedAt") or 0)
                session_file = row.get("sessionFile")
                session_id = row.get("sessionId")
                if updated_at >= best_updated_at and session_file and session_id:
                    best_updated_at = updated_at
                    best_session_id = str(session_id)
                    best_session_file = str(session_file)

    if best_session_file:
        try:
            resolved = _map_visible_openclaw_path(Path(best_session_file))
            if resolved.exists() and resolved.is_file():
                updated_at_iso = (
                    datetime.fromtimestamp(best_updated_at / 1000, tz=timezone.utc).isoformat()
                    if best_updated_at > 0
                    else None
                )
                return best_session_id, updated_at_iso, resolved
        except Exception:
            pass

    jsonl_files = sorted(sessions_root.glob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not jsonl_files:
        return None, None, None
    latest = jsonl_files[0]
    return latest.stem, datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat(), latest


def _message_text_summary(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    texts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and part.get("text"):
            texts.append(str(part["text"]).strip())
        elif part.get("type") == "tool_use" and part.get("name"):
            texts.append(f"调用工具：{part['name']}")
    summary = " ".join(texts).strip()
    return summary[:600]


def _activity_text_excerpt(value: Any, limit: int = 600) -> str:
    clean = str(value or "").strip()
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit].rstrip()}..."


def _scheduled_job_status_label(status: str) -> str:
    lowered = str(status or "").strip().lower()
    if lowered == "ok":
        return "成功"
    if lowered == "error":
        return "失败"
    if lowered == "skipped":
        return "跳过"
    if lowered == "running":
        return "运行中"
    return lowered or "未知"


def _scheduled_job_action_label(action: str) -> str:
    lowered = str(action or "").strip().lower()
    if lowered == "finished":
        return "执行完成"
    if lowered == "started":
        return "开始执行"
    return lowered or "运行事件"


def _format_duration_ms(value: Any) -> str | None:
    try:
        duration_ms = int(value)
    except (TypeError, ValueError):
        return None
    if duration_ms < 0:
        return None
    if duration_ms >= 1000:
        return f"{duration_ms / 1000:.1f}s"
    return f"{duration_ms}ms"


def _load_agent_scheduled_job_index(agent_id: str) -> dict[str, dict[str, Any]]:
    payload = _load_openclaw_jobs_document()
    jobs = payload.get("jobs") or []
    index: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if str(job.get("agentId") or "").strip() != agent_id:
            continue
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            continue
        index[job_id] = {
            "id": job_id,
            "name": str(job.get("name") or "").strip() or job_id,
            "enabled": bool(job.get("enabled", True)),
        }
    return index


def _load_agent_scheduled_job_run_events(agent_id: str) -> list[dict[str, Any]]:
    runs_root = _resolved_openclaw_cron_runs_root()
    if not runs_root.exists() or not runs_root.is_dir():
        return []

    job_index = _load_agent_scheduled_job_index(agent_id)
    if not job_index:
        return []

    events: list[dict[str, Any]] = []
    for job_id, job_meta in job_index.items():
        run_file = runs_root / f"{job_id}.jsonl"
        if not run_file.exists() or not run_file.is_file():
            continue

        with run_file.open(encoding="utf-8", errors="replace") as handle:
            tail_lines = deque(handle, maxlen=max(1, CRON_RUN_ACTIVITY_TAIL_PER_JOB))

        for index, line in enumerate(tail_lines):
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue

                event_ts = row.get("ts") or row.get("runAtMs") or row.get("nextRunAtMs")
                timestamp = _ts_ms_to_iso(event_ts) or now_iso()
                title = f"定时任务 · {job_meta['name']}"
                detail_lines = [
                    f"执行状态：{_scheduled_job_status_label(str(row.get('status') or ''))}",
                    f"动作：{_scheduled_job_action_label(str(row.get('action') or ''))}",
                ]

                started_at = _ts_ms_to_iso(row.get("runAtMs"))
                if started_at:
                    detail_lines.append(f"开始时间：{started_at}")

                duration_label = _format_duration_ms(row.get("durationMs"))
                if duration_label:
                    detail_lines.append(f"耗时：{duration_label}")

                delivery_status = str(row.get("deliveryStatus") or "").strip()
                if delivery_status:
                    detail_lines.append(f"投递状态：{delivery_status}")

                session_id = str(row.get("sessionId") or "").strip()
                if session_id:
                    detail_lines.append(f"会话：{session_id}")

                error_text = _activity_text_excerpt(row.get("error"), 400)
                summary_text = _activity_text_excerpt(row.get("summary"), 800)
                if error_text:
                    detail_lines.append(f"错误：{error_text}")
                elif summary_text:
                    detail_lines.append(f"摘要：{summary_text}")

                events.append(
                    {
                        "id": f"cron:{job_id}:{index}:{event_ts or index}",
                        "timestamp": timestamp,
                        "kind": "scheduled_job",
                        "actor": "system",
                        "title": title,
                        "detail": "\n".join(detail_lines),
                    }
                )
    return events


def _session_row_text(row: dict[str, Any]) -> str:
    row_type = str(row.get("type") or "").strip().lower()
    if row_type == "message":
        message = row.get("message")
        if isinstance(message, dict):
            return _message_text_summary(message)
    if row_type == "custom":
        custom_type = str(row.get("customType") or "").strip()
        data = row.get("data")
        data_text = json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data or "")
        return f"{custom_type} {data_text}".strip()
    return json.dumps(row, ensure_ascii=False)


def _is_heartbeat_only_session_row(row: dict[str, Any]) -> bool:
    row_type = str(row.get("type") or "").strip().lower()
    if row_type == "custom" and "heartbeat" in str(row.get("customType") or "").strip().lower():
        return True
    if row_type == "message":
        message = row.get("message")
        role = str((message or {}).get("role") or "").strip().lower() if isinstance(message, dict) else ""
        if role not in {"assistant", "toolresult"}:
            return False
    text = _session_row_text(row).strip()
    if not text:
        return False
    normalized = " ".join(text.lower().split())
    return any(pattern.search(normalized) for pattern in AGENT_RUNTIME_HEARTBEAT_ONLY_PATTERNS)


def _is_meaningful_activity_row(row: dict[str, Any]) -> bool:
    if _is_heartbeat_only_session_row(row):
        return False
    row_type = str(row.get("type") or "").strip().lower()
    if row_type == "message":
        message = row.get("message")
        role = str((message or {}).get("role") or "").strip().lower() if isinstance(message, dict) else ""
        return role in {"user", "assistant", "toolresult"}
    if row_type == "custom":
        custom_type = str(row.get("customType") or "").strip().lower()
        return any(token in custom_type for token in ("job", "tool", "task", "agentturn", "run"))
    return False


def _is_recovery_activity_row(row: dict[str, Any]) -> bool:
    if _is_heartbeat_only_session_row(row):
        return False
    row_type = str(row.get("type") or "").strip().lower()
    if _is_meaningful_activity_row(row):
        return True
    return row_type in {"model_change", "thinking_level_change", "custom"}


def _extract_session_tail_runtime_snapshot(
    session_file: Path,
    fallback_iso: str | None,
) -> dict[str, Any]:
    snapshot = {
        "latest_activity_at": fallback_iso,
        "latest_meaningful_activity_at": None,
        "last_heartbeat_only_at": None,
        "fatal_match": False,
        "fatal_excerpt": None,
        "fatal_at": None,
        "last_recovery_at": None,
    }

    try:
        with session_file.open(encoding="utf-8", errors="replace") as handle:
            tail_lines = deque(handle, maxlen=max(1, AGENT_RUNTIME_SESSION_TAIL_LINES))
    except Exception:
        return snapshot

    for line in tail_lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue

        timestamp = str(row.get("timestamp") or "").strip() or None
        if timestamp:
            snapshot["latest_activity_at"] = timestamp

        row_text = _session_row_text(row)
        if _is_heartbeat_only_session_row(row):
            if timestamp:
                snapshot["last_heartbeat_only_at"] = timestamp
            continue

        if _is_meaningful_activity_row(row) and timestamp:
            snapshot["latest_meaningful_activity_at"] = timestamp

        if _is_recovery_activity_row(row) and timestamp:
            snapshot["last_recovery_at"] = timestamp

        if snapshot["fatal_match"]:
            continue
        lowered_text = row_text.lower()
        for pattern in AGENT_RUNTIME_FATAL_PATTERNS:
            if pattern.search(lowered_text):
                snapshot["fatal_match"] = True
                snapshot["fatal_excerpt"] = row_text[:600]
                snapshot["fatal_at"] = timestamp
                break

    return snapshot


def _resolve_agent_session_runtime_snapshot(agent_id: str) -> dict[str, Any]:
    session_id, updated_at, session_file = _resolve_agent_session_file(agent_id)
    if not session_file:
        return {
            "session_id": None,
            "session_updated_at": None,
            "session_file": None,
            "latest_activity_at": None,
            "latest_meaningful_activity_at": None,
            "last_heartbeat_only_at": None,
            "fatal_match": False,
            "fatal_excerpt": None,
            "fatal_at": None,
            "last_recovery_at": None,
        }

    snapshot = _extract_session_tail_runtime_snapshot(session_file, updated_at)
    snapshot.update(
        {
            "session_id": session_id,
            "session_updated_at": updated_at,
            "session_file": session_file,
        }
    )
    return snapshot


def _resolve_agent_latest_activity_at(agent_id: str) -> str | None:
    snapshot = _resolve_agent_session_runtime_snapshot(agent_id)
    return str(snapshot.get("latest_meaningful_activity_at") or "") or None


def _derive_agent_runtime_snapshot(
    agent: dict[str, Any],
    *,
    official_signal: dict[str, Any] | None,
    node_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    session_snapshot = _resolve_agent_session_runtime_snapshot(str(agent.get("agent_id") or ""))
    latest_activity_at = str(session_snapshot.get("latest_meaningful_activity_at") or "") or None
    latest_any_activity_at = str(session_snapshot.get("latest_activity_at") or "") or None
    status_at: str | None = latest_activity_at or latest_any_activity_at
    runtime_node_status = (
        str(node_snapshot.get("status"))
        if isinstance(node_snapshot, dict) and node_snapshot.get("status")
        else None
    )

    fatal_at = _parse_iso_utc(str(session_snapshot.get("fatal_at") or ""), "agent_runtime_fatal_at")
    recovery_at = _parse_iso_utc(str(session_snapshot.get("last_recovery_at") or ""), "agent_runtime_recovery_at")
    if fatal_at and (recovery_at is None or recovery_at <= fatal_at):
        return {
            "latest_activity_at": latest_activity_at,
            "runtime_status": "crashed",
            "runtime_status_reason": "最近会话日志命中崩溃特征，且之后没有恢复活动。",
            "runtime_status_at": str(session_snapshot.get("fatal_at") or status_at or ""),
            "runtime_signal_source": "fatal_log",
            "runtime_node_status": runtime_node_status,
            "runtime_crash_excerpt": session_snapshot.get("fatal_excerpt"),
        }

    if isinstance(official_signal, dict) and official_signal.get("host_online") is False:
        return {
            "latest_activity_at": latest_activity_at,
            "runtime_status": "offline",
            "runtime_status_reason": str(official_signal.get("reason") or "官方 liveness 信号显示宿主不可达。"),
            "runtime_status_at": str(official_signal.get("observed_at") or status_at or ""),
            "runtime_signal_source": str(official_signal.get("source") or "official_signal"),
            "runtime_node_status": runtime_node_status,
            "runtime_crash_excerpt": None,
        }

    if runtime_node_status == "offline":
        return {
            "latest_activity_at": latest_activity_at,
            "runtime_status": "offline",
            "runtime_status_reason": "节点 heartbeat 已超时，当前宿主被判定为离线。",
            "runtime_status_at": str((node_snapshot or {}).get("last_seen_at") or status_at or ""),
            "runtime_signal_source": "node_heartbeat",
            "runtime_node_status": runtime_node_status,
            "runtime_crash_excerpt": None,
        }

    if isinstance(official_signal, dict) and official_signal.get("work_state") == "working":
        return {
            "latest_activity_at": latest_activity_at,
            "runtime_status": "working",
            "runtime_status_reason": str(official_signal.get("reason") or "官方 work state 显示当前存在活跃工作。"),
            "runtime_status_at": str(official_signal.get("observed_at") or status_at or ""),
            "runtime_signal_source": str(official_signal.get("source") or "official_signal"),
            "runtime_node_status": runtime_node_status,
            "runtime_crash_excerpt": None,
        }

    latest_dt = _parse_iso_utc(latest_activity_at, "agent_runtime_latest_activity_at")
    if latest_dt:
        delta = datetime.now(timezone.utc) - latest_dt
        if delta.total_seconds() <= AGENT_RUNTIME_WORKING_WINDOW_SEC:
            return {
                "latest_activity_at": latest_activity_at,
                "runtime_status": "working",
                "runtime_status_reason": "最近有效活动仍在工作时间窗口内。",
                "runtime_status_at": latest_dt.isoformat(),
                "runtime_signal_source": "session_activity",
                "runtime_node_status": runtime_node_status,
                "runtime_crash_excerpt": None,
            }

    reachable = False
    if isinstance(official_signal, dict) and official_signal.get("host_online") is True:
        reachable = True
    if runtime_node_status == "online":
        reachable = True
    if session_snapshot.get("session_file"):
        reachable = True

    reference_iso = latest_activity_at or latest_any_activity_at or str(agent.get("created_at") or "").strip() or None
    reference_dt = _parse_iso_utc(reference_iso, "agent_runtime_reference_at")
    if not reachable:
        is_stale = True
        if reference_dt:
            is_stale = (datetime.now(timezone.utc) - reference_dt).total_seconds() >= AGENT_RUNTIME_OFFLINE_STALE_WINDOW_SEC
        if is_stale:
            return {
                "latest_activity_at": latest_activity_at,
                "runtime_status": "offline",
                "runtime_status_reason": "缺少可达性信号，且最近有效活动已超过离线兜底窗口。",
                "runtime_status_at": reference_iso,
                "runtime_signal_source": "stale_fallback",
                "runtime_node_status": runtime_node_status,
                "runtime_crash_excerpt": None,
            }

    idle_reason = "当前宿主可达，但最近没有处于工作窗口内的有效活动。"
    idle_source = "session_activity"
    if isinstance(official_signal, dict) and official_signal.get("host_online") is True:
        idle_reason = str(official_signal.get("reason") or idle_reason)
        idle_source = str(official_signal.get("source") or "official_signal")
    elif runtime_node_status == "online":
        idle_reason = "节点 heartbeat 正常，但最近没有处于工作窗口内的有效活动。"
        idle_source = "node_heartbeat"

    return {
        "latest_activity_at": latest_activity_at,
        "runtime_status": "idle",
        "runtime_status_reason": idle_reason,
        "runtime_status_at": reference_iso,
        "runtime_signal_source": idle_source,
        "runtime_node_status": runtime_node_status,
        "runtime_crash_excerpt": None,
    }


def get_agent_activity_logs(agent_id: str, limit: int = 80) -> dict[str, Any]:
    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")
    session_id, updated_at, session_file = _resolve_agent_session_file(agent_id)

    events: list[dict[str, Any]] = []
    if session_file:
        with session_file.open(encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                try:
                    row = json.loads(line)
                except Exception:
                    continue

                row_type = str(row.get("type") or "unknown")
                timestamp = str(row.get("timestamp") or updated_at or now_iso())
                entry = {
                    "id": f"{session_id or session_file.stem}:{index}",
                    "timestamp": timestamp,
                    "kind": row_type,
                    "actor": "system",
                    "title": "运行事件",
                    "detail": "",
                }

                if row_type == "session":
                    entry["title"] = "会话启动"
                    entry["detail"] = str(row.get("cwd") or "")
                elif row_type == "model_change":
                    entry["title"] = "切换模型"
                    entry["detail"] = f"{row.get('provider') or 'unknown'} / {row.get('modelId') or 'unknown'}"
                elif row_type == "thinking_level_change":
                    entry["title"] = "思考级别变更"
                    entry["detail"] = str(row.get("thinkingLevel") or "unknown")
                elif row_type == "custom":
                    custom_type = str(row.get("customType") or "custom")
                    entry["title"] = f"自定义事件 · {custom_type}"
                    entry["detail"] = json.dumps(row.get("data") or {}, ensure_ascii=False)[:600]
                elif row_type == "message":
                    message = row.get("message") or {}
                    role = str(message.get("role") or "unknown")
                    actor_map = {
                        "user": "user",
                        "assistant": "assistant",
                        "toolResult": "tool",
                    }
                    title_map = {
                        "user": "收到指令",
                        "assistant": "Agent 响应",
                        "toolResult": "工具结果",
                    }
                    entry["actor"] = actor_map.get(role, "system")
                    entry["title"] = title_map.get(role, f"消息 · {role}")
                    entry["detail"] = _message_text_summary(message) or "无文本摘要"
                else:
                    entry["detail"] = json.dumps(row, ensure_ascii=False)[:600]

                events.append(entry)

    events.extend(_load_agent_scheduled_job_run_events(agent_id))

    safe_limit = max(1, min(limit, SESSION_LOG_LIMIT_MAX))
    events.sort(key=lambda item: (str(item.get("timestamp") or ""), str(item.get("id") or "")))
    trimmed = events[-safe_limit:]
    return {
        "agent_id": agent_id,
        "agent_name": agent["display_name"],
        "session_id": session_id,
        "session_updated_at": updated_at,
        "session_file": str(session_file).replace(str(_resolved_openclaw_host_root()), str(WORKSPACE_VISIBLE_ROOT), 1),
        "items": trimmed,
    }


def create_task(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = generate_task_id()
    now = now_iso()
    row = {
        "task_id": task_id,
        "title": payload["title"],
        "description": payload.get("description"),
        "creator_type": payload["creator_type"],
        "creator_id": payload["creator_id"],
        "assignee_agent_id": payload["assignee_agent_id"],
        "status": "todo",
        "priority": payload.get("priority", "medium"),
        "expected_output": payload["expected_output"],
        "acceptance_criteria": payload["acceptance_criteria"],
        "deadline_at": payload.get("deadline_at"),
        "created_at": now,
        "updated_at": now,
    }

    with get_conn() as conn:
        agent = conn.execute(
            "SELECT agent_id FROM agents WHERE agent_id = ?",
            (payload["assignee_agent_id"],),
        ).fetchone()
        if not agent:
            raise ValueError("assignee_not_found")

        conn.execute(
            """
            INSERT INTO tasks (
                task_id, title, description, creator_type, creator_id,
                assignee_agent_id, status, priority, expected_output,
                acceptance_criteria, deadline_at, created_at, updated_at
            ) VALUES (
                :task_id, :title, :description, :creator_type, :creator_id,
                :assignee_agent_id, :status, :priority, :expected_output,
                :acceptance_criteria, :deadline_at, :created_at, :updated_at
            )
            """,
            row,
        )
        add_task_event(
            conn,
            task_id=task_id,
            event_type="created",
            actor_type=row["creator_type"],
            actor_id=row["creator_id"],
            payload={
                "assignee_agent_id": row["assignee_agent_id"],
                "expected_output": row["expected_output"],
            },
        )
        conn.commit()
    return row


def add_task_event(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    event_type: str,
    actor_type: str,
    actor_id: str,
    payload: dict[str, Any] | None,
) -> None:
    conn.execute(
        """
        INSERT INTO task_events (task_id, event_type, actor_type, actor_id, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            event_type,
            actor_type,
            actor_id,
            json.dumps(payload or {}, ensure_ascii=False),
            now_iso(),
        ),
    )


def list_tasks(
    *,
    status: str | None,
    assignee_agent_id: str | None,
    creator_type: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    with get_conn() as conn:
        where = "WHERE 1=1"
        params: list[Any] = []
        if status:
            where += " AND status = ?"
            params.append(status)
        if assignee_agent_id:
            where += " AND assignee_agent_id = ?"
            params.append(assignee_agent_id)
        if creator_type:
            where += " AND creator_type = ?"
            params.append(creator_type)

        total_row = conn.execute(f"SELECT COUNT(1) AS cnt FROM tasks {where}", params).fetchone()
        total = int(total_row["cnt"] if total_row else 0)

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
        return [dict(r) for r in rows], total


def get_task(task_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def get_task_with_events(task_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    with get_conn() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            return None, []

        rows = conn.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC",
            (task_id,),
        ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            payload = item.get("payload_json")
            item["payload"] = json.loads(payload) if payload else {}
            item.pop("payload_json", None)
            events.append(item)
        return dict(task), events


def dispatch_task(task_id: str, actor_id: str, mode: str, session_hint: str | None) -> dict[str, Any]:
    with get_conn() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            raise LookupError("task_not_found")
        if task["status"] != "todo":
            raise RuntimeError("task_not_dispatchable")

        conn.execute(
            "UPDATE tasks SET status = 'doing', updated_at = ? WHERE task_id = ?",
            (now_iso(), task_id),
        )
        session_id = str(uuid.uuid4())
        add_task_event(
            conn,
            task_id=task_id,
            event_type="dispatched",
            actor_type="system",
            actor_id=actor_id,
            payload={"mode": mode, "session_hint": session_hint, "session_id": session_id},
        )
        conn.commit()
        return {
            "task_id": task_id,
            "mode": mode,
            "session_id": session_id,
            "dispatched_at": now_iso(),
        }


def submit_task(task_id: str, actor_agent_id: str, summary: str, evidence_links: list[str] | None) -> dict[str, Any]:
    with get_conn() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            raise LookupError("task_not_found")
        if task["status"] not in ("doing", "review"):
            raise RuntimeError("task_not_submittable")
        if task["assignee_agent_id"] != actor_agent_id:
            raise PermissionError("submitter_not_assignee")

        conn.execute(
            "UPDATE tasks SET status = 'review', updated_at = ? WHERE task_id = ?",
            (now_iso(), task_id),
        )
        add_task_event(
            conn,
            task_id=task_id,
            event_type="submitted",
            actor_type="agent",
            actor_id=actor_agent_id,
            payload={"summary": summary, "evidence_links": evidence_links or []},
        )
        conn.commit()

    task = get_task(task_id)
    if not task:
        raise LookupError("task_not_found_after_submit")
    return task


def review_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload["decision"]
    reviewer_id = payload["reviewer_id"]
    score_delta = int(payload.get("score_delta", 0))
    receipt = payload.get("receipt")

    with get_conn() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            raise LookupError("task_not_found")
        if task["status"] != "review":
            raise RuntimeError("task_not_reviewable")

        if decision == "approved":
            if not receipt:
                raise ValueError("receipt_required")
            if task["creator_type"] == "agent" and not receipt.get("include_creator_agent_id"):
                raise ValueError("receipt_include_creator_agent_id_required")

        next_status = "done" if decision == "approved" else "rejected"
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (next_status, now_iso(), task_id),
        )

        add_task_event(
            conn,
            task_id=task_id,
            event_type="reviewed",
            actor_type="human",
            actor_id=reviewer_id,
            payload={
                "decision": decision,
                "review_comment": payload.get("review_comment"),
                "score_delta": score_delta,
            },
        )

        score_written = False
        if decision == "approved" and score_delta != 0:
            conn.execute(
                """
                INSERT INTO score_ledger (agent_id, source_type, source_id, delta_points, reason, created_at)
                VALUES (?, 'task', ?, ?, ?, ?)
                """,
                (
                    task["assignee_agent_id"],
                    task_id,
                    score_delta,
                    payload.get("review_comment") or "task_review",
                    now_iso(),
                ),
            )
            score_written = True

        receipt_sent = False
        if decision == "approved" and receipt:
            add_task_event(
                conn,
                task_id=task_id,
                event_type="receipt_sent",
                actor_type="system",
                actor_id="ops-backend",
                payload=receipt,
            )
            receipt_sent = True

        conn.commit()

    task_now = get_task(task_id)
    if not task_now:
        raise LookupError("task_not_found_after_review")
    return {
        "task": task_now,
        "score_ledger_written": score_written,
        "receipt_sent": receipt_sent,
    }


def get_leaderboard(period: str) -> dict[str, Any]:
    if period not in {"all", "weekly", "monthly"}:
        raise ValueError("invalid_period")

    enriched_agents = {str(item.get("agent_id") or ""): item for item in list_agents(status=None, q=None)}

    with get_conn() as conn:
        sql = """
            SELECT a.agent_id, a.display_name, a.role, COALESCE(SUM(s.delta_points), 0) AS points
            FROM agents a
            LEFT JOIN score_ledger s ON s.agent_id = a.agent_id
            GROUP BY a.agent_id, a.display_name, a.role
            ORDER BY points DESC, a.agent_id ASC
        """
        rows = conn.execute(sql).fetchall()

    items = []
    rank = 1
    for row in rows:
        agent_id = str(row["agent_id"])
        enriched = enriched_agents.get(agent_id) or {}
        items.append(
            {
                "rank": rank,
                "agent_id": agent_id,
                "display_name": str(enriched.get("display_name") or row["display_name"]),
                "points": int(row["points"]),
                "role": str(enriched.get("role") or row["role"] or "").strip() or None,
                "role_summary": str(enriched.get("role_summary") or "").strip() or None,
                "channel": str(enriched.get("channel") or "").strip() or None,
                "avatar_url": str(enriched.get("avatar_url") or "").strip() or None,
                "avatar_hint": str(enriched.get("avatar_hint") or "").strip() or None,
            }
        )
        rank += 1

    return {
        "period": period,
        "items": items,
        "generated_at": now_iso(),
    }


def _training_state_label(value: str) -> str:
    return {
        "not_enrolled": "未入学",
        "pending_training": "待培训",
        "training": "培训中",
        "recently_trained": "近期已培训",
    }.get(value, value)


def _resolve_local_training_skill_source(skill_name: str = TRAINING_SKILL_NAME) -> Path:
    candidates: list[Path] = []
    if TRAINING_SKILL_SOURCE_OVERRIDE:
        candidates.append(Path(TRAINING_SKILL_SOURCE_OVERRIDE).expanduser())

    home = Path.home()
    direct_candidates = [
        home / ".cursor" / "skills" / skill_name,
        home / ".codex" / "skills" / skill_name,
    ]
    candidates.extend(direct_candidates)

    for root in (home / ".cursor" / "skills", home / ".codex" / "skills"):
        if not root.exists() or not root.is_dir():
            continue
        for candidate in sorted(root.glob(f"{skill_name}*")):
            candidates.append(candidate)

    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate if candidate.is_dir() else candidate.parent
        key = str(normalized)
        if key in seen:
            continue
        seen.add(key)
        skill_md = normalized / "SKILL.md"
        if skill_md.exists() and skill_md.is_file():
            return normalized.resolve()
    raise LookupError("training_skill_source_not_found")


def _resolve_local_onboarding_skill_source(skill_name: str = ONBOARDING_SKILL_NAME) -> Path:
    candidates: list[Path] = []
    if ONBOARDING_SKILL_SOURCE_OVERRIDE:
        candidates.append(Path(ONBOARDING_SKILL_SOURCE_OVERRIDE).expanduser())

    home = Path.home()
    direct_candidates = [
        home / ".cursor" / "skills" / skill_name,
        home / ".codex" / "skills" / skill_name,
    ]
    candidates.extend(direct_candidates)

    for root in (home / ".cursor" / "skills", home / ".codex" / "skills"):
        if not root.exists() or not root.is_dir():
            continue
        for candidate in sorted(root.glob(f"{skill_name}*")):
            candidates.append(candidate)

    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate if candidate.is_dir() else candidate.parent
        key = str(normalized)
        if key in seen:
            continue
        seen.add(key)
        skill_md = normalized / "SKILL.md"
        if skill_md.exists() and skill_md.is_file():
            return normalized.resolve()
    raise LookupError("onboarding_skill_source_not_found")


PROFILE_TARGET_FILES = [
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "MEMORY.md",
    "TASK_POLICY.md",
]


PROFILE_GENERATION_TIMEOUT = 180


def generate_agent_profile(
    agent_id: str,
    *,
    executor_agent_id: str,
    agent_name: str,
    role_summary: str,
    core_work: list[str],
) -> dict[str, Any]:
    """Use `openclaw agent` CLI to send a profile planning prompt to the executor agent."""
    if not OPENCLAW_CLI_BIN:
        raise RuntimeError("openclaw_cli_unavailable")

    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")

    executor = get_agent_by_id(executor_agent_id)
    if not executor:
        raise LookupError("executor_agent_not_found")

    skill_md_content = ""
    try:
        skill_source = _resolve_local_onboarding_skill_source()
        skill_md = skill_source / "SKILL.md"
        if skill_md.exists():
            skill_md_content = skill_md.read_text(encoding="utf-8")
    except LookupError:
        pass

    existing_files: dict[str, str | None] = {}
    try:
        _agent_data, _ws_display, workspace_root = _get_agent_workspace_roots(agent_id)
        for file_name in PROFILE_TARGET_FILES:
            file_path = workspace_root / file_name
            if file_path.exists() and file_path.is_file():
                try:
                    existing_files[file_name] = file_path.read_text(encoding="utf-8")
                except Exception:
                    existing_files[file_name] = None
            else:
                existing_files[file_name] = None
    except Exception:
        for file_name in PROFILE_TARGET_FILES:
            existing_files[file_name] = None

    core_work_text = "\n".join(f"  {i + 1}. {item}" for i, item in enumerate(core_work))

    existing_section_parts: list[str] = []
    for file_name in PROFILE_TARGET_FILES:
        content = existing_files.get(file_name)
        if content:
            existing_section_parts.append(f"### {file_name} (current)\n```\n{content}\n```")
        else:
            existing_section_parts.append(f"### {file_name} (not created yet)")
    existing_section = "\n\n".join(existing_section_parts)

    prompt = (
        "你是一个 OpenClaw Agent 画像规划专家。请基于下面的 agent-onboarding 规范和用户提供的参数，"
        "为这个 Agent 生成完整的画像文件集。\n\n"
        f"## Agent 基本信息\n"
        f"- Agent ID: {agent_id}\n"
        f"- 岗位名称: {agent_name}\n"
        f"- 岗位职责: {role_summary}\n"
        f"- 核心工作:\n{core_work_text}\n\n"
        f"## agent-onboarding Skill 规范参考\n"
        f"{skill_md_content[:8000] if skill_md_content else '(Skill 文件不可用，请基于通用最佳实践生成)'}\n\n"
        f"## 该 Agent 的现有画像文件\n{existing_section}\n\n"
        "## 输出要求\n"
        "请为这个 Agent 生成以下 6 个画像文件的内容。输出必须严格使用以下 JSON 格式，不要包含其他文字：\n\n"
        '```json\n'
        '{\n'
        '  "files": [\n'
        '    {"path": "IDENTITY.md", "content": "文件内容..."},\n'
        '    {"path": "SOUL.md", "content": "文件内容..."},\n'
        '    {"path": "USER.md", "content": "文件内容..."},\n'
        '    {"path": "AGENTS.md", "content": "文件内容..."},\n'
        '    {"path": "MEMORY.md", "content": "文件内容..."},\n'
        '    {"path": "TASK_POLICY.md", "content": "文件内容..."}\n'
        '  ]\n'
        '}\n'
        '```\n\n'
        "关键要求：\n"
        "1. IDENTITY.md 必须包含 Name、岗位职责、核心工作(>=3)\n"
        "2. SOUL.md 定义 Agent 的性格、价值观和沟通风格\n"
        "3. USER.md 描述 Agent 的用户交互偏好\n"
        "4. AGENTS.md 定义 Agent 与其他 Agent 的协作规范\n"
        "5. MEMORY.md 包含项目铁律和工作规范\n"
        "6. TASK_POLICY.md 包含任务合同规范（单任务单责任人 + 创建人回执）\n"
        "7. 如果已有文件内容，请在此基础上优化和补充，而非完全重写\n"
        "8. 所有内容使用中文"
    )

    args = [
        OPENCLAW_CLI_BIN,
        "agent",
        "--agent", executor_agent_id,
        "--message", prompt,
        "--json",
    ]
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=PROFILE_GENERATION_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("profile_generation_timeout") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"profile_generation_failed:{exc}") from exc

    assistant_text = ""
    if completed.returncode == 0 and completed.stdout:
        raw_stdout = completed.stdout.strip()
        try:
            response_json = json.loads(raw_stdout)
            if isinstance(response_json, dict):
                assistant_text = str(response_json.get("reply") or response_json.get("text") or response_json.get("content") or response_json.get("message") or "")
                if not assistant_text:
                    choices = response_json.get("choices")
                    if isinstance(choices, list) and choices:
                        msg = choices[0].get("message") or {}
                        assistant_text = str(msg.get("content") or "")
                if not assistant_text:
                    assistant_text = raw_stdout
        except json.JSONDecodeError:
            assistant_text = raw_stdout
    else:
        stderr_text = (completed.stderr or "").strip()
        stdout_text = (completed.stdout or "").strip()
        if stdout_text:
            assistant_text = stdout_text
        else:
            raise RuntimeError(
                f"profile_generation_failed:exit_code={completed.returncode} "
                f"stderr={stderr_text[:500]}"
            )

    files = _parse_profile_files_from_text(assistant_text, existing_files)
    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "executor_agent_id": executor_agent_id,
        "files": files,
    }


def _parse_profile_files_from_text(
    text: str, existing_files: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Extract profile file contents from agent response text."""
    files: list[dict[str, Any]] = []

    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        raw_json = text[json_start:json_end]
        try:
            parsed = json.loads(raw_json)
            raw_files = parsed.get("files") or []
            for item in raw_files:
                path = str(item.get("path") or "").strip()
                content = str(item.get("content") or "").strip()
                if path and content:
                    existing_content = existing_files.get(path)
                    files.append({
                        "path": path,
                        "content": content,
                        "existing_content": existing_content,
                        "exists": existing_content is not None,
                    })
        except json.JSONDecodeError:
            pass

    if not files:
        for file_name in PROFILE_TARGET_FILES:
            block_marker = f"### {file_name}"
            file_content = ""
            idx = text.find(block_marker)
            if idx >= 0:
                code_start = text.find("```", idx + len(block_marker))
                if code_start >= 0:
                    code_content_start = text.find("\n", code_start) + 1
                    code_end = text.find("```", code_content_start)
                    if code_end > code_content_start:
                        file_content = text[code_content_start:code_end].strip()
            if not file_content:
                file_content = f"# {file_name}\n\n(Generated content pending - please edit manually)"
            existing_content = existing_files.get(file_name)
            files.append({
                "path": file_name,
                "content": file_content,
                "existing_content": existing_content,
                "exists": existing_content is not None,
            })

    return files


def _copy_local_skill_to_agent_workspace(
    agent_id: str,
    *,
    skill_name: str = TRAINING_SKILL_NAME,
) -> dict[str, Any]:
    source_path = _resolve_local_training_skill_source(skill_name=skill_name)
    agent, workspace_display_path, workspace_root, skills_root = _resolve_agent_skills_root(agent_id)
    destination = _ensure_child_path(skills_root, skill_name, _workspace_shared_allowed_roots())

    if destination.exists():
        if destination.is_symlink():
            destination.unlink()
        elif destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    shutil.copytree(source_path, destination)
    relative_path = str(destination.relative_to(workspace_root))
    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "skill_name": skill_name,
        "skill_source_path": str(source_path),
        "skill_target_path": relative_path,
        "skill_target_display_path": _workspace_visible_path(workspace_display_path, relative_path),
    }


def _get_training_module_settings_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM training_module_settings WHERE singleton = 1").fetchone()


def _serialize_training_module_coach(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    coach = get_agent_by_id(str(payload.get("coach_agent_id") or "").strip())
    coach_name = str((coach or {}).get("display_name") or payload.get("coach_agent_id") or "").strip()
    return {
        "coach_agent_id": str(payload["coach_agent_id"]),
        "coach_agent_name": coach_name,
        "skill_name": str(payload["skill_name"]),
        "skill_source_path": str(payload["skill_source_path"]),
        "skill_target_path": str(payload["skill_target_path"]),
        "configured_at": str(payload["configured_at"]),
        "updated_at": str(payload["updated_at"]),
    }


def get_training_module_settings() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = _get_training_module_settings_row(conn)
    if not row:
        return None
    return _serialize_training_module_coach(row)


def _training_document_relative_path(kind: str, run_id: str | None = None) -> str:
    if kind == "status":
        return TRAINING_STATUS_DOC_PATH
    if kind == "profile":
        return TRAINING_PROFILE_DOC_PATH
    if kind == "run":
        if not run_id:
            raise ValueError("training_run_id_required")
        return f"{TRAINING_RUN_DOCS_DIR}/{run_id}.md"
    raise ValueError("training_document_kind_invalid")


def _training_document_title(kind: str, run_id: str | None = None) -> str:
    if kind == "status":
        return "状态"
    if kind == "profile":
        return "学员档案"
    if kind == "run":
        return f"培训记录 {run_id}"
    raise ValueError("training_document_kind_invalid")


def _build_default_training_document_content(
    agent: dict[str, Any],
    *,
    kind: str,
    run: dict[str, Any] | None = None,
    coach_name: str | None = None,
) -> str:
    display_name = str(agent.get("display_name") or agent.get("agent_id") or "学员")
    agent_id = str(agent.get("agent_id") or "").strip()
    role_summary = str(agent.get("role_summary") or agent.get("role") or "待补充职责").strip()
    if kind == "profile":
        return (
            f"# 学员档案\n\n"
            f"## 基础信息\n"
            f"- Agent ID: {agent_id}\n"
            f"- 名称: {display_name}\n"
            f"- 职责: {role_summary}\n\n"
            f"## 能力画像\n"
            f"- 强项: 待补充\n"
            f"- 弱项: 待补充\n\n"
            f"## 培训建议\n"
            f"- 待补充\n"
        )
    if kind == "status":
        return (
            f"# 当前培训状态\n\n"
            f"- 学员: {display_name} ({agent_id})\n"
            f"- 当前状态: 待培训\n"
            f"- 教练: {coach_name or '待配置'}\n\n"
            f"## 当前判断\n"
            f"- 待开始本轮训练\n\n"
            f"## 下一步\n"
            f"- 创建或分配培训任务\n"
        )
    if kind == "run":
        current_run_id = str((run or {}).get("run_id") or "").strip()
        phase = str((run or {}).get("phase") or "exam").strip()
        return (
            f"# 培训记录 {current_run_id}\n\n"
            f"- 学员: {display_name} ({agent_id})\n"
            f"- 教练: {coach_name or '待配置'}\n"
            f"- 阶段: {phase}\n\n"
            f"## 培训目标\n"
            f"- 待补充\n\n"
            f"## 观察记录\n"
            f"- 待补充\n"
        )
    raise ValueError("training_document_kind_invalid")


def _get_training_document_payload(
    agent_id: str,
    *,
    kind: str,
    run_id: str | None = None,
    create_if_missing: bool = False,
    coach_name: str | None = None,
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agent, workspace_display_path, workspace_root = _get_agent_workspace_roots(agent_id)
    relative_path = _training_document_relative_path(kind, run_id=run_id)
    display_path = _workspace_visible_path(workspace_display_path, relative_path)
    file_path = _ensure_child_path(workspace_root, relative_path, _workspace_shared_allowed_roots())
    exists = file_path.exists() and file_path.is_file()

    if exists:
        file_payload = read_agent_workspace_file(agent_id, relative_path)
        return {
            "agent_id": agent["agent_id"],
            "agent_name": agent["display_name"],
            "kind": kind,
            "run_id": run_id,
            "title": _training_document_title(kind, run_id=run_id),
            "path": relative_path,
            "display_path": file_payload["display_path"],
            "exists": True,
            "editable": True,
            "content": str(file_payload.get("content") or ""),
            "modified_at": file_payload.get("modified_at"),
        }

    content = _build_default_training_document_content(agent, kind=kind, run=run, coach_name=coach_name)
    if create_if_missing:
        create_agent_workspace_file(agent_id, relative_path, content)
        file_payload = read_agent_workspace_file(agent_id, relative_path)
        return {
            "agent_id": agent["agent_id"],
            "agent_name": agent["display_name"],
            "kind": kind,
            "run_id": run_id,
            "title": _training_document_title(kind, run_id=run_id),
            "path": relative_path,
            "display_path": file_payload["display_path"],
            "exists": True,
            "editable": True,
            "content": str(file_payload.get("content") or ""),
            "modified_at": file_payload.get("modified_at"),
        }

    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["display_name"],
        "kind": kind,
        "run_id": run_id,
        "title": _training_document_title(kind, run_id=run_id),
        "path": relative_path,
        "display_path": display_path,
        "exists": False,
        "editable": True,
        "content": content,
        "modified_at": None,
    }


def get_training_document(agent_id: str, kind: str, run_id: str | None = None) -> dict[str, Any]:
    run = get_training_run_by_id(run_id) if kind == "run" and run_id else None
    coach_name = str((run or {}).get("coach_agent_name") or "").strip() or None
    return _get_training_document_payload(
        agent_id,
        kind=kind,
        run_id=run_id,
        create_if_missing=False,
        coach_name=coach_name,
        run=run,
    )


def save_training_document(agent_id: str, kind: str, content: str, run_id: str | None = None) -> dict[str, Any]:
    normalized = str(content or "")
    relative_path = _training_document_relative_path(kind, run_id=run_id)
    try:
        update_agent_workspace_file(agent_id, relative_path, normalized)
    except LookupError:
        create_agent_workspace_file(agent_id, relative_path, normalized)
    return get_training_document(agent_id, kind=kind, run_id=run_id)


def _training_profile_exists(agent_id: str) -> bool:
    try:
        agent, _workspace_display_path, workspace_root = _get_agent_workspace_roots(agent_id)
    except LookupError:
        return False
    relative_path = _training_document_relative_path("profile")
    file_path = _ensure_child_path(workspace_root, relative_path, _workspace_shared_allowed_roots())
    return file_path.exists() and file_path.is_file() and bool(agent)


def _list_training_runs_with_context(agent_id: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if agent_id:
        where = "WHERE tr.agent_id = ?"
        params.append(agent_id)

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT tr.*,
                   ctx.coach_agent_id,
                   coach.display_name AS coach_agent_name,
                   ctx.orchestration_state,
                   ctx.orchestration_error,
                   ctx.observation_job_id,
                   ctx.run_doc_path,
                   ctx.completed_at
            FROM training_runs tr
            LEFT JOIN training_run_contexts ctx ON ctx.run_id = tr.run_id
            LEFT JOIN agents coach ON coach.agent_id = ctx.coach_agent_id
            {where}
            ORDER BY tr.created_at DESC, tr.run_id DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def _serialize_training_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "agent_id": str(row["agent_id"]),
        "onboarding_job_id": row.get("onboarding_job_id"),
        "phase": str(row["phase"]),
        "status": str(row["status"]),
        "score": row.get("score"),
        "result": row.get("result"),
        "report_url": row.get("report_url"),
        "observe_days": row.get("observe_days"),
        "coach_agent_id": row.get("coach_agent_id"),
        "coach_agent_name": row.get("coach_agent_name"),
        "orchestration_state": row.get("orchestration_state"),
        "orchestration_error": row.get("orchestration_error"),
        "observation_job_id": row.get("observation_job_id"),
        "run_doc_path": row.get("run_doc_path"),
        "completed_at": row.get("completed_at"),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def get_training_run_by_id(run_id: str | None) -> dict[str, Any] | None:
    raw_run_id = str(run_id or "").strip()
    if not raw_run_id:
        return None
    rows = _list_training_runs_with_context()
    for row in rows:
        if str(row.get("run_id") or "").strip() == raw_run_id:
            return _serialize_training_run_row(row)
    return None


def _derive_training_agent_summary(agent: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    profile_exists = _training_profile_exists(str(agent["agent_id"]))
    active_runs = [run for run in runs if str(run.get("status") or "") == "running"]
    completed_runs = [run for run in runs if str(run.get("status") or "") in {"passed", "failed"}]

    latest_completed_at: str | None = None
    for run in completed_runs:
        candidate = str(run.get("completed_at") or run.get("updated_at") or "").strip()
        if not candidate:
            continue
        if not latest_completed_at:
            latest_completed_at = candidate
            continue
        current_dt = _parse_iso_utc(latest_completed_at, "training_summary_completed_at")
        candidate_dt = _parse_iso_utc(candidate, "training_summary_completed_at")
        if current_dt and candidate_dt and candidate_dt > current_dt:
            latest_completed_at = candidate

    recent_threshold = datetime.now(timezone.utc) - timedelta(days=TRAINING_RECENT_WINDOW_DAYS)
    recent_completed = False
    if latest_completed_at:
        latest_dt = _parse_iso_utc(latest_completed_at, "training_summary_latest_completed_at")
        recent_completed = bool(latest_dt and latest_dt >= recent_threshold)

    if not profile_exists:
        training_state = "not_enrolled"
    elif active_runs:
        training_state = "training"
    elif recent_completed:
        training_state = "recently_trained"
    else:
        training_state = "pending_training"

    active_run = active_runs[0] if active_runs else None
    return {
        "agent_id": str(agent["agent_id"]),
        "display_name": str(agent.get("display_name") or agent["agent_id"]),
        "role_summary": str(agent.get("role_summary") or agent.get("role") or "").strip() or None,
        "avatar_url": agent.get("avatar_url"),
        "avatar_hint": agent.get("avatar_hint"),
        "emoji": agent.get("emoji"),
        "training_state": training_state,
        "training_state_label": _training_state_label(training_state),
        "training_count": len(completed_runs),
        "latest_completed_at": latest_completed_at,
        "active_run_id": active_run.get("run_id") if active_run else None,
        "active_run_phase": active_run.get("phase") if active_run else None,
        "profile_exists": profile_exists,
    }


def list_training_agent_summaries() -> list[dict[str, Any]]:
    agents = list_agents(status=None, q=None)
    runs_by_agent: dict[str, list[dict[str, Any]]] = {}
    for row in _list_training_runs_with_context():
        serialized = _serialize_training_run_row(row)
        runs_by_agent.setdefault(serialized["agent_id"], []).append(serialized)

    summaries = [
        _derive_training_agent_summary(agent, runs_by_agent.get(str(agent["agent_id"]), []))
        for agent in agents
    ]
    state_order = {
        "training": 0,
        "pending_training": 1,
        "recently_trained": 2,
        "not_enrolled": 3,
    }
    summaries.sort(key=lambda item: (state_order.get(item["training_state"], 99), item["display_name"]))
    return summaries


def _training_module_counts(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "total": len(items),
        "not_enrolled": 0,
        "pending_training": 0,
        "training": 0,
        "recently_trained": 0,
    }
    for item in items:
        key = str(item.get("training_state") or "").strip()
        if key in counts:
            counts[key] += 1
    return counts


def get_training_module_overview() -> dict[str, Any]:
    setup = get_setup_status()
    nodes_payload = list_nodes()
    online_node_total = sum(1 for item in nodes_payload["items"] if item.get("status") == "online")
    initialized = bool(setup["has_openclaw_config"]) and online_node_total > 0
    coach = get_training_module_settings()
    agents = list_training_agent_summaries() if initialized else []
    return {
        "initialized": initialized,
        "needs_coach_setup": bool(initialized and coach is None),
        "home_url": "/",
        "has_openclaw_config": bool(setup["has_openclaw_config"]),
        "online_node_total": online_node_total,
        "node_total": int(setup["node_total"]),
        "coach": coach,
        "counts": _training_module_counts(agents),
        "agents": agents,
    }


def configure_training_module(payload: dict[str, Any]) -> dict[str, Any]:
    overview = get_training_module_overview()
    if not overview["initialized"]:
        raise RuntimeError("training_module_not_initialized")

    coach_agent_id = str(payload.get("coach_agent_id") or "").strip()
    if not coach_agent_id:
        raise ValueError("coach_agent_id_required")

    coach = get_agent_by_id(coach_agent_id)
    if not coach:
        raise ValueError("coach_agent_not_found")

    copied = _copy_local_skill_to_agent_workspace(coach_agent_id, skill_name=TRAINING_SKILL_NAME)
    now = now_iso()
    with get_conn() as conn:
        existing = _get_training_module_settings_row(conn)
        configured_at = str(existing["configured_at"]) if existing else now
        conn.execute(
            """
            INSERT INTO training_module_settings (
                singleton, coach_agent_id, skill_name, skill_source_path, skill_target_path, configured_at, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
                coach_agent_id = excluded.coach_agent_id,
                skill_name = excluded.skill_name,
                skill_source_path = excluded.skill_source_path,
                skill_target_path = excluded.skill_target_path,
                updated_at = excluded.updated_at
            """,
            (
                coach_agent_id,
                copied["skill_name"],
                copied["skill_source_path"],
                copied["skill_target_path"],
                configured_at,
                now,
            ),
        )
        conn.commit()
        row = _get_training_module_settings_row(conn)

    if not row:
        raise RuntimeError("training_module_settings_missing")
    return {"configured": True, "coach": _serialize_training_module_coach(row)}


def get_training_agent_detail(agent_id: str) -> dict[str, Any]:
    agent = get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")

    summaries = {item["agent_id"]: item for item in list_training_agent_summaries()}
    summary = summaries.get(agent_id)
    if not summary:
        summary = _derive_training_agent_summary(agent, [])

    runs = list_training_runs(agent_id=agent_id)
    coach_name = str((get_training_module_settings() or {}).get("coach_agent_name") or "").strip() or None
    status_document = _get_training_document_payload(
        agent_id,
        kind="status",
        create_if_missing=False,
        coach_name=coach_name,
    )
    profile_document = _get_training_document_payload(
        agent_id,
        kind="profile",
        create_if_missing=False,
        coach_name=coach_name,
    )
    return {
        "agent": summary,
        "status_document": status_document,
        "profile_document": profile_document,
        "runs": runs,
    }


def _build_training_run_coach_prompt(
    trainee: dict[str, Any],
    *,
    coach_agent_id: str,
    run_id: str,
    observe_days: int,
    status_document: dict[str, Any],
    profile_document: dict[str, Any],
    run_document_path: str,
    run_document_display_path: str,
) -> str:
    coach = get_agent_by_id(coach_agent_id) or {}
    coach_name = str(coach.get("display_name") or coach_agent_id).strip()
    display_name = str(trainee.get("display_name") or trainee["agent_id"]).strip()
    role_summary = str(trainee.get("role_summary") or trainee.get("role") or "待补充职责").strip()
    return (
        f"你是训练模块当前教练 {coach_name}。\n\n"
        f"请针对学员 {display_name} ({trainee['agent_id']}) 发起一轮培训 run：{run_id}。\n"
        f"学员职责：{role_summary}\n"
        f"观察期：{observe_days} 天\n\n"
        f"请使用已经同步到你 workspace 的 {TRAINING_SKILL_NAME} skill，完成以下动作：\n"
        f"1. 阅读学员档案：{profile_document['display_path']}\n"
        f"2. 更新当前状态文档：{status_document['display_path']}\n"
        f"3. 在 run 记录文档中写入本轮培训目标、检查清单、交付标准与阶段安排：{run_document_display_path}\n"
        f"4. 使用 sessions_send 把本轮培训要求发送给学员 {trainee['agent_id']}\n"
        f"5. 后续观察任务会继续提醒你补充 run 记录和状态文档\n\n"
        f"要求：\n"
        f"- 先写文档，再派发\n"
        f"- run 文档路径：{run_document_path}\n"
        f"- 输出内容必须可执行、可验收\n"
    )


def _create_training_observation_job(
    *,
    coach_agent_id: str,
    trainee: dict[str, Any],
    run_id: str,
    observe_every_hours: int,
    observe_days: int,
    run_document_display_path: str,
    status_document_display_path: str,
) -> str:
    end_at = datetime.now(timezone.utc) + timedelta(days=observe_days)
    payload = create_agent_scheduled_job(
        coach_agent_id,
        {
            "name": f"[training] observe {trainee['agent_id']} {run_id[:8]}",
            "description": f"训练观察任务：{trainee['display_name']} / {run_id}",
            "schedule_kind": "every",
            "every_ms": int(observe_every_hours) * 60 * 60 * 1000,
            "content": (
                f"请对学员 {trainee['display_name']} ({trainee['agent_id']}) 的培训 run {run_id} 做观察记录。\n"
                f"- 更新状态文档：{status_document_display_path}\n"
                f"- 追加 run 记录：{run_document_display_path}\n"
                f"- 观察截止：{end_at.isoformat()}\n"
            ),
            "enabled": True,
        },
    )
    return str(payload["id"])


def _disable_scheduled_job(job_id: str | None) -> None:
    raw_job_id = str(job_id or "").strip()
    if not raw_job_id:
        return
    document = _load_openclaw_jobs_document()
    jobs = document.get("jobs") or []
    changed = False
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if str(job.get("id") or "").strip() != raw_job_id:
            continue
        job["enabled"] = False
        job["updatedAtMs"] = int(time.time() * 1000)
        changed = True
        break
    if changed:
        _write_openclaw_jobs_document(document)


def start_training_run(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    overview = get_training_module_overview()
    if not overview["initialized"]:
        raise RuntimeError("training_module_not_initialized")

    trainee = get_agent_by_id(agent_id)
    if not trainee:
        raise ValueError("agent_not_found")

    settings = get_training_module_settings()
    if not settings:
        raise RuntimeError("training_module_coach_not_configured")

    observe_days = int(payload.get("observe_days") or 14)
    observe_every_hours = int(payload.get("observe_every_hours") or TRAINING_DEFAULT_OBSERVE_EVERY_HOURS)
    if observe_every_hours < 1 or observe_every_hours > 24:
        raise ValueError("training_observe_every_hours_invalid")

    run_id = generate_training_run_id()
    now = now_iso()
    coach_agent_id = str(settings["coach_agent_id"])

    status_document = _get_training_document_payload(
        agent_id,
        kind="status",
        create_if_missing=True,
        coach_name=settings["coach_agent_name"],
    )
    _get_training_document_payload(
        agent_id,
        kind="profile",
        create_if_missing=True,
        coach_name=settings["coach_agent_name"],
    )

    run_relative_path = _training_document_relative_path("run", run_id=run_id)
    agent_record, workspace_display_path, _workspace_root = _get_agent_workspace_roots(agent_id)
    run_document_display_path = _workspace_visible_path(workspace_display_path, run_relative_path)
    coach_prompt = _build_training_run_coach_prompt(
        agent_record,
        coach_agent_id=coach_agent_id,
        run_id=run_id,
        observe_days=observe_days,
        status_document=status_document,
        profile_document=_get_training_document_payload(agent_id, kind="profile", create_if_missing=False),
        run_document_path=run_relative_path,
        run_document_display_path=run_document_display_path,
    )

    observation_job_id: str | None = None
    try:
        save_training_document(
            agent_id,
            "run",
            _build_default_training_document_content(
                agent_record,
                kind="run",
                run={"run_id": run_id, "phase": "exam"},
                coach_name=settings["coach_agent_name"],
            ),
            run_id=run_id,
        )
        observation_job_id = _create_training_observation_job(
            coach_agent_id=coach_agent_id,
            trainee=agent_record,
            run_id=run_id,
            observe_every_hours=observe_every_hours,
            observe_days=observe_days,
            run_document_display_path=run_document_display_path,
            status_document_display_path=status_document["display_path"],
        )
        _run_openclaw_cli_text(
            [
                OPENCLAW_CLI_BIN,
                "agent",
                "--agent",
                coach_agent_id,
                "--message",
                coach_prompt,
            ],
            timeout=45,
        )
    except Exception:
        if observation_job_id:
            _disable_scheduled_job(observation_job_id)
        raise

    run = {
        "run_id": run_id,
        "agent_id": agent_id,
        "onboarding_job_id": None,
        "phase": "exam",
        "status": "running",
        "score": None,
        "result": None,
        "report_url": None,
        "observe_days": observe_days,
        "created_at": now,
        "updated_at": now,
    }

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO training_runs (
                run_id, agent_id, onboarding_job_id, phase, status, score, result,
                report_url, observe_days, created_at, updated_at
            ) VALUES (
                :run_id, :agent_id, :onboarding_job_id, :phase, :status, :score, :result,
                :report_url, :observe_days, :created_at, :updated_at
            )
            """,
            run,
        )
        conn.execute(
            """
            INSERT INTO training_run_contexts (
                run_id, coach_agent_id, status_doc_path, profile_doc_path, run_doc_path,
                observation_job_id, orchestration_state, orchestration_error, coach_prompt,
                generated_at, dispatched_at, observation_created_at, completed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'observing', NULL, ?, ?, ?, ?, NULL, ?)
            """,
            (
                run_id,
                coach_agent_id,
                TRAINING_STATUS_DOC_PATH,
                TRAINING_PROFILE_DOC_PATH,
                run_relative_path,
                observation_job_id,
                coach_prompt,
                now,
                now,
                now,
                now,
            ),
        )
        conn.commit()

    created = get_training_run_by_id(run_id)
    if not created:
        raise RuntimeError("training_run_not_found_after_create")
    return created


def _build_openclaw_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("OPENCLAW_CONFIG_PATH", str(_resolved_openclaw_config_path()))
    env.setdefault("OPENCLAW_STATE_DIR", str(_resolved_openclaw_host_root()))
    env.setdefault("OPENCLAW_HOME", str(_resolved_openclaw_host_root()))
    return env


def _parse_json_payload(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty_output")
    if text.startswith("{") or text.startswith("["):
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
        raise ValueError("json_not_object")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("json_not_found")
    payload = json.loads(text[start : end + 1])
    if isinstance(payload, dict):
        return payload
    raise ValueError("json_not_object")


def _run_skill_script_json(script_path: Path, args: list[str], *, timeout: int = 180) -> dict[str, Any]:
    command = [sys.executable, str(script_path), *args]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_build_openclaw_env(),
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip() or f"exit_code_{completed.returncode}"
        raise RuntimeError(f"script_failed:{script_path.name}:{message}")
    try:
        return _parse_json_payload(completed.stdout)
    except Exception as exc:
        raise RuntimeError(f"script_invalid_json:{script_path.name}") from exc


def run_feishu_app_ui_automation(payload: dict[str, Any]) -> dict[str, Any]:
    if not FEISHU_UI_AUTOMATION_SCRIPT_PATH.exists():
        return {
            "status": "failed",
            "step": "init",
            "message": "script_missing",
            "app_id": None,
            "app_secret": None,
            "chat_url": None,
            "execution_mode": None,
            "debugger_url": None,
        }
    app_name = (payload.get("app_name") or FEISHU_UI_AUTOMATION_DEFAULT_APP_NAME).strip()
    app_description = (payload.get("app_description") or FEISHU_UI_AUTOMATION_DEFAULT_APP_DESCRIPTION).strip()
    menu_name = (payload.get("menu_name") or FEISHU_UI_AUTOMATION_DEFAULT_MENU_NAME).strip()
    automation_mode = (payload.get("automation_mode") or "auto").strip().lower()
    if automation_mode not in {"auto", "cdp", "profile"}:
        automation_mode = "auto"
    cdp_url = (payload.get("cdp_url") or os.getenv("FEISHU_UI_AUTOMATION_CDP_URL", "")).strip()
    profile_dir = (payload.get("profile_dir") or str(Path.home() / ".clawpilot" / "feishu-ui-profile")).strip()
    headless = bool(payload.get("headless", False))
    wait_for_login = bool(payload.get("wait_for_login", False))
    timeout_sec = int(payload.get("timeout_sec") or 180)
    args = [
        "--app-name",
        app_name,
        "--app-description",
        app_description,
        "--menu-name",
        menu_name,
        "--automation-mode",
        automation_mode,
        "--profile-dir",
        profile_dir,
        "--timeout-sec",
        str(timeout_sec),
    ]
    if cdp_url:
        args.extend(["--cdp-url", cdp_url])
    if headless:
        args.append("--headless")
    if wait_for_login:
        args.append("--wait-for-login")
    try:
        return _run_skill_script_json(
            FEISHU_UI_AUTOMATION_SCRIPT_PATH,
            args,
            timeout=max(timeout_sec + 480, 600),
        )
    except Exception as exc:
        return {
            "status": "failed",
            "step": "automation",
            "message": str(exc),
            "app_id": None,
            "app_secret": None,
            "chat_url": None,
            "execution_mode": None,
            "debugger_url": None,
        }


def _resolve_default_identity_key(config: dict[str, Any]) -> str | None:
    feishu = (config.get("channels") or {}).get("feishu") or {}
    identities = feishu.get("userIdentities")
    if isinstance(identities, dict) and identities:
        return sorted(identities.keys())[0]
    return "default"


def _resolve_feishu_group_options(config: dict[str, Any]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_item(chat_id: str | None, name: str | None, require_mention: bool | None, source: str) -> None:
        if not chat_id:
            return
        chat_id = str(chat_id).strip()
        if not chat_id or chat_id in seen:
            return
        seen.add(chat_id)
        options.append(
            {
                "chat_id": chat_id,
                "name": (str(name).strip() if name else None),
                "require_mention": require_mention if require_mention is not None else None,
                "source": source,
            }
        )

    groups = ((config.get("channels") or {}).get("feishu") or {}).get("groups")
    if isinstance(groups, dict):
        for key, value in groups.items():
            if isinstance(value, dict):
                chat_id = value.get("chatId") or value.get("chat_id") or value.get("id") or key
                name = value.get("name") or value.get("label") or value.get("title") or key
                require_mention = value.get("requireMention") if isinstance(value.get("requireMention"), bool) else value.get("require_mention")
                add_item(chat_id, name, require_mention if isinstance(require_mention, bool) else None, "openclaw")
            else:
                add_item(str(value), str(key), None, "openclaw")
    elif isinstance(groups, list):
        for item in groups:
            if isinstance(item, dict):
                chat_id = item.get("chatId") or item.get("chat_id") or item.get("id")
                name = item.get("name") or item.get("label") or item.get("title")
                require_mention = item.get("requireMention") if isinstance(item.get("requireMention"), bool) else item.get("require_mention")
                add_item(chat_id, name, require_mention if isinstance(require_mention, bool) else None, "openclaw")
            else:
                add_item(str(item), None, None, "openclaw")
    return options


def _build_onboarding_step_plan(payload: dict[str, Any]) -> list[dict[str, Any]]:
    persona = payload.get("persona_strategy") or {}
    groups = payload.get("groups") or {}
    execution = payload.get("execution") or {}
    steps: list[dict[str, Any]] = []
    for index, definition in enumerate(ONBOARDING_STEP_DEFS):
        status = "todo"
        if definition["key"] == "persona_writer" and persona.get("mode") != "agent_assisted":
            status = "skipped"
        if definition["key"] == "group_join" and not groups.get("auto_join"):
            status = "skipped"
        if definition["key"] == "restart" and not execution.get("restart_gateway"):
            status = "skipped"
        steps.append(
            {
                "key": definition["key"],
                "label": definition["label"],
                "order_index": index,
                "status": status,
            }
        )
    return steps


def _serialize_onboarding_step_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "key": str(payload["step_key"]),
        "label": str(payload["label"]),
        "status": str(payload["status"]),
        "summary": payload.get("result_summary"),
        "detail": payload.get("result_payload_json"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
    }


def _load_onboarding_steps(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT run_id, step_key, label, order_index, status, result_summary,
               result_payload_json, started_at, finished_at
        FROM agent_onboarding_run_steps
        WHERE run_id = ?
        ORDER BY order_index ASC
        """,
        (run_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _compute_onboarding_progress(steps: list[dict[str, Any]]) -> tuple[int, int, str]:
    total = len(steps)
    completed = sum(1 for step in steps if step.get("status") in {"done", "skipped"})
    has_failed = any(step.get("status") == "failed" for step in steps)
    has_warn = any(step.get("status") == "warn" for step in steps)
    has_running = any(step.get("status") == "running" for step in steps)
    if total and completed == total and not has_failed:
        status = "completed"
    elif has_running:
        status = "running"
    elif has_failed or has_warn:
        status = "partial"
    else:
        status = "paused"
    return completed, total, status


def _serialize_onboarding_run_row(row: sqlite3.Row | dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(row)
    completed, total, status = _compute_onboarding_progress(steps)
    warnings = []
    if payload.get("warnings_json"):
        try:
            warnings = json.loads(payload.get("warnings_json") or "[]")
        except Exception:
            warnings = []
    return {
        "run_id": str(payload["run_id"]),
        "owner_agent_id": str(payload["owner_agent_id"]),
        "target_agent_id": str(payload["target_agent_id"]),
        "target_agent_name": str(payload["target_agent_name"]),
        "status": status if status in ONBOARDING_RUN_STATUSES else str(payload.get("status") or "running"),
        "completed_step_count": completed,
        "total_step_count": total,
        "pending_restart": bool(payload.get("pending_restart")),
        "warnings": [str(item) for item in warnings],
        "steps": [_serialize_onboarding_step_row(step) for step in steps],
        "created_at": str(payload["created_at"]),
        "updated_at": str(payload["updated_at"]),
    }


def list_multi_agent_onboarding_runs(include_completed: bool = False) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_onboarding_runs ORDER BY created_at DESC, run_id DESC"
        ).fetchall()
        runs: list[dict[str, Any]] = []
        for row in rows:
            steps = _load_onboarding_steps(conn, str(row["run_id"]))
            serialized = _serialize_onboarding_run_row(row, steps)
            if not include_completed and serialized["status"] == "completed":
                continue
            runs.append(serialized)
    return runs


def _insert_onboarding_run(
    conn: sqlite3.Connection,
    run_id: str,
    payload: dict[str, Any],
    steps: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    now = now_iso()
    warnings_json = json.dumps(warnings or [], ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO agent_onboarding_runs (
            run_id, owner_agent_id, target_agent_id, target_agent_name,
            status, pending_restart, request_json, warnings_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            payload["owner_agent_id"],
            payload["agent_id"],
            payload["agent_name"],
            "running",
            0,
            json.dumps(payload, ensure_ascii=False),
            warnings_json,
            now,
            now,
        ),
    )
    for step in steps:
        conn.execute(
            """
            INSERT INTO agent_onboarding_run_steps (
                run_id, step_key, label, order_index, status,
                result_summary, result_payload_json, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
            """,
            (
                run_id,
                step["key"],
                step["label"],
                step["order_index"],
                step["status"],
            ),
        )
    conn.commit()
    return {"run_id": run_id, "created_at": now, "updated_at": now}


def _update_onboarding_step(
    conn: sqlite3.Connection,
    run_id: str,
    step_key: str,
    *,
    status: str,
    summary: str | None = None,
    payload: dict[str, Any] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    if status not in ONBOARDING_STEP_STATUSES:
        raise ValueError("onboarding_step_status_invalid")
    conn.execute(
        """
        UPDATE agent_onboarding_run_steps
        SET status = ?, result_summary = ?, result_payload_json = ?, started_at = ?, finished_at = ?
        WHERE run_id = ? AND step_key = ?
        """,
        (
            status,
            summary,
            json.dumps(payload, ensure_ascii=False) if payload else None,
            started_at,
            finished_at,
            run_id,
            step_key,
        ),
    )


def _resolve_onboarding_scripts() -> dict[str, Path]:
    skill_dir = _resolve_local_onboarding_skill_source()
    scripts_dir = skill_dir / "scripts"
    scripts = {
        "ensure_feishu_agent": scripts_dir / "ensure_feishu_agent.py",
        "scaffold_docs": scripts_dir / "scaffold_agent_workspace_docs.py",
        "validate_memory": scripts_dir / "validate_memory_feishu_rules.py",
        "validate_identity": scripts_dir / "validate_agent_workspace_identity.py",
        "validate_task_contract": scripts_dir / "validate_agent_task_contract_rules.py",
        "ensure_dependency": scripts_dir / "ensure_python_dependency.py",
        "group_membership": scripts_dir / "feishu_group_membership.py",
    }
    for key, path in scripts.items():
        if not path.exists():
            raise LookupError(f"onboarding_script_missing:{key}")
    return scripts


def get_multi_agent_onboarding_bootstrap() -> dict[str, Any]:
    config = _load_openclaw_config()
    agents = list_agents(status=None, q=None)
    group_options = _resolve_feishu_group_options(config)
    in_progress = list_multi_agent_onboarding_runs(include_completed=False)
    official_checklist = [
        "bindings/account/userIdentities 完整",
        "dmPolicy=open 时 allowFrom 包含 *",
        "目标群 requireMention=true",
        "openclaw doctor --fix",
        "openclaw agents list --bindings",
        "openclaw channels status --probe",
    ]
    skill_checklist = [
        "脚本 ensure_feishu_agent/scaffold/validate 资源可用",
        "requests 依赖可安装",
        "群组配置/手动 chat_id 可解析",
    ]
    return {
        "agents": agents,
        "persona_writer_candidates": agents,
        "group_options": group_options,
        "default_identity_key": _resolve_default_identity_key(config),
        "official_checklist": official_checklist,
        "skill_checklist": skill_checklist,
        "in_progress_runs": in_progress,
    }


def dry_run_multi_agent_onboarding(payload: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []
    steps = _build_onboarding_step_plan(payload)

    if not _resolved_openclaw_config_path().exists():
        blockers.append("openclaw_config_missing")

    try:
        scripts = _resolve_onboarding_scripts()
    except LookupError as exc:
        blockers.append(str(exc))
        scripts = {}

    feishu = payload.get("feishu") or {}
    if not feishu.get("app_id"):
        blockers.append("feishu_app_id_missing")
    if not feishu.get("app_secret"):
        blockers.append("feishu_app_secret_missing")
    if not feishu.get("operator_open_id"):
        blockers.append("feishu_operator_open_id_missing")

    persona = payload.get("persona_strategy") or {}
    if persona.get("mode") == "agent_assisted" and not OPENCLAW_CLI_BIN:
        warnings.append("openclaw_cli_unavailable_for_persona_dispatch")

    groups = payload.get("groups") or {}
    if groups.get("auto_join") and not (groups.get("items") or []):
        warnings.append("group_auto_join_enabled_but_no_groups")

    step_results = []
    for step in steps:
        status = step["status"]
        summary = None
        if step["key"] == "upsert":
            if blockers:
                status = "failed"
                summary = "配置校验未通过"
            else:
                summary = "配置 upsert 将执行"
        if step["key"] == "persona_writer" and status == "skipped":
            summary = "未启用人设补写"
        if step["key"] == "group_join" and status == "skipped":
            summary = "未启用自动加群"
        if step["key"] == "restart" and status == "skipped":
            summary = "未启用重启"
        if step["key"] == "persona_writer" and status != "skipped" and not OPENCLAW_CLI_BIN:
            status = "warn"
            summary = "CLI 不可用，需手动补写人设"
        step_results.append(
            {
                "key": step["key"],
                "label": step["label"],
                "status": status,
                "summary": summary,
                "detail": None,
                "started_at": None,
                "finished_at": None,
            }
        )

    if scripts and not blockers:
        try:
            dry_payload = _run_skill_script_json(
                scripts["ensure_feishu_agent"],
                [
                    "upsert",
                    "--agent-id",
                    payload["agent_id"],
                    "--agent-name",
                    payload["agent_name"],
                    "--app-id",
                    feishu.get("app_id", ""),
                    "--app-secret",
                    feishu.get("app_secret", ""),
                    "--operator-open-id",
                    feishu.get("operator_open_id", ""),
                    "--identity-key",
                    feishu.get("identity_key") or "",
                    "--dry-run",
                ],
                timeout=60,
            )
            for step in step_results:
                if step["key"] == "upsert":
                    step["detail"] = json.dumps(dry_payload, ensure_ascii=False)
        except Exception as exc:
            blockers.append(f"upsert_dry_run_failed:{exc}")

    return {"steps": step_results, "warnings": warnings, "blockers": blockers}


def _execute_onboarding_run(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    scripts = _resolve_onboarding_scripts()
    feishu = payload.get("feishu") or {}
    persona = payload.get("persona_strategy") or {}
    groups = payload.get("groups") or {}
    execution = payload.get("execution") or {}
    warnings: list[str] = []
    pending_restart = False
    workspace_dir = None
    if OPENCLAW_CLI_BIN:
        try:
            contract_message = json.dumps(
                {
                    "type": "agent_onboarding_contract",
                    "owner_agent_id": payload.get("owner_agent_id"),
                    "target_agent_id": payload.get("agent_id"),
                    "target_agent_name": payload.get("agent_name"),
                    "persona_mode": persona.get("mode"),
                    "persona_docs": persona.get("docs") or [],
                    "note": "请在可用时使用 sessions_send/agent-to-agent 工具完成补写与派发。",
                },
                ensure_ascii=False,
            )
            _run_openclaw_cli_text(
                [
                    OPENCLAW_CLI_BIN,
                    "agent",
                    "--agent",
                    payload["owner_agent_id"],
                    "--message",
                    contract_message,
                ],
                timeout=30,
            )
        except Exception as exc:
            warnings.append(f"owner_agent_dispatch_failed:{exc}")
    else:
        warnings.append("openclaw_cli_unavailable_owner_dispatch")

    with get_conn() as conn:
        steps = _load_onboarding_steps(conn, run_id)

        for step in steps:
            if step.get("status") in {"done", "skipped"}:
                continue
            started_at = now_iso()
            _update_onboarding_step(conn, run_id, step["step_key"], status="running", started_at=started_at)
            conn.commit()
            try:
                if step["step_key"] == "upsert":
                    result = _run_skill_script_json(
                        scripts["ensure_feishu_agent"],
                        [
                            "upsert",
                            "--agent-id",
                            payload["agent_id"],
                            "--agent-name",
                            payload["agent_name"],
                            "--app-id",
                            feishu.get("app_id", ""),
                            "--app-secret",
                            feishu.get("app_secret", ""),
                            "--operator-open-id",
                            feishu.get("operator_open_id", ""),
                            "--identity-key",
                            feishu.get("identity_key") or "",
                        ],
                        timeout=90,
                    )
                    workspace_dir = (result.get("filesystem_plan") or {}).get("workspaceDir")
                    summary = "配置写入完成"
                    _update_onboarding_step(
                        conn,
                        run_id,
                        step["step_key"],
                        status="done",
                        summary=summary,
                        payload=result,
                        finished_at=now_iso(),
                    )
                elif step["step_key"] == "scaffold_docs":
                    if not workspace_dir:
                        raise RuntimeError("workspace_dir_missing")
                    result = _run_skill_script_json(
                        scripts["scaffold_docs"],
                        [
                            "--agent-id",
                            payload["agent_id"],
                            "--agent-name",
                            payload["agent_name"],
                            "--workspace-dir",
                            workspace_dir,
                            "--role-summary",
                            payload["role_summary"],
                            *sum([["--core-work", item] for item in (payload.get("core_work") or [])], []),
                        ],
                        timeout=90,
                    )
                    _update_onboarding_step(
                        conn,
                        run_id,
                        step["step_key"],
                        status="done",
                        summary="文档脚手架已生成",
                        payload=result,
                        finished_at=now_iso(),
                    )
                elif step["step_key"] == "persona_writer":
                    if persona.get("mode") != "agent_assisted":
                        _update_onboarding_step(
                            conn,
                            run_id,
                            step["step_key"],
                            status="skipped",
                            summary="未启用人设补写",
                            finished_at=now_iso(),
                        )
                    elif not OPENCLAW_CLI_BIN:
                        warnings.append("openclaw_cli_unavailable_for_persona_dispatch")
                        _update_onboarding_step(
                            conn,
                            run_id,
                            step["step_key"],
                            status="warn",
                            summary="CLI 不可用，需手动补写人设",
                            finished_at=now_iso(),
                        )
                    else:
                        writer_agent_id = persona.get("writer_agent_id") or payload["owner_agent_id"]
                        docs = persona.get("docs") or ["SOUL.md", "IDENTITY.md", "USER.md"]
                        message = json.dumps(
                            {
                                "type": "persona_writer",
                                "target_agent_id": payload["agent_id"],
                                "writer_agent_id": writer_agent_id,
                                "docs": docs,
                                "workspace_dir": workspace_dir,
                            },
                            ensure_ascii=False,
                        )
                        _run_openclaw_cli_text(
                            [
                                OPENCLAW_CLI_BIN,
                                "agent",
                                "--agent",
                                payload["owner_agent_id"],
                                "--message",
                                message,
                            ],
                            timeout=45,
                        )
                        _update_onboarding_step(
                            conn,
                            run_id,
                            step["step_key"],
                            status="done",
                            summary="已派发人设补写任务",
                            payload={"writer_agent_id": writer_agent_id, "docs": docs},
                            finished_at=now_iso(),
                        )
                elif step["step_key"] == "group_join":
                    if not groups.get("auto_join"):
                        _update_onboarding_step(
                            conn,
                            run_id,
                            step["step_key"],
                            status="skipped",
                            summary="未启用自动加群",
                            finished_at=now_iso(),
                        )
                    else:
                        _run_skill_script_json(
                            scripts["ensure_dependency"],
                            ["--module", "requests", "--package", "requests"],
                            timeout=120,
                        )
                        chat_ids = [str(item.get("chat_id")) for item in (groups.get("items") or []) if item.get("chat_id")]
                        args = [
                            "ensure-bot-groups",
                            "--target-account-id",
                            payload["agent_id"],
                        ]
                        for chat_id in chat_ids:
                            args.extend(["--chat-id", chat_id])
                        result = _run_skill_script_json(scripts["group_membership"], args, timeout=180)
                        _update_onboarding_step(
                            conn,
                            run_id,
                            step["step_key"],
                            status="done",
                            summary="群组邀请已执行",
                            payload=result,
                            finished_at=now_iso(),
                        )
                elif step["step_key"] == "audit":
                    audit_payload: dict[str, Any] = {}
                    audit_payload["memory_rules"] = _run_skill_script_json(
                        scripts["validate_memory"],
                        ["--agent-id", payload["agent_id"]],
                        timeout=60,
                    )
                    if workspace_dir:
                        audit_payload["workspace_identity"] = _run_skill_script_json(
                            scripts["validate_identity"],
                            [
                                "--agent-id",
                                payload["agent_id"],
                                "--agent-name",
                                payload["agent_name"],
                                "--workspace-dir",
                                workspace_dir,
                            ],
                            timeout=60,
                        )
                    audit_payload["task_contract"] = _run_skill_script_json(
                        scripts["validate_task_contract"],
                        ["--agent-id", payload["agent_id"]],
                        timeout=60,
                    )
                    if execution.get("run_doctor", True) and OPENCLAW_CLI_BIN:
                        audit_payload["doctor"] = _run_openclaw_cli_text(
                            [OPENCLAW_CLI_BIN, "doctor", "--fix"],
                            timeout=45,
                        )
                    if execution.get("run_probe", True) and OPENCLAW_CLI_BIN:
                        audit_payload["probe"] = _run_openclaw_cli_text(
                            [OPENCLAW_CLI_BIN, "channels", "status", "--probe"],
                            timeout=45,
                        )
                    sync_agents_from_openclaw_config()
                    _update_onboarding_step(
                        conn,
                        run_id,
                        step["step_key"],
                        status="done",
                        summary="审计已完成",
                        payload=audit_payload,
                        finished_at=now_iso(),
                    )
                elif step["step_key"] == "restart":
                    if not execution.get("restart_gateway"):
                        pending_restart = True
                        _update_onboarding_step(
                            conn,
                            run_id,
                            step["step_key"],
                            status="skipped",
                            summary="未启用重启",
                            finished_at=now_iso(),
                        )
                    elif not OPENCLAW_CLI_BIN:
                        pending_restart = True
                        warnings.append("openclaw_cli_unavailable_for_restart")
                        _update_onboarding_step(
                            conn,
                            run_id,
                            step["step_key"],
                            status="warn",
                            summary="CLI 不可用，需手动重启",
                            finished_at=now_iso(),
                        )
                    else:
                        _run_openclaw_cli_text([OPENCLAW_CLI_BIN, "gateway", "restart"], timeout=45)
                        _update_onboarding_step(
                            conn,
                            run_id,
                            step["step_key"],
                            status="done",
                            summary="已触发 gateway 重启",
                            finished_at=now_iso(),
                        )
                conn.commit()
            except Exception as exc:
                _update_onboarding_step(
                    conn,
                    run_id,
                    step["step_key"],
                    status="failed",
                    summary=str(exc),
                    finished_at=now_iso(),
                )
                conn.commit()
                warnings.append(str(exc))
                break

        steps = _load_onboarding_steps(conn, run_id)
        completed, total, status = _compute_onboarding_progress(steps)
        conn.execute(
            """
            UPDATE agent_onboarding_runs
            SET status = ?, pending_restart = ?, warnings_json = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (
                status,
                1 if pending_restart else 0,
                json.dumps(warnings, ensure_ascii=False),
                now_iso(),
                run_id,
            ),
        )
        conn.commit()

        run_row = conn.execute("SELECT * FROM agent_onboarding_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not run_row:
            raise RuntimeError("onboarding_run_not_found")
        serialized = _serialize_onboarding_run_row(run_row, steps)
        return {"run": serialized, "steps": serialized["steps"], "warnings": warnings, "pending_restart": serialized["pending_restart"]}


def start_multi_agent_onboarding(payload: dict[str, Any]) -> dict[str, Any]:
    dry_run = dry_run_multi_agent_onboarding(payload)
    if dry_run["blockers"]:
        raise ValueError(f"onboarding_blocked:{','.join(dry_run['blockers'])}")
    run_id = generate_onboarding_run_id()
    steps = _build_onboarding_step_plan(payload)
    with get_conn() as conn:
        _insert_onboarding_run(conn, run_id, payload, steps, warnings=dry_run["warnings"])
    return _execute_onboarding_run(run_id, payload)


def resume_multi_agent_onboarding(run_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        run_row = conn.execute("SELECT * FROM agent_onboarding_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not run_row:
            raise LookupError("onboarding_run_not_found")
        raw_payload = run_row.get("request_json") if isinstance(run_row, dict) else run_row["request_json"]
        if not raw_payload:
            raise ValueError("onboarding_run_payload_missing")
        payload = json.loads(raw_payload)
    return _execute_onboarding_run(run_id, payload)


def confirm_onboarding(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = generate_onboarding_job_id()
    run_id = generate_training_run_id()
    now = now_iso()

    with get_conn() as conn:
        agent = conn.execute("SELECT agent_id FROM agents WHERE agent_id = ?", (payload["agent_id"],)).fetchone()
        if not agent:
            raise ValueError("agent_not_found")

        conn.execute(
            """
            INSERT INTO onboarding_jobs (
                job_id, agent_id, agent_name, role_summary, creator_type, creator_id,
                status, trigger_training, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?)
            """,
            (
                job_id,
                payload["agent_id"],
                payload["agent_name"],
                payload["role_summary"],
                payload["creator_type"],
                payload["creator_id"],
                1 if payload.get("trigger_training", True) else 0,
                now,
                now,
            ),
        )

        training_run = None
        if payload.get("trigger_training", True):
            training_run = {
                "run_id": run_id,
                "agent_id": payload["agent_id"],
                "onboarding_job_id": job_id,
                "phase": "exam",
                "status": "planned",
                "score": None,
                "result": None,
                "report_url": None,
                "observe_days": int(payload.get("observe_days", 14)),
                "created_at": now,
                "updated_at": now,
            }
            conn.execute(
                """
                INSERT INTO training_runs (
                    run_id, agent_id, onboarding_job_id, phase, status, score, result,
                    report_url, observe_days, created_at, updated_at
                ) VALUES (
                    :run_id, :agent_id, :onboarding_job_id, :phase, :status, :score, :result,
                    :report_url, :observe_days, :created_at, :updated_at
                )
                """,
                training_run,
            )
        conn.commit()

    response = {
        "job_id": job_id,
        "agent_id": payload["agent_id"],
        "status": "confirmed",
        "trigger_training": bool(payload.get("trigger_training", True)),
        "created_at": now,
        "completed_at": now,
    }
    if training_run:
        created = get_training_run_by_id(training_run["run_id"])
        response["training_run"] = created or training_run
    return response


def create_training_run(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = generate_training_run_id()
    now = now_iso()
    run = {
        "run_id": run_id,
        "agent_id": payload["agent_id"],
        "onboarding_job_id": payload.get("onboarding_job_id"),
        "phase": payload.get("phase", "exam"),
        "status": payload.get("status", "planned"),
        "score": payload.get("score"),
        "result": payload.get("result"),
        "report_url": payload.get("report_url"),
        "observe_days": payload.get("observe_days"),
        "created_at": now,
        "updated_at": now,
    }

    with get_conn() as conn:
        agent = conn.execute("SELECT agent_id FROM agents WHERE agent_id = ?", (run["agent_id"],)).fetchone()
        if not agent:
            raise ValueError("agent_not_found")
        conn.execute(
            """
            INSERT INTO training_runs (
                run_id, agent_id, onboarding_job_id, phase, status, score, result,
                report_url, observe_days, created_at, updated_at
            ) VALUES (
                :run_id, :agent_id, :onboarding_job_id, :phase, :status, :score, :result,
                :report_url, :observe_days, :created_at, :updated_at
            )
            """,
            run,
        )
        conn.commit()
    created = get_training_run_by_id(run_id)
    return created or run


def list_training_runs(agent_id: str | None = None) -> list[dict[str, Any]]:
    return [_serialize_training_run_row(row) for row in _list_training_runs_with_context(agent_id=agent_id)]


def gate_training_run(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    status = "passed" if result == "GRADUATE" else "failed"
    now = now_iso()

    with get_conn() as conn:
        run = conn.execute("SELECT * FROM training_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not run:
            raise LookupError("training_run_not_found")

        conn.execute(
            """
            UPDATE training_runs
            SET phase = 'gate', status = ?, score = ?, result = ?, report_url = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (
                status,
                payload.get("score"),
                result,
                payload.get("report_url"),
                now,
                run_id,
            ),
        )
        try:
            context = conn.execute(
                "SELECT observation_job_id FROM training_run_contexts WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            context = None

        if context and context["observation_job_id"]:
            _disable_scheduled_job(context["observation_job_id"])
            conn.execute(
                """
                UPDATE training_run_contexts
                SET orchestration_state = 'completed', completed_at = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (now, now, run_id),
            )

        if result == "GRADUATE":
            conn.execute(
                "UPDATE agents SET status = 'active' WHERE agent_id = ?",
                (run["agent_id"],),
            )
        else:
            conn.execute(
                "UPDATE agents SET status = 'probation' WHERE agent_id = ?",
                (run["agent_id"],),
            )
        conn.commit()

    updated = get_training_run_by_id(run_id)
    return updated or {}
