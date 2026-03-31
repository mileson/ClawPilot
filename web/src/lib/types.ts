export type AgentStatus = "active" | "probation" | "suspended";
export type AgentRuntimeStatus = "working" | "idle" | "offline" | "crashed";
export type AgentChannelStatus = "missing" | "configured" | "warning";
export type AgentChannelBindingStatus = "configured" | "warning";
export type CurrencyPreference = "CNY" | "USD";
export type AccountStatus = "active" | "disabled";

export interface AgentChannelBinding {
  channel: string;
  account_id: string | null;
  primary: boolean;
  status: AgentChannelBindingStatus;
  reason?: string | null;
}

export interface AccountRole {
  role_id: string;
  name: string;
  description?: string | null;
  is_system?: boolean | null;
}

export interface Account {
  account_id: string;
  username: string;
  display_name: string;
  email?: string | null;
  status: AccountStatus;
  must_change_password: boolean;
  force_logout_at?: string | null;
  last_login_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  roles: AccountRole[];
}

export interface Role {
  role_id: string;
  name: string;
  description?: string | null;
  is_system?: boolean | null;
  permission_count?: number | null;
  member_count?: number | null;
}

export interface Permission {
  permission_id: string;
  module_key: string;
  module_label: string;
  action_key: string;
  action_label: string;
  description?: string | null;
}

export interface AccountAccess {
  account: Account;
  role_ids: string[];
  roles: AccountRole[];
  inherited_permission_ids: string[];
  manual_permission_ids: string[];
  effective_permission_ids: string[];
  editable_permission_ids: string[];
}

