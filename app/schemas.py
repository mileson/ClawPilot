# Copyright (c) 2026 ClawPilot Contributors. All rights reserved.
# Licensed under the Business Source License 1.1 — see LICENSE file.
# NOTICE: Reverse engineering, decompilation, or disassembly is prohibited.

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


TaskStatus = Literal["todo", "doing", "review", "done", "rejected"]
CreatorType = Literal["human", "agent"]
SceneJobStatus = Literal["queued", "running", "completed", "failed"]
SceneStepStatus = Literal["pending", "running", "completed", "failed"]
NodeStatus = Literal["pending", "online", "offline"]
NodeType = Literal["vps", "linux", "macos"]
AgentRuntimeStatus = Literal["working", "idle", "offline", "crashed"]
CurrencyPreference = Literal["CNY", "USD"]
AgentChannelStatus = Literal["missing", "configured", "warning"]
AgentChannelBindingStatus = Literal["configured", "warning"]
LobsterToolkitToolKind = Literal["skill", "cli"]
LobsterToolkitDeliveryKind = Literal["skill", "openclaw_extension", "standalone_cli"]
LobsterToolkitSourceScope = Literal["system", "user"]
LobsterToolkitTargetScope = Literal["shared", "agent"]
LobsterToolkitProvider = Literal["manual", "github", "clawhub", "skills_sh"]
LobsterToolkitCheckStatus = Literal["idle", "ready", "update_available", "failed"]
LobsterToolkitCognitionStatus = Literal["not_applicable", "pending", "synced", "failed"]


class AgentChannelBindingOut(BaseModel):
    channel: str
    account_id: str | None = None
    primary: bool = False
    status: AgentChannelBindingStatus = "configured"
    reason: str | None = None


class AgentOut(BaseModel):
    agent_id: str
    display_name: str
    role: str
    status: Literal["active", "probation", "suspended"]
    channel: str
    primary_channel: str | None = None
    connected_channels: list[AgentChannelBindingOut] = Field(default_factory=list)
    channel_status: AgentChannelStatus = "missing"
    channel_status_reason: str | None = None
    account_id: str
    open_id: str | None = None
    workspace_path: str | None = None
    identity_complete: bool
    role_summary: str | None = None
    core_work: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    delegate_when: list[str] = Field(default_factory=list)
    do_not_delegate_when: list[str] = Field(default_factory=list)
    priority: int | None = None
    enabled: bool | None = None
    main_dispatch_allowed: bool | None = None
    last_known_active: str | None = None
    latest_activity_at: str | None = None
    runtime_status: AgentRuntimeStatus | None = None
    runtime_status_reason: str | None = None
    runtime_status_at: str | None = None
    runtime_signal_source: str | None = None
    runtime_node_status: NodeStatus | None = None
    runtime_crash_excerpt: str | None = None
    emoji: str | None = None
    avatar_hint: str | None = None
    avatar_url: str | None = None
    scene_preset_id: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    model_label: str | None = None
    config_model_provider: str | None = None
    config_model_id: str | None = None
    config_model_label: str | None = None
    recent_model_provider: str | None = None
    recent_model_id: str | None = None
    recent_model_label: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None
    usage_total_tokens: int | None = None
    usage_context_tokens: int | None = None
    estimated_cost_usd: float | None = None
    created_at: str


class ListAgentsResponse(BaseModel):
    items: list[AgentOut]
    total: int


FirstLobsterChannel = Literal["feishu", "telegram", "discord", "weixin"]
FirstLobsterWorkspaceSource = Literal["config", "fallback"]


class FirstLobsterFieldDefinitionOut(BaseModel):
    key: str
    label: str
    secret: bool = False
    placeholder: str | None = None
    description: str | None = None


class FirstLobsterChannelDefinitionOut(BaseModel):
    channel: FirstLobsterChannel
    label: str
    description: str | None = None
    default_account_id: str
    fields: list[FirstLobsterFieldDefinitionOut] = Field(default_factory=list)


class FirstLobsterWorkspacePreviewOut(BaseModel):
    path: str
    source: FirstLobsterWorkspaceSource
    available: bool
    error: str | None = None


class FirstLobsterBootstrapFileOut(BaseModel):
    path: str
    exists: bool
    size: int | None = None
    modified_at: str | None = None
    preview: str | None = None
    preview_truncated: bool = False
    error: str | None = None


class FirstLobsterBootstrapPreviewResponse(BaseModel):
    workspace: FirstLobsterWorkspacePreviewOut
    recommended_agent_id: str
    recommended_agent_name: str
    recommended_app_name: str
    supported_channels: list[FirstLobsterChannelDefinitionOut] = Field(default_factory=list)
    files: list[FirstLobsterBootstrapFileOut] = Field(default_factory=list)


class FirstLobsterFeishuConfig(BaseModel):
    app_id: str = Field(min_length=1, max_length=128)
    app_secret: str = Field(min_length=1, max_length=256)


class FirstLobsterTelegramConfig(BaseModel):
    bot_token: str = Field(min_length=1, max_length=256)


