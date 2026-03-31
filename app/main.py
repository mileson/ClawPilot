# Copyright 2026 Mileson
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import db
from . import first_lobster_jobs
from . import scene_jobs
from .schemas import (
    AgentActivityLogOut,
    AgentFeishuPairingConfirmRequest,
    AgentFeishuPairingConfirmResponse,
    AgentOut,
    AgentSceneGenerateRequest,
    AgentSceneJobOut,
    AgentPortablePackagePreviewOut,
    AgentScheduledJobOut,
    AgentScheduledJobsResponse,
    CreateNodeRequest,
    ClaimFirstLobsterRequest,
    ClaimFirstLobsterResponse,
    ConnectAgentFeishuChannelRequest,
    ConnectAgentFeishuChannelResponse,
    ControlPlaneActionRequest,
    ControlPlaneActionResponse,
    ControlPlaneJobStatusResponse,
    ScheduledJobsTimelineResponseOut,
    AgentSkillDeleteResultOut,
    AgentRemoveResultOut,
    AgentSkillImportResultOut,
    AgentUserAuthStateOut,
    AgentWorkspaceDirectoryOut,
    AgentWorkspaceFileOut,
    CreateAgentScheduledJobRequest,
    CreateWorkspaceFileRequest,
    ConfigureTrainingModuleRequest,
    CreateTrainingRunRequest,
    CreateTaskRequest,
    DispatchTaskRequest,
    DispatchTaskResponse,
    ChangePasswordRequest,
    CreateAccountRequest,
    CreateAccountResponse,
    CreateRoleRequest,
    CreateRoleResponse,
    ErrorResponse,
    RescueCenterActivateThreadRequest,
    RescueCenterBootstrapResponse,
    RescueCenterEventListResponse,
    RescueCenterMessageDispatchResponse,
    RescueCenterReadinessOut,
    RescueCenterResetResponse,
    RescueCenterSendMessageRequest,
    RescueCenterThreadListResponse,
    RescueCenterThreadResponse,
    BootstrapAccountResponse,
    TrainingAgentDetailOut,
    TrainingDocumentOut,
    TrainingModuleConfigureResponse,
    TrainingModuleOverviewOut,
    GateTrainingRunRequest,
    HealthResponse,
    ImportGithubSkillRequest,
    LeaderboardResponse,
    ListAgentsResponse,
    FirstLobsterBootstrapPreviewResponse,
    FirstLobsterAutoClaimRequest,
    FirstLobsterAutoClaimRunOut,
    FirstLobsterFeishuPairingConfirmRequest,
    FirstLobsterFeishuPairingConfirmResponse,
    ListNodesResponse,
    ListTasksResponse,
    ListTrainingRunsResponse,
    BasicAgentCreateRequest,
    BasicAgentCreateResponse,
    NodeBootstrapResponse,
    NodeHeartbeatRequest,
    NodeHeartbeatResponse,
    NodeSyncResultsRequest,
    NodeSyncResultsResponse,
    OpenClawRootDirectoryOut,
    OpenClawRootFileOut,
    OnboardingConfirmRequest,
    OnboardingConfirmResponse,
    MultiAgentOnboardingRequest,
    MultiAgentOnboardingBootstrapResponse,
    MultiAgentOnboardingDryRunResponse,
    MultiAgentOnboardingRunResponse,
    MultiAgentOnboardingRunsResponse,
    FeishuAppAutoCreateRequest,
    FeishuAppAutoCreateResponse,
    ReviewTaskRequest,
    ReviewTaskResponse,
    StartAgentUserAuthResponse,
    StartTrainingRunRequest,
    SendWorkspaceInstructionRequest,
    SendWorkspaceInstructionResponse,
    SubmitTaskRequest,
    SetupStatusResponse,
    SystemSettingsOut,
    GatewaySettingsOut,
    GatewayApplyResponse,
    GatewayJobStatusResponse,
    TaskDetailResponse,
    TaskOut,
    TrainingRunOut,
    UpdateTrainingDocumentRequest,
    UpdateAgentScenePresetRequest,
    UpdateAgentScheduledJobRequest,
    UpdateWorkspaceFileRequest,
    UpdateSystemCurrencyRequest,
    UpdateGatewaySettingsRequest,
    UpdateSystemStatusAliasesRequest,
    ListAccountsResponse,
    AccountAccessResponse,
    AccountOut,
    UpdateAccountRolesRequest,
    UpdateAccountAccessRequest,
    ResetAccountPasswordResponse,
    LoginRequest,
    LoginResponse,
    RoleOut,
    ListRolesResponse,
    ListPermissionsResponse,
    UpdateRoleRequest,
    RolePermissionsResponse,
    RolePermissionsMappingResponse,
    UpdateRolePermissionsRequest,
    ListAuditLogsResponse,
    DiagnosticLogOut,
    CreateDiagnosticLogRequest,
    ListDiagnosticLogsResponse,
    LobsterToolkitDeleteDeploymentResponseOut,
    LobsterToolkitDeleteSourceResponseOut,
    LobsterToolkitDispatchRequest,
    LobsterToolkitDispatchResponseOut,
    LobsterToolkitListResponseOut,
    LobsterToolkitSearchResponseOut,
    LobsterToolkitSourceOut,
    LobsterToolkitSourceUpsertRequest,
    LobsterToolkitUpdateRequest,
    GenerateAgentProfileRequest,
    GenerateAgentProfileResponse,
    WeixinQrStartResponse,
    WeixinQrPollResponse,
    WeixinBridgeStartResponse,
    WeixinBridgeStopResponse,
    WeixinBridgeStatusResponse,
)

APP_VERSION = "0.1.0"
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"

DEFAULT_LOCAL_CORS_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
)


def _resolve_cors_allow_origins() -> list[str]:
    configured = os.getenv("OPENCLAW_CORS_ALLOW_ORIGINS", "")
    extra = [item.strip() for item in configured.split(",") if item.strip()]
    # Preserve order while removing duplicates.
    return list(dict.fromkeys([*DEFAULT_LOCAL_CORS_ORIGINS, *extra]))

app = FastAPI(
    title="ClawPilot",
    version=APP_VERSION,
    description="ClawPilot backend for multi-agent operations and coordination",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _extract_session_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            return token
    cookie_token = request.cookies.get("oc_session")
    if cookie_token:
        return cookie_token.strip() or None
    return None


def _require_account(request: Request, *, allow_password_change: bool = False) -> dict[str, Any]:
    token = _extract_session_token(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(code="unauthorized", message="未登录").model_dump(),
        )
    try:
        account = db.get_account_by_session(token)
    except PermissionError as exc:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(code="unauthorized", message=str(exc)).model_dump(),
        ) from exc
    if account.get("must_change_password") and not allow_password_change:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="password_change_required", message="需要先修改密码").model_dump(),
        )
    return account