export interface AuditLog {
  audit_id: string;
  actor_account_id?: string | null;
  action: string;
  target_type: string;
  target_id?: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface DiagnosticLog {
  diagnostic_id: string;
  actor_account_id?: string | null;
  source: "client" | "server";
  category: string;
  event: string;
  level: "info" | "warn" | "error";
  trace_id?: string | null;
  request_path?: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface Agent {
  agent_id: string;
  display_name: string;
  role: string;
  status: AgentStatus;
  channel: string;
  primary_channel?: string | null;
  connected_channels: AgentChannelBinding[];
  channel_status: AgentChannelStatus;
  channel_status_reason?: string | null;
  account_id: string;
  open_id: string | null;
  workspace_path: string | null;
  identity_complete: boolean;
  role_summary?: string | null;
  core_work?: string[];
  capabilities?: string[];
  skills?: string[];
  delegate_when?: string[];
  do_not_delegate_when?: string[];
  priority?: number | null;
  enabled?: boolean | null;
  main_dispatch_allowed?: boolean | null;
  last_known_active?: string | null;
  latest_activity_at?: string | null;
  runtime_status?: AgentRuntimeStatus | null;
  runtime_status_reason?: string | null;
  runtime_status_at?: string | null;
  runtime_signal_source?: string | null;
  runtime_node_status?: NodeStatus | null;
  runtime_crash_excerpt?: string | null;
  emoji?: string | null;
  avatar_hint?: string | null;
  avatar_url?: string | null;
  scene_preset_id?: string | null;
  model_provider?: string | null;
  model_id?: string | null;
  model_label?: string | null;
  config_model_provider?: string | null;
  config_model_id?: string | null;
  config_model_label?: string | null;
  recent_model_provider?: string | null;
  recent_model_id?: string | null;
  recent_model_label?: string | null;
  usage_input_tokens?: number | null;
  usage_output_tokens?: number | null;
  usage_total_tokens?: number | null;
  usage_context_tokens?: number | null;
  estimated_cost_usd?: number | null;
  created_at: string;
}

export interface AgentRemoveResult {
  status: "removed";
  agent_id: string;
  display_name: string;
  removed_bindings: number;
  database_row_removed: boolean;
  retained_history: boolean;
  config_path?: string | null;
  backup_path?: string | null;
}

export interface BasicAgentCreateResponse {
  status: "created";
  agent: Agent;
  warnings: string[];
}

export interface ConnectAgentFeishuChannelResponse {
  status: "connected";
  channel: "feishu";
  agent: Agent;
  warnings: string[];
}

export interface AgentFeishuPairingConfirmResult {
  status: "confirmed";
  agent_id: string;
  agent_name: string;
  user_open_id: string;
  pairing_code: string;
  completed_at: string;
}

export type OnboardingStepStatus = "todo" | "running" | "done" | "warn" | "failed" | "skipped";
export type OnboardingRunStatus = "draft" | "running" | "paused" | "partial" | "completed" | "failed";

export interface FeishuGroupOption {
  chat_id: string;
  name?: string | null;
  require_mention?: boolean | null;
  source?: string | null;
}

export interface MultiAgentOnboardingStep {
  key: string;
  label: string;
  status: OnboardingStepStatus;
  summary?: string | null;
  detail?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface MultiAgentOnboardingRunSummary {
  run_id: string;
  owner_agent_id: string;
  target_agent_id: string;
  target_agent_name: string;
  status: OnboardingRunStatus;
  completed_step_count: number;
  total_step_count: number;
  pending_restart: boolean;
  warnings: string[];
  steps: MultiAgentOnboardingStep[];
  created_at: string;
  updated_at: string;
}

export interface MultiAgentOnboardingBootstrap {
  agents: Agent[];
  persona_writer_candidates: Agent[];
  group_options: FeishuGroupOption[];
  default_identity_key: string | null;
  official_checklist: string[];
  skill_checklist: string[];
  in_progress_runs: MultiAgentOnboardingRunSummary[];
}

export interface MultiAgentOnboardingDryRun {
  steps: MultiAgentOnboardingStep[];
  warnings: string[];
  blockers: string[];
}

export interface MultiAgentOnboardingRunResponse {
  run: MultiAgentOnboardingRunSummary;
  steps: MultiAgentOnboardingStep[];
  warnings: string[];
  pending_restart: boolean;
}

export interface MultiAgentOnboardingRunsResponse {
  items: MultiAgentOnboardingRunSummary[];
  total: number;
}

export interface FeishuAppAutoCreateResponse {
  status: "success" | "failed" | "login_required" | "dependency_missing";
  step?: string | null;
  message?: string | null;
  app_id?: string | null;
  app_secret?: string | null;
  chat_url?: string | null;
  execution_mode?: "cdp" | "profile" | null;
  debugger_url?: string | null;
}

export interface FirstLobsterAutoClaimRun {
  job_id: string;
  status: "queued" | "waiting_login" | "claiming" | "completed" | "failed";
  current_stage: "queued" | "waiting_login" | "claiming" | "completed" | "failed";
  trace_id?: string | null;
  message?: string | null;
  error_message?: string | null;
  execution_mode?: "cdp" | "profile" | null;
  debugger_url?: string | null;
  chat_url?: string | null;
  app_id?: string | null;
  agent_id?: string | null;
  selected_channels: Array<"feishu" | "telegram" | "discord">;
  primary_channel?: "feishu" | "telegram" | "discord" | null;
  config_path?: string | null;
  backup_path?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface FirstLobsterFeishuPairingConfirmResult {
  status: "confirmed";
  agent_id: string;
  agent_name: string;
  user_open_id: string;
  pairing_code: string;
  completed_at: string;
}

export interface Task {
  task_id: string;
  title: string;
  description: string | null;
  creator_type: "human" | "agent";
  creator_id: string;
  assignee_agent_id: string;
  status: "todo" | "doing" | "review" | "done" | "rejected";
  priority: "low" | "medium" | "high" | "urgent";
  expected_output: string;
  acceptance_criteria: string;
  deadline_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrainingRun {
  run_id: string;
  agent_id: string;
  onboarding_job_id: string | null;
  phase: "exam" | "observe" | "gate";
  status: "planned" | "running" | "passed" | "failed";
  score: number | null;
  result: "GRADUATE" | "REMEDIATE" | null;
  report_url: string | null;
  observe_days: number | null;
  created_at: string;
  updated_at: string;
}

export type TrainingAgentState = "not_enrolled" | "pending_training" | "training" | "recently_trained";

export interface TrainingModuleCoach {
  coach_agent_id: string;
  coach_agent_name: string;
  skill_name: string;
  skill_source_path: string;
  skill_target_path: string;
  configured_at: string;
  updated_at: string;
}

export interface TrainingModuleCounts {
  total: number;
  not_enrolled: number;
  pending_training: number;
  training: number;
  recently_trained: number;
}

export interface TrainingAgentSummary {
  agent_id: string;
  display_name: string;
  role_summary?: string | null;
  avatar_url?: string | null;
  avatar_hint?: string | null;
  emoji?: string | null;
  training_state: TrainingAgentState;
  training_state_label: string;
  training_count: number;
  latest_completed_at?: string | null;
  active_run_id?: string | null;
  active_run_phase?: string | null;
  profile_exists: boolean;
}

export interface TrainingModuleOverview {
  initialized: boolean;
  needs_coach_setup: boolean;
  home_url: string;
  has_openclaw_config: boolean;
  online_node_total: number;
  node_total: number;
  coach?: TrainingModuleCoach | null;
  counts: TrainingModuleCounts;
  agents: TrainingAgentSummary[];
}

export interface LeaderboardEntry {
  rank: number;
  agent_id: string;
  display_name: string;
  points: number;
  role?: string | null;
  role_summary?: string | null;
  channel?: string | null;
  avatar_url?: string | null;
  avatar_hint?: string | null;
}

export interface DashboardStats {
  agentTotal: number;
  taskTotal: number;
  trainingTotal: number;
  topPoints: number;
}

export interface AppBuildInfo {
  gitSha: string;
  shortSha: string;
  builtAt: string;
  builtAtLabel: string;
}

export interface SetupStatus {
  has_openclaw_config: boolean;
  node_total: number;
  bootstrap_ready: boolean;
  bootstrap_reason: string | null;
  bootstrap_mode: "public" | "local" | "unavailable";
  bootstrap_base: string | null;
  bootstrap_prompt?: string | null;
  install_operation?: string | null;
  install_stage?: string | null;
  install_result?: string | null;
  install_updated_at?: string | null;
  local_web_url?: string | null;
  local_api_health_url?: string | null;
  local_web_ok?: boolean | null;
  local_api_ok?: boolean | null;
  public_url?: string | null;
  public_url_status?: string | null;
  public_url_reason?: string | null;
  public_url_provider?: string | null;
  public_url_enabled?: boolean;
  openclaw_cli_installed?: boolean;
  openclaw_cli_path?: string | null;
  openclaw_current_version?: string | null;
  openclaw_latest_version?: string | null;
  openclaw_update_available?: boolean;
}

export interface ControlPlaneActionAccepted {
  job_id: string;
  action: "bootstrap" | "repair_local" | "repair_tunnel" | "install_openclaw" | "update_status" | "update_install";
  status: "accepted" | "running" | "completed" | "failed";
  accepted_at: string;
  detail: Record<string, unknown>;
}

export interface ControlPlaneJobStatus {
  job_id: string;
  kind: string;
  status: "accepted" | "running" | "completed" | "failed";
  accepted_at: string;
  started_at?: string | null;
  first_progress_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  detail: Record<string, unknown>;
}

export type FirstLobsterChannel = "feishu" | "telegram" | "discord" | "weixin";

export interface FirstLobsterFieldDefinition {
  key: string;
  label: string;
  secret?: boolean;
  placeholder?: string | null;
  description?: string | null;
}

export interface FirstLobsterChannelDefinition {
  channel: FirstLobsterChannel;
  label: string;
  description?: string | null;
  default_account_id: string;
  fields: FirstLobsterFieldDefinition[];
}

export interface FirstLobsterWorkspacePreview {
  path: string;
  source: "config" | "fallback";
  available: boolean;
  error?: string | null;
}

export interface FirstLobsterBootstrapFile {
  path: string;
  exists: boolean;
  size?: number | null;
  modified_at?: string | null;
  preview?: string | null;
  preview_truncated: boolean;
  error?: string | null;
}

export interface FirstLobsterBootstrapPreview {
  workspace: FirstLobsterWorkspacePreview;
  recommended_agent_id: string;
  recommended_agent_name: string;
  recommended_app_name: string;
  supported_channels: FirstLobsterChannelDefinition[];
  files: FirstLobsterBootstrapFile[];
}

export interface ClaimFirstLobsterResult {
  status: "claimed";
  selected_channels: FirstLobsterChannel[];
  primary_channel: FirstLobsterChannel;
  config_path: string;
  backup_path?: string | null;
  agent: Agent;
}

export interface SystemSettings {
  currency_preference: CurrencyPreference;
  exchange_rate_usd_cny: number;
  exchange_rate_source: string;
  exchange_rate_updated_at?: string | null;
  exchange_rate_checked_at?: string | null;
  updated_at?: string | null;
  status_aliases?: {
    working?: string | null;
    idle?: string | null;
    offline?: string | null;
    crashed?: string | null;
  };
  gateway_settings?: GatewaySettings;
}

export interface GatewaySettings {
  mode_preference: "auto" | "existing-proxy" | "caddy" | "public-port";
  domain?: string | null;
  ssl_email?: string | null;
  public_host_ip?: string | null;
  public_web_port: number;
  auto_https: boolean;
  status: "idle" | "saved" | "error";
  access_url?: string | null;
  last_error?: string | null;
  verified_at?: string | null;
  updated_at?: string | null;
}

export interface GatewayApplyAccepted {
  job_id: string;
  status: "accepted" | "running" | "completed" | "failed";
  accepted_at: string;
  detail: Record<string, unknown>;
}

export interface GatewayJobStatus {
  job_id: string;
  kind: string;
  status: "accepted" | "running" | "completed" | "failed";
  accepted_at: string;
  started_at?: string | null;
  first_progress_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  detail: Record<string, unknown>;
}

export type NodeStatus = "pending" | "online" | "offline";
export type NodeType = "vps" | "linux" | "macos";

export interface NodeConnection {
  node_id: string;
  display_name: string;
  node_type: NodeType;
  expected_openclaw_root: string;
  reported_openclaw_root: string | null;
  hostname: string | null;
  platform: string | null;
  connector_version: string | null;
  status: NodeStatus;
  token_last4: string;
  activated_at: string | null;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NodeConnectionsResponse {
  items: NodeConnection[];
  total: number;
  bootstrap_ready: boolean;
  bootstrap_reason: string | null;
  bootstrap_mode: "public" | "local" | "unavailable";
  bootstrap_base: string | null;
}

export interface NodeBootstrapResult {
  node: NodeConnection;
  raw_token: string;
  bootstrap_script_url: string | null;
  bootstrap_command: string | null;
  bootstrap_ready: boolean;
  bootstrap_reason: string | null;
  bootstrap_mode: "public" | "local" | "unavailable";
  bootstrap_base: string | null;
}

export type AgentSceneKey = "working" | "idle" | "offline" | "crashed";
export type AgentSceneJobStatus = "queued" | "running" | "completed" | "failed";
export type AgentSceneStepStatus = "pending" | "running" | "completed" | "failed";

export interface AgentSceneJobStep {
  scene: AgentSceneKey;
  label: string;
  status: AgentSceneStepStatus;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
  output_mp4: string | null;
}

export interface AgentSceneJob {
  job_id: string;
  agent_id: string;
  status: AgentSceneJobStatus;
  current_scene: AgentSceneKey | null;
  current_stage: string | null;
  upstream_task_id: string | null;
  upstream_status: string | null;
  last_poll_at: string | null;
  progress_done: number;
  progress_total: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  steps: AgentSceneJobStep[];
}

export interface WorkspaceEntry {
  name: string;
  path: string;
  display_path: string;
  kind: "file" | "directory";
  size: number | null;
  modified_at: string;
  editable: boolean;
  previewable: boolean;
  preview_kind: string;
  mime_type: string | null;
  code_language: string | null;
  is_symlink?: boolean;
  symlink_target?: string | null;
  preview_url: string | null;
  pdf_preview_url: string | null;
  download_url: string | null;
}

export interface AgentWorkspaceDirectory {
  agent_id: string;
  agent_name: string;
  root_path: string;
  current_path: string;
  current_display_path: string;
  parent_path: string | null;
  entries: WorkspaceEntry[];
}

export interface AgentWorkspaceFile {
  agent_id: string;
  agent_name: string;
  root_path: string;
  path: string;
  display_path: string;
  name: string;
  size: number;
  modified_at: string;
  editable: boolean;
  previewable: boolean;
  preview_kind: string;
  mime_type: string;
  code_language: string | null;
  preview_url: string | null;
  pdf_preview_url: string | null;
  download_url: string | null;
  truncated: boolean;
  content: string | null;
}

export interface OpenClawRootDirectory {
  root_path: string;
  current_path: string;
  current_display_path: string;
  parent_path: string | null;
  entries: WorkspaceEntry[];
}

export interface OpenClawRootFile {
  root_path: string;
  path: string;
  display_path: string;
  name: string;
  size: number;
  modified_at: string;
  editable: boolean;
  previewable: boolean;
  preview_kind: string;
  mime_type: string;
  code_language: string | null;
  preview_url: string | null;
  pdf_preview_url: string | null;
  download_url: string | null;
  truncated: boolean;
  content: string | null;
}

export type RescueCenterStatus = "ready" | "blocked";
export type RescueCenterBlockerCode =
  | "missing-cli"
  | "missing-auth"
  | "root-missing"
  | "launch-failed"
  | "resume-failed"
  | "cwd-locked";
export type RescueCenterAuthStatus = "logged_in" | "missing" | "unknown";
export type RescueCenterRuntimeStatus = "idle" | "awaiting_events" | "recovering" | "recovered" | "failed" | "blocked";
export type RescueCenterRecoveryState = "none" | "fresh_transport" | "auto_recovered";
export type RescueCenterDispatchStatus = "accepted" | "running" | "completed" | "failed";

export interface RescueCenterGuide {
  docs_url: string;
  auth_url: string;
  app_server_url: string;
  install_commands: string[];
  login_command: string;
  status_command: string;
  root_path: string;
}

export interface RescueCenterReadiness {
  status: RescueCenterStatus;
  blocker_code: RescueCenterBlockerCode | null;
  blocker_title: string | null;
  blocker_message: string | null;
  cli_installed: boolean;
  cli_path: string | null;
  cli_version: string | null;
  auth_status: RescueCenterAuthStatus;
  root_path: string;
  root_exists: boolean;
  guide: RescueCenterGuide;
  checked_at: string;
}

export interface RescueCenterMessage {
  message_id: string | null;
  role: "user" | "assistant" | "system";
  text: string;
  turn_id: string | null;
  item_type: string | null;
  created_at: string | null;
}

export interface RescueCenterThreadSummary {
  thread_id: string;
  title: string | null;
  preview: string | null;
  message_count: number;
  status: string;
  codex_path: string | null;
  codex_version: string | null;
  cwd: string;
  last_error_code: string | null;
  last_error_message: string | null;
  runtime_status: RescueCenterRuntimeStatus;
  runtime_turn_id: string | null;
  last_event_at: string | null;
  recovery_state: RescueCenterRecoveryState;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface RescueCenterThreadDetail extends RescueCenterThreadSummary {
  messages: RescueCenterMessage[];
}

export interface RescueCenterBootstrap {
  readiness: RescueCenterReadiness;
  threads: RescueCenterThreadSummary[];
  active_thread: RescueCenterThreadDetail | null;
  runtime_diagnostics: Record<string, unknown>;
}

export interface RescueCenterThreadListResponse {
  items: RescueCenterThreadSummary[];
  total: number;
  active_thread_id: string | null;
}

export interface RescueCenterMessageDispatch {
  job_id: string;
  thread_id: string;
  turn_id: string | null;
  status: RescueCenterDispatchStatus;
  accepted_at: string;
  runtime_status: RescueCenterRuntimeStatus;
  thread: RescueCenterThreadSummary;
}

export interface RescueCenterEvent {
  seq: number;
  event: string;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface RescueCenterEventListResponse {
  items: RescueCenterEvent[];
  latest_seq: number;
}

export interface AgentSkillImportResult {
  agent_id: string;
  agent_name: string;
  skill_name: string;
  skill_path: string;
  display_path: string;
  imported_from: "zip" | "github";
  overwritten: boolean;
}

export interface AgentSkillDeleteResult {
  agent_id: string;
  agent_name: string;
  skill_name: string;
  deleted_path: string;
}

export type LobsterToolkitToolKind = "skill" | "cli";
export type LobsterToolkitDeliveryKind = "skill" | "openclaw_extension" | "standalone_cli";
export type LobsterToolkitSourceScope = "system" | "user";
export type LobsterToolkitTargetScope = "shared" | "agent";
export type LobsterToolkitProvider = "manual" | "github" | "clawhub" | "skills_sh";
export type LobsterToolkitCheckStatus = "idle" | "ready" | "update_available" | "failed";
export type LobsterToolkitCognitionStatus = "not_applicable" | "pending" | "synced" | "failed";

export interface LobsterToolkitDeployment {
  id: string;
  source_scope: LobsterToolkitSourceScope;
  source_key: string;
  tool_kind: LobsterToolkitToolKind;
  delivery_kind: LobsterToolkitDeliveryKind;
  target_scope: LobsterToolkitTargetScope;
  target_agent_id: string | null;
  install_root: string;
  install_path: string;
  installed_version: string | null;
  installed_revision: string | null;
  last_deployed_at: string;
  cognition_status: LobsterToolkitCognitionStatus;
  cognition_updated_at: string | null;
  tutorial_skill_path: string | null;
}

export interface LobsterToolkitSource {
  source_scope: LobsterToolkitSourceScope;
  source_key: string;
  source_id: string | null;
  tool_kind: LobsterToolkitToolKind;
  delivery_kind: LobsterToolkitDeliveryKind;
  provider: LobsterToolkitProvider;
  name: string;
  slug: string;
  brand: string | null;
  brand_bg_color: string | null;
  brand_text_color: string | null;
  description_i18n: Record<string, string>;
  remote_url: string;
  ref: string | null;
  summary: string | null;
  editable: boolean;
  enabled: boolean;
  latest_version: string | null;
  latest_revision: string | null;
  latest_revision_short: string | null;
  latest_published_at: string | null;
  last_checked_at: string | null;
  check_status: LobsterToolkitCheckStatus;
  last_error: string | null;
  tutorial_metadata: Record<string, unknown>;
  deployments: LobsterToolkitDeployment[];
  shared_targets_count: number;
  agent_targets_count: number;
  total_targets_count: number;
}

export interface LobsterToolkitListResponse {
  items: LobsterToolkitSource[];
  total: number;
}

export interface LobsterToolkitSearchResult {
  provider: LobsterToolkitProvider;
  title: string;
  slug: string;
  summary: string | null;
  canonical_url: string;
  remote_url: string;
  ref: string | null;
  delivery_kind: LobsterToolkitDeliveryKind;
  validation_status: string;
}

export interface LobsterToolkitSearchResponse {
  provider: LobsterToolkitProvider;
  query: string;
  items: LobsterToolkitSearchResult[];
}

export interface LobsterToolkitDispatchTarget {
  target_scope: LobsterToolkitTargetScope;
  target_agent_id?: string | null;
}

export interface LobsterToolkitDispatchResponse {
  source: LobsterToolkitSource;
  deployments: LobsterToolkitDeployment[];
  tutorial_paths: Record<string, string | null>;
}

export interface LobsterToolkitDeleteSourceResponse {
  status: "deleted";
  source_id: string;
  name: string;
}

export interface LobsterToolkitDeleteDeploymentResponse {
  status: "deleted";
  deployment_id: string;
  deleted_path: string;
  tutorial_paths: Record<string, string | null>;
}

export interface AgentPortablePackageFile {
  name: string;
  package_path: string;
  size: number;
  sha256: string | null;
}

export interface AgentPortablePackageSkill {
  name: string;
  package_path: string;
  file_count: number;
  total_bytes: number;
}

export interface AgentPortablePackageWarning {
  code: string;
  message: string;
  path: string | null;
}

export interface AgentPortablePackagePreview {
  agent_id: string;
  agent_name: string;
  package_name: string;
  docs: AgentPortablePackageFile[];
  skills: AgentPortablePackageSkill[];
  scheduled_jobs: AgentScheduledJob[];
  missing_docs: string[];
  warnings: AgentPortablePackageWarning[];
  total_files: number;
  total_bytes: number;
  docs_count: number;
  skill_count: number;
  scheduled_job_count: number;
}

export interface AgentActivityLogItem {
  id: string;
  timestamp: string;
  kind: string;
  actor: string;
  title: string;
  detail: string;
}

export interface AgentActivityLog {
  agent_id: string;
  agent_name: string;
  session_id: string | null;
  session_updated_at: string | null;
  session_file: string | null;
  items: AgentActivityLogItem[];
}

export type AgentScheduledJobKind = "cron" | "every" | "at";
export type AgentScheduledJobDeliveryChannel = "internal" | "feishu" | "openclaw" | "telegram" | "weixin";

export interface WeixinBridgeStatus {
  running: boolean;
  pid: number | null;
  uptime_seconds: number | null;
  message: string | null;
}
export type AgentScheduledJobBootstrapScope = "auto" | "local" | "remote";
export type AgentScheduledJobBootstrapStatus = "disabled" | "pending" | "synced" | "failed";
export type AgentScheduledJobTemplateKind = "plain_text" | "feishu_card";

export interface AgentScheduledJob {
  id: string;
  agent_id: string | null;
  name: string;
  description: string | null;
  enabled: boolean;
  schedule_kind: AgentScheduledJobKind;
  cron_expr: string | null;
  timezone: string | null;
  every_ms: number | null;
  every_minutes: number | null;
  at: string | null;
  payload_kind: string | null;
  content_field: "message" | "text" | null;
  content: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: string | null;
  updated_at: string | null;
  delivery_channel: AgentScheduledJobDeliveryChannel;
  delivery_mode: string | null;
  delivery_target: Record<string, string | string[]>;
  delivery_bootstrap_enabled: boolean;
  delivery_bootstrap_scope: AgentScheduledJobBootstrapScope;
  delivery_bootstrap_status: AgentScheduledJobBootstrapStatus;
  delivery_bootstrap_message: string | null;
  delivery_bootstrap_synced_at: string | null;
  delivery_bootstrap_synced_root: string | null;
  delivery_synced_files: string[];
  template_kind: AgentScheduledJobTemplateKind | null;
  template_title: string | null;
  template_summary: string | null;
  template_body: string | null;
  template_footer: string | null;
  template_accent: string | null;
  template_show_sender: boolean;
  template_mentions: string[];
}

export interface AgentScheduledJobsResponse {
  agent_id: string;
  agent_name: string;
  jobs: AgentScheduledJob[];
}

export interface ScheduledJobTimelineRange {
  start_at: string;
  end_at: string;
  minutes: number;
}

export interface ScheduledJobTimelineOccurrence {
  occurrence_id: string;
  job: AgentScheduledJob;
  start_at: string;
  end_at: string;
  minutes: number;
  estimated: boolean;
}

export interface ScheduledJobTimelineRow {
  agent_id: string;
  agent_name: string;
  coverage_ratio: number;
  occupied_minutes: number;
  conflict_minutes: number;
  enabled_job_count: number;
  occurrence_count: number;
  occurrences: ScheduledJobTimelineOccurrence[];
  conflict_ranges: ScheduledJobTimelineRange[];
  idle_ranges: ScheduledJobTimelineRange[];
}

export interface ScheduledJobsTimelineResponse {
  from_at: string;
  to_at: string;
  generated_at: string;
  rows: ScheduledJobTimelineRow[];
}

export interface SendWorkspaceInstructionResult {
  source_agent_id: string;
  source_agent_name: string;
  target_agent_id: string;
  target_agent_name: string;
  sender_agent_id: string;
  sender_agent_name: string;
  file_name: string;
  transport: string | null;
  text_message_id: string | null;
  file_message_id: string | null;
  sent_at: string;
}

export interface AgentUserAuthState {
  agent_id: string;
  agent_name: string;
  supported: boolean;
  callback_ready: boolean;
  authorized: boolean;
  user_label: string | null;
  user_open_id: string | null;
  scope: string | null;
  authorized_at: string | null;
  expires_at: string | null;
  message: string | null;
}

export interface StartAgentUserAuthResult {
  agent_id: string;
  agent_name: string;
  authorize_url: string;
  state: string;
  expires_at: string;
}