class FirstLobsterDiscordConfig(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class FirstLobsterWeixinConfig(BaseModel):
    account_id: str = Field(min_length=1, max_length=256)


class ClaimFirstLobsterRequest(BaseModel):
    selected_channels: list[FirstLobsterChannel] = Field(default_factory=list)
    primary_channel: FirstLobsterChannel | None = None
    agent_name: str | None = Field(default=None, max_length=64)
    feishu: FirstLobsterFeishuConfig | None = None
    telegram: FirstLobsterTelegramConfig | None = None
    discord: FirstLobsterDiscordConfig | None = None
    weixin: FirstLobsterWeixinConfig | None = None

    @model_validator(mode="after")
    def validate_claim_payload(self) -> "ClaimFirstLobsterRequest":
        normalized: list[FirstLobsterChannel] = []
        for channel in self.selected_channels:
            if channel not in normalized:
                normalized.append(channel)
        if not normalized:
            raise ValueError("first_lobster_channel_required")

        self.selected_channels = normalized
        if self.primary_channel is None and len(normalized) == 1:
            self.primary_channel = normalized[0]
        if self.primary_channel is None:
            raise ValueError("first_lobster_primary_channel_required")
        if self.primary_channel not in normalized:
            raise ValueError("first_lobster_primary_channel_invalid")
        if "feishu" in normalized and self.feishu is None:
            raise ValueError("first_lobster_feishu_credentials_required")
        if "telegram" in normalized and self.telegram is None:
            raise ValueError("first_lobster_telegram_credentials_required")
        if "discord" in normalized and self.discord is None:
            raise ValueError("first_lobster_discord_credentials_required")
        if "weixin" in normalized and self.weixin is None:
            raise ValueError("first_lobster_weixin_credentials_required")
        return self


class ClaimFirstLobsterResponse(BaseModel):
    status: Literal["claimed"]
    selected_channels: list[FirstLobsterChannel]
    primary_channel: FirstLobsterChannel
    config_path: str
    backup_path: str | None = None
    agent: AgentOut


class BasicAgentCreateRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    agent_name: str = Field(min_length=1, max_length=64)
    role_summary: str = Field(min_length=1, max_length=500)
    core_work: list[str] = Field(default_factory=list, max_length=8)


class BasicAgentCreateResponse(BaseModel):
    status: Literal["created"]
    agent: AgentOut
    warnings: list[str] = Field(default_factory=list)


class ConnectAgentFeishuChannelRequest(BaseModel):
    app_id: str = Field(min_length=1, max_length=128)
    app_secret: str = Field(min_length=1, max_length=256)
    operator_open_id: str | None = Field(default=None, max_length=128)
    identity_key: str | None = Field(default=None, max_length=128)


class ConnectAgentFeishuChannelResponse(BaseModel):
    status: Literal["connected"]
    channel: Literal["feishu"] = "feishu"
    agent: AgentOut
    warnings: list[str] = Field(default_factory=list)


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    creator_type: CreatorType
    creator_id: str = Field(min_length=1, max_length=128)
    assignee_agent_id: str = Field(min_length=1, max_length=64)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    expected_output: str = Field(min_length=1, max_length=2000)
    acceptance_criteria: str = Field(min_length=1, max_length=3000)
    deadline_at: datetime | None = None


class TaskOut(BaseModel):
    task_id: str
    title: str
    description: str | None = None
    creator_type: CreatorType
    creator_id: str
    assignee_agent_id: str
    status: TaskStatus
    priority: Literal["low", "medium", "high", "urgent"]
    expected_output: str
    acceptance_criteria: str
    deadline_at: str | None = None
    created_at: str
    updated_at: str


class ListTasksResponse(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int


class TaskEventOut(BaseModel):
    id: int
    task_id: str
    event_type: str
    actor_type: str
    actor_id: str
    payload: dict[str, Any]
    created_at: str


class TaskDetailResponse(BaseModel):
    task: TaskOut
    events: list[TaskEventOut]


class DispatchTaskRequest(BaseModel):
    mode: Literal["send", "spawn"]
    session_hint: str | None = None


class DispatchTaskResponse(BaseModel):
    task_id: str
    mode: Literal["send", "spawn"]
    session_id: str | None = None
    dispatched_at: str


class SubmitTaskRequest(BaseModel):
    actor_agent_id: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=3000)
    evidence_links: list[str] | None = None


class TaskReceipt(BaseModel):
    recipient_type: Literal["human", "agent"]
    recipient_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    include_creator_agent_id: bool = False


class ReviewTaskRequest(BaseModel):
    reviewer_id: str = Field(min_length=1)
    decision: Literal["approved", "rejected"]
    review_comment: str | None = Field(default=None, max_length=3000)
    score_delta: int = Field(default=0, ge=-100, le=100)
    receipt: TaskReceipt | None = None

    @model_validator(mode="after")
    def validate_receipt_for_approved(self) -> "ReviewTaskRequest":
        if self.decision == "approved" and self.receipt is None:
            raise ValueError("approved decision requires receipt")
        return self


class ReviewTaskResponse(BaseModel):
    task: TaskOut
    score_ledger_written: bool
    receipt_sent: bool


class LeaderboardEntry(BaseModel):
    rank: int
    agent_id: str
    display_name: str
    points: int
    role: str | None = None
    role_summary: str | None = None
    channel: str | None = None
    avatar_url: str | None = None
    avatar_hint: str | None = None


class LeaderboardResponse(BaseModel):
    period: Literal["all", "weekly", "monthly"]
    items: list[LeaderboardEntry]
    generated_at: str


class OnboardingConfirmRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    agent_name: str = Field(min_length=1, max_length=128)
    role_summary: str = Field(min_length=1, max_length=500)
    creator_type: CreatorType
    creator_id: str = Field(min_length=1, max_length=128)
    trigger_training: bool = True
    observe_days: int = Field(default=14, ge=1, le=120)


class TrainingRunOut(BaseModel):
    run_id: str
    agent_id: str
    onboarding_job_id: str | None = None
    phase: Literal["exam", "observe", "gate"]
    status: Literal["planned", "running", "passed", "failed"]
    score: int | None = None
    result: Literal["GRADUATE", "REMEDIATE"] | None = None
    report_url: str | None = None
    observe_days: int | None = None
    coach_agent_id: str | None = None
    coach_agent_name: str | None = None
    orchestration_state: str | None = None
    orchestration_error: str | None = None
    observation_job_id: str | None = None
    run_doc_path: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


class OnboardingConfirmResponse(BaseModel):
    job_id: str
    agent_id: str
    status: Literal["confirmed"]
    trigger_training: bool
    created_at: str
    completed_at: str
    training_run: TrainingRunOut | None = None


OnboardingStepStatus = Literal["todo", "running", "done", "warn", "failed", "skipped"]
OnboardingRunStatus = Literal["draft", "running", "paused", "partial", "completed", "failed"]


class FeishuGroupOption(BaseModel):
    chat_id: str = Field(min_length=1, max_length=128)
    name: str | None = Field(default=None, max_length=200)
    require_mention: bool | None = None
    source: str | None = Field(default=None, max_length=64)


class OnboardingPersonaStrategy(BaseModel):
    mode: Literal["template_only", "agent_assisted"] = "template_only"
    writer_agent_id: str | None = Field(default=None, max_length=64)
    docs: list[str] = Field(default_factory=list)


class OnboardingFeishuConfig(BaseModel):
    app_id: str = Field(min_length=1, max_length=128)
    app_secret: str = Field(min_length=1, max_length=128)
    operator_open_id: str = Field(min_length=1, max_length=128)
    identity_key: str | None = Field(default=None, max_length=128)


class OnboardingGroupSelection(BaseModel):
    auto_join: bool = False
    items: list[FeishuGroupOption] = Field(default_factory=list)


class OnboardingExecutionOptions(BaseModel):
    run_doctor: bool = True
    run_probe: bool = True
    restart_gateway: bool = False


class MultiAgentOnboardingRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    agent_name: str = Field(min_length=1, max_length=128)
    role_summary: str = Field(min_length=1, max_length=500)
    core_work: list[str] = Field(default_factory=list)
    channel_type: Literal["feishu"] = "feishu"
    feishu: OnboardingFeishuConfig
    owner_agent_id: str = Field(min_length=1, max_length=64)
    persona_strategy: OnboardingPersonaStrategy = Field(default_factory=OnboardingPersonaStrategy)
    groups: OnboardingGroupSelection = Field(default_factory=OnboardingGroupSelection)
    execution: OnboardingExecutionOptions = Field(default_factory=OnboardingExecutionOptions)

    @model_validator(mode="after")
    def validate_persona_strategy(self) -> "MultiAgentOnboardingRequest":
        if self.persona_strategy.mode == "agent_assisted":
            if not self.persona_strategy.writer_agent_id:
                self.persona_strategy.writer_agent_id = self.owner_agent_id
        return self


class MultiAgentOnboardingStep(BaseModel):
    key: str
    label: str
    status: OnboardingStepStatus
    summary: str | None = None
    detail: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class MultiAgentOnboardingRunSummary(BaseModel):
    run_id: str
    owner_agent_id: str
    target_agent_id: str
    target_agent_name: str
    status: OnboardingRunStatus
    completed_step_count: int
    total_step_count: int
    pending_restart: bool
    warnings: list[str] = Field(default_factory=list)
    steps: list[MultiAgentOnboardingStep] = Field(default_factory=list)
    created_at: str
    updated_at: str


class MultiAgentOnboardingBootstrapResponse(BaseModel):
    agents: list[AgentOut]
    persona_writer_candidates: list[AgentOut]
    group_options: list[FeishuGroupOption]
    default_identity_key: str | None = None
    official_checklist: list[str]
    skill_checklist: list[str]
    in_progress_runs: list[MultiAgentOnboardingRunSummary]


class MultiAgentOnboardingDryRunResponse(BaseModel):
    steps: list[MultiAgentOnboardingStep]
    warnings: list[str]
    blockers: list[str]


class MultiAgentOnboardingRunResponse(BaseModel):
    run: MultiAgentOnboardingRunSummary
    steps: list[MultiAgentOnboardingStep]
    warnings: list[str]
    pending_restart: bool


class MultiAgentOnboardingRunsResponse(BaseModel):
    items: list[MultiAgentOnboardingRunSummary]
    total: int


class FeishuAppAutoCreateRequest(BaseModel):
    app_name: str | None = Field(default=None, max_length=64)
    app_description: str | None = Field(default=None, max_length=200)
    menu_name: str | None = Field(default=None, max_length=64)
    automation_mode: Literal["auto", "cdp", "profile"] = "auto"
    cdp_url: str | None = Field(default=None, max_length=300)
    headless: bool = False
    timeout_sec: int = Field(default=180, ge=30, le=900)
    profile_dir: str | None = Field(default=None, max_length=300)


class FeishuAppAutoCreateResponse(BaseModel):
    status: Literal["success", "failed", "login_required", "dependency_missing"]
    step: str | None = None
    message: str | None = None
    app_id: str | None = None
    app_secret: str | None = None
    chat_url: str | None = None
    execution_mode: Literal["cdp", "profile"] | None = None
    debugger_url: str | None = None


class FirstLobsterAutoClaimRequest(BaseModel):
    app_name: str = Field(min_length=1, max_length=64)
    app_description: str | None = Field(default=None, max_length=200)
    menu_name: str | None = Field(default=None, max_length=64)
    timeout_sec: int = Field(default=600, ge=60, le=900)
    trace_id: str | None = Field(default=None, max_length=64)


class FirstLobsterAutoClaimRunOut(BaseModel):
    job_id: str
    status: Literal["queued", "waiting_login", "claiming", "completed", "failed"]
    current_stage: Literal["queued", "waiting_login", "claiming", "completed", "failed"]
    trace_id: str | None = None
    message: str | None = None
    error_message: str | None = None
    execution_mode: Literal["cdp", "profile"] | None = None
    debugger_url: str | None = None
    chat_url: str | None = None
    app_id: str | None = None
    agent_id: str | None = None
    selected_channels: list[FirstLobsterChannel] = Field(default_factory=list)
    primary_channel: FirstLobsterChannel | None = None
    config_path: str | None = None
    backup_path: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class FirstLobsterFeishuPairingConfirmRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    pairing_text: str = Field(min_length=1, max_length=4000)


class FirstLobsterFeishuPairingConfirmResponse(BaseModel):
    status: Literal["confirmed"]
    agent_id: str
    agent_name: str
    user_open_id: str
    pairing_code: str
    completed_at: str


class AgentFeishuPairingConfirmRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    pairing_text: str = Field(min_length=1, max_length=4000)


class AgentFeishuPairingConfirmResponse(BaseModel):
    status: Literal["confirmed"]
    agent_id: str
    agent_name: str
    user_open_id: str
    pairing_code: str
    completed_at: str


class CreateTrainingRunRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    onboarding_job_id: str | None = Field(default=None, max_length=64)
    phase: Literal["exam", "observe", "gate"] = "exam"
    status: Literal["planned", "running", "passed", "failed"] = "planned"
    observe_days: int | None = Field(default=None, ge=1, le=120)
    score: int | None = Field(default=None, ge=0, le=100)
    result: Literal["GRADUATE", "REMEDIATE"] | None = None
    report_url: str | None = Field(default=None, max_length=1000)


class ListTrainingRunsResponse(BaseModel):
    items: list[TrainingRunOut]
    total: int


class GateTrainingRunRequest(BaseModel):
    result: Literal["GRADUATE", "REMEDIATE"]
    score: int | None = Field(default=None, ge=0, le=100)
    report_url: str | None = Field(default=None, max_length=1000)


TrainingAgentState = Literal["not_enrolled", "pending_training", "training", "recently_trained"]
TrainingDocumentKind = Literal["status", "profile", "run"]


class TrainingModuleCoachOut(BaseModel):
    coach_agent_id: str
    coach_agent_name: str
    skill_name: str
    skill_source_path: str
    skill_target_path: str
    configured_at: str
    updated_at: str


class TrainingModuleCountsOut(BaseModel):
    total: int
    not_enrolled: int = 0
    pending_training: int = 0
    training: int = 0
    recently_trained: int = 0


class TrainingAgentSummaryOut(BaseModel):
    agent_id: str
    display_name: str
    role_summary: str | None = None
    avatar_url: str | None = None
    avatar_hint: str | None = None
    emoji: str | None = None
    training_state: TrainingAgentState
    training_state_label: str
    training_count: int = 0
    latest_completed_at: str | None = None
    active_run_id: str | None = None
    active_run_phase: str | None = None
    profile_exists: bool = False


class TrainingDocumentOut(BaseModel):
    agent_id: str
    agent_name: str
    kind: TrainingDocumentKind
    run_id: str | None = None
    title: str
    path: str
    display_path: str
    exists: bool
    editable: bool = True
    content: str
    modified_at: str | None = None


class TrainingAgentDetailOut(BaseModel):
    agent: TrainingAgentSummaryOut
    status_document: TrainingDocumentOut
    profile_document: TrainingDocumentOut
    runs: list[TrainingRunOut]


class TrainingModuleOverviewOut(BaseModel):
    initialized: bool
    needs_coach_setup: bool
    home_url: str = "/"
    has_openclaw_config: bool
    online_node_total: int
    node_total: int
    coach: TrainingModuleCoachOut | None = None
    counts: TrainingModuleCountsOut
    agents: list[TrainingAgentSummaryOut]


class ConfigureTrainingModuleRequest(BaseModel):
    coach_agent_id: str = Field(min_length=1, max_length=64)


class TrainingModuleConfigureResponse(BaseModel):
    configured: bool
    coach: TrainingModuleCoachOut


class UpdateTrainingDocumentRequest(BaseModel):
    content: str = Field(max_length=600000)


class StartTrainingRunRequest(BaseModel):
    observe_days: int = Field(default=14, ge=1, le=120)
    observe_every_hours: int = Field(default=6, ge=1, le=24)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class SetupStatusResponse(BaseModel):
    has_openclaw_config: bool
    node_total: int
    bootstrap_ready: bool
    bootstrap_reason: str | None = None
    bootstrap_mode: Literal["public", "local", "unavailable"] = "public"
    bootstrap_base: str | None = None
    bootstrap_prompt: str | None = None
    install_operation: str | None = None
    install_stage: str | None = None
    install_result: str | None = None
    install_updated_at: str | None = None
    local_web_url: str | None = None
    local_api_health_url: str | None = None
    local_web_ok: bool | None = None
    local_api_ok: bool | None = None
    public_url: str | None = None
    public_url_status: str | None = None
    public_url_reason: str | None = None
    public_url_provider: str | None = None
    public_url_enabled: bool = False
    openclaw_cli_installed: bool = False
    openclaw_cli_path: str | None = None
    openclaw_current_version: str | None = None
    openclaw_latest_version: str | None = None
    openclaw_update_available: bool = False


class ControlPlaneActionRequest(BaseModel):
    action: Literal["bootstrap", "repair_local", "repair_tunnel", "install_openclaw", "update_status", "update_install"]


class ControlPlaneActionResponse(BaseModel):
    job_id: str
    action: str
    status: Literal["accepted", "running", "completed", "failed"]
    accepted_at: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ControlPlaneJobStatusResponse(BaseModel):
    job_id: str
    kind: str
    status: Literal["accepted", "running", "completed", "failed"]
    accepted_at: str
    started_at: str | None = None
    first_progress_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class SystemSettingsOut(BaseModel):
    currency_preference: CurrencyPreference
    exchange_rate_usd_cny: float
    exchange_rate_source: str
    exchange_rate_updated_at: str | None = None
    exchange_rate_checked_at: str | None = None
    updated_at: str | None = None
    status_aliases: dict[str, str | None] = Field(default_factory=dict)
    gateway_settings: dict[str, Any] = Field(default_factory=dict)


class UpdateSystemCurrencyRequest(BaseModel):
    currency_preference: CurrencyPreference


class UpdateSystemStatusAliasesRequest(BaseModel):
    working: str | None = Field(default=None, max_length=40)
    idle: str | None = Field(default=None, max_length=40)
    offline: str | None = Field(default=None, max_length=40)
    crashed: str | None = Field(default=None, max_length=40)


class GatewaySettingsOut(BaseModel):
    mode_preference: Literal["auto", "existing-proxy", "caddy", "public-port"] = "auto"
    domain: str | None = None
    ssl_email: str | None = None
    public_host_ip: str | None = None
    public_web_port: int = 13000
    auto_https: bool = True
    status: Literal["idle", "saved", "error"] = "idle"
    access_url: str | None = None
    last_error: str | None = None
    verified_at: str | None = None
    updated_at: str | None = None


class UpdateGatewaySettingsRequest(BaseModel):
    mode_preference: Literal["auto", "existing-proxy", "caddy", "public-port"] = "auto"
    domain: str | None = Field(default=None, max_length=255)
    ssl_email: str | None = Field(default=None, max_length=255)
    public_host_ip: str | None = Field(default=None, max_length=255)
    public_web_port: int = Field(default=13000, ge=1, le=65535)
    auto_https: bool = True


class GatewayApplyResponse(BaseModel):
    job_id: str
    status: Literal["accepted", "running", "completed", "failed"]
    accepted_at: str
    detail: dict[str, Any] = Field(default_factory=dict)


class GatewayJobStatusResponse(BaseModel):
    job_id: str
    kind: str
    status: Literal["accepted", "running", "completed", "failed"]
    accepted_at: str
    started_at: str | None = None
    first_progress_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class LobsterToolkitDeploymentTargetRequest(BaseModel):
    target_scope: LobsterToolkitTargetScope
    target_agent_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_target(self) -> "LobsterToolkitDeploymentTargetRequest":
        if self.target_scope == "agent" and not str(self.target_agent_id or "").strip():
            raise ValueError("toolkit_target_agent_required")
        if self.target_scope == "shared":
            self.target_agent_id = None
        return self


class LobsterToolkitSourceUpsertRequest(BaseModel):
    tool_kind: LobsterToolkitToolKind
    delivery_kind: LobsterToolkitDeliveryKind
    provider: LobsterToolkitProvider = "manual"
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    brand: str | None = Field(default=None, max_length=80)
    brand_bg_color: str | None = Field(default=None, max_length=32)
    brand_text_color: str | None = Field(default=None, max_length=32)
    remote_url: str = Field(min_length=1, max_length=2000)
    ref: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=800)
    enabled: bool = True
    tutorial_metadata: dict[str, Any] = Field(default_factory=dict)


