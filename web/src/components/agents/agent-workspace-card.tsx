"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { startTransition, useEffect, useState } from "react";
import {
  DownloadSimpleIcon,
  FolderOpenIcon,
  GearSixIcon,
  GraduationCapIcon,
  RobotIcon,
  SparkleIcon,
} from "@phosphor-icons/react";

import { avatarFromAgent, platformMeta } from "@/lib/agent-presenter";
import { AgentActivityDialog } from "@/components/agents/agent-activity-dialog";
import { AgentChannelConnectDialog } from "@/components/agents/agent-channel-connect-dialog";
import { AgentExportPackageDialog } from "@/components/agents/agent-export-package-dialog";
import { AgentScenePresetsDialog, type ScenePreset } from "@/components/agents/agent-scene-presets-dialog";
import { AgentScheduledJobsDialog } from "@/components/agents/agent-scheduled-jobs-dialog";
import { AgentSkillsDialog } from "@/components/agents/agent-skills-dialog";
import { useI18n } from "@/components/i18n/use-locale";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { updateAgentScenePreset } from "@/lib/api";
import type { Agent, AgentRuntimeStatus, SystemSettings } from "@/lib/types";

type SceneState = "working" | "idle" | "offline" | "crashed";
export type AgentCardViewMode = "patrol" | "manage";

const sceneVisualMap: Record<
  SceneState,
  {
    tone: "active" | "probation" | "suspended";
    fallbackScene: string;
    sceneTone: string;
    cardGlow: string;
    cardRing: string;
    menuTone: string;
    patrolTone: string;
  }
> = {
  working: {
    tone: "active",
    fallbackScene: "/scenes/live-frames/workspace-active-live.gif",
    sceneTone: "from-emerald-900/55 via-transparent to-emerald-900/20",
    cardGlow: "shadow-[0_0_0_1px_rgba(16,185,129,0.32),0_14px_38px_rgba(16,185,129,0.24)]",
    cardRing: "ring-1 ring-emerald-300/55",
    menuTone: "border-emerald-300/85 bg-emerald-50/95 text-emerald-700",
    patrolTone: "border-orange-200/90 bg-orange-50/95 text-orange-800",
  },
  idle: {
    tone: "probation",
    fallbackScene: "/scenes/workspace-probation-ai.png",
    sceneTone: "from-sky-900/55 via-transparent to-sky-900/20",
    cardGlow: "shadow-[0_0_0_1px_rgba(59,130,246,0.30),0_14px_38px_rgba(59,130,246,0.22)]",
    cardRing: "ring-1 ring-sky-300/50",
    menuTone: "border-sky-300/85 bg-sky-50/95 text-sky-700",
    patrolTone: "border-sky-200/90 bg-sky-50/95 text-sky-800",
  },
  offline: {
    tone: "suspended",
    fallbackScene: "/scenes/workspace-suspended-ai.png",
    sceneTone: "from-zinc-900/55 via-transparent to-zinc-900/28",
    cardGlow: "shadow-[0_0_0_1px_rgba(107,114,128,0.36),0_14px_38px_rgba(75,85,99,0.24)]",
    cardRing: "ring-1 ring-zinc-300/45",
    menuTone: "border-zinc-300/85 bg-zinc-50/95 text-zinc-700",
    patrolTone: "border-[#333333]/90 bg-[#333333] text-white",
  },
  crashed: {
    tone: "suspended",
    fallbackScene: "/scenes/workspace-suspended-ai.png",
    sceneTone: "from-rose-950/70 via-transparent to-rose-950/30",
    cardGlow: "shadow-[0_0_0_1px_rgba(239,68,68,0.38),0_14px_38px_rgba(220,38,38,0.24)]",
    cardRing: "ring-1 ring-rose-300/50",
    menuTone: "border-rose-300/85 bg-rose-50/95 text-rose-700",
    patrolTone: "border-rose-200/90 bg-rose-50/95 text-rose-800",
  },
};