def _require_permission(account: dict[str, Any], permission_id: str) -> None:
    permissions = db.list_account_permissions(account["account_id"])
    if permission_id not in permissions:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message="权限不足").model_dump(),
        )


def _raise_rescue_center_http_exception(exc: rescue_center.RescueCenterError) -> None:
    status_code = 409 if exc.code in {"missing-cli", "missing-auth", "root-missing", "cwd-locked"} else 503
    raise HTTPException(
        status_code=status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message, details=exc.details or None).model_dump(),
    )


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    db.sync_agents_from_openclaw_config(refresh_feishu_profiles=False)
    system_jobs.start_exchange_rate_refresher()


@app.on_event("shutdown")
def on_shutdown() -> None:
    rescue_center.shutdown_rescue_center_transports()


# ──────────────────────────────────────────────
# @tier:core — 健康检查
# ──────────────────────────────────────────────
@app.get("/healthz", response_model=HealthResponse)
def get_health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


# ──────────────────────────────────────────────
# @tier:core — 前端 SPA 入口页
# ──────────────────────────────────────────────
@app.get("/", include_in_schema=False)
@app.get("/agents", include_in_schema=False)
@app.get("/tasks", include_in_schema=False)
@app.get("/leaderboard", include_in_schema=False)
@app.get("/training", include_in_schema=False)
def get_index() -> FileResponse:
    return FileResponse(str(INDEX_FILE))


# ──────────────────────────────────────────────
# @tier:core — Agent 基础管理
# ──────────────────────────────────────────────
# @tier:core
@app.get("/api/agents", response_model=ListAgentsResponse, tags=["Agents"])
def list_agents(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1, max_length=100),
) -> dict[str, Any]:
    items = db.list_agents(
        status=status,
        q=q,
        include_feishu_profiles=False,
        include_official_runtime_signal=False,
    )
    normalized = []
    for row in items:
        row["identity_complete"] = bool(row.get("identity_complete"))
        normalized.append(row)
    return {"items": normalized, "total": len(normalized)}


# @tier:core
@app.post("/api/agents/sync", tags=["Agents"])
def sync_agents() -> dict[str, Any]:
    synced = db.sync_agents_from_openclaw_config()
    return {"synced": synced, "fallback_seeded": False}