class LobsterToolkitDeploymentOut(BaseModel):
    id: str
    source_scope: LobsterToolkitSourceScope
    source_key: str
    tool_kind: LobsterToolkitToolKind
    delivery_kind: LobsterToolkitDeliveryKind
    target_scope: LobsterToolkitTargetScope
    target_agent_id: str | None = None
    install_root: str
    install_path: str
    installed_version: str | None = None
    installed_revision: str | None = None
    last_deployed_at: str
    cognition_status: LobsterToolkitCognitionStatus
    cognition_updated_at: str | None = None
    tutorial_skill_path: str | None = None


class LobsterToolkitSourceOut(BaseModel):
    source_scope: LobsterToolkitSourceScope
    source_key: str
    source_id: str | None = None
    tool_kind: LobsterToolkitToolKind
    delivery_kind: LobsterToolkitDeliveryKind
    provider: LobsterToolkitProvider
    name: str
    slug: str
    brand: str | None = None
    brand_bg_color: str | None = None
    brand_text_color: str | None = None
    description_i18n: dict[str, str] = Field(default_factory=dict)
    remote_url: str
    ref: str | None = None
    summary: str | None = None
    editable: bool = False
    enabled: bool = True
    latest_version: str | None = None
    latest_revision: str | None = None
    latest_revision_short: str | None = None
    latest_published_at: str | None = None
    last_checked_at: str | None = None
    check_status: LobsterToolkitCheckStatus
    last_error: str | None = None
    tutorial_metadata: dict[str, Any] = Field(default_factory=dict)
    deployments: list[LobsterToolkitDeploymentOut] = Field(default_factory=list)
    shared_targets_count: int = 0
    agent_targets_count: int = 0
    total_targets_count: int = 0