function formatRelativeLastActive(value: string | null | undefined, t: (key: string, params?: Record<string, string | number>) => string): string {
  if (!value) return t("agentCard.lastActive.inactive");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return t("agentCard.lastActive.inactive");
  const diff = Date.now() - date.getTime();
  if (diff < 60 * 1000) return t("agentCard.lastActive.justNow");
  if (diff < 60 * 60 * 1000) {
    return t("agentCard.lastActive.minutesAgo", { count: Math.max(1, Math.floor(diff / (60 * 1000))) });
  }
  if (diff < 24 * 60 * 60 * 1000) {
    return t("agentCard.lastActive.hoursAgo", { count: Math.max(1, Math.floor(diff / (60 * 60 * 1000))) });
  }
  if (diff < 30 * 24 * 60 * 60 * 1000) {
    return t("agentCard.lastActive.daysAgo", { count: Math.max(1, Math.floor(diff / (24 * 60 * 60 * 1000))) });
  }
  return t("agentCard.lastActive.monthsAgo", { count: Math.max(1, Math.floor(diff / (30 * 24 * 60 * 60 * 1000))) });
}

function resolveSceneState(agent: Agent): SceneState {
  const runtimeStatus = (agent.runtime_status || "").toLowerCase() as AgentRuntimeStatus | "";
  if (runtimeStatus && runtimeStatus in sceneVisualMap) return runtimeStatus as SceneState;
  if (agent.status === "active") return "working";
  if (agent.status === "probation") return "idle";
  return "offline";
}

function formatTokenCount(
  value: number | null | undefined,
  t: (key: string, params?: Record<string, string | number>) => string,
): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return null;
  if (value >= 1_000_000) return t("agentCard.tokens", { count: `${(value / 1_000_000).toFixed(1)}M` });
  if (value >= 1_000) return t("agentCard.tokens", { count: `${(value / 1_000).toFixed(1)}K` });
  return t("agentCard.tokens", { count: Math.round(value) });
}