@app.post("/api/agents/basic-create", response_model=BasicAgentCreateResponse, tags=["Agents"])
def create_basic_agent(payload: BasicAgentCreateRequest, request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return db.create_basic_agent(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc


@app.put("/api/agents/{agent_id}/scene-preset", response_model=AgentOut, tags=["Agents"])
def update_agent_scene_preset(agent_id: str, payload: UpdateAgentScenePresetRequest) -> dict[str, Any]:
    try:
        return db.update_agent_scene_preset(agent_id=agent_id, preset_id=payload.preset_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/channels/feishu",
    response_model=ConnectAgentFeishuChannelResponse,
    tags=["Agents"],
)
def connect_agent_feishu_channel(
    agent_id: str,
    payload: ConnectAgentFeishuChannelRequest,
    request: Request,
) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return db.connect_agent_feishu_channel(agent_id, payload.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/channels/feishu/pairing-confirm",
    response_model=AgentFeishuPairingConfirmResponse,
    tags=["Agents"],
)
def confirm_agent_feishu_pairing(
    agent_id: str,
    payload: AgentFeishuPairingConfirmRequest,
    request: Request,
) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        merged = payload.model_dump(mode="json")
        merged["agent_id"] = agent_id
        return db.confirm_agent_feishu_pairing(
            merged,
            actor_account_id=account["account_id"],
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/empty-state/bootstrap-preview",
    response_model=FirstLobsterBootstrapPreviewResponse,
    tags=["Agents"],
)
def get_first_lobster_bootstrap_preview() -> dict[str, Any]:
    return db.get_first_lobster_bootstrap_preview()


# ──────────────────────────────────────────────
# @tier:internal — Rescue Center（不进公开版）
# ──────────────────────────────────────────────
@app.get("/api/rescue-center/readiness", response_model=RescueCenterReadinessOut, tags=["Rescue Center"])
def get_rescue_center_readiness(request: Request) -> dict[str, Any]:
    _require_account(request)
    return rescue_center.get_rescue_center_readiness()


@app.get("/api/rescue-center/bootstrap", response_model=RescueCenterBootstrapResponse, tags=["Rescue Center"])
def get_rescue_center_bootstrap(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    return rescue_center.get_rescue_center_bootstrap(account["account_id"])


@app.get("/api/rescue-center/threads", response_model=RescueCenterThreadListResponse, tags=["Rescue Center"])
def list_rescue_center_threads(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    return rescue_center.list_rescue_center_threads(account["account_id"])


@app.post("/api/rescue-center/threads/new", response_model=RescueCenterThreadResponse, tags=["Rescue Center"])
def create_rescue_center_thread(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    try:
        return rescue_center.create_rescue_center_thread(account["account_id"])
    except rescue_center.RescueCenterError as exc:
        _raise_rescue_center_http_exception(exc)


@app.post(
    "/api/rescue-center/threads/activate",
    response_model=RescueCenterThreadResponse,
    tags=["Rescue Center"],
)
def activate_rescue_center_thread(
    payload: RescueCenterActivateThreadRequest,
    request: Request,
) -> dict[str, Any]:
    account = _require_account(request)
    try:
        return rescue_center.activate_rescue_center_thread(account["account_id"], payload.thread_id)
    except rescue_center.RescueCenterError as exc:
        _raise_rescue_center_http_exception(exc)


@app.post("/api/rescue-center/threads/reset", response_model=RescueCenterResetResponse, tags=["Rescue Center"])
def reset_rescue_center_threads(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    return rescue_center.reset_rescue_center(account["account_id"])


@app.post("/api/rescue-center/messages", response_model=RescueCenterThreadResponse, tags=["Rescue Center"])
def send_rescue_center_message(
    payload: RescueCenterSendMessageRequest,
    request: Request,
) -> dict[str, Any]:
    account = _require_account(request)
    try:
        return rescue_center.send_rescue_center_message(
            account["account_id"],
            thread_id=payload.thread_id,
            message=payload.message,
            trace_id=payload.trace_id,
        )
    except rescue_center.RescueCenterError as exc:
        _raise_rescue_center_http_exception(exc)


@app.post(
    "/api/rescue-center/messages/dispatch",
    response_model=RescueCenterMessageDispatchResponse,
    tags=["Rescue Center"],
)
def dispatch_rescue_center_message(
    payload: RescueCenterSendMessageRequest,
    request: Request,
) -> dict[str, Any]:
    account = _require_account(request)
    try:
        return rescue_center.dispatch_rescue_center_message(
            account["account_id"],
            thread_id=payload.thread_id,
            message=payload.message,
            trace_id=payload.trace_id,
        )
    except rescue_center.RescueCenterError as exc:
        _raise_rescue_center_http_exception(exc)


@app.get(
    "/api/rescue-center/events",
    response_model=RescueCenterEventListResponse,
    tags=["Rescue Center"],
)
def get_rescue_center_events(
    request: Request,
    thread_id: str = Query(min_length=1, max_length=128),
    after_seq: int = Query(default=0, ge=0),
    wait_ms: int = Query(default=0, ge=0, le=5000),
) -> dict[str, Any]:
    account = _require_account(request)
    try:
        return rescue_center.list_rescue_center_events(
            account["account_id"],
            thread_id=thread_id,
            after_seq=after_seq,
            wait_ms=wait_ms,
        )
    except rescue_center.RescueCenterError as exc:
        _raise_rescue_center_http_exception(exc)


@app.get(
    "/api/rescue-center/threads/{thread_id}",
    response_model=RescueCenterThreadResponse,
    tags=["Rescue Center"],
)
def get_rescue_center_thread(thread_id: str, request: Request) -> dict[str, Any]:
    account = _require_account(request)
    try:
        return rescue_center.read_rescue_center_thread(account["account_id"], thread_id)
    except rescue_center.RescueCenterError as exc:
        _raise_rescue_center_http_exception(exc)


@app.post(
    "/api/agents/claim-first-lobster",
    response_model=ClaimFirstLobsterResponse,
    tags=["Agents"],
)
def claim_first_lobster(payload: ClaimFirstLobsterRequest, request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return db.claim_first_lobster(
            payload.model_dump(mode="json"),
            actor_account_id=account["account_id"],
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/claim-first-lobster/auto-run",
    response_model=FirstLobsterAutoClaimRunOut,
    tags=["Agents"],
)
def start_first_lobster_auto_claim(payload: FirstLobsterAutoClaimRequest, request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return first_lobster_jobs.start_first_lobster_auto_claim(
            account["account_id"],
            payload.model_dump(mode="json"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/claim-first-lobster/auto-run/{job_id}",
    response_model=FirstLobsterAutoClaimRunOut,
    tags=["Agents"],
)
def get_first_lobster_auto_claim(job_id: str, request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return first_lobster_jobs.get_first_lobster_auto_claim_job(account["account_id"], job_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/claim-first-lobster/feishu-pairing-confirm",
    response_model=FirstLobsterFeishuPairingConfirmResponse,
    tags=["Agents"],
)
def confirm_first_lobster_feishu_pairing(
    payload: FirstLobsterFeishuPairingConfirmRequest,
    request: Request,
) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return db.confirm_first_lobster_feishu_pairing(
            payload.model_dump(mode="json"),
            actor_account_id=account["account_id"],
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/first-lobster/weixin/start-qr",
    response_model=WeixinQrStartResponse,
    tags=["Agents"],
)
def start_weixin_qr(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return db.start_weixin_qr_login()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code=str(exc), message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/first-lobster/weixin/poll-qr/{session_id}",
    response_model=WeixinQrPollResponse,
    tags=["Agents"],
)
def poll_weixin_qr(session_id: str, request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    return db.poll_weixin_qr_login(session_id)


@app.post(
    "/api/weixin-bridge/start",
    response_model=WeixinBridgeStartResponse,
    tags=["Agents"],
)
def start_weixin_bridge(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return db.start_weixin_bridge()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code=str(exc), message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/weixin-bridge/stop",
    response_model=WeixinBridgeStopResponse,
    tags=["Agents"],
)
def stop_weixin_bridge(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    return db.stop_weixin_bridge()


@app.get(
    "/api/weixin-bridge/status",
    response_model=WeixinBridgeStatusResponse,
    tags=["Agents"],
)
def get_weixin_bridge_status(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    return db.get_weixin_bridge_status()


# ──────────────────────────────────────────────
# @tier:ee — 微信桥接（不进公开版）
# ──────────────────────────────────────────────
@app.post("/api/weixin-bridge/chat", tags=["Agents"])
async def weixin_bridge_chat(request: Request) -> dict[str, Any]:
    body = await request.json()
    text = str(body.get("text", "")).strip()
    conversation_id = str(body.get("conversation_id", "")).strip()
    if not text:
        return {"text": "（收到空消息）", "media_url": None}
    return {
        "text": f"[ClawPilot] 收到来自微信的消息：{text[:200]}",
        "media_url": None,
        "media_type": None,
        "media_file_name": None,
    }


# ──────────────────────────────────────────────
# @tier:core — Setup & Auth
# ──────────────────────────────────────────────
@app.get("/api/setup/status", response_model=SetupStatusResponse, tags=["Setup"])
def get_setup_status() -> dict[str, Any]:
    return db.get_setup_status()


# ──────────────────────────────────────────────
# @tier:internal — Control Plane（不进公开版）
# ──────────────────────────────────────────────
@app.get("/api/control-plane/status", tags=["Setup"])
def get_control_plane_status() -> dict[str, Any]:
    return control_plane_ops.get_control_plane_status()


@app.get("/api/control-plane/doctor", tags=["Setup"])
def get_control_plane_doctor() -> dict[str, Any]:
    return control_plane_ops.get_control_plane_doctor()


@app.post("/api/control-plane/actions", response_model=ControlPlaneActionResponse, tags=["Setup"])
def start_control_plane_action(
    payload: ControlPlaneActionRequest,
    request: Request,
) -> dict[str, Any]:
    _require_account(request)
    try:
        return control_plane_ops.start_control_plane_action(payload.action)
    except control_plane_ops.ControlPlaneOpsError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code=exc.code, message=exc.message, details=exc.details).model_dump(),
        ) from exc


@app.get("/api/control-plane/actions/{job_id}", response_model=ControlPlaneJobStatusResponse, tags=["Setup"])
def get_control_plane_action(job_id: str, request: Request) -> dict[str, Any]:
    _require_account(request)
    try:
        return control_plane_ops.get_control_plane_action(job_id)
    except control_plane_ops.ControlPlaneOpsError as exc:
        raise HTTPException(
            status_code=404 if exc.code == "job_not_found" else 400,
            detail=ErrorResponse(code=exc.code, message=exc.message, details=exc.details).model_dump(),
        ) from exc


@app.get("/api/auth/bootstrap", response_model=BootstrapAccountResponse, tags=["Accounts"])
def get_bootstrap_account() -> dict[str, Any]:
    try:
        return db.reveal_bootstrap_account()
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/auth/login", response_model=LoginResponse, tags=["Accounts"])
def login(payload: LoginRequest) -> dict[str, Any]:
    try:
        return db.authenticate_account(payload.username, payload.password)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/auth/logout", tags=["Accounts"])
def logout(request: Request) -> dict[str, Any]:
    token = _extract_session_token(request)
    if not token:
        return {"ok": True}
    db.revoke_session(token)
    return {"ok": True}


@app.post("/api/auth/password/change", response_model=AccountOut, tags=["Accounts"])
def change_password(request: Request, payload: ChangePasswordRequest) -> dict[str, Any]:
    account = _require_account(request, allow_password_change=True)
    try:
        return db.change_account_password(
            account_id=account["account_id"],
            current_password=payload.current_password,
            new_password=payload.new_password,
            actor_account_id=account["account_id"],
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


# ──────────────────────────────────────────────
# @tier:ee — Accounts / Roles / Permissions（不进公开版）
# ──────────────────────────────────────────────
@app.get("/api/accounts", response_model=ListAccountsResponse, tags=["Accounts"])
def list_accounts(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.view")
    items = db.list_accounts()
    return {"items": items, "total": len(items)}


@app.post("/api/accounts", response_model=CreateAccountResponse, tags=["Accounts"])
def create_account(request: Request, payload: CreateAccountRequest) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.invite")
    try:
        return db.create_account(payload.model_dump(mode="json"), actor_account_id=account["account_id"])
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.put("/api/accounts/{account_id}/roles", response_model=AccountOut, tags=["Accounts"])
def update_account_roles(
    request: Request, account_id: str, payload: UpdateAccountRolesRequest
) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "roles.assign")
    try:
        return db.update_account_roles(account_id, payload.role_ids, actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/accounts/{account_id}/access", response_model=AccountAccessResponse, tags=["Accounts"])
def get_account_access(request: Request, account_id: str) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "roles.assign")
    try:
        return db.get_account_access(account_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.put("/api/accounts/{account_id}/access", response_model=AccountAccessResponse, tags=["Accounts"])
def update_account_access(
    request: Request, account_id: str, payload: UpdateAccountAccessRequest
) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "roles.assign")
    try:
        return db.update_account_access(
            account_id,
            role_ids=payload.role_ids,
            manual_permission_ids=payload.manual_permission_ids,
            actor_account_id=account["account_id"],
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/accounts/{account_id}/disable", response_model=AccountOut, tags=["Accounts"])
def disable_account(request: Request, account_id: str) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.disable")
    try:
        return db.disable_account(account_id, actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/accounts/{account_id}/enable", response_model=AccountOut, tags=["Accounts"])
def enable_account(request: Request, account_id: str) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.disable")
    try:
        return db.enable_account(account_id, actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/accounts/{account_id}/reset-password", response_model=ResetAccountPasswordResponse, tags=["Accounts"])
def reset_account_password(request: Request, account_id: str) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.reset_password")
    try:
        return db.reset_account_password(account_id, actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/accounts/{account_id}/force-logout", response_model=AccountOut, tags=["Accounts"])
def force_logout_account(request: Request, account_id: str) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.force_logout")
    try:
        return db.force_logout_account(account_id, actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.delete("/api/accounts/{account_id}", tags=["Accounts"])
def delete_account(request: Request, account_id: str) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.delete")
    try:
        db.delete_account(account_id, actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    return {"ok": True}


@app.get("/api/roles", response_model=ListRolesResponse, tags=["Accounts"])
def list_roles(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.view")
    items = db.list_roles()
    return {"items": items}


@app.post("/api/roles", response_model=CreateRoleResponse, tags=["Accounts"])
def create_role(request: Request, payload: CreateRoleRequest) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "roles.manage")
    try:
        return db.create_role(payload.model_dump(mode="json"), actor_account_id=account["account_id"])
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.patch("/api/roles/{role_id}", response_model=RoleOut, tags=["Accounts"])
def update_role(request: Request, role_id: str, payload: UpdateRoleRequest) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "roles.manage")
    try:
        return db.update_role(role_id, payload.model_dump(mode="json"), actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.delete("/api/roles/{role_id}", tags=["Accounts"])
def delete_role(request: Request, role_id: str) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "roles.manage")
    try:
        db.delete_role(role_id, actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    return {"ok": True}


@app.get("/api/permissions", response_model=ListPermissionsResponse, tags=["Accounts"])
def list_permissions(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "accounts.view")
    items = db.list_permissions()
    return {"items": items}


@app.get("/api/roles/permissions", response_model=RolePermissionsMappingResponse, tags=["Accounts"])
def list_role_permissions(request: Request) -> dict[str, Any]:
    account = _require_account(request)
    permissions = db.list_account_permissions(account["account_id"])
    if "roles.manage" not in permissions and "roles.assign" not in permissions:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message="权限不足").model_dump(),
        )
    mapping = db.list_role_permissions()
    return {"mapping": mapping}


@app.put("/api/roles/{role_id}/permissions", response_model=RolePermissionsResponse, tags=["Accounts"])
def update_role_permissions(
    request: Request, role_id: str, payload: UpdateRolePermissionsRequest
) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "roles.manage")
    try:
        return db.update_role_permissions(
            role_id=role_id,
            permission_ids=payload.permission_ids,
            actor_account_id=account["account_id"],
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/audit-logs", response_model=ListAuditLogsResponse, tags=["Accounts"])
def list_audit_logs(request: Request, limit: int = Query(default=200, ge=1, le=500)) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "audit.view")
    items = db.list_audit_logs(limit=limit)
    return {"items": items, "total": len(items)}


@app.get("/api/diagnostic-logs", response_model=ListDiagnosticLogsResponse, tags=["Accounts"])
def list_diagnostic_logs(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    source: str | None = Query(default=None),
    category: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "audit.view")
    items = db.list_diagnostic_logs(
        limit=limit,
        source=source,
        category=category,
        trace_id=trace_id,
    )
    return {"items": items, "total": len(items)}


@app.post("/api/diagnostic-logs", response_model=DiagnosticLogOut, status_code=201, tags=["Accounts"])
def create_diagnostic_log(payload: CreateDiagnosticLogRequest, request: Request) -> dict[str, Any]:
    account = _require_account(request, allow_password_change=True)
    return db.record_diagnostic_log(
        actor_account_id=account["account_id"],
        source=payload.source,
        category=payload.category,
        event=payload.event,
        level=payload.level,
        trace_id=payload.trace_id,
        request_path=payload.request_path,
        detail=payload.detail,
    )


# ──────────────────────────────────────────────
# @tier:ee — System Settings & Gateway（不进公开版）
# ──────────────────────────────────────────────
@app.get("/api/system-settings", response_model=SystemSettingsOut, tags=["System"])
def get_system_settings() -> dict[str, Any]:
    return db.get_system_settings()


@app.put("/api/system-settings/currency", response_model=SystemSettingsOut, tags=["System"])
def update_system_currency(payload: UpdateSystemCurrencyRequest) -> dict[str, Any]:
    try:
        return db.update_system_currency(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/system-settings/exchange-rate/refresh", response_model=SystemSettingsOut, tags=["System"])
def refresh_system_exchange_rate() -> dict[str, Any]:
    return db.refresh_exchange_rate_if_due(force=True)


@app.put("/api/system-settings/status-aliases", response_model=SystemSettingsOut, tags=["System"])
def update_system_status_aliases(payload: UpdateSystemStatusAliasesRequest) -> dict[str, Any]:
    return db.update_system_status_aliases(payload.model_dump(mode="json", exclude_unset=True))


@app.get("/api/system-settings/gateway", response_model=GatewaySettingsOut, tags=["System"])
def get_gateway_settings() -> dict[str, Any]:
    return db.get_gateway_settings()


@app.put("/api/system-settings/gateway", response_model=GatewaySettingsOut, tags=["System"])
def update_gateway_settings(payload: UpdateGatewaySettingsRequest) -> dict[str, Any]:
    try:
        return db.update_gateway_settings(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/system-settings/gateway/apply", response_model=GatewayApplyResponse, tags=["System"])
def apply_gateway_settings() -> dict[str, Any]:
    try:
        return gateway_execution.start_gateway_apply()
    except gateway_execution.GatewayExecutionError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code=exc.code, message=exc.message, details=exc.details or None).model_dump(),
        ) from exc


@app.get("/api/system-settings/gateway/jobs/{job_id}", response_model=GatewayJobStatusResponse, tags=["System"])
def get_gateway_apply_job(job_id: str) -> dict[str, Any]:
    try:
        return gateway_execution.get_gateway_apply_job(job_id)
    except gateway_execution.GatewayExecutionError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code=exc.code, message=exc.message, details=exc.details or None).model_dump(),
        ) from exc


# ──────────────────────────────────────────────
# @tier:ee — Lobster Toolkit（不进公开版）
# ──────────────────────────────────────────────
@app.get("/api/lobster-toolkit/sources", response_model=LobsterToolkitListResponseOut, tags=["Toolkit"])
def list_lobster_toolkit_sources(
    request: Request,
    tool_kind: str | None = Query(default=None),
    source_scope: str | None = Query(default=None),
    q: str | None = Query(default=None),
    auto_refresh: bool = Query(default=False),
) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.list_sources(
            tool_kind=tool_kind,
            source_scope=source_scope,
            query=q,
            auto_refresh=auto_refresh,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/lobster-toolkit/sources", response_model=LobsterToolkitSourceOut, tags=["Toolkit"])
def create_lobster_toolkit_source(
    request: Request,
    payload: LobsterToolkitSourceUpsertRequest,
) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.create_user_source(payload.model_dump(mode="json"))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.patch("/api/lobster-toolkit/sources/{source_id}", response_model=LobsterToolkitSourceOut, tags=["Toolkit"])
def update_lobster_toolkit_source(
    request: Request,
    source_id: str,
    payload: LobsterToolkitSourceUpsertRequest,
) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.update_user_source(source_id, payload.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.delete(
    "/api/lobster-toolkit/sources/{source_id}",
    response_model=LobsterToolkitDeleteSourceResponseOut,
    tags=["Toolkit"],
)
def delete_lobster_toolkit_source(request: Request, source_id: str) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.delete_user_source(source_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/lobster-toolkit/sources/refresh",
    response_model=LobsterToolkitSourceOut,
    tags=["Toolkit"],
)
def refresh_lobster_toolkit_source(
    request: Request,
    payload: LobsterToolkitDispatchRequest,
) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.refresh_source_state(payload.source_scope, payload.source_key)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/lobster-toolkit/search", response_model=LobsterToolkitSearchResponseOut, tags=["Toolkit"])
def search_lobster_toolkit_skills(
    request: Request,
    provider: str = Query(...),
    q: str = Query(...),
    limit: int = Query(default=12, ge=1, le=30),
) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.search_skill_sources(provider, q, limit)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(code="upstream_error", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/lobster-toolkit/dispatch", response_model=LobsterToolkitDispatchResponseOut, tags=["Toolkit"])
def dispatch_lobster_toolkit_source(
    request: Request,
    payload: LobsterToolkitDispatchRequest,
) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.dispatch_source(payload.source_scope, payload.source_key, payload.targets)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/lobster-toolkit/update", response_model=LobsterToolkitDispatchResponseOut, tags=["Toolkit"])
def update_lobster_toolkit_source_deployments(
    request: Request,
    payload: LobsterToolkitUpdateRequest,
) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.update_source_deployments(
            payload.source_scope,
            payload.source_key,
            deployment_ids=payload.deployment_ids,
            targets=payload.targets,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.delete(
    "/api/lobster-toolkit/deployments/{deployment_id}",
    response_model=LobsterToolkitDeleteDeploymentResponseOut,
    tags=["Toolkit"],
)
def delete_lobster_toolkit_deployment(
    request: Request,
    deployment_id: str,
) -> dict[str, Any]:
    _require_account(request)
    try:
        return lobster_toolkit.delete_deployment(deployment_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


# ──────────────────────────────────────────────
# @tier:ee — Nodes（不进公开版）
# ──────────────────────────────────────────────
@app.get("/api/nodes", response_model=ListNodesResponse, tags=["Nodes"])
def get_nodes() -> dict[str, Any]:
    return db.list_nodes()


@app.post("/api/nodes", response_model=NodeBootstrapResponse, status_code=201, tags=["Nodes"])
def create_node(payload: CreateNodeRequest) -> dict[str, Any]:
    try:
        return db.create_node(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/nodes/{node_id}/token", response_model=NodeBootstrapResponse, tags=["Nodes"])
def rotate_node_token(node_id: str) -> dict[str, Any]:
    try:
        return db.rotate_node_token(node_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/nodes/heartbeat", response_model=NodeHeartbeatResponse, tags=["Nodes"])
def record_node_heartbeat(payload: NodeHeartbeatRequest) -> dict[str, Any]:
    try:
        return db.record_node_heartbeat(payload.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/nodes/sync-results", response_model=NodeSyncResultsResponse, tags=["Nodes"])
def record_node_sync_results(payload: NodeSyncResultsRequest) -> dict[str, Any]:
    try:
        return db.record_node_sync_results(payload.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/nodes/bootstrap.sh", response_class=PlainTextResponse, include_in_schema=False, tags=["Nodes"])
def get_node_bootstrap_script(
    node_id: str = Query(..., min_length=1, max_length=64),
    token: str = Query(..., min_length=1, max_length=256),
) -> PlainTextResponse:
    try:
        script = db.build_node_bootstrap_script(node_id=node_id, raw_token=token)
        return PlainTextResponse(script, media_type="text/x-shellscript; charset=utf-8")
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/openclaw/explorer",
    response_model=OpenClawRootDirectoryOut,
    tags=["OpenClaw"],
)
def get_openclaw_root_directory(
    path: str | None = Query(default=None, max_length=1000),
) -> dict[str, Any]:
    try:
        return db.list_openclaw_root_entries(relative_path=path)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/openclaw/explorer/file",
    response_model=OpenClawRootFileOut,
    tags=["OpenClaw"],
)
def get_openclaw_root_file(
    path: str = Query(..., min_length=1, max_length=1000),
) -> dict[str, Any]:
    try:
        return db.read_openclaw_root_file(relative_path=path)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/openclaw/explorer/asset",
    tags=["OpenClaw"],
)
def get_openclaw_root_asset(
    path: str = Query(..., min_length=1, max_length=1000),
    variant: str = Query(default="raw", pattern="^(raw|pdf)$"),
) -> FileResponse:
    try:
        asset_path, media_type, file_name = db.resolve_openclaw_root_asset(
            relative_path=path,
            variant=variant,
        )
        return FileResponse(
            str(asset_path),
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{file_name}"'},
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="service_unavailable", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


# ──────────────────────────────────────────────
# @tier:ee — Agent 高级工作区 / 技能 / 导出（不进公开版）
# ──────────────────────────────────────────────
@app.get(
    "/api/agents/{agent_id}/workspace",
    response_model=AgentWorkspaceDirectoryOut,
    tags=["Agents"],
)
def get_agent_workspace_directory(
    agent_id: str,
    path: str | None = Query(default=None, max_length=1000),
) -> dict[str, Any]:
    try:
        return db.list_agent_workspace_entries(agent_id=agent_id, relative_path=path)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/workspace/file",
    response_model=AgentWorkspaceFileOut,
    tags=["Agents"],
)
def get_agent_workspace_file(
    agent_id: str,
    path: str = Query(..., min_length=1, max_length=1000),
) -> dict[str, Any]:
    try:
        return db.read_agent_workspace_file(agent_id=agent_id, relative_path=path)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/workspace/asset",
    tags=["Agents"],
)
def get_agent_workspace_asset(
    agent_id: str,
    path: str = Query(..., min_length=1, max_length=1000),
    variant: str = Query(default="raw", pattern="^(raw|pdf)$"),
) -> FileResponse:
    try:
        asset_path, media_type, file_name = db.resolve_agent_workspace_asset(
            agent_id=agent_id,
            relative_path=path,
            variant=variant,
        )
        return FileResponse(
            str(asset_path),
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{file_name}"'},
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="service_unavailable", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.put(
    "/api/agents/{agent_id}/workspace/file",
    response_model=AgentWorkspaceFileOut,
    tags=["Agents"],
)
def update_agent_workspace_file(agent_id: str, payload: UpdateWorkspaceFileRequest) -> dict[str, Any]:
    try:
        return db.update_agent_workspace_file(
            agent_id=agent_id,
            relative_path=payload.path,
            content=payload.content,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/workspace/file",
    response_model=AgentWorkspaceFileOut,
    tags=["Agents"],
)
def create_agent_workspace_file(agent_id: str, payload: CreateWorkspaceFileRequest) -> dict[str, Any]:
    try:
        return db.create_agent_workspace_file(
            agent_id=agent_id,
            relative_path=payload.path,
            content=payload.content,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/profile/generate",
    response_model=GenerateAgentProfileResponse,
    tags=["Agents"],
)
def generate_agent_profile(agent_id: str, payload: GenerateAgentProfileRequest, request: Request) -> dict[str, Any]:
    _require_account(request)
    try:
        return db.generate_agent_profile(
            agent_id,
            executor_agent_id=payload.executor_agent_id,
            agent_name=payload.agent_name,
            role_summary=payload.role_summary,
            core_work=payload.core_work,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(code="generation_failed", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/skills/import-zip",
    response_model=AgentSkillImportResultOut,
    tags=["Agents"],
)
async def import_agent_skill_zip(
    agent_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        file_name = file.filename or "skill.zip"
        file_bytes = await file.read()
        return db.import_agent_skill_zip(
            agent_id=agent_id,
            file_name=file_name,
            file_bytes=file_bytes,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(code="upstream_error", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/skills/import-github",
    response_model=AgentSkillImportResultOut,
    tags=["Agents"],
)
def import_agent_skill_github(
    agent_id: str,
    payload: ImportGithubSkillRequest,
) -> dict[str, Any]:
    try:
        return db.import_agent_skill_from_github(
            agent_id=agent_id,
            source_url=payload.url,
            target_name=payload.target_name,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(code="upstream_error", message=str(exc)).model_dump(),
        ) from exc


@app.delete(
    "/api/agents/{agent_id}",
    response_model=AgentRemoveResultOut,
    tags=["Agents"],
)
def remove_agent(request: Request, agent_id: str) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    try:
        return db.remove_agent(agent_id, actor_account_id=account["account_id"])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.delete(
    "/api/agents/{agent_id}/skills/{skill_name}",
    response_model=AgentSkillDeleteResultOut,
    tags=["Agents"],
)
def delete_agent_skill(
    agent_id: str,
    skill_name: str,
) -> dict[str, Any]:
    try:
        return db.delete_agent_skill(
            agent_id=agent_id,
            skill_name=skill_name,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/export-package/preview",
    response_model=AgentPortablePackagePreviewOut,
    tags=["Agents"],
)
def get_agent_export_package_preview(agent_id: str) -> dict[str, Any]:
    try:
        return db.preview_agent_portable_package(agent_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="service_unavailable", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/export-package",
    tags=["Agents"],
)
def export_agent_package(agent_id: str) -> StreamingResponse:
    try:
        file_name, archive_bytes = db.build_agent_portable_package_zip(agent_id)
        return StreamingResponse(
            iter([archive_bytes]),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="service_unavailable", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/activity-log",
    response_model=AgentActivityLogOut,
    tags=["Agents"],
)
def get_agent_activity_log(
    agent_id: str,
    limit: int = Query(default=80, ge=1, le=200),
) -> dict[str, Any]:
    try:
        return db.get_agent_activity_logs(agent_id=agent_id, limit=limit)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/scheduled-jobs",
    response_model=AgentScheduledJobsResponse,
    tags=["Agents"],
)
def get_agent_scheduled_jobs(agent_id: str) -> dict[str, Any]:
    try:
        return db.list_agent_scheduled_jobs(agent_id=agent_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="service_unavailable", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/scheduled-jobs/timeline",
    response_model=ScheduledJobsTimelineResponseOut,
    tags=["Agents"],
)
def get_scheduled_jobs_timeline(
    from_at: str | None = Query(default=None, max_length=64),
    to_at: str | None = Query(default=None, max_length=64),
    agent_ids: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return db.get_scheduled_jobs_timeline(from_at=from_at, to_at=to_at, agent_ids=agent_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="service_unavailable", message=str(exc)).model_dump(),
        ) from exc


@app.put(
    "/api/agents/{agent_id}/scheduled-jobs/{job_id}",
    response_model=AgentScheduledJobOut,
    tags=["Agents"],
)
def update_agent_scheduled_job(
    agent_id: str,
    job_id: str,
    payload: UpdateAgentScheduledJobRequest,
) -> dict[str, Any]:
    try:
        return db.update_agent_scheduled_job(
            agent_id=agent_id,
            job_id=job_id,
            payload=payload.model_dump(mode="json", exclude_unset=True),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="service_unavailable", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/scheduled-jobs",
    response_model=AgentScheduledJobOut,
    tags=["Agents"],
)
def create_agent_scheduled_job(
    agent_id: str,
    payload: CreateAgentScheduledJobRequest,
) -> dict[str, Any]:
    try:
        return db.create_agent_scheduled_job(
            agent_id=agent_id,
            payload=payload.model_dump(mode="json"),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="service_unavailable", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/workspace/send-instruction",
    response_model=SendWorkspaceInstructionResponse,
    tags=["Agents"],
)
def send_workspace_instruction(
    agent_id: str,
    payload: SendWorkspaceInstructionRequest,
) -> dict[str, Any]:
    try:
        return db.send_workspace_instruction_to_agent(
            source_agent_id=agent_id,
            relative_path=payload.path,
            target_agent_id=payload.target_agent_id,
            instruction=payload.instruction,
            sender_agent_id=payload.sender_agent_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(code="upstream_error", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/user-auth/state",
    response_model=AgentUserAuthStateOut,
    tags=["Agents"],
)
def get_agent_user_auth_state(agent_id: str) -> dict[str, Any]:
    try:
        return db.get_agent_user_auth_state(agent_id=agent_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/user-auth/start",
    response_model=StartAgentUserAuthResponse,
    tags=["Agents"],
)
def start_agent_user_auth(agent_id: str) -> dict[str, Any]:
    try:
        return db.start_agent_user_auth(agent_id=agent_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(code="upstream_error", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/user-auth/callback",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def complete_agent_user_auth_callback(
    agent_id: str,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> HTMLResponse:
    title = "HR 用户授权"
    if error:
        detail = error_description or error
        return HTMLResponse(
            f"""
            <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:32px;">
            <h1>{title}失败</h1>
            <p>飞书返回错误：{detail}</p>
            <p>可以关闭此页，回到工区重新发起授权。</p>
            </body></html>
            """,
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            f"""
            <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:32px;">
            <h1>{title}失败</h1>
            <p>缺少 code 或 state，无法完成授权。</p>
            </body></html>
            """,
            status_code=400,
        )
    try:
        auth_state = db.complete_agent_user_auth(agent_id=agent_id, code=code, state=state)
    except LookupError as exc:
        return HTMLResponse(
            f"""
            <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:32px;">
            <h1>{title}失败</h1>
            <p>{str(exc)}</p>
            </body></html>
            """,
            status_code=404,
        )
    except (ValueError, RuntimeError) as exc:
        return HTMLResponse(
            f"""
            <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:32px;">
            <h1>{title}失败</h1>
            <p>{str(exc)}</p>
            <p>可以关闭此页，回到工区重试。</p>
            </body></html>
            """,
            status_code=400,
        )

    user_label = auth_state.get("user_label") or "当前用户"
    return HTMLResponse(
        f"""
        <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:32px;">
        <h1>{title}已完成</h1>
        <p>已连接用户：{user_label}</p>
        <p>现在可以关闭此页，回到 Agent 工区继续给 {auth_state.get("agent_name") or agent_id} 发送文件和指令。</p>
        <script>
        if (window.opener) {{
          try {{
            window.opener.postMessage({{"type":"openclaw-feishu-user-auth-complete","agentId":"{agent_id}"}}, "*");
          }} catch (e) {{}}
        }}
        </script>
        </body></html>
        """
    )


@app.post(
    "/api/agents/{agent_id}/scenes/generate",
    response_model=AgentSceneJobOut,
    status_code=202,
    tags=["Agents"],
)
def generate_agent_scenes(agent_id: str, payload: AgentSceneGenerateRequest) -> dict[str, Any]:
    try:
        return scene_jobs.start_scene_job(agent_id=agent_id, force=payload.force)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except scene_jobs.SceneJobDependencyError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(code="scene_generator_dependency_missing", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/scenes/job-latest",
    response_model=AgentSceneJobOut,
    tags=["Agents"],
)
def get_latest_agent_scene_job(agent_id: str) -> dict[str, Any]:
    try:
        return scene_jobs.get_latest_scene_job(agent_id=agent_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/scenes/jobs/{job_id}",
    response_model=AgentSceneJobOut,
    tags=["Agents"],
)
def get_agent_scene_job(agent_id: str, job_id: str) -> dict[str, Any]:
    try:
        return scene_jobs.get_scene_job(agent_id=agent_id, job_id=job_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/agents/{agent_id}/scenes/{scene_key}.mp4", include_in_schema=False, tags=["Agents"])
def get_agent_scene_mp4(agent_id: str, scene_key: str) -> FileResponse:
    if scene_key not in {"working", "idle", "offline", "crashed"}:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message="scene_not_found").model_dump(),
        )
    file_path = scene_jobs.scene_mp4_path(agent_id=agent_id, scene_key=scene_key)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message="scene_not_found").model_dump(),
        )
    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


# ──────────────────────────────────────────────
# @tier:core — Tasks
# ──────────────────────────────────────────────
@app.get("/api/tasks", response_model=ListTasksResponse, tags=["Tasks"])
def list_tasks(
    status: str | None = Query(default=None),
    assignee_agent_id: str | None = Query(default=None, min_length=1, max_length=64),
    creator_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    items, total = db.list_tasks(
        status=status,
        assignee_agent_id=assignee_agent_id,
        creator_type=creator_type,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/api/tasks", response_model=TaskOut, status_code=201, tags=["Tasks"])
def create_task(payload: CreateTaskRequest) -> dict[str, Any]:
    try:
        return db.create_task(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/tasks/{task_id}", response_model=TaskDetailResponse, tags=["Tasks"])
def get_task(task_id: str) -> dict[str, Any]:
    task, events = db.get_task_with_events(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message="task_not_found").model_dump(),
        )
    return {"task": task, "events": events}


@app.post("/api/tasks/{task_id}/dispatch", response_model=DispatchTaskResponse, tags=["Tasks"])
def dispatch_task(task_id: str, payload: DispatchTaskRequest) -> dict[str, Any]:
    try:
        return db.dispatch_task(
            task_id=task_id,
            actor_id="ops-backend",
            mode=payload.mode,
            session_hint=payload.session_hint,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/tasks/{task_id}/submit", response_model=TaskOut, tags=["Tasks"])
def submit_task(task_id: str, payload: SubmitTaskRequest) -> dict[str, Any]:
    try:
        return db.submit_task(
            task_id=task_id,
            actor_agent_id=payload.actor_agent_id,
            summary=payload.summary,
            evidence_links=payload.evidence_links,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/tasks/{task_id}/review", response_model=ReviewTaskResponse, tags=["Tasks"])
def review_task(task_id: str, payload: ReviewTaskRequest) -> dict[str, Any]:
    try:
        return db.review_task(task_id=task_id, payload=payload.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/onboarding/confirm", response_model=OnboardingConfirmResponse, tags=["Onboarding"])
def confirm_onboarding(payload: OnboardingConfirmRequest) -> dict[str, Any]:
    try:
        return db.confirm_onboarding(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agent-configs/multi-agent/bootstrap",
    response_model=MultiAgentOnboardingBootstrapResponse,
    tags=["Agent Config"],
)
def get_multi_agent_onboarding_bootstrap() -> dict[str, Any]:
    return db.get_multi_agent_onboarding_bootstrap()


@app.post(
    "/api/agent-configs/multi-agent/dry-run",
    response_model=MultiAgentOnboardingDryRunResponse,
    tags=["Agent Config"],
)
def dry_run_multi_agent_onboarding(payload: MultiAgentOnboardingRequest) -> dict[str, Any]:
    try:
        return db.dry_run_multi_agent_onboarding(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agent-configs/multi-agent/start",
    response_model=MultiAgentOnboardingRunResponse,
    tags=["Agent Config"],
)
def start_multi_agent_onboarding(payload: MultiAgentOnboardingRequest) -> dict[str, Any]:
    try:
        return db.start_multi_agent_onboarding(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc


@app.post(
    "/api/agent-configs/multi-agent/{run_id}/resume",
    response_model=MultiAgentOnboardingRunResponse,
    tags=["Agent Config"],
)
def resume_multi_agent_onboarding(run_id: str) -> dict[str, Any]:
    try:
        return db.resume_multi_agent_onboarding(run_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get(
    "/api/agent-configs/multi-agent/runs",
    response_model=MultiAgentOnboardingRunsResponse,
    tags=["Agent Config"],
)
def list_multi_agent_onboarding_runs(include_completed: bool = Query(default=False)) -> dict[str, Any]:
    items = db.list_multi_agent_onboarding_runs(include_completed=include_completed)
    return {"items": items, "total": len(items)}


@app.post("/api/feishu/auto-create", response_model=FeishuAppAutoCreateResponse, tags=["Feishu"])
def auto_create_feishu_app(payload: FeishuAppAutoCreateRequest, request: Request) -> dict[str, Any]:
    account = _require_account(request)
    _require_permission(account, "agents.manage")
    return db.run_feishu_app_ui_automation(payload.model_dump(mode="json"))


# ──────────────────────────────────────────────
# @tier:core — Training / Leaderboard
# ──────────────────────────────────────────────
@app.get("/api/training/module", response_model=TrainingModuleOverviewOut, tags=["Training"])
def get_training_module_overview() -> dict[str, Any]:
    return db.get_training_module_overview()


@app.post("/api/training/module/configure", response_model=TrainingModuleConfigureResponse, tags=["Training"])
def configure_training_module(payload: ConfigureTrainingModuleRequest) -> dict[str, Any]:
    try:
        return db.configure_training_module(payload.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/training/agents/{agent_id}", response_model=TrainingAgentDetailOut, tags=["Training"])
def get_training_agent_detail(agent_id: str) -> dict[str, Any]:
    try:
        return db.get_training_agent_detail(agent_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/training/agents/{agent_id}/documents/{kind}", response_model=TrainingDocumentOut, tags=["Training"])
def get_training_document(agent_id: str, kind: str, run_id: str | None = Query(default=None, max_length=64)) -> dict[str, Any]:
    try:
        if kind == "run" and not run_id:
            raise ValueError("training_run_id_required")
        return db.get_training_document(agent_id=agent_id, kind=kind, run_id=run_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.put("/api/training/agents/{agent_id}/documents/{kind}", response_model=TrainingDocumentOut, tags=["Training"])
def update_training_document(
    agent_id: str,
    kind: str,
    payload: UpdateTrainingDocumentRequest,
    run_id: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    try:
        if kind == "run" and not run_id:
            raise ValueError("training_run_id_required")
        return db.save_training_document(agent_id=agent_id, kind=kind, run_id=run_id, content=payload.content)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(code="forbidden", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/training/agents/{agent_id}/runs/start", response_model=TrainingRunOut, tags=["Training"])
def start_training_run(agent_id: str, payload: StartTrainingRunRequest) -> dict[str, Any]:
    try:
        return db.start_training_run(agent_id=agent_id, payload=payload.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.get("/api/training/runs", response_model=ListTrainingRunsResponse, tags=["Training"])
def list_training_runs(agent_id: str | None = Query(default=None, min_length=1, max_length=64)) -> dict[str, Any]:
    items = db.list_training_runs(agent_id=agent_id)
    return {"items": items, "total": len(items)}


@app.post("/api/training/runs", response_model=TrainingRunOut, status_code=201, tags=["Training"])
def create_training_run(payload: CreateTrainingRunRequest) -> dict[str, Any]:
    try:
        return db.create_training_run(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


@app.post("/api/training/runs/{run_id}/gate", response_model=TrainingRunOut, tags=["Training"])
def gate_training_run(run_id: str, payload: GateTrainingRunRequest) -> dict[str, Any]:
    try:
        return db.gate_training_run(run_id=run_id, payload=payload.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(code="not_found", message=str(exc)).model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(code="conflict", message=str(exc)).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


# @tier:core
@app.get("/api/leaderboard", response_model=LeaderboardResponse, tags=["Leaderboard"])
def get_leaderboard(period: str = Query(default="all")) -> dict[str, Any]:
    try:
        return db.get_leaderboard(period)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(code="bad_request", message=str(exc)).model_dump(),
        ) from exc