class LobsterToolkitListResponseOut(BaseModel):
    items: list[LobsterToolkitSourceOut]
    total: int


class LobsterToolkitSearchResultOut(BaseModel):
    provider: LobsterToolkitProvider
    title: str
    slug: str
    summary: str | None = None
    canonical_url: str
    remote_url: str
    ref: str | None = None
    delivery_kind: LobsterToolkitDeliveryKind
    validation_status: str


class LobsterToolkitSearchResponseOut(BaseModel):
    provider: LobsterToolkitProvider
    query: str
    items: list[LobsterToolkitSearchResultOut]


class LobsterToolkitDispatchRequest(BaseModel):
    source_scope: LobsterToolkitSourceScope
    source_key: str = Field(min_length=1, max_length=255)
    targets: list[LobsterToolkitDeploymentTargetRequest] = Field(default_factory=list)


class LobsterToolkitUpdateRequest(BaseModel):
    source_scope: LobsterToolkitSourceScope
    source_key: str = Field(min_length=1, max_length=255)
    deployment_ids: list[str] = Field(default_factory=list, max_length=50)
    targets: list[LobsterToolkitDeploymentTargetRequest] = Field(default_factory=list)


class LobsterToolkitDispatchResponseOut(BaseModel):
    source: LobsterToolkitSourceOut
    deployments: list[LobsterToolkitDeploymentOut] = Field(default_factory=list)
    tutorial_paths: dict[str, str | None] = Field(default_factory=dict)


