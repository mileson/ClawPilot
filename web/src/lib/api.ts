import type {
  Agent,
  AgentActivityLog,
  AgentRemoveResult,
  AgentPortablePackagePreview,
  AgentScheduledJob,
  AgentScheduledJobsResponse,
  NodeBootstrapResult,
  NodeConnectionsResponse,
  ScheduledJobsTimelineResponse,
  AgentSkillDeleteResult,
  AgentSceneJob,
  AgentSkillImportResult,
  AgentUserAuthState,
  AgentWorkspaceDirectory,
  AgentWorkspaceFile,
  Account,
  AccountAccess,
  Role,
  Permission,
  AuditLog,
  BasicAgentCreateResponse,
  DiagnosticLog,
  ClaimFirstLobsterResult,
  ConnectAgentFeishuChannelResponse,
  ControlPlaneActionAccepted,
  ControlPlaneJobStatus,
  DashboardStats,
  FirstLobsterAutoClaimRun,
  FirstLobsterFeishuPairingConfirmResult,
  LeaderboardEntry,
  FirstLobsterBootstrapPreview,
  MultiAgentOnboardingBootstrap,
  MultiAgentOnboardingDryRun,
  MultiAgentOnboardingRunResponse,
  MultiAgentOnboardingRunsResponse,
  FeishuAppAutoCreateResponse,
  OpenClawRootDirectory,
  OpenClawRootFile,
  RescueCenterBootstrap,
  RescueCenterEventListResponse,
  RescueCenterMessageDispatch,
  RescueCenterReadiness,
  RescueCenterThreadDetail,
  RescueCenterThreadListResponse,
  SendWorkspaceInstructionResult,
  SetupStatus,
  SystemSettings,
  GatewaySettings,
  GatewayApplyAccepted,
  GatewayJobStatus,
  StartAgentUserAuthResult,
  Task,
  TrainingModuleOverview,
  TrainingRun,
} from "@/lib/types";
import { tRuntime } from "@/i18n/runtime";
import { clearStoredSession, markStoredAccountPasswordChangeRequired } from "@/lib/auth-session";
import { recordClientDiagnosticLog, type DiagnosticDetailValue } from "@/lib/diagnostics";

const SERVER_API_BASE = process.env.OPENCLAW_API_BASE || "http://127.0.0.1:8088";
const CLIENT_API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";
const CLIENT_API_TRANSPORT = process.env.NEXT_PUBLIC_API_TRANSPORT || "auto";

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

type ApiErrorPayload = {
  detail?:
    | {
        code?: string;
        message?: string;
        details?: unknown;
      }
    | string
    | Array<{
        type?: string;
        msg?: string;
        loc?: Array<string | number>;
        ctx?: Record<string, unknown>;
      }>;
  message?: string;
};

function readStructuredDetail(
  detail: ApiErrorPayload["detail"] | { message?: string } | undefined,
): { code?: string; message?: string; details?: unknown } | undefined {
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return undefined;
  return detail;
}