function formatUsdCost(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
  if (value === 0) return "$0.00";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

const DEFAULT_USD_CNY_RATE = 7.2;

function formatCnyCost(value: number | null | undefined, locale: string): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
  if (value === 0) return "¥0.00";
  const decimals = value < 0.01 ? 4 : 2;
  return `¥${value.toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function formatCurrencyCost(
  valueUsd: number | null | undefined,
  settings: SystemSettings | null | undefined,
  locale: string,
): string | null {
  if (typeof valueUsd !== "number" || !Number.isFinite(valueUsd) || valueUsd < 0) return null;
  const currency = settings?.currency_preference ?? "CNY";
  if (currency === "USD") return formatUsdCost(valueUsd);
  const rate = settings?.exchange_rate_usd_cny ?? DEFAULT_USD_CNY_RATE;
  return formatCnyCost(valueUsd * rate, locale);
}

function resolveSceneAlias(
  scene: SceneState,
  settings: SystemSettings | null | undefined,
  t: (key: string) => string,
): string {
  const aliases = settings?.status_aliases || {};
  const raw = aliases[scene];
  const cleaned = typeof raw === "string" ? raw.trim() : "";
  if (cleaned) return cleaned;
  if (scene === "working") return t("agentCard.status.working");
  if (scene === "idle") return t("agentCard.status.idle");
  if (scene === "offline") return t("agentCard.status.offline");
  return t("agentCard.status.crashed");
}

function buildScenePresets(t: (key: string) => string): ScenePreset[] {
  return [
    {
      id: "preset-standard",
      name: t("agentCard.presets.lobster"),
      story: t("scenePresets.stories.lobster"),
      posterSrc: "/scenes/presets/lobster/avatar.png",
      sources: {
        working: "/scenes/presets/lobster/working.mp4",
        idle: "/scenes/presets/lobster/idle.mp4",
        offline: "/scenes/presets/lobster/offline.mp4",
        crashed: "/scenes/presets/lobster/crashed.mp4",
      },
    },
    {
      id: "preset-cat-lobster",
      name: t("agentCard.presets.catLobster"),
      story: t("scenePresets.stories.catLobster"),
      posterSrc: "/scenes/presets/cat-lobster/avatar.png",
      sources: {
        working: "/scenes/presets/cat-lobster/working.mp4",
        idle: "/scenes/presets/cat-lobster/idle.mp4",
        offline: "/scenes/presets/cat-lobster/offline.mp4",
        crashed: "/scenes/presets/cat-lobster/crashed.mp4",
      },
    },
    {
      id: "preset-bear-lobster",
      name: t("agentCard.presets.bearLobster"),
      story: t("scenePresets.stories.bearLobster"),
      posterSrc: "/scenes/presets/bear-lobster/avatar.png",
      sources: {
        working: "/scenes/presets/bear-lobster/working.mp4",
        idle: "/scenes/presets/bear-lobster/idle.mp4",
        offline: "/scenes/presets/bear-lobster/offline.mp4",
        crashed: "/scenes/presets/bear-lobster/crashed.mp4",
      },
    },
  ];
}

export function AgentWorkspaceCard({
  agent,
  systemSettings,
  summary,
  viewMode = "manage",
}: {
  agent: Agent;
  systemSettings?: SystemSettings | null;
  summary?: {
    trainingCount?: number;
    scheduledJobCount?: number;
    openTaskCount?: number;
    latestTrainingAt?: string | null;
  } | null;
  viewMode?: AgentCardViewMode;
}) {
  const { locale, t } = useI18n();
  const router = useRouter();
  const [failedSceneKey, setFailedSceneKey] = useState<string | null>(null);
  const [activityOpen, setActivityOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [scheduledJobsOpen, setScheduledJobsOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [channelDialogOpen, setChannelDialogOpen] = useState(false);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const [scenePresetId, setScenePresetId] = useState<string | null>(agent.scene_preset_id ?? null);
  const [applyingPresetId, setApplyingPresetId] = useState<string | null>(null);
  const [presetError, setPresetError] = useState<string | null>(null);

  useEffect(() => {
    setScenePresetId(agent.scene_preset_id ?? null);
  }, [agent.agent_id, agent.scene_preset_id]);

  const sceneState = resolveSceneState(agent);
  const visual = sceneVisualMap[sceneState];
  const scenePresets = buildScenePresets(t);
  const selectedPreset = scenePresets.find((preset) => preset.id === scenePresetId) ?? null;

  const generatedScene = `/api/agents/${agent.agent_id}/scenes/${sceneState}.mp4`;
  const sceneSource =
    selectedPreset?.sources[sceneState] ?? (sceneState === "working" ? generatedScene : visual.fallbackScene);
  const sceneAssetKey = `${agent.agent_id}:${scenePresetId || "live"}:${sceneState}`;
  const shouldUseFallback = failedSceneKey === sceneAssetKey;
  const displayScene = shouldUseFallback ? visual.fallbackScene : sceneSource;

  const roleSummary = agent.role_summary || agent.role || t("agentCard.roleFallback");
  const avatar = avatarFromAgent(agent);
  const lastActiveLabel = formatRelativeLastActive(agent.latest_activity_at, t);
  const primaryPlatform = platformMeta(agent.primary_channel || agent.channel, t);
  const configModelProvider = agent.config_model_provider?.trim() || agent.model_provider?.trim() || null;
  const configModelId = agent.config_model_id?.trim() || agent.model_id?.trim() || null;
  const configModelLabel = agent.config_model_label?.trim() || agent.model_label?.trim() || null;
  const recentModelProvider = agent.recent_model_provider?.trim() || null;
  const recentModelId = agent.recent_model_id?.trim() || null;
  const recentModelLabel = agent.recent_model_label?.trim() || null;
  const tokenLabel = formatTokenCount(agent.usage_total_tokens ?? null, t);
  const costLabel = formatCurrencyCost(agent.estimated_cost_usd ?? null, systemSettings, locale);
  const spendLabel = costLabel
    ? tokenLabel
      ? t("agentCard.spend.costWithTokens", { cost: costLabel, tokens: tokenLabel })
      : costLabel
    : tokenLabel || t("common.placeholder");
  const skillCount = agent.skills?.length || 0;
  const scheduledJobCount = summary?.scheduledJobCount ?? 0;
  const openTaskCount = summary?.openTaskCount ?? 0;
  const trainingCount = summary?.trainingCount ?? 0;
  const channelBadgeLabel =
    agent.channel_status === "missing"
      ? "待配置渠道"
      : agent.channel_status === "warning"
        ? "渠道异常"
        : primaryPlatform.label;
  const channelBadges = (agent.connected_channels || []).map((item) => ({
    ...item,
    meta: platformMeta(item.channel, t),
  }));
  const riskMessages = [
    agent.channel_status === "missing" ? "待配置渠道" : null,
    agent.channel_status === "warning" ? "渠道异常，建议进入渠道管理补齐" : null,
    agent.channel_status !== "missing" && !agent.identity_complete ? "身份配置待补全" : null,
    sceneState === "crashed" ? "最近运行异常" : null,
    sceneState === "offline" ? "当前离线" : null,
    openTaskCount > 0 ? `待处理任务 ${openTaskCount} 项` : null,
    trainingCount === 0 ? "建议继续训练" : null,
  ].filter((item): item is string => Boolean(item));
  const sceneLabels: Record<SceneState, string> = {
    working: resolveSceneAlias("working", systemSettings, t),
    idle: resolveSceneAlias("idle", systemSettings, t),
    offline: resolveSceneAlias("offline", systemSettings, t),
    crashed: resolveSceneAlias("crashed", systemSettings, t),
  };
  const channelEntryLabel = agent.channel_status === "missing" ? "接入渠道" : "管理渠道";
  const patrolDescription = agent.role_summary?.trim() || agent.role?.trim() || "待补充角色描述";

  function handleOpenPresets() {
    setPresetError(null);
    setPresetsOpen(true);
  }

  function handleClosePresets() {
    setPresetsOpen(false);
    setPresetError(null);
  }

  async function handleSelectPreset(preset: ScenePreset) {
    if (applyingPresetId || scenePresetId === preset.id) return;
    const previousPresetId = scenePresetId;
    setPresetError(null);
    setApplyingPresetId(preset.id);
    setScenePresetId(preset.id);

    try {
      const updated = await updateAgentScenePreset(agent.agent_id, preset.id);
      setScenePresetId(updated.scene_preset_id ?? preset.id);
      setPresetsOpen(false);
      startTransition(() => {
        router.refresh();
      });
    } catch (error) {
      setScenePresetId(previousPresetId);
      setPresetError(error instanceof Error ? error.message : t("scenePresets.errors.updateFailed"));
    } finally {
      setApplyingPresetId(null);
    }
  }

  return (
    <>
      <article
        className={`group relative z-0 rounded-2xl border border-[var(--line)] bg-white ${visual.cardRing} ${visual.cardGlow} transition hover:-translate-y-0.5 hover:z-30`}
      >
        <div className="relative border-b border-[var(--line)]">
          <div className="relative overflow-hidden rounded-t-2xl">
            <button
              type="button"
              className="relative block aspect-video w-full text-left"
              onClick={viewMode === "patrol" ? handleOpenPresets : undefined}
              title={viewMode === "patrol" ? t("agentCard.presets.title") : undefined}
            >
              {shouldUseFallback ? (
                // 使用原生 img 显示回退场景
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={displayScene}
                  src={displayScene}
                  alt={t("agentCard.sceneAlt", { name: agent.display_name })}
                  className="h-full w-full object-cover"
                  loading="lazy"
                  decoding="async"
                />
              ) : (
                <video
                  key={displayScene}
                  src={displayScene}
                  poster={selectedPreset?.posterSrc}
                  className="h-full w-full object-cover"
                  autoPlay
                  loop
                  muted
                  playsInline
                  preload="metadata"
                  onError={() => {
                    if (failedSceneKey !== sceneAssetKey) setFailedSceneKey(sceneAssetKey);
                  }}
                />
              )}
              <div className={`absolute inset-0 bg-gradient-to-t ${visual.sceneTone}`} />

              {viewMode === "patrol" ? (
                <div className="absolute right-2.5 top-2.5 z-20">
                  <span className={`inline-flex h-7 items-center rounded-full border px-2.5 text-[10px] font-medium shadow-sm backdrop-blur ${visual.patrolTone}`}>
                    {sceneLabels[sceneState]}
                  </span>
                </div>
              ) : null}

              {viewMode === "manage" ? (
                <>
                  <button
                    type="button"
                    className="absolute left-2.5 top-2.5 inline-flex h-10 max-w-[58%] items-center gap-1.5 rounded-full border border-white/75 bg-white/90 px-2 py-1 text-left text-[var(--text)] shadow-sm backdrop-blur transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/85 focus-visible:ring-offset-2 focus-visible:ring-offset-black/20"
                    onClick={handleOpenPresets}
                    title={t("agentCard.presets.title")}
                    aria-label={`${t("agentCard.presets.title")} · ${agent.display_name}`}
                  >
                    <span className="group/avatar relative h-6 w-6 shrink-0 overflow-hidden rounded-full border border-neutral-300 bg-neutral-100">
                      <Image
                        src={avatar}
                        alt={agent.display_name}
                        width={24}
                        height={24}
                        className="h-full w-full object-cover"
                        unoptimized
                      />
                      <span className="absolute inset-0 flex items-center justify-center bg-black/55 text-[10px] font-medium text-white opacity-0 transition group-hover/avatar:opacity-100">
                        <RobotIcon size={13} />
                      </span>
                    </span>
                    <p className="truncate text-[10px] font-semibold leading-none">{agent.display_name}</p>
                  </button>

                  <button
                    type="button"
                    className="absolute bottom-2.5 right-2.5 z-10 rounded-full border border-white/70 bg-black/45 px-2 py-1 text-[10px] font-medium text-white backdrop-blur transition hover:bg-black/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/85 focus-visible:ring-offset-2 focus-visible:ring-offset-black/20"
                    onClick={() => setActivityOpen(true)}
                    title={t("agentCard.actions.activity")}
                    aria-label={`${t("agentCard.actions.activity")} · ${agent.display_name}`}
                  >
                    {lastActiveLabel}
                  </button>
                </>
              ) : null}
            </button>
          </div>

          {viewMode === "manage" ? (
            <div className="absolute right-2.5 top-2.5 z-20">
              <button
                type="button"
                className={`inline-flex h-10 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-medium shadow-sm backdrop-blur transition hover:brightness-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/85 focus-visible:ring-offset-2 focus-visible:ring-offset-black/20 ${visual.menuTone}`}
                title={channelEntryLabel}
                aria-label={`${channelEntryLabel} · ${agent.display_name}`}
                onClick={() => setChannelDialogOpen(true)}
              >
                <span className="grid h-4 w-4 shrink-0 place-items-center overflow-hidden rounded-[4px] bg-white/80 ring-1 ring-black/5">
                  {primaryPlatform.iconSrc && agent.channel_status !== "missing" ? (
                    <Image
                      src={primaryPlatform.iconSrc}
                      alt={primaryPlatform.label}
                      width={16}
                      height={16}
                      className="h-4 w-4 object-contain"
                      unoptimized
                    />
                  ) : (
                    <span className="text-[9px] font-semibold leading-none">
                      {agent.channel_status === "missing" ? "待" : primaryPlatform.monogram}
                    </span>
                  )}
                </span>
                {channelBadgeLabel}
              </button>
            </div>
          ) : null}
        </div>

        <div className="space-y-2 p-3">
          {viewMode === "patrol" ? (
            <>
              <div className="space-y-1">
                <p className="truncate text-sm font-semibold text-[var(--text)]" title={agent.display_name}>
                  {agent.display_name}
                </p>
                <p className="line-clamp-2 text-[11px] leading-5 text-[var(--muted)]" title={patrolDescription}>
                  {patrolDescription}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 justify-start rounded-2xl px-3 text-[11px]"
                  onClick={() => setActivityOpen(true)}
                >
                  {lastActiveLabel}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 justify-start rounded-2xl px-3 text-[11px]"
                  onClick={() => setChannelDialogOpen(true)}
                >
                  <span className="grid h-4 w-4 shrink-0 place-items-center overflow-hidden rounded-[4px] bg-white ring-1 ring-black/5">
                    {primaryPlatform.iconSrc && agent.channel_status !== "missing" ? (
                      <Image
                        src={primaryPlatform.iconSrc}
                        alt={primaryPlatform.label}
                        width={16}
                        height={16}
                        className="h-4 w-4 object-contain"
                        unoptimized
                      />
                    ) : (
                      <span className="text-[9px] font-semibold leading-none">
                        {agent.channel_status === "missing" ? "待" : primaryPlatform.monogram}
                      </span>
                    )}
                  </span>
                  {channelBadgeLabel}
                </Button>
              </div>
            </>
          ) : (
            <div className="flex items-start gap-3">
              <p
                className="line-clamp-2 min-w-0 flex-1 text-[10.5px] leading-4 text-neutral-800"
                title={roleSummary}
              >
                {roleSummary}
              </p>
            </div>
          )}
          {viewMode === "manage" ? (
            <>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="neutral">技能 {skillCount}</Badge>
                <Badge variant="neutral">任务 {scheduledJobCount}</Badge>
                <Badge variant="neutral">协作 {openTaskCount}</Badge>
                <Badge variant="neutral">训练 {trainingCount}</Badge>
                {agent.identity_complete ? <Badge variant="neutral">配置完成</Badge> : <Badge variant="suspended">待补配置</Badge>}
              </div>
              <div className="space-y-1.5">
                <p className="text-[10px] text-[var(--muted)]">渠道状态</p>
                <div className="flex flex-wrap gap-1.5">
                  {agent.channel_status === "missing" ? <Badge variant="suspended">待配置渠道</Badge> : null}
                  {agent.channel_status === "warning" ? <Badge variant="probation">渠道异常</Badge> : null}
                  {channelBadges.map((item) => (
                    <Badge key={`${item.channel}:${item.account_id || "none"}`} variant="neutral">
                      {item.primary ? "主渠道 · " : ""}
                      {item.meta.label}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5">
                <p className="text-[10px] text-[var(--muted)]">{t("agentCard.model.currentLabel")}</p>
                <div
                  className="flex flex-wrap items-center gap-1.5"
                  title={configModelLabel || undefined}
                >
                  {configModelProvider ? <Badge variant="neutral">{configModelProvider}</Badge> : null}
                  {configModelId ? <Badge variant="neutral">{configModelId}</Badge> : null}
                  {!configModelProvider && !configModelId ? (
                    <Badge variant="neutral">{configModelLabel || t("agentCard.model.pending")}</Badge>
                  ) : null}
                </div>
              </div>
              <p
                className="text-[10px] leading-4 text-[var(--muted)]"
                title={recentModelLabel || undefined}
              >
                {t("agentCard.model.recentLabel")}{" "}
                {recentModelLabel ||
                  (recentModelProvider && recentModelId
                    ? `${recentModelProvider}/${recentModelId}`
                    : recentModelProvider || recentModelId || t("agentCard.model.noRecord"))}
              </p>
              <p
                className="text-[10px] leading-4 text-[var(--muted)]"
                title={configModelLabel || undefined}
              >
                {t("agentCard.spend.label", { value: spendLabel })}
              </p>
              {riskMessages.length ? (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-700">当前提醒</p>
                  <div className="mt-2 space-y-1 text-[10px] leading-4 text-amber-800">
                    {riskMessages.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button
                  type="button"
                  variant="outline"
                  className="justify-start rounded-2xl"
                  onClick={() => router.push(`/agents/${agent.agent_id}/workspace`)}
                >
                  <FolderOpenIcon size={14} />
                  工区
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="justify-start rounded-2xl"
                  onClick={() => router.push("/agent-configs")}
                >
                  <GearSixIcon size={14} />
                  配置
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="justify-start rounded-2xl"
                  onClick={() => router.push("/training")}
                >
                  <GraduationCapIcon size={14} />
                  培训
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="justify-start rounded-2xl"
                  onClick={() => setExportOpen(true)}
                >
                  <DownloadSimpleIcon size={14} />
                  导出
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="justify-start rounded-2xl"
                  onClick={() => setChannelDialogOpen(true)}
                >
                  <SparkleIcon size={14} />
                  {channelEntryLabel}
                </Button>
              </div>
              <Button
                type="button"
                variant="outline"
                className="w-full justify-start rounded-2xl text-[11px]"
                onClick={() => router.push("/tasks")}
              >
                <SparkleIcon size={14} />
                交给其他 Agent 优化
              </Button>
            </>
          ) : null}
        </div>

        <AgentActivityDialog agent={agent} open={activityOpen} onClose={() => setActivityOpen(false)} />
        <AgentScenePresetsDialog
          open={presetsOpen}
          onClose={handleClosePresets}
          presets={scenePresets}
          sceneLabels={sceneLabels}
          selectedPresetId={scenePresetId}
          applyingPresetId={applyingPresetId}
          errorMessage={presetError}
          onSelectPreset={handleSelectPreset}
        />
        <AgentSkillsDialog agent={agent} open={skillsOpen} onClose={() => setSkillsOpen(false)} />
        <AgentScheduledJobsDialog
          agent={agent}
          open={scheduledJobsOpen}
          onClose={() => setScheduledJobsOpen(false)}
        />
        <AgentExportPackageDialog agent={agent} open={exportOpen} onClose={() => setExportOpen(false)} />
        <AgentChannelConnectDialog agent={agent} open={channelDialogOpen} onOpenChange={setChannelDialogOpen} />
      </article>
    </>
  );
}