class LobsterToolkitDeleteSourceResponseOut(BaseModel):
    status: Literal["deleted"]
    source_id: str
    name: str


class LobsterToolkitDeleteDeploymentResponseOut(BaseModel):
    status: Literal["deleted"]
    deployment_id: str
    deleted_path: str
    tutorial_paths: dict[str, str | None] = Field(default_factory=dict)


WeixinQrStatus = Literal["waiting", "scanned", "confirmed", "expired", "error"]


class WeixinQrStartResponse(BaseModel):
    session_id: str
    qr_url: str
    expires_at: str


class WeixinQrPollResponse(BaseModel):
    status: WeixinQrStatus
    account_id: str | None = None
    message: str | None = None


class WeixinBridgeStartResponse(BaseModel):
    status: str
    pid: int | None = None
    message: str | None = None


class WeixinBridgeStopResponse(BaseModel):
    status: str
    message: str | None = None


class WeixinBridgeStatusResponse(BaseModel):
    running: bool
    pid: int | None = None
    uptime_seconds: int | None = None
    message: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


RescueCenterStatus = Literal["ready", "blocked"]
RescueCenterBlockerCode = Literal[
    "missing-cli",
    "missing-auth",
    "root-missing",
    "launch-failed",
    "resume-failed",
    "cwd-locked",
]
RescueCenterAuthStatus = Literal["logged_in", "missing", "unknown"]
RescueCenterRuntimeStatus = Literal["idle", "awaiting_events", "recovering", "recovered", "failed", "blocked"]
RescueCenterRecoveryState = Literal["none", "fresh_transport", "auto_recovered"]
RescueCenterDispatchStatus = Literal["accepted", "running", "completed", "failed"]


class RescueCenterGuideOut(BaseModel):
    docs_url: str
    auth_url: str
    app_server_url: str
    install_commands: list[str] = Field(default_factory=list)
    login_command: str
    status_command: str
    root_path: str


class RescueCenterReadinessOut(BaseModel):
    status: RescueCenterStatus
    blocker_code: RescueCenterBlockerCode | None = None
    blocker_title: str | None = None
    blocker_message: str | None = None
    cli_installed: bool
    cli_path: str | None = None
    cli_version: str | None = None
    auth_status: RescueCenterAuthStatus
    root_path: str
    root_exists: bool
    guide: RescueCenterGuideOut
    checked_at: str


class RescueCenterMessageOut(BaseModel):
    message_id: str | None = None
    role: Literal["user", "assistant", "system"]
    text: str
    turn_id: str | None = None
    item_type: str | None = None
    created_at: str | None = None


class RescueCenterThreadSummaryOut(BaseModel):
    thread_id: str
    title: str | None = None
    preview: str | None = None
    message_count: int
    status: str
    codex_path: str | None = None
    codex_version: str | None = None
    cwd: str
    last_error_code: str | None = None
    last_error_message: str | None = None
    runtime_status: RescueCenterRuntimeStatus = "idle"
    runtime_turn_id: str | None = None
    last_event_at: str | None = None
    recovery_state: RescueCenterRecoveryState = "none"
    last_message_at: str | None = None
    created_at: str
    updated_at: str
    is_active: bool


