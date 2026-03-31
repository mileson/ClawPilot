# Copyright (c) 2026 ClawPilot Contributors. All rights reserved.
# Licensed under the Business Source License 1.1 — see LICENSE file.
# NOTICE: Reverse engineering, decompilation, or disassembly is prohibited.

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from typing import Any

from . import db

_JOBS: dict[str, dict[str, Any]] = {}
_RUNNING_JOB_BY_ACCOUNT: dict[str, str] = {}
_LOCK = threading.Lock()

_ACTIVE_STATUSES = {"queued", "waiting_login", "claiming"}


def _snapshot(job: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(job)


def _set_job(job_id: str, patch: dict[str, Any]) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.update(patch)


def _record_job_audit(
    *,
    actor_account_id: str | None,
    action: str,
    job_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    with db.get_conn() as conn:
        db._record_audit_log(
            conn,
            actor_account_id=actor_account_id,
            action=action,
            target_type="job",
            target_id=job_id,
            detail=detail,
        )
        conn.commit()


def _record_job_diagnostic(
    *,
    actor_account_id: str | None,
    job_id: str,
    trace_id: str | None,
    event: str,
    level: str = "info",
    request_path: str | None = "/api/agents/claim-first-lobster/auto-run",
    detail: dict[str, Any] | None = None,
) -> None:
    merged_detail = {"job_id": job_id}
    if detail:
        merged_detail.update(detail)
    db.record_diagnostic_log(
        actor_account_id=actor_account_id,
        source="server",
        category="first_lobster_auto_claim",
        event=event,
        level=level,
        trace_id=trace_id,
        request_path=request_path,
        detail=merged_detail,
    )


def _active_job_for_account(account_id: str | None) -> dict[str, Any] | None:
    if not account_id:
        return None
    job_id = _RUNNING_JOB_BY_ACCOUNT.get(account_id)
    if not job_id:
        return None
    job = _JOBS.get(job_id)
    if not job:
        return None
    if str(job.get("status") or "") not in _ACTIVE_STATUSES:
        return None
    return job


def _build_automation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "app_name": str(payload.get("app_name") or "").strip(),
        "app_description": payload.get("app_description"),
        "menu_name": payload.get("menu_name"),
        "automation_mode": "auto",
        "timeout_sec": int(payload.get("timeout_sec") or 600),
        "wait_for_login": True,
    }


def _build_claim_payload(app_id: str, app_secret: str, agent_name: str | None = None) -> dict[str, Any]:
    return {
        "selected_channels": ["feishu"],
        "primary_channel": "feishu",
        "agent_name": agent_name,
        "feishu": {
            "app_id": app_id,
            "app_secret": app_secret,
        },
    }


def _normalize_failure_message(result: dict[str, Any]) -> str:
    message = str(result.get("message") or "").strip()
    if result.get("status") == "dependency_missing":
        return message or "缺少飞书自动化依赖，请先安装 Playwright 相关依赖后重试。"
    if result.get("status") == "login_required":
        return message or "在等待时间内未检测到飞书开放平台登录完成，请重试。"
    return message or "自动创建飞书应用失败，请稍后重试。"


def _run_job(job_id: str, actor_account_id: str | None, payload: dict[str, Any]) -> None:
    trace_id = str(payload.get("trace_id") or "").strip() or None
    _set_job(
        job_id,
        {
            "status": "waiting_login",
            "current_stage": "waiting_login",
            "message": "已打开飞书页面，等待你在浏览器里完成登录。",
            "started_at": db.now_iso(),
        },
    )
    _record_job_diagnostic(
        actor_account_id=actor_account_id,
        job_id=job_id,
        trace_id=trace_id,
        event="job.waiting_login",
        detail={
            "app_name": str(payload.get("app_name") or "").strip(),
            "message": "已打开飞书页面，等待你在浏览器里完成登录。",
        },
    )
    try:
        automation = db.run_feishu_app_ui_automation(_build_automation_payload(payload))
        if automation.get("status") != "success":
            raise RuntimeError(_normalize_failure_message(automation))

        app_id = str(automation.get("app_id") or "").strip()
        app_secret = str(automation.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            raise RuntimeError("飞书应用已创建，但未能读取完整凭证，请重试。")

        _set_job(
            job_id,
            {
                "status": "claiming",
                "current_stage": "claiming",
                "message": "已检测到飞书登录，正在自动创建机器人并完成领取。",
                "execution_mode": automation.get("execution_mode"),
                "debugger_url": automation.get("debugger_url"),
                "chat_url": automation.get("chat_url"),
                "app_id": app_id,
            },
        )
        _record_job_diagnostic(
            actor_account_id=actor_account_id,
            job_id=job_id,
            trace_id=trace_id,
            event="automation.success",
            detail={
                "app_name": str(payload.get("app_name") or "").strip(),
                "app_id": app_id,
                "chat_url": automation.get("chat_url"),
                "execution_mode": automation.get("execution_mode"),
            },
        )
        _record_job_diagnostic(
            actor_account_id=actor_account_id,
            job_id=job_id,
            trace_id=trace_id,
            event="claim.started",
            detail={
                "app_name": str(payload.get("app_name") or "").strip(),
                "app_id": app_id,
            },
        )

        result = db.claim_first_lobster(
            _build_claim_payload(app_id, app_secret, str(payload.get("app_name") or "").strip() or None),
            actor_account_id=actor_account_id,
        )
        detail = {
            "job_id": job_id,
            "status": "completed",
            "app_name": str(payload.get("app_name") or "").strip(),
            "app_id": app_id,
            "chat_url": automation.get("chat_url"),
            "agent_id": ((result.get("agent") or {}).get("agent_id") or None),
            "selected_channels": result.get("selected_channels") or [],
            "primary_channel": result.get("primary_channel"),
            "config_path": result.get("config_path"),
            "backup_path": result.get("backup_path"),
        }
        _set_job(
            job_id,
            {
                "status": "completed",
                "current_stage": "completed",
                "message": "已完成自动创建并领取。",
                "finished_at": db.now_iso(),
                "agent_id": ((result.get("agent") or {}).get("agent_id") or None),
                "selected_channels": result.get("selected_channels") or [],
                "primary_channel": result.get("primary_channel"),
                "config_path": result.get("config_path"),
                "backup_path": result.get("backup_path"),
            },
        )
        _record_job_diagnostic(
            actor_account_id=actor_account_id,
            job_id=job_id,
            trace_id=trace_id,
            event="claim.completed",
            detail=detail,
        )
        _record_job_audit(
            actor_account_id=actor_account_id,
            action="agents.claim_first_lobster_auto_run.completed",
            job_id=job_id,
            detail=detail,
        )
    except Exception as exc:
        current_job = get_first_lobster_auto_claim_job(actor_account_id, job_id)
        _set_job(
            job_id,
            {
                "status": "failed",
                "current_stage": "failed",
                "message": "自动领取失败。",
                "error_message": str(exc),
                "finished_at": db.now_iso(),
            },
        )
        _record_job_diagnostic(
            actor_account_id=actor_account_id,
            job_id=job_id,
            trace_id=trace_id,
            event="job.failed",
            level="error",
            detail={
                "app_name": str(payload.get("app_name") or "").strip(),
                "current_stage": current_job.get("current_stage"),
                "message": current_job.get("message"),
                "error_message": str(exc),
            },
        )
        _record_job_audit(
            actor_account_id=actor_account_id,
            action="agents.claim_first_lobster_auto_run.failed",
            job_id=job_id,
            detail={
                "job_id": job_id,
                "status": "failed",
                "app_name": str(payload.get("app_name") or "").strip(),
                "current_stage": current_job.get("current_stage"),
                "message": current_job.get("message"),
                "error_message": str(exc),
            },
        )
    finally:
        if actor_account_id:
            with _LOCK:
                running_job_id = _RUNNING_JOB_BY_ACCOUNT.get(actor_account_id)
                if running_job_id == job_id:
                    _RUNNING_JOB_BY_ACCOUNT.pop(actor_account_id, None)


def start_first_lobster_auto_claim(actor_account_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    app_name = str(payload.get("app_name") or "").strip()
    if not app_name:
        raise ValueError("first_lobster_name_required")
    trace_id = str(payload.get("trace_id") or "").strip() or f"lobster_{uuid.uuid4().hex[:12]}"

    with _LOCK:
        active_job = _active_job_for_account(actor_account_id)
        if active_job:
            return _snapshot(active_job)

        job_id = f"flc_{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "account_id": actor_account_id,
            "status": "queued",
            "current_stage": "queued",
            "trace_id": trace_id,
            "message": "正在准备飞书自动领取任务。",
            "error_message": None,
            "execution_mode": None,
            "debugger_url": None,
            "chat_url": None,
            "app_id": None,
            "agent_id": None,
            "selected_channels": [],
            "primary_channel": None,
            "config_path": None,
            "backup_path": None,
            "created_at": db.now_iso(),
            "started_at": None,
            "finished_at": None,
        }
        _JOBS[job_id] = job
        if actor_account_id:
            _RUNNING_JOB_BY_ACCOUNT[actor_account_id] = job_id

    thread = threading.Thread(
        target=_run_job,
        kwargs={
            "job_id": job_id,
            "actor_account_id": actor_account_id,
            "payload": {
                **dict(payload),
                "trace_id": trace_id,
            },
        },
        daemon=True,
    )
    thread.start()
    _record_job_diagnostic(
        actor_account_id=actor_account_id,
        job_id=job_id,
        trace_id=trace_id,
        event="job.started",
        detail={
            "app_name": app_name,
            "current_stage": job["current_stage"],
            "message": job["message"],
        },
    )
    _record_job_audit(
        actor_account_id=actor_account_id,
        action="agents.claim_first_lobster_auto_run.started",
        job_id=job_id,
        detail={
            "job_id": job_id,
            "status": "started",
            "app_name": app_name,
            "current_stage": job["current_stage"],
            "message": job["message"],
        },
    )
    return _snapshot(job)


def get_first_lobster_auto_claim_job(actor_account_id: str | None, job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise LookupError("first_lobster_auto_claim_job_not_found")
        if actor_account_id and str(job.get("account_id") or "") != actor_account_id:
            raise LookupError("first_lobster_auto_claim_job_not_found")
        return _snapshot(job)