function readDetailMessage(
  detail: ApiErrorPayload["detail"] | { message?: string } | undefined,
): string | undefined {
  const structuredDetail = readStructuredDetail(detail);
  return typeof structuredDetail?.message === "string" && structuredDetail.message.trim()
    ? structuredDetail.message.trim()
    : undefined;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(message: string, options: { status: number; code?: string; details?: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
  }
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = String(hostname || "").trim().toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}

function getConfiguredClientTransportMode() {
  return CLIENT_API_TRANSPORT === "direct" || CLIENT_API_TRANSPORT === "proxy"
    ? CLIENT_API_TRANSPORT
    : "auto";
}

function resolveClientApiStrategy() {
  const configuredMode = getConfiguredClientTransportMode();
  if (typeof window === "undefined") {
    return {
      mode: configuredMode === "auto" ? (CLIENT_API_BASE ? "direct" : "proxy") : configuredMode,
      base: CLIENT_API_BASE || SERVER_API_BASE,
    };
  }
  return {
    mode: "proxy" as const,
    base: window.location.origin,
  };
}

function resolveApiUrl(path: string): string {
  if (typeof window === "undefined") {
    return `${SERVER_API_BASE}${path}`;
  }
  const strategy = resolveClientApiStrategy();
  return strategy.mode === "proxy" ? path : `${strategy.base}${path}`;
}

function resolveBrowserApiFallbackUrl(path: string): string | null {
  if (typeof window === "undefined") return null;
  const strategy = resolveClientApiStrategy();
  if (strategy.mode !== "direct") return null;
  try {
    const target = new URL(`${strategy.base}${path}`);
    if (target.origin === window.location.origin) return null;
  } catch {
    return path;
  }
  return path;
}

export function getClientApiTransportInfo() {
  const strategy = resolveClientApiStrategy();
  return strategy;
}

function resolveApiErrorMessage(data: ApiErrorPayload): string {
  if (Array.isArray(data.detail) && data.detail.length > 0) {
    const firstIssue = data.detail[0];
    const field = String(firstIssue.loc?.[firstIssue.loc.length - 1] ?? "");
    const minLength = Number(firstIssue.ctx?.min_length ?? 0);
    if (field === "new_password" && minLength > 0) {
      return tRuntime("password.errors.minLength", { min: minLength });
    }
    return firstIssue.msg || tRuntime("api.requestInvalid");
  }

  if (typeof data.detail === "string" && data.detail.trim()) {
    return data.detail.trim();
  }

  return readDetailMessage(data.detail) || data?.message || tRuntime("api.requestFailed");
}

function logApiDiagnostic(payload: {
  level: "warn" | "error";
  event: string;
  requestPath: string;
  detail: Record<string, DiagnosticDetailValue>;
}) {
  if (typeof window === "undefined") return;
  void recordClientDiagnosticLog({
    category: "api",
    event: payload.event,
    level: payload.level,
    request_path: payload.requestPath,
    detail: payload.detail,
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveApiUrl(path);
  const fallbackUrl = resolveBrowserApiFallbackUrl(path);
  const method = String(init?.method || "GET").toUpperCase();
  const isFormData =
    typeof FormData !== "undefined" && init?.body != null && init.body instanceof FormData;
  const authHeaders: Record<string, string> = {};
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("oc_session");
    if (token) {
      authHeaders.Authorization = `Bearer ${token}`;
    }
  }
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        ...authHeaders,
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (error) {
    if (fallbackUrl && fallbackUrl !== url) {
      let fallbackResponse: Response | null = null;
      try {
        fallbackResponse = await fetch(fallbackUrl, {
          ...init,
          headers: {
            ...authHeaders,
            ...(isFormData ? {} : { "Content-Type": "application/json" }),
            ...(init?.headers ?? {}),
          },
          cache: "no-store",
        });
      } catch {
        // Fall through to the original network error reporting below.
      }
      if (fallbackResponse) {
        const data = (await fallbackResponse.json().catch(() => ({}))) as ApiErrorPayload & T;
        if (!fallbackResponse.ok) {
          const structuredDetail = readStructuredDetail(data.detail);
          const code = structuredDetail?.code;
          const message = resolveApiErrorMessage(data);
          logApiDiagnostic({
            level: fallbackResponse.status >= 500 ? "error" : "warn",
            event: "request.http_error",
            requestPath: path,
            detail: {
              method,
              url: fallbackUrl,
              status: fallbackResponse.status,
              code: code || null,
              message,
            },
          });
          if (typeof window !== "undefined") {
            if (code === "unauthorized") {
              clearStoredSession();
            } else if (code === "password_change_required") {
              markStoredAccountPasswordChangeRequired();
            }
          }
          throw new ApiError(message, {
            status: fallbackResponse.status,
            code,
            details: Array.isArray(data?.detail) ? data.detail : structuredDetail?.details,
          });
        }
        return data as T;
      }
    }
    logApiDiagnostic({
      level: "error",
      event: "request.network_error",
      requestPath: path,
      detail: {
        method,
        url,
        reason: error instanceof Error ? error.message : tRuntime("api.requestFailed"),
      },
    });
    throw new Error(
      tRuntime("api.unreachable", {
        url,
        reason: error instanceof Error ? error.message : tRuntime("api.requestFailed"),
      }),
    );
  }

  const data = (await res.json().catch(() => ({}))) as ApiErrorPayload & T;

  if (!res.ok) {
    const structuredDetail = readStructuredDetail(data.detail);
    const code = structuredDetail?.code;
    const message = resolveApiErrorMessage(data);
    logApiDiagnostic({
      level: res.status >= 500 ? "error" : "warn",
      event: "request.http_error",
      requestPath: path,
      detail: {
        method,
        url,
        status: res.status,
        code: code || null,
        message,
      },
    });
    if (typeof window !== "undefined") {
      if (code === "unauthorized") {
        clearStoredSession();
      } else if (code === "password_change_required") {
        markStoredAccountPasswordChangeRequired();
      }
    }
    throw new ApiError(message, {
      status: res.status,
      code,
      details: Array.isArray(data?.detail) ? data.detail : structuredDetail?.details,
    });
  }

  return data as T;
}

export async function getAgents(): Promise<Agent[]> {
  const data = await request<{ items: Agent[] }>("/api/agents");
  return data.items;
}

export async function removeAgent(agentId: string) {
  return request<AgentRemoveResult>(`/api/agents/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
  });
}

export async function updateAgentScenePreset(agentId: string, presetId: string) {
  return request<Agent>(`/api/agents/${encodeURIComponent(agentId)}/scene-preset`, {
    method: "PUT",
    body: JSON.stringify({ preset_id: presetId }),
  });
}

export async function getMultiAgentOnboardingBootstrap(): Promise<MultiAgentOnboardingBootstrap> {
  return request<MultiAgentOnboardingBootstrap>("/api/agent-configs/multi-agent/bootstrap");
}

export async function dryRunMultiAgentOnboarding(payload: Record<string, JsonValue>): Promise<MultiAgentOnboardingDryRun> {
  return request<MultiAgentOnboardingDryRun>("/api/agent-configs/multi-agent/dry-run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function startMultiAgentOnboarding(
  payload: Record<string, JsonValue>,
): Promise<MultiAgentOnboardingRunResponse> {
  return request<MultiAgentOnboardingRunResponse>("/api/agent-configs/multi-agent/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function resumeMultiAgentOnboarding(runId: string): Promise<MultiAgentOnboardingRunResponse> {
  return request<MultiAgentOnboardingRunResponse>(`/api/agent-configs/multi-agent/${runId}/resume`, {
    method: "POST",
  });
}

export async function listMultiAgentOnboardingRuns(
  includeCompleted = false,
): Promise<MultiAgentOnboardingRunsResponse> {
  const query = new URLSearchParams();
  if (includeCompleted) query.set("include_completed", "true");
  const suffix = query.toString();
  return request<MultiAgentOnboardingRunsResponse>(
    `/api/agent-configs/multi-agent/runs${suffix ? `?${suffix}` : ""}`,
  );
}

export async function autoCreateFeishuApp(payload: {
  app_name?: string | null;
  app_description?: string | null;
  menu_name?: string | null;
  automation_mode?: "auto" | "cdp" | "profile";
  cdp_url?: string | null;
  headless?: boolean;
  timeout_sec?: number;
  profile_dir?: string | null;
}): Promise<FeishuAppAutoCreateResponse> {
  return request<FeishuAppAutoCreateResponse>("/api/feishu/auto-create", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function syncAgents(): Promise<{ synced: number; fallback_seeded: boolean }> {
  return request<{ synced: number; fallback_seeded: boolean }>("/api/agents/sync", {
    method: "POST",
  });
}

export async function createBasicAgent(payload: {
  agent_id: string;
  agent_name: string;
  role_summary: string;
  core_work: string[];
}) {
  return request<BasicAgentCreateResponse>("/api/agents/basic-create", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function connectAgentFeishuChannel(
  agentId: string,
  payload: { app_id: string; app_secret: string; operator_open_id?: string | null; identity_key?: string | null },
) {
  return request<ConnectAgentFeishuChannelResponse>(`/api/agents/${agentId}/channels/feishu`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function confirmAgentFeishuPairing(
  agentId: string,
  payload: { pairing_text: string },
) {
  return request<import("./types").AgentFeishuPairingConfirmResult>(
    `/api/agents/${agentId}/channels/feishu/pairing-confirm`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function getFirstLobsterBootstrapPreview(): Promise<FirstLobsterBootstrapPreview> {
  return request<FirstLobsterBootstrapPreview>("/api/agents/empty-state/bootstrap-preview");
}

export async function claimFirstLobster(payload: {
  selected_channels: Array<"feishu" | "telegram" | "discord" | "weixin">;
  primary_channel?: "feishu" | "telegram" | "discord" | "weixin" | null;
  agent_name?: string | null;
  feishu?: { app_id: string; app_secret: string } | null;
  telegram?: { bot_token: string } | null;
  discord?: { token: string } | null;
  weixin?: { account_id: string } | null;
}): Promise<ClaimFirstLobsterResult> {
  return request<ClaimFirstLobsterResult>("/api/agents/claim-first-lobster", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function startFirstLobsterAutoClaim(payload: {
  app_name: string;
  app_description?: string | null;
  menu_name?: string | null;
  timeout_sec?: number;
  trace_id?: string | null;
}): Promise<FirstLobsterAutoClaimRun> {
  return request<FirstLobsterAutoClaimRun>("/api/agents/claim-first-lobster/auto-run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getFirstLobsterAutoClaimRun(jobId: string): Promise<FirstLobsterAutoClaimRun> {
  return request<FirstLobsterAutoClaimRun>(`/api/agents/claim-first-lobster/auto-run/${jobId}`);
}

export async function confirmFirstLobsterFeishuPairing(payload: {
  agent_id: string;
  pairing_text: string;
}): Promise<FirstLobsterFeishuPairingConfirmResult> {
  return request<FirstLobsterFeishuPairingConfirmResult>("/api/agents/claim-first-lobster/feishu-pairing-confirm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getSetupStatus() {
  return request<SetupStatus>("/api/setup/status");
}

export async function getControlPlaneStatus() {
  return request<Record<string, unknown>>("/api/control-plane/status");
}

export async function getControlPlaneDoctor() {
  return request<Record<string, unknown>>("/api/control-plane/doctor");
}

export async function startControlPlaneAction(
  action: "bootstrap" | "repair_local" | "repair_tunnel" | "install_openclaw" | "update_status" | "update_install",
) {
  return request<ControlPlaneActionAccepted>("/api/control-plane/actions", {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export async function getControlPlaneAction(jobId: string) {
  return request<ControlPlaneJobStatus>(`/api/control-plane/actions/${encodeURIComponent(jobId)}`);
}

export async function getBootstrapAccount() {
  return request<{ username: string; temp_password?: string | null; created_at?: string | null; revealed_at?: string | null }>(
    "/api/auth/bootstrap",
  );
}

export async function loginAccount(payload: { username: string; password: string }) {
  return request<{ account: Account; token: string; expires_at: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function logoutAccount() {
  return request<{ ok: boolean }>("/api/auth/logout", {
    method: "POST",
  });
}

export async function changePassword(payload: { current_password?: string | null; new_password: string }) {
  return request<Account>("/api/auth/password/change", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listAccounts(): Promise<Account[]> {
  const data = await request<{ items: Account[] }>("/api/accounts");
  return data.items;
}

export async function createAccount(payload: {
  username: string;
  display_name: string;
  email?: string | null;
  role_ids: string[];
}) {
  return request<{ account: Account; temp_password: string }>("/api/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccountRoles(accountId: string, payload: { role_ids: string[] }) {
  return request<Account>(`/api/accounts/${accountId}/roles`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getAccountAccess(accountId: string) {
  return request<AccountAccess>(`/api/accounts/${accountId}/access`);
}

export async function updateAccountAccess(
  accountId: string,
  payload: { role_ids: string[]; manual_permission_ids: string[] },
) {
  return request<AccountAccess>(`/api/accounts/${accountId}/access`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function disableAccount(accountId: string) {
  return request<Account>(`/api/accounts/${accountId}/disable`, { method: "POST" });
}

export async function enableAccount(accountId: string) {
  return request<Account>(`/api/accounts/${accountId}/enable`, { method: "POST" });
}

export async function resetAccountPassword(accountId: string) {
  return request<{ account: Account; temp_password: string }>(`/api/accounts/${accountId}/reset-password`, {
    method: "POST",
  });
}

export async function forceLogoutAccount(accountId: string) {
  return request<Account>(`/api/accounts/${accountId}/force-logout`, { method: "POST" });
}

export async function deleteAccount(accountId: string) {
  return request<{ ok: boolean }>(`/api/accounts/${accountId}`, { method: "DELETE" });
}

export async function listRoles(): Promise<Role[]> {
  const data = await request<{ items: Role[] }>("/api/roles");
  return data.items;
}

export async function createRole(payload: {
  name: string;
  description?: string | null;
  permission_ids: string[];
}) {
  return request<{ role: Role; permission_ids: string[] }>("/api/roles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateRole(roleId: string, payload: { name: string; description?: string | null }) {
  return request<Role>(`/api/roles/${roleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteRole(roleId: string) {
  return request<{ ok: boolean }>(`/api/roles/${roleId}`, { method: "DELETE" });
}

export async function listPermissions(): Promise<Permission[]> {
  const data = await request<{ items: Permission[] }>("/api/permissions");
  return data.items;
}

export async function listRolePermissions(): Promise<Record<string, string[]>> {
  const data = await request<{ mapping: Record<string, string[]> }>("/api/roles/permissions");
  return data.mapping;
}

export async function updateRolePermissions(roleId: string, permissionIds: string[]) {
  return request<{ role_id: string; permission_ids: string[] }>(`/api/roles/${roleId}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ permission_ids: permissionIds }),
  });
}

export async function listAuditLogs(limit = 200): Promise<AuditLog[]> {
  const data = await request<{ items: AuditLog[] }>(`/api/audit-logs?limit=${limit}`);
  return data.items;
}

export async function listDiagnosticLogs(params?: {
  limit?: number;
  source?: "client" | "server";
  category?: string;
  trace_id?: string;
}): Promise<DiagnosticLog[]> {
  const query = new URLSearchParams();
  query.set("limit", String(params?.limit || 200));
  if (params?.source) query.set("source", params.source);
  if (params?.category) query.set("category", params.category);
  if (params?.trace_id) query.set("trace_id", params.trace_id);
  const data = await request<{ items: DiagnosticLog[] }>(`/api/diagnostic-logs?${query.toString()}`);
  return data.items;
}

export async function getSystemSettings(): Promise<SystemSettings> {
  return request<SystemSettings>("/api/system-settings");
}

export async function updateSystemCurrency(payload: { currency_preference: SystemSettings["currency_preference"] }) {
  return request<SystemSettings>("/api/system-settings/currency", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function refreshExchangeRate() {
  return request<SystemSettings>("/api/system-settings/exchange-rate/refresh", {
    method: "POST",
  });
}

export async function updateSystemStatusAliases(payload: {
  working?: string | null;
  idle?: string | null;
  offline?: string | null;
  crashed?: string | null;
}) {
  return request<SystemSettings>("/api/system-settings/status-aliases", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getGatewaySettings() {
  return request<GatewaySettings>("/api/system-settings/gateway");
}

export async function updateGatewaySettings(payload: {
  mode_preference?: "auto" | "existing-proxy" | "caddy" | "public-port";
  domain?: string | null;
  ssl_email?: string | null;
  public_host_ip?: string | null;
  public_web_port: number;
  auto_https: boolean;
}) {
  return request<GatewaySettings>("/api/system-settings/gateway", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function applyGatewaySettings() {
  return request<GatewayApplyAccepted>("/api/system-settings/gateway/apply", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function getGatewayApplyJob(jobId: string) {
  return request<GatewayJobStatus>(`/api/system-settings/gateway/jobs/${encodeURIComponent(jobId)}`);
}

export async function getNodes() {
  return request<NodeConnectionsResponse>("/api/nodes");
}

export async function createNode(payload: {
  display_name: string;
  node_type: "vps" | "linux" | "macos";
  expected_openclaw_root: string;
}) {
  return request<NodeBootstrapResult>("/api/nodes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function rotateNodeToken(nodeId: string) {
  return request<NodeBootstrapResult>(`/api/nodes/${nodeId}/token`, {
    method: "POST",
  });
}

export async function getTasks(): Promise<Task[]> {
  const data = await request<{ items: Task[] }>("/api/tasks?page=1&page_size=100");
  return data.items;
}

export async function getTrainingRuns(): Promise<TrainingRun[]> {
  const data = await request<{ items: TrainingRun[] }>("/api/training/runs");
  return data.items;
}

export async function getTrainingModuleOverview() {
  return request<TrainingModuleOverview>("/api/training/module");
}

export async function getLeaderboard(): Promise<LeaderboardEntry[]> {
  const data = await request<{ items: LeaderboardEntry[] }>("/api/leaderboard?period=all");
  return data.items;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const [agents, tasks, training, leaderboard] = await Promise.all([
    getAgents(),
    getTasks(),
    getTrainingRuns(),
    getLeaderboard(),
  ]);

  return {
    agentTotal: agents.length,
    taskTotal: tasks.length,
    trainingTotal: training.length,
    topPoints: leaderboard[0]?.points ?? 0,
  };
}

export async function postTask(payload: Record<string, JsonValue>) {
  return request<Task>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function dispatchTask(taskId: string, mode: "send" | "spawn") {
  return request<{ task_id: string; mode: "send" | "spawn" }>(`/api/tasks/${taskId}/dispatch`, {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
}

export async function submitTask(taskId: string, actorAgentId: string, summary: string) {
  return request<Task>(`/api/tasks/${taskId}/submit`, {
    method: "POST",
    body: JSON.stringify({ actor_agent_id: actorAgentId, summary, evidence_links: [] }),
  });
}

export async function reviewTask(taskId: string, payload: Record<string, JsonValue>) {
  return request<{ score_ledger_written: boolean }>(`/api/tasks/${taskId}/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function onboardingConfirm(payload: Record<string, JsonValue>) {
  return request<{ job_id: string }>("/api/onboarding/confirm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createTrainingRun(payload: Record<string, JsonValue>) {
  return request<TrainingRun>("/api/training/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function gateTrainingRun(
  runId: string,
  payload: { result: "GRADUATE" | "REMEDIATE"; score: number; report_url: string | null },
) {
  return request<TrainingRun>(`/api/training/runs/${runId}/gate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function startAgentSceneGeneration(agentId: string, force = false) {
  return request<AgentSceneJob>(`/api/agents/${agentId}/scenes/generate`, {
    method: "POST",
    body: JSON.stringify({ force }),
  });
}

export async function getAgentSceneGenerationJob(agentId: string, jobId: string) {
  return request<AgentSceneJob>(`/api/agents/${agentId}/scenes/jobs/${jobId}`);
}

export async function getLatestAgentSceneGenerationJob(agentId: string) {
  return request<AgentSceneJob>(`/api/agents/${agentId}/scenes/job-latest`);
}

export async function getAgentWorkspaceDirectory(agentId: string, path = "") {
  const search = new URLSearchParams();
  if (path) search.set("path", path);
  const query = search.toString();
  return request<AgentWorkspaceDirectory>(`/api/agents/${agentId}/workspace${query ? `?${query}` : ""}`);
}

export async function getAgentWorkspaceFile(agentId: string, path: string) {
  const search = new URLSearchParams({ path });
  return request<AgentWorkspaceFile>(`/api/agents/${agentId}/workspace/file?${search.toString()}`);
}

export async function getOpenClawDirectory(path = "") {
  const search = new URLSearchParams();
  if (path) search.set("path", path);
  const query = search.toString();
  return request<OpenClawRootDirectory>(`/api/openclaw/explorer${query ? `?${query}` : ""}`);
}

export async function getOpenClawFile(path: string) {
  const search = new URLSearchParams({ path });
  return request<OpenClawRootFile>(`/api/openclaw/explorer/file?${search.toString()}`);
}

export async function getRescueCenterReadiness() {
  return request<RescueCenterReadiness>("/api/rescue-center/readiness");
}

export async function getRescueCenterBootstrap() {
  return request<RescueCenterBootstrap>("/api/rescue-center/bootstrap");
}

export async function listRescueCenterThreads() {
  return request<RescueCenterThreadListResponse>("/api/rescue-center/threads");
}

export async function createRescueCenterThread() {
  return request<{ thread: RescueCenterThreadDetail }>("/api/rescue-center/threads/new", {
    method: "POST",
  });
}

export async function activateRescueCenterThread(threadId: string) {
  return request<{ thread: RescueCenterThreadDetail }>("/api/rescue-center/threads/activate", {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId }),
  });
}

export async function getRescueCenterThread(threadId: string) {
  return request<{ thread: RescueCenterThreadDetail }>(
    `/api/rescue-center/threads/${encodeURIComponent(threadId)}`,
  );
}

export async function resetRescueCenterThreads() {
  return request<{ status: "reset"; cleared_count: number }>("/api/rescue-center/threads/reset", {
    method: "POST",
  });
}

export async function sendRescueCenterMessage(payload: { thread_id?: string | null; message: string; trace_id?: string | null }) {
  return request<{ thread: RescueCenterThreadDetail }>("/api/rescue-center/messages", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function dispatchRescueCenterMessage(payload: { thread_id?: string | null; message: string; trace_id?: string | null }) {
  return request<RescueCenterMessageDispatch>("/api/rescue-center/messages/dispatch", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getRescueCenterEvents(
  threadId: string,
  options?: { afterSeq?: number; waitMs?: number },
) {
  const search = new URLSearchParams({
    thread_id: threadId,
    after_seq: String(options?.afterSeq ?? 0),
    wait_ms: String(options?.waitMs ?? 0),
  });
  return request<RescueCenterEventListResponse>(`/api/rescue-center/events?${search.toString()}`);
}

export async function updateAgentWorkspaceFile(agentId: string, path: string, content: string) {
  return request<AgentWorkspaceFile>(`/api/agents/${agentId}/workspace/file`, {
    method: "PUT",
    body: JSON.stringify({ path, content }),
  });
}

export async function createAgentWorkspaceFile(agentId: string, path: string, content = "") {
  return request<AgentWorkspaceFile>(`/api/agents/${agentId}/workspace/file`, {
    method: "POST",
    body: JSON.stringify({ path, content }),
  });
}

export interface GeneratedProfileFile {
  path: string;
  content: string;
  existing_content: string | null;
  exists: boolean;
}

export interface GenerateAgentProfileResponse {
  agent_id: string;
  agent_name: string;
  executor_agent_id: string;
  files: GeneratedProfileFile[];
}

export async function generateAgentProfile(
  agentId: string,
  payload: { executor_agent_id: string; agent_name: string; role_summary: string; core_work: string[] },
) {
  return request<GenerateAgentProfileResponse>(`/api/agents/${agentId}/profile/generate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function importAgentSkillZip(agentId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);

  return request<AgentSkillImportResult>(`/api/agents/${agentId}/skills/import-zip`, {
    method: "POST",
    body: formData,
  });
}

export async function importAgentSkillGithub(
  agentId: string,
  payload: { url: string; target_name?: string },
) {
  return request<AgentSkillImportResult>(`/api/agents/${agentId}/skills/import-github`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteAgentSkill(agentId: string, skillName: string) {
  return request<AgentSkillDeleteResult>(
    `/api/agents/${agentId}/skills/${encodeURIComponent(skillName)}`,
    {
      method: "DELETE",
    },
  );
}

export async function getLobsterToolkitSources(params?: {
  tool_kind?: "skill" | "cli";
  source_scope?: "system" | "user";
  q?: string;
  auto_refresh?: boolean;
}) {
  const search = new URLSearchParams();
  if (params?.tool_kind) search.set("tool_kind", params.tool_kind);
  if (params?.source_scope) search.set("source_scope", params.source_scope);
  if (params?.q) search.set("q", params.q);
  if (params?.auto_refresh) search.set("auto_refresh", "1");
  const suffix = search.toString();
  return request<import("./types").LobsterToolkitListResponse>(
    `/api/lobster-toolkit/sources${suffix ? `?${suffix}` : ""}`,
  );
}

export async function createLobsterToolkitSource(payload: {
  tool_kind: "skill" | "cli";
  delivery_kind: "skill" | "openclaw_extension" | "standalone_cli";
  provider?: "manual" | "github" | "clawhub" | "skills_sh";
  name: string;
  slug?: string;
  brand?: string | null;
  brand_bg_color?: string | null;
  brand_text_color?: string | null;
  remote_url: string;
  ref?: string | null;
  summary?: string | null;
  enabled?: boolean;
  tutorial_metadata?: Record<string, unknown>;
}) {
  return request<import("./types").LobsterToolkitSource>("/api/lobster-toolkit/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateLobsterToolkitSource(
  sourceId: string,
  payload: {
    tool_kind: "skill" | "cli";
    delivery_kind: "skill" | "openclaw_extension" | "standalone_cli";
    provider?: "manual" | "github" | "clawhub" | "skills_sh";
    name: string;
    slug?: string;
    brand?: string | null;
    brand_bg_color?: string | null;
    brand_text_color?: string | null;
    remote_url: string;
    ref?: string | null;
    summary?: string | null;
    enabled?: boolean;
    tutorial_metadata?: Record<string, unknown>;
  },
) {
  return request<import("./types").LobsterToolkitSource>(`/api/lobster-toolkit/sources/${encodeURIComponent(sourceId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteLobsterToolkitSource(sourceId: string) {
  return request<import("./types").LobsterToolkitDeleteSourceResponse>(
    `/api/lobster-toolkit/sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" },
  );
}

export async function refreshLobsterToolkitSource(payload: {
  source_scope: "system" | "user";
  source_key: string;
}) {
  return request<import("./types").LobsterToolkitSource>("/api/lobster-toolkit/sources/refresh", {
    method: "POST",
    body: JSON.stringify({ ...payload, targets: [] }),
  });
}

export async function searchLobsterToolkitSkills(payload: {
  provider: "github" | "clawhub" | "skills_sh";
  q: string;
  limit?: number;
}) {
  const search = new URLSearchParams({
    provider: payload.provider,
    q: payload.q,
  });
  if (payload.limit) search.set("limit", String(payload.limit));
  return request<import("./types").LobsterToolkitSearchResponse>(`/api/lobster-toolkit/search?${search.toString()}`);
}

export async function dispatchLobsterToolkitSource(payload: {
  source_scope: "system" | "user";
  source_key: string;
  targets: Array<{ target_scope: "shared" | "agent"; target_agent_id?: string | null }>;
}) {
  return request<import("./types").LobsterToolkitDispatchResponse>("/api/lobster-toolkit/dispatch", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateLobsterToolkitSourceDeployments(payload: {
  source_scope: "system" | "user";
  source_key: string;
  deployment_ids?: string[];
  targets?: Array<{ target_scope: "shared" | "agent"; target_agent_id?: string | null }>;
}) {
  return request<import("./types").LobsterToolkitDispatchResponse>("/api/lobster-toolkit/update", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteLobsterToolkitDeployment(deploymentId: string) {
  return request<import("./types").LobsterToolkitDeleteDeploymentResponse>(
    `/api/lobster-toolkit/deployments/${encodeURIComponent(deploymentId)}`,
    { method: "DELETE" },
  );
}

export async function getAgentPortablePackagePreview(agentId: string) {
  return request<AgentPortablePackagePreview>(`/api/agents/${agentId}/export-package/preview`);
}

export async function downloadAgentPortablePackage(agentId: string) {
  const response = await fetch(resolveApiUrl(`/api/agents/${agentId}/export-package`), {
    method: "POST",
    cache: "no-store",
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as {
      detail?: { message?: string };
      message?: string;
    };
    throw new Error(readDetailMessage(data.detail) || data?.message || tRuntime("api.exportPackageFailed"));
  }
  const blob = await response.blob();
  const contentDisposition = response.headers.get("Content-Disposition") || "";
  const match =
    contentDisposition.match(/filename="([^"]+)"/i) || contentDisposition.match(/filename=([^;]+)/i);
  const fileName = match?.[1]?.replace(/^["']|["']$/g, "") || `${agentId}-portable-package.zip`;
  return { blob, fileName };
}

export async function getAgentActivityLog(agentId: string, limit = 80) {
  return request<AgentActivityLog>(`/api/agents/${agentId}/activity-log?limit=${limit}`);
}

export async function getAgentScheduledJobs(agentId: string) {
  return request<AgentScheduledJobsResponse>(`/api/agents/${agentId}/scheduled-jobs`);
}

export async function updateAgentScheduledJob(
  agentId: string,
  jobId: string,
  payload: {
    name?: string | null;
    description?: string | null;
    schedule_kind: AgentScheduledJob["schedule_kind"];
    enabled?: boolean | null;
    cron_expr?: string | null;
    every_ms?: number | null;
    at?: string | null;
    content: string;
    delivery_channel?: AgentScheduledJob["delivery_channel"] | null;
    delivery_mode?: string | null;
    delivery_target?: Record<string, string | string[]> | null;
    delivery_bootstrap_enabled?: boolean | null;
    delivery_bootstrap_scope?: AgentScheduledJob["delivery_bootstrap_scope"] | null;
    template_kind?: AgentScheduledJob["template_kind"] | null;
    template_title?: string | null;
    template_summary?: string | null;
    template_body?: string | null;
    template_footer?: string | null;
    template_accent?: string | null;
    template_show_sender?: boolean | null;
    template_mentions?: string[] | null;
  },
) {
  return request<AgentScheduledJob>(`/api/agents/${agentId}/scheduled-jobs/${encodeURIComponent(jobId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function createAgentScheduledJob(
  agentId: string,
  payload: {
    name: string;
    description?: string | null;
    enabled?: boolean;
    schedule_kind: AgentScheduledJob["schedule_kind"];
    cron_expr?: string | null;
    every_ms?: number | null;
    at?: string | null;
    content: string;
    delivery_channel?: AgentScheduledJob["delivery_channel"] | null;
    delivery_mode?: string | null;
    delivery_target?: Record<string, string | string[]> | null;
    delivery_bootstrap_enabled?: boolean;
    delivery_bootstrap_scope?: AgentScheduledJob["delivery_bootstrap_scope"] | null;
    template_kind?: AgentScheduledJob["template_kind"] | null;
    template_title?: string | null;
    template_summary?: string | null;
    template_body?: string | null;
    template_footer?: string | null;
    template_accent?: string | null;
    template_show_sender?: boolean;
    template_mentions?: string[] | null;
  },
) {
  return request<AgentScheduledJob>(`/api/agents/${agentId}/scheduled-jobs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getScheduledJobsTimeline(params?: {
  from_at?: string;
  to_at?: string;
  agent_ids?: string[];
}) {
  const search = new URLSearchParams();
  if (params?.from_at) search.set("from_at", params.from_at);
  if (params?.to_at) search.set("to_at", params.to_at);
  for (const agentId of params?.agent_ids || []) {
    if (agentId) search.append("agent_ids", agentId);
  }
  const query = search.toString();
  return request<ScheduledJobsTimelineResponse>(`/api/scheduled-jobs/timeline${query ? `?${query}` : ""}`);
}

export async function sendWorkspaceInstruction(
  agentId: string,
  payload: {
    path: string;
    target_agent_id: string;
    instruction: string;
    sender_agent_id?: string;
  },
) {
  return request<SendWorkspaceInstructionResult>(`/api/agents/${agentId}/workspace/send-instruction`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getAgentUserAuthState(agentId: string) {
  return request<AgentUserAuthState>(`/api/agents/${agentId}/user-auth/state`);
}

export async function startAgentUserAuth(agentId: string) {
  return request<StartAgentUserAuthResult>(`/api/agents/${agentId}/user-auth/start`, {
    method: "POST",
  });
}

export interface WeixinQrStartResult {
  session_id: string;
  qr_url: string;
  expires_at: string;
}

export type WeixinQrStatus = "waiting" | "scanned" | "confirmed" | "expired" | "error";

export interface WeixinQrPollResult {
  status: WeixinQrStatus;
  account_id: string | null;
  message: string | null;
}

export async function startWeixinQrLogin() {
  return request<WeixinQrStartResult>("/api/first-lobster/weixin/start-qr", {
    method: "POST",
  });
}

export async function pollWeixinQrLogin(sessionId: string) {
  return request<WeixinQrPollResult>(`/api/first-lobster/weixin/poll-qr/${sessionId}`);
}

export interface WeixinBridgeStatusResult {
  running: boolean;
  pid: number | null;
  uptime_seconds: number | null;
  message: string | null;
}

export async function getWeixinBridgeStatus() {
  return request<WeixinBridgeStatusResult>("/api/weixin-bridge/status");
}

export async function startWeixinBridge() {
  return request<{ status: string; pid: number | null; message: string | null }>(
    "/api/weixin-bridge/start",
    { method: "POST" },
  );
}

export async function stopWeixinBridge() {
  return request<{ status: string; message: string | null }>(
    "/api/weixin-bridge/stop",
    { method: "POST" },
  );
}