class RescueCenterThreadDetailOut(RescueCenterThreadSummaryOut):
    messages: list[RescueCenterMessageOut] = Field(default_factory=list)


class RescueCenterBootstrapResponse(BaseModel):
    readiness: RescueCenterReadinessOut
    threads: list[RescueCenterThreadSummaryOut] = Field(default_factory=list)
    active_thread: RescueCenterThreadDetailOut | None = None
    runtime_diagnostics: dict[str, Any] = Field(default_factory=dict)


class RescueCenterThreadListResponse(BaseModel):
    items: list[RescueCenterThreadSummaryOut] = Field(default_factory=list)
    total: int
    active_thread_id: str | None = None


class RescueCenterThreadResponse(BaseModel):
    thread: RescueCenterThreadDetailOut


class RescueCenterActivateThreadRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)


class RescueCenterSendMessageRequest(BaseModel):
    thread_id: str | None = Field(default=None, max_length=128)
    message: str = Field(min_length=1, max_length=12000)
    trace_id: str | None = Field(default=None, max_length=64)


class RescueCenterResetResponse(BaseModel):
    status: Literal["reset"]
    cleared_count: int


class RescueCenterMessageDispatchResponse(BaseModel):
    job_id: str
    thread_id: str
    turn_id: str | None = None
    status: RescueCenterDispatchStatus
    accepted_at: str
    runtime_status: RescueCenterRuntimeStatus
    thread: RescueCenterThreadSummaryOut


class RescueCenterEventOut(BaseModel):
    seq: int
    event: str
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RescueCenterEventListResponse(BaseModel):
    items: list[RescueCenterEventOut] = Field(default_factory=list)
    latest_seq: int


class NodeOut(BaseModel):
    node_id: str
    display_name: str
    node_type: NodeType
    expected_openclaw_root: str
    reported_openclaw_root: str | None = None
    hostname: str | None = None
    platform: str | None = None
    connector_version: str | None = None
    status: NodeStatus
    token_last4: str
    activated_at: str | None = None
    last_seen_at: str | None = None
    created_at: str
    updated_at: str


class ListNodesResponse(BaseModel):
    items: list[NodeOut]
    total: int
    bootstrap_ready: bool
    bootstrap_reason: str | None = None
    bootstrap_mode: Literal["public", "local", "unavailable"] = "public"
    bootstrap_base: str | None = None


class CreateNodeRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    node_type: NodeType
    expected_openclaw_root: str = Field(min_length=1, max_length=500)


class NodeBootstrapResponse(BaseModel):
    node: NodeOut
    raw_token: str
    bootstrap_script_url: str | None = None
    bootstrap_command: str | None = None
    bootstrap_ready: bool
    bootstrap_reason: str | None = None
    bootstrap_mode: Literal["public", "local", "unavailable"] = "public"
    bootstrap_base: str | None = None


class NodeHeartbeatRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1, max_length=256)
    connector_version: str = Field(min_length=1, max_length=120)
    hostname: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=120)
    openclaw_root: str = Field(min_length=1, max_length=500)


class NodeSyncJobOut(BaseModel):
    sync_id: str
    source_kind: str
    source_id: str
    resource_key: str
    relative_path: str
    operation_kind: Literal["write_text_file", "upsert_json_value"]
    payload: dict[str, Any]


class NodeHeartbeatResponse(BaseModel):
    node_id: str
    status: NodeStatus
    accepted_at: str
    activated_at: str | None = None
    last_seen_at: str | None = None
    sync_jobs: list[NodeSyncJobOut] = Field(default_factory=list)


class NodeSyncResultItemRequest(BaseModel):
    sync_id: str = Field(min_length=1, max_length=64)
    status: Literal["applied", "failed"]
    error_message: str | None = Field(default=None, max_length=1000)


class NodeSyncResultsRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1, max_length=256)
    results: list[NodeSyncResultItemRequest] = Field(default_factory=list)


class NodeSyncResultsResponse(BaseModel):
    node_id: str
    accepted_at: str
    applied_count: int
    failed_count: int
    ignored_count: int


class AgentSceneGenerateRequest(BaseModel):
    force: bool = False


class UpdateAgentScenePresetRequest(BaseModel):
    preset_id: str = Field(min_length=1, max_length=64)


class AgentSceneJobStepOut(BaseModel):
    scene: Literal["working", "idle", "offline", "crashed"]
    label: str
    status: SceneStepStatus
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    output_mp4: str | None = None


class AgentSceneJobOut(BaseModel):
    job_id: str
    agent_id: str
    status: SceneJobStatus
    current_scene: Literal["working", "idle", "offline", "crashed"] | None = None
    current_stage: str | None = None
    upstream_task_id: str | None = None
    upstream_status: str | None = None
    last_poll_at: str | None = None
    progress_done: int = 0
    progress_total: int = 4
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    steps: list[AgentSceneJobStepOut]


class WorkspaceEntryOut(BaseModel):
    name: str
    path: str
    display_path: str
    kind: Literal["file", "directory"]
    size: int | None = None
    modified_at: str
    editable: bool
    previewable: bool
    preview_kind: str
    mime_type: str | None = None
    code_language: str | None = None
    is_symlink: bool = False
    symlink_target: str | None = None
    preview_url: str | None = None
    pdf_preview_url: str | None = None
    download_url: str | None = None


class AgentWorkspaceDirectoryOut(BaseModel):
    agent_id: str
    agent_name: str
    root_path: str
    current_path: str
    current_display_path: str
    parent_path: str | None = None
    entries: list[WorkspaceEntryOut]


class AgentWorkspaceFileOut(BaseModel):
    agent_id: str
    agent_name: str
    root_path: str
    path: str
    display_path: str
    name: str
    size: int
    modified_at: str
    editable: bool
    previewable: bool
    preview_kind: str
    mime_type: str
    code_language: str | None = None
    preview_url: str | None = None
    pdf_preview_url: str | None = None
    download_url: str | None = None
    truncated: bool = False
    content: str | None = None


class OpenClawRootDirectoryOut(BaseModel):
    root_path: str
    current_path: str
    current_display_path: str
    parent_path: str | None = None
    entries: list[WorkspaceEntryOut]


class OpenClawRootFileOut(BaseModel):
    root_path: str
    path: str
    display_path: str
    name: str
    size: int
    modified_at: str
    editable: bool
    previewable: bool
    preview_kind: str
    mime_type: str
    code_language: str | None = None
    preview_url: str | None = None
    pdf_preview_url: str | None = None
    download_url: str | None = None
    truncated: bool = False
    content: str | None = None


class UpdateWorkspaceFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=600000)


class CreateWorkspaceFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(default="", max_length=600000)


class ImportGithubSkillRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    target_name: str | None = Field(default=None, max_length=255)


class AgentSkillImportResultOut(BaseModel):
    agent_id: str
    agent_name: str
    skill_name: str
    skill_path: str
    display_path: str
    imported_from: Literal["zip", "github"]
    overwritten: bool = False


class AgentSkillDeleteResultOut(BaseModel):
    agent_id: str
    agent_name: str
    skill_name: str
    deleted_path: str


class AgentRemoveResultOut(BaseModel):
    status: Literal["removed"]
    agent_id: str
    display_name: str
    removed_bindings: int
    database_row_removed: bool
    retained_history: bool
    config_path: str | None = None
    backup_path: str | None = None


class AgentPortablePackageFileOut(BaseModel):
    name: str
    package_path: str
    size: int
    sha256: str | None = None


class AgentPortablePackageSkillOut(BaseModel):
    name: str
    package_path: str
    file_count: int
    total_bytes: int


class AgentPortablePackageWarningOut(BaseModel):
    code: str
    message: str
    path: str | None = None


class AgentPortablePackagePreviewOut(BaseModel):
    agent_id: str
    agent_name: str
    package_name: str
    docs: list[AgentPortablePackageFileOut] = Field(default_factory=list)
    skills: list[AgentPortablePackageSkillOut] = Field(default_factory=list)
    scheduled_jobs: list["AgentScheduledJobOut"] = Field(default_factory=list)
    missing_docs: list[str] = Field(default_factory=list)
    warnings: list[AgentPortablePackageWarningOut] = Field(default_factory=list)
    total_files: int = 0
    total_bytes: int = 0
    docs_count: int = 0
    skill_count: int = 0
    scheduled_job_count: int = 0


class AgentActivityLogItemOut(BaseModel):
    id: str
    timestamp: str
    kind: str
    actor: str
    title: str
    detail: str


class AgentActivityLogOut(BaseModel):
    agent_id: str
    agent_name: str
    session_id: str | None = None
    session_updated_at: str | None = None
    session_file: str | None = None
    items: list[AgentActivityLogItemOut]


class AgentScheduledJobOut(BaseModel):
    id: str
    agent_id: str | None = None
    name: str
    description: str | None = None
    enabled: bool
    schedule_kind: Literal["cron", "every", "at"]
    cron_expr: str | None = None
    timezone: str | None = None
    every_ms: int | None = None
    every_minutes: int | None = None
    at: str | None = None
    payload_kind: str | None = None
    content_field: Literal["message", "text"] | None = None
    content: str | None = None
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_status: str | None = None
    updated_at: str | None = None
    delivery_channel: Literal["internal", "feishu", "openclaw", "telegram", "weixin"] = "internal"
    delivery_mode: str | None = None
    delivery_target: dict[str, Any] = Field(default_factory=dict)
    delivery_bootstrap_enabled: bool = False
    delivery_bootstrap_scope: Literal["auto", "local", "remote"] = "auto"
    delivery_bootstrap_status: Literal["disabled", "pending", "synced", "failed"] = "disabled"
    delivery_bootstrap_message: str | None = None
    delivery_bootstrap_synced_at: str | None = None
    delivery_bootstrap_synced_root: str | None = None
    delivery_synced_files: list[str] = Field(default_factory=list)
    template_kind: Literal["plain_text", "feishu_card"] | None = None
    template_title: str | None = None
    template_summary: str | None = None
    template_body: str | None = None
    template_footer: str | None = None
    template_accent: str | None = None
    template_show_sender: bool = True
    template_mentions: list[str] = Field(default_factory=list)


class AgentScheduledJobsResponse(BaseModel):
    agent_id: str
    agent_name: str
    jobs: list[AgentScheduledJobOut]


class ScheduledJobTimelineRangeOut(BaseModel):
    start_at: str
    end_at: str
    minutes: int


class ScheduledJobTimelineOccurrenceOut(BaseModel):
    occurrence_id: str
    job: AgentScheduledJobOut
    start_at: str
    end_at: str
    minutes: int
    estimated: bool = True


class ScheduledJobTimelineAgentRowOut(BaseModel):
    agent_id: str
    agent_name: str
    coverage_ratio: float = 0
    occupied_minutes: int = 0
    conflict_minutes: int = 0
    enabled_job_count: int = 0
    occurrence_count: int = 0
    occurrences: list[ScheduledJobTimelineOccurrenceOut] = Field(default_factory=list)
    conflict_ranges: list[ScheduledJobTimelineRangeOut] = Field(default_factory=list)
    idle_ranges: list[ScheduledJobTimelineRangeOut] = Field(default_factory=list)


class ScheduledJobsTimelineResponseOut(BaseModel):
    from_at: str
    to_at: str
    generated_at: str
    rows: list[ScheduledJobTimelineAgentRowOut]


class UpdateAgentScheduledJobRequest(BaseModel):
    schedule_kind: Literal["cron", "every", "at"]
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    enabled: bool | None = None
    cron_expr: str | None = Field(default=None, max_length=128)
    every_ms: int | None = Field(default=None, ge=1, le=1000 * 60 * 60 * 24 * 365 * 10)
    at: str | None = Field(default=None, max_length=64)
    content: str = Field(min_length=1, max_length=50000)
    delivery_channel: Literal["internal", "feishu", "openclaw", "telegram", "weixin"] | None = None
    delivery_mode: str | None = Field(default=None, max_length=128)
    delivery_target: dict[str, Any] | None = None
    delivery_bootstrap_enabled: bool | None = None
    delivery_bootstrap_scope: Literal["auto", "local", "remote"] | None = None
    template_kind: Literal["plain_text", "feishu_card"] | None = None
    template_title: str | None = Field(default=None, max_length=200)
    template_summary: str | None = Field(default=None, max_length=400)
    template_body: str | None = Field(default=None, max_length=20000)
    template_footer: str | None = Field(default=None, max_length=200)
    template_accent: str | None = Field(default=None, max_length=32)
    template_show_sender: bool | None = None
    template_mentions: list[str] | None = None


class CreateAgentScheduledJobRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    enabled: bool = True
    schedule_kind: Literal["cron", "every", "at"]
    cron_expr: str | None = Field(default=None, max_length=128)
    every_ms: int | None = Field(default=None, ge=1, le=1000 * 60 * 60 * 24 * 365 * 10)
    at: str | None = Field(default=None, max_length=64)
    content: str = Field(min_length=1, max_length=50000)
    delivery_channel: Literal["internal", "feishu", "openclaw", "telegram", "weixin"] | None = None
    delivery_mode: str | None = Field(default=None, max_length=128)
    delivery_target: dict[str, Any] | None = None
    delivery_bootstrap_enabled: bool = False
    delivery_bootstrap_scope: Literal["auto", "local", "remote"] = "auto"
    template_kind: Literal["plain_text", "feishu_card"] | None = None
    template_title: str | None = Field(default=None, max_length=200)
    template_summary: str | None = Field(default=None, max_length=400)
    template_body: str | None = Field(default=None, max_length=20000)
    template_footer: str | None = Field(default=None, max_length=200)
    template_accent: str | None = Field(default=None, max_length=32)
    template_show_sender: bool = True
    template_mentions: list[str] | None = None


class SendWorkspaceInstructionRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    target_agent_id: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=4000)
    sender_agent_id: str = Field(default="main", min_length=1, max_length=64)


class SendWorkspaceInstructionResponse(BaseModel):
    source_agent_id: str
    source_agent_name: str
    target_agent_id: str
    target_agent_name: str
    sender_agent_id: str
    sender_agent_name: str
    file_name: str
    transport: str | None = None
    text_message_id: str | None = None
    file_message_id: str | None = None
    sent_at: str


class AgentUserAuthStateOut(BaseModel):
    agent_id: str
    agent_name: str
    supported: bool
    callback_ready: bool
    authorized: bool
    user_label: str | None = None
    user_open_id: str | None = None
    scope: str | None = None
    authorized_at: str | None = None
    expires_at: str | None = None
    message: str | None = None


class StartAgentUserAuthResponse(BaseModel):
    agent_id: str
    agent_name: str
    authorize_url: str
    state: str
    expires_at: str


class AccountRoleOut(BaseModel):
    role_id: str
    name: str
    description: str | None = None
    is_system: bool = False


class AccountOut(BaseModel):
    account_id: str
    username: str
    display_name: str
    email: str | None = None
    status: Literal["active", "disabled"]
    must_change_password: bool
    force_logout_at: str | None = None
    last_login_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    roles: list[AccountRoleOut] = Field(default_factory=list)


class ListAccountsResponse(BaseModel):
    items: list[AccountOut]
    total: int


class CreateAccountRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    role_ids: list[str] = Field(default_factory=list)


class CreateAccountResponse(BaseModel):
    account: AccountOut
    temp_password: str


class UpdateAccountRolesRequest(BaseModel):
    role_ids: list[str] = Field(default_factory=list)


class UpdateAccountAccessRequest(BaseModel):
    role_ids: list[str] = Field(default_factory=list)
    manual_permission_ids: list[str] = Field(default_factory=list)


class ResetAccountPasswordResponse(BaseModel):
    account: AccountOut
    temp_password: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    account: AccountOut
    token: str
    expires_at: str


class ChangePasswordRequest(BaseModel):
    current_password: str | None = Field(default=None, min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class BootstrapAccountResponse(BaseModel):
    username: str
    temp_password: str | None = None
    created_at: str | None = None
    revealed_at: str | None = None


class PermissionOut(BaseModel):
    permission_id: str
    module_key: str
    module_label: str
    action_key: str
    action_label: str
    description: str | None = None


class ListPermissionsResponse(BaseModel):
    items: list[PermissionOut]


class RoleOut(BaseModel):
    role_id: str
    name: str
    description: str | None = None
    is_system: bool = False
    permission_count: int = 0
    member_count: int = 0


class ListRolesResponse(BaseModel):
    items: list[RoleOut]


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permission_ids: list[str] = Field(default_factory=list)


class UpdateRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)


class CreateRoleResponse(BaseModel):
    role: RoleOut
    permission_ids: list[str] = Field(default_factory=list)


class RolePermissionsResponse(BaseModel):
    role_id: str
    permission_ids: list[str]


class UpdateRolePermissionsRequest(BaseModel):
    permission_ids: list[str] = Field(default_factory=list)


class RolePermissionsMappingResponse(BaseModel):
    mapping: dict[str, list[str]]


class AccountAccessResponse(BaseModel):
    account: AccountOut
    role_ids: list[str] = Field(default_factory=list)
    roles: list[AccountRoleOut] = Field(default_factory=list)
    inherited_permission_ids: list[str] = Field(default_factory=list)
    manual_permission_ids: list[str] = Field(default_factory=list)
    effective_permission_ids: list[str] = Field(default_factory=list)
    editable_permission_ids: list[str] = Field(default_factory=list)


class AuditLogOut(BaseModel):
    audit_id: str
    actor_account_id: str | None = None
    action: str
    target_type: str
    target_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ListAuditLogsResponse(BaseModel):
    items: list[AuditLogOut]
    total: int


class DiagnosticLogOut(BaseModel):
    diagnostic_id: str
    actor_account_id: str | None = None
    source: Literal["client", "server"]
    category: str
    event: str
    level: Literal["info", "warn", "error"]
    trace_id: str | None = None
    request_path: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class CreateDiagnosticLogRequest(BaseModel):
    source: Literal["client", "server"]
    category: str = Field(min_length=1, max_length=64)
    event: str = Field(min_length=1, max_length=128)
    level: Literal["info", "warn", "error"] = "info"
    trace_id: str | None = Field(default=None, max_length=64)
    request_path: str | None = Field(default=None, max_length=300)
    detail: dict[str, Any] = Field(default_factory=dict)


class ListDiagnosticLogsResponse(BaseModel):
    items: list[DiagnosticLogOut]
    total: int


class GenerateAgentProfileRequest(BaseModel):
    executor_agent_id: str = Field(min_length=1, max_length=128)
    agent_name: str = Field(min_length=1, max_length=128)
    role_summary: str = Field(min_length=1, max_length=500)
    core_work: list[str] = Field(min_length=3, max_length=10)


class GenerateAgentProfileFileOut(BaseModel):
    path: str
    content: str
    existing_content: str | None = None
    exists: bool = False


class GenerateAgentProfileResponse(BaseModel):
    agent_id: str
    agent_name: str
    executor_agent_id: str
    files: list[GenerateAgentProfileFileOut]


AgentPortablePackagePreviewOut.model_rebuild()
