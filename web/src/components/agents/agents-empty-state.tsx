"use client";

import { startTransition, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";

import { useI18n } from "@/components/i18n/use-locale";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ApiError,
  claimFirstLobster,
  confirmFirstLobsterFeishuPairing,
  getFirstLobsterAutoClaimRun,
  getFirstLobsterBootstrapPreview,
  pollWeixinQrLogin,
  startFirstLobsterAutoClaim,
  startWeixinQrLogin,
  type WeixinQrPollResult,
  type WeixinQrStartResult,
} from "@/lib/api";
import { buildAuthRedirectPath } from "@/lib/auth-session";
import { createDiagnosticTraceId, recordClientDiagnosticLog } from "@/lib/diagnostics";
import type {
  FirstLobsterAutoClaimRun,
  FirstLobsterBootstrapPreview,
  FirstLobsterChannel,
  FirstLobsterFeishuPairingConfirmResult,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type ChannelVisual = {
  iconSrc: string;
  iconShell: string;
  iconClass?: string;
  outline: string;
};
type ClaimLobsterEntryVariant = "empty" | "toolbar";
type ClaimLobsterStep = "name" | "channel" | "pairingHello" | "pairingPaste";

const VISIBLE_FIRST_LOBSTER_CHANNELS: FirstLobsterChannel[] = ["feishu", "weixin"];
const VISIBLE_FIRST_LOBSTER_CHANNEL_SET = new Set<FirstLobsterChannel>(VISIBLE_FIRST_LOBSTER_CHANNELS);
const CHANNEL_ORDER: FirstLobsterChannel[] = [...VISIBLE_FIRST_LOBSTER_CHANNELS];

const CHANNEL_VISUALS: Record<FirstLobsterChannel, ChannelVisual> = {
  feishu: {
    iconSrc: "/platforms/feishu.png",
    iconShell: "bg-[#eef4ff]",
    outline: "border-[#3370ff]/30",
  },
  weixin: {
    iconSrc: "/platforms/wechat.svg",
    iconShell: "bg-[#ebf8e5]",
    outline: "border-[#07c160]/30",
  },
  telegram: {
    iconSrc: "/platforms/telegram.svg",
    iconShell: "bg-white",
    outline: "border-[#2aabee]/28",
  },
  discord: {
    iconSrc: "/platforms/discord.svg",
    iconShell: "bg-[#5865f2]",
    iconClass: "h-4 w-5",
    outline: "border-[#5865f2]/26",
  },
};

const ACTIVE_CLAIM_RUN_STATUSES = new Set<FirstLobsterAutoClaimRun["status"]>(["queued", "waiting_login", "claiming"]);
const FEISHU_PAIRING_STEP_ORDER: ClaimLobsterStep[] = ["name", "channel", "pairingHello", "pairingPaste"];
const DEFAULT_STEP_ORDER: ClaimLobsterStep[] = ["name", "channel"];

function PlatformIcon({
  channel,
  label,
  className,
}: {
  channel: FirstLobsterChannel;
  label: string;
  className?: string;
}) {
  const visual = CHANNEL_VISUALS[channel];
  return (
    <span
      className={cn(
        "flex h-12 w-12 items-center justify-center rounded-[18px] border border-white/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]",
        visual.iconShell,
        className,
      )}
    >
      <Image
        src={visual.iconSrc}
        alt={label}
        width={24}
        height={24}
        className={cn("h-6 w-6 object-contain", visual.iconClass)}
      />
    </span>
  );
}

function StepSection({
  step,
  title,
  description,
  children,
  className,
}: {
  step: string;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-[24px] border border-[var(--line)] bg-white/92 p-4 shadow-[0_10px_24px_rgba(15,23,42,0.045)]",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-[var(--brand-ink)] text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,23,42,0.16)]">
          {step}
        </span>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="space-y-1">
            <h3 className="text-[20px] font-semibold text-[var(--text)]">{title}</h3>
            {description ? <p className="text-[13px] leading-6 text-[var(--muted)]">{description}</p> : null}
          </div>
          {children}
        </div>
      </div>
    </section>
  );
}

function ClaimLobsterEntry({ variant }: { variant: ClaimLobsterEntryVariant }) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [preview, setPreview] = useState<FirstLobsterBootstrapPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [openclawName, setOpenclawName] = useState("ClawPilot");
  const [primaryChannel, setPrimaryChannel] = useState<FirstLobsterChannel>("feishu");
  const [currentStep, setCurrentStep] = useState<ClaimLobsterStep>("name");
  const [formError, setFormError] = useState<string | null>(null);
  const [claimRun, setClaimRun] = useState<FirstLobsterAutoClaimRun | null>(null);
  const [claimTraceId, setClaimTraceId] = useState<string | null>(null);
  const suggestedAppNameRef = useRef("ClawPilot");
  const loggedRunStateRef = useRef<string | null>(null);
  const [submittingDirectClaim, setSubmittingDirectClaim] = useState(false);
  const [weixinQr, setWeixinQr] = useState<WeixinQrStartResult | null>(null);
  const [weixinQrStatus, setWeixinQrStatus] = useState<WeixinQrPollResult["status"] | null>(null);
  const [weixinAccountId, setWeixinAccountId] = useState<string | null>(null);
  const [weixinQrLoading, setWeixinQrLoading] = useState(false);
  const [weixinQrMessage, setWeixinQrMessage] = useState<string | null>(null);
  const [pairingText, setPairingText] = useState("");
  const [submittingPairingConfirm, setSubmittingPairingConfirm] = useState(false);
  const [pairingConfirmed, setPairingConfirmed] = useState<FirstLobsterFeishuPairingConfirmResult | null>(null);

  const orderedSupportedChannels = useMemo(() => {
    if (!preview) return [];
    return preview.supported_channels
      .filter((item) => VISIBLE_FIRST_LOBSTER_CHANNEL_SET.has(item.channel))
      .sort((left, right) => CHANNEL_ORDER.indexOf(left.channel) - CHANNEL_ORDER.indexOf(right.channel));
  }, [preview]);
  const recommendedAgentName = preview?.recommended_agent_name || t("pages.agents.claimMore.fallbackAgentName");
  const recommendedAgentId = preview?.recommended_agent_id || "main";
  const effectiveAgentName = openclawName.trim() || recommendedAgentName;

  const workspaceReady = Boolean(preview?.workspace.available);
  const claimRunActive = Boolean(claimRun && ACTIVE_CLAIM_RUN_STATUSES.has(claimRun.status));
  const stepOrder = primaryChannel === "feishu" ? FEISHU_PAIRING_STEP_ORDER : DEFAULT_STEP_ORDER;
  const currentStepIndex = Math.max(0, stepOrder.indexOf(currentStep)) + 1;
  const nameStepNextDisabled = loadingPreview || !openclawName.trim();
  const basePrimaryActionDisabled = claimRunActive || submittingDirectClaim || loadingPreview || !workspaceReady || !openclawName.trim();
  const primaryActionDisabled = primaryChannel === "weixin"
    ? basePrimaryActionDisabled
      || weixinQrLoading
      || (Boolean(weixinQr) && !weixinAccountId && weixinQrStatus !== "expired" && weixinQrStatus !== "error")
    : basePrimaryActionDisabled;

  const claimStatusTitle = claimRun
    ? claimRun.status === "queued"
      ? t("pages.agents.empty.firstLobster.run.preparingTitle")
      : claimRun.status === "waiting_login"
        ? t("pages.agents.empty.firstLobster.run.waitingLoginTitle")
        : claimRun.status === "claiming"
          ? t("pages.agents.empty.firstLobster.run.claimingTitle")
          : claimRun.status === "completed"
            ? t("pages.agents.empty.firstLobster.run.completedTitle")
            : t("pages.agents.empty.firstLobster.run.failedTitle")
    : null;
  const claimStatusDescription = claimRun
    ? claimRun.status === "queued"
      ? t("pages.agents.empty.firstLobster.run.preparingDescription")
      : claimRun.status === "waiting_login"
        ? t("pages.agents.empty.firstLobster.run.waitingLoginDescription")
        : claimRun.status === "claiming"
          ? t("pages.agents.empty.firstLobster.run.claimingDescription", { agentName: effectiveAgentName })
          : claimRun.status === "completed"
            ? t("pages.agents.empty.firstLobster.run.completedDescription", { agentName: effectiveAgentName })
            : claimRun.error_message ||
              claimRun.message ||
              t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName })
    : null;
  const currentStepLabel = currentStep === "name"
    ? t("pages.agents.empty.firstLobster.steps.name.title")
    : currentStep === "channel"
      ? t("pages.agents.empty.firstLobster.steps.channel.title")
      : currentStep === "pairingHello"
        ? t("pages.agents.empty.firstLobster.steps.pairingHello.title")
        : t("pages.agents.empty.firstLobster.steps.pairingPaste.title");

  const logClaimDiagnostic = useCallback(
    (
      event: string,
      options?: {
        level?: "info" | "warn" | "error";
        traceId?: string | null;
        detail?: Record<string, unknown>;
      },
    ) => {
      void recordClientDiagnosticLog({
        category: "first_lobster_ui",
        event,
        level: options?.level,
        trace_id: options?.traceId ?? claimRun?.trace_id ?? claimTraceId,
        request_path: pathname || "/agents",
        detail: {
          variant,
          agent_id: recommendedAgentId,
          agent_name: effectiveAgentName,
          ...(options?.detail || {}),
        },
      });
    },
    [claimRun?.trace_id, claimTraceId, effectiveAgentName, pathname, recommendedAgentId, variant],
  );

  useEffect(() => {
    if (!preview) return;
    const suggestedAppName = preview.recommended_app_name?.trim() || "ClawPilot";
    const previousSuggestedAppName = suggestedAppNameRef.current;
    setOpenclawName((current) => {
      const normalized = current.trim();
      if (!normalized || normalized === previousSuggestedAppName) {
        return suggestedAppName;
      }
      return current;
    });
    suggestedAppNameRef.current = suggestedAppName;
  }, [preview]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !claimRunActive && !submittingDirectClaim && !submittingPairingConfirm) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [claimRunActive, open, submittingDirectClaim, submittingPairingConfirm]);

  useEffect(() => {
    if (!open) {
      setCurrentStep("name");
      setFormError(null);
      setSubmittingDirectClaim(false);
      setSubmittingPairingConfirm(false);
      setPairingText("");
      setPairingConfirmed(null);
      if (!claimRunActive) {
        setClaimRun(null);
      }
      if (!claimRunActive) {
        loggedRunStateRef.current = null;
      }
    }
  }, [claimRunActive, open]);

  useEffect(() => {
    if (!open || primaryChannel !== "feishu" || claimRun?.status !== "completed") {
      return;
    }
    setFormError(null);
    setCurrentStep((current) => (current === "pairingPaste" ? current : "pairingHello"));
  }, [claimRun?.status, open, primaryChannel]);

  useEffect(() => {
    if (!orderedSupportedChannels.length) return;
    if (orderedSupportedChannels.some((item) => item.channel === primaryChannel)) return;
    setPrimaryChannel(orderedSupportedChannels[0].channel);
  }, [orderedSupportedChannels, primaryChannel]);

  useEffect(() => {
    if (!claimRun) {
      loggedRunStateRef.current = null;
      return;
    }
    const logKey = [
      claimRun.job_id,
      claimRun.trace_id || claimTraceId || "",
      claimRun.status,
      claimRun.current_stage,
      claimRun.error_message || "",
    ].join(":");
    if (loggedRunStateRef.current === logKey) {
      return;
    }
    loggedRunStateRef.current = logKey;
    logClaimDiagnostic(
      claimRun.status === "completed"
        ? "auto_claim.completed"
        : claimRun.status === "failed"
          ? "auto_claim.failed"
          : "auto_claim.status_changed",
      {
        level: claimRun.status === "failed" ? "error" : "info",
        traceId: claimRun.trace_id ?? claimTraceId,
        detail: {
          job_id: claimRun.job_id,
          status: claimRun.status,
          current_stage: claimRun.current_stage,
          message: claimRun.message || null,
          error_message: claimRun.error_message || null,
          execution_mode: claimRun.execution_mode || null,
          app_id: claimRun.app_id || null,
          agent_id: claimRun.agent_id || null,
        },
      },
    );
  }, [claimRun, claimTraceId, logClaimDiagnostic]);

  useEffect(() => {
    if (!open || !claimRun || !ACTIVE_CLAIM_RUN_STATUSES.has(claimRun.status)) {
      return;
    }
    const pollIntervalMs = claimRun.status === "claiming" ? 600 : 1200;
    const timer = window.setTimeout(async () => {
      try {
        const next = await getFirstLobsterAutoClaimRun(claimRun.job_id);
        setClaimRun(next);
        if (next.trace_id && next.trace_id !== claimTraceId) {
          setClaimTraceId(next.trace_id);
        }
        if (next.status === "failed") {
          setFormError(
            next.error_message ||
              next.message ||
              t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName }),
          );
        }
      } catch (error) {
        if (error instanceof ApiError && error.code === "unauthorized") {
          logClaimDiagnostic("auto_claim.poll_unauthorized", {
            level: "warn",
            detail: { job_id: claimRun.job_id },
          });
          setFormError(t("pages.agents.empty.firstLobster.validation.sessionExpired", { agentName: effectiveAgentName }));
          router.replace(buildAuthRedirectPath("/login", pathname || "/agents"));
          return;
        }
        if (error instanceof ApiError && error.code === "password_change_required") {
          logClaimDiagnostic("auto_claim.poll_password_change_required", {
            level: "warn",
            detail: { job_id: claimRun.job_id },
          });
          setFormError(
            t("pages.agents.empty.firstLobster.validation.sessionPasswordChangeRequired", { agentName: effectiveAgentName }),
          );
          router.replace(buildAuthRedirectPath("/account/password", pathname || "/agents"));
          return;
        }
        logClaimDiagnostic("auto_claim.poll_failed", {
          level: "error",
          detail: {
            job_id: claimRun.job_id,
            error_message:
              error instanceof Error
                ? error.message
                : t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName }),
          },
        });
        setFormError(
          error instanceof Error ? error.message : t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName }),
        );
        setClaimRun((current) =>
          current
            ? {
                ...current,
                status: "failed",
                current_stage: "failed",
                error_message:
                  error instanceof Error
                    ? error.message
                    : t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName }),
                finished_at: current.finished_at ?? new Date().toISOString(),
              }
            : current,
        );
      }
    }, pollIntervalMs);
    return () => window.clearTimeout(timer);
  }, [claimRun, claimTraceId, effectiveAgentName, logClaimDiagnostic, open, pathname, router, t]);

  async function loadPreview(force = false, traceIdOverride?: string | null) {
    if (loadingPreview) return;
    if (preview && !force) return;
    try {
      setLoadingPreview(true);
      setPreviewError(null);
      const next = await getFirstLobsterBootstrapPreview();
      setPreview(next);
      logClaimDiagnostic("bootstrap_preview.loaded", {
        traceId: traceIdOverride,
        detail: {
          workspace_available: next.workspace.available,
          recommended_agent_id: next.recommended_agent_id,
          recommended_app_name: next.recommended_app_name,
          supported_channels: next.supported_channels.map((item) => item.channel),
        },
      });
    } catch (error) {
      logClaimDiagnostic("bootstrap_preview.failed", {
        level: "error",
        traceId: traceIdOverride,
        detail: {
          error_message: error instanceof Error ? error.message : t("pages.agents.empty.firstLobster.errors.previewFailed"),
        },
      });
      setPreviewError(error instanceof Error ? error.message : t("pages.agents.empty.firstLobster.errors.previewFailed"));
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleStartWeixinQr() {
    try {
      setWeixinQrLoading(true);
      setFormError(null);
      setWeixinQrMessage(null);
      setWeixinQr(null);
      setWeixinQrStatus(null);
      setWeixinAccountId(null);
      const result = await startWeixinQrLogin();
      setWeixinQr(result);
      setWeixinQrStatus("waiting");
    } catch (error) {
      if (
        error instanceof ApiError
        && (error.code === "openclaw_cli_not_found" || error.code === "weixin_qr_worker_not_found")
      ) {
        setFormError(t("pages.agents.empty.firstLobster.errors.weixinCliMissing"));
      } else if (error instanceof ApiError && error.code === "weixin_qr_login_timeout") {
        setFormError(t("pages.agents.empty.firstLobster.errors.weixinQrTimeout"));
      } else {
        setFormError(error instanceof Error ? error.message : t("pages.agents.empty.firstLobster.errors.weixinQrFailed"));
      }
    } finally {
      setWeixinQrLoading(false);
    }
  }

  useEffect(() => {
    if (
      !open
      || currentStep !== "channel"
      || primaryChannel !== "weixin"
      || !weixinQr
      || (weixinQrStatus !== "waiting" && weixinQrStatus !== "scanned")
    ) {
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const result = await pollWeixinQrLogin(weixinQr.session_id);
        setWeixinQrStatus(result.status);
        setWeixinQrMessage(result.message);
        if (result.status === "confirmed" && result.account_id) {
          setWeixinAccountId(result.account_id);
        }
      } catch {
        /* silently retry on next poll */
      }
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [currentStep, open, primaryChannel, weixinQr, weixinQrStatus]);

  function resolvePairingConfirmError(error: unknown): string {
    if (error instanceof ApiError && error.code === "unauthorized") {
      return t("pages.agents.empty.firstLobster.validation.sessionExpired", { agentName: effectiveAgentName });
    }
    if (error instanceof ApiError && error.code === "password_change_required") {
      return t("pages.agents.empty.firstLobster.validation.sessionPasswordChangeRequired", { agentName: effectiveAgentName });
    }
    if (error instanceof ApiError && error.message === "first_lobster_feishu_pairing_text_required") {
      return t("pages.agents.empty.firstLobster.validation.pairingTextRequired");
    }
    if (error instanceof ApiError && error.message === "first_lobster_feishu_pairing_text_invalid") {
      return t("pages.agents.empty.firstLobster.errors.pairingTextInvalid");
    }
    if (error instanceof ApiError && error.message === "openclaw_cli_unavailable") {
      return t("pages.agents.empty.firstLobster.errors.pairingCliMissing");
    }
    if (error instanceof ApiError && error.message.startsWith("first_lobster_feishu_pairing_approve_failed:")) {
      return t("pages.agents.empty.firstLobster.errors.pairingApproveFailed", {
        reason: error.message.split(":").slice(1).join(":").trim() || t("common.unknown"),
      });
    }
    if (error instanceof ApiError && error.message === "agent_not_found") {
      return t("pages.agents.empty.firstLobster.errors.pairingAgentMissing");
    }
    return error instanceof Error ? error.message : t("pages.agents.empty.firstLobster.errors.pairingConfirmFailed");
  }

  function openFeishuChat() {
    if (!claimRun?.chat_url) return false;
    const nextWindow = window.open(claimRun.chat_url, "_blank", "noopener,noreferrer");
    if (!nextWindow) {
      setFormError(t("pages.agents.empty.firstLobster.errors.openChatBlocked"));
      return false;
    }
    return true;
  }

  function finishPairingFlow() {
    setPairingConfirmed(null);
    setOpen(false);
    setClaimRun(null);
    startTransition(() => {
      router.refresh();
    });
  }

  async function handleConfirmPairing() {
    if (!pairingText.trim()) {
      setFormError(t("pages.agents.empty.firstLobster.validation.pairingTextRequired"));
      return;
    }
    if (!claimRun?.agent_id) {
      setFormError(t("pages.agents.empty.firstLobster.errors.pairingAgentMissing"));
      return;
    }
    try {
      setFormError(null);
      setSubmittingPairingConfirm(true);
      const result = await confirmFirstLobsterFeishuPairing({
        agent_id: claimRun.agent_id,
        pairing_text: pairingText.trim(),
      });
      setPairingConfirmed(result);
      startTransition(() => {
        router.refresh();
      });
    } catch (error) {
      if (error instanceof ApiError && error.code === "unauthorized") {
        router.replace(buildAuthRedirectPath("/login", pathname || "/agents"));
        return;
      }
      if (error instanceof ApiError && error.code === "password_change_required") {
        router.replace(buildAuthRedirectPath("/account/password", pathname || "/agents"));
        return;
      }
      setFormError(resolvePairingConfirmError(error));
    } finally {
      setSubmittingPairingConfirm(false);
    }
  }

  function handleOpen() {
    const traceId = createDiagnosticTraceId("lobster");
    setClaimTraceId(traceId);
    setCurrentStep("name");
    setOpen(true);
    logClaimDiagnostic("claim_dialog.opened", {
      traceId,
      detail: { has_existing_preview: Boolean(preview) },
    });
    void loadPreview(true, traceId);
  }

  function handleClose() {
    if (claimRunActive || submittingDirectClaim || submittingPairingConfirm) {
      return;
    }
    logClaimDiagnostic("claim_dialog.closed");
    setOpen(false);
  }

  function channelLabel(channel: FirstLobsterChannel) {
    return t(`common.platforms.${channel}`);
  }

  function handleSelectPrimaryChannel(channel: FirstLobsterChannel) {
    setFormError(null);
    if (channel !== primaryChannel) {
      setWeixinQr(null);
      setWeixinQrStatus(null);
      setWeixinAccountId(null);
      setWeixinQrMessage(null);
    }
    setPrimaryChannel(channel);
  }

  function handleNextFromName() {
    if (!openclawName.trim()) {
      setFormError(t("pages.agents.empty.firstLobster.validation.nameRequired"));
      return;
    }
    setFormError(null);
    setCurrentStep("channel");
  }

  function handleGoToPairingPaste() {
    setFormError(null);
    setCurrentStep("pairingPaste");
  }

  async function handleClaim() {
    if (!preview?.workspace.available) {
      logClaimDiagnostic("claim.validation_failed", {
        level: "warn",
        detail: { reason: "workspace_unavailable" },
      });
      setFormError(t("pages.agents.empty.firstLobster.validation.workspaceUnavailable"));
      return;
    }
    if (!openclawName.trim()) {
      logClaimDiagnostic("claim.validation_failed", {
        level: "warn",
        detail: { reason: "name_required" },
      });
      setFormError(t("pages.agents.empty.firstLobster.validation.nameRequired"));
      return;
    }
    if (primaryChannel === "weixin") {
      if (!weixinAccountId) {
        if (!weixinQr || weixinQrStatus === "expired" || weixinQrStatus === "error") {
          await handleStartWeixinQr();
          return;
        }
        setFormError(t("pages.agents.empty.firstLobster.errors.weixinQrNotConfirmed"));
        return;
      }
      try {
        setFormError(null);
        setSubmittingDirectClaim(true);
        const activeTraceId = claimTraceId || createDiagnosticTraceId("lobster");
        setClaimTraceId(activeTraceId);
        logClaimDiagnostic("claim.weixin.started", {
          traceId: activeTraceId,
          detail: {
            agent_name: openclawName.trim(),
            primary_channel: primaryChannel,
            weixin_account_id: weixinAccountId,
          },
        });
        await claimFirstLobster({
          selected_channels: ["weixin"],
          primary_channel: "weixin",
          agent_name: openclawName.trim(),
          weixin: {
            account_id: weixinAccountId,
          },
        });
        logClaimDiagnostic("claim.weixin.completed", {
          traceId: activeTraceId,
          detail: {
            agent_name: openclawName.trim(),
            primary_channel: primaryChannel,
          },
        });
        setOpen(false);
        startTransition(() => {
          router.refresh();
        });
      } catch (error) {
        if (error instanceof ApiError && error.code === "unauthorized") {
          logClaimDiagnostic("claim.weixin.unauthorized", {
            level: "warn",
            detail: { agent_name: openclawName.trim() },
          });
          setFormError(t("pages.agents.empty.firstLobster.validation.sessionExpired", { agentName: effectiveAgentName }));
          router.replace(buildAuthRedirectPath("/login", pathname || "/agents"));
          return;
        }
        if (error instanceof ApiError && error.code === "password_change_required") {
          logClaimDiagnostic("claim.weixin.password_change_required", {
            level: "warn",
            detail: { agent_name: openclawName.trim() },
          });
          setFormError(
            t("pages.agents.empty.firstLobster.validation.sessionPasswordChangeRequired", { agentName: effectiveAgentName }),
          );
          router.replace(buildAuthRedirectPath("/account/password", pathname || "/agents"));
          return;
        }
        logClaimDiagnostic("claim.weixin.failed", {
          level: "error",
          detail: {
            agent_name: openclawName.trim(),
            error_message:
              error instanceof Error
                ? error.message
                : t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName }),
          },
        });
        setFormError(
          error instanceof Error ? error.message : t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName }),
        );
      } finally {
        setSubmittingDirectClaim(false);
      }
      return;
    }
    if (primaryChannel !== "feishu") {
      logClaimDiagnostic("claim.validation_failed", {
        level: "warn",
        detail: { reason: "primary_channel_not_supported", primary_channel: primaryChannel },
      });
      setFormError(t("pages.agents.empty.firstLobster.actions.defaultFlowOnlyFeishu"));
      return;
    }
    try {
      setFormError(null);
      const activeTraceId = claimTraceId || createDiagnosticTraceId("lobster");
      setClaimTraceId(activeTraceId);
      logClaimDiagnostic("auto_claim.started", {
        traceId: activeTraceId,
        detail: {
          app_name: openclawName.trim(),
          primary_channel: primaryChannel,
        },
      });
      const job = await startFirstLobsterAutoClaim({
        app_name: openclawName.trim(),
        app_description: t("pages.agents.empty.firstLobster.autoCreate.appDescription", { agentName: effectiveAgentName }),
        menu_name: t("pages.agents.empty.firstLobster.autoCreate.menuName"),
        timeout_sec: 600,
        trace_id: activeTraceId,
      });
      if (job.trace_id && job.trace_id !== activeTraceId) {
        setClaimTraceId(job.trace_id);
      }
      setClaimRun(job);
    } catch (error) {
      if (error instanceof ApiError && error.code === "unauthorized") {
        logClaimDiagnostic("auto_claim.start_unauthorized", {
          level: "warn",
          detail: { app_name: openclawName.trim() },
        });
        setFormError(t("pages.agents.empty.firstLobster.validation.sessionExpired", { agentName: effectiveAgentName }));
        router.replace(buildAuthRedirectPath("/login", pathname || "/agents"));
        return;
      }
      if (error instanceof ApiError && error.code === "password_change_required") {
        logClaimDiagnostic("auto_claim.start_password_change_required", {
          level: "warn",
          detail: { app_name: openclawName.trim() },
        });
        setFormError(
          t("pages.agents.empty.firstLobster.validation.sessionPasswordChangeRequired", { agentName: effectiveAgentName }),
        );
        router.replace(buildAuthRedirectPath("/account/password", pathname || "/agents"));
        return;
      }
      logClaimDiagnostic("auto_claim.start_failed", {
        level: "error",
        detail: {
          app_name: openclawName.trim(),
          error_message:
            error instanceof Error
              ? error.message
              : t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName }),
        },
      });
      setFormError(
        error instanceof Error ? error.message : t("pages.agents.empty.firstLobster.errors.claimFailed", { agentName: effectiveAgentName }),
      );
    }
  }

  return (
    <>
      {variant === "empty" ? (
        <Card className="rounded-[28px] border-dashed border-[var(--line)] bg-[var(--surface)]/70">
          <CardContent className="space-y-5 px-5 py-8 text-sm text-[var(--muted)]">
            <div className="space-y-3">
              <p className="font-medium text-[var(--text)]">{t("pages.agents.empty.title")}</p>
              <p>{t("pages.agents.empty.description")}</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" className="rounded-full px-5" onClick={handleOpen}>
                {t("pages.agents.empty.firstLobster.cta")}
              </Button>
              <p className="text-xs text-[var(--muted)]">{t("pages.agents.empty.firstLobster.ctaHint")}</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Button type="button" className="rounded-full px-5" onClick={handleOpen}>
          {t("pages.agents.claimMore.cta")}
        </Button>
      )}

      {open ? (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-[rgba(15,23,42,0.38)] px-4 py-6 backdrop-blur-sm">
          <div className="absolute inset-0" onClick={handleClose} />
          <section className="relative z-[91] flex max-h-[92vh] w-full max-w-[1080px] flex-col overflow-hidden rounded-[32px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(245,245,242,0.98))] shadow-[0_32px_100px_rgba(15,23,42,0.24)]">
            <header className="border-b border-[var(--line)]/85 px-5 py-4 md:px-6">
              <div className="flex items-start justify-between gap-4">
                <h2 className="font-[var(--font-serif)] text-[28px] leading-none text-[var(--text)] md:text-[32px]">
                  {variant === "toolbar" ? t("pages.agents.claimMore.title") : t("pages.agents.empty.firstLobster.title")}
                </h2>
                <Button type="button" variant="outline" onClick={handleClose} disabled={claimRunActive || submittingDirectClaim || submittingPairingConfirm}>
                  {t("pages.agents.empty.firstLobster.close")}
                </Button>
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 md:px-5 md:py-5">
              {loadingPreview && !preview ? (
                <div className="rounded-[24px] border border-[var(--line)] bg-[var(--surface)]/35 p-5 text-sm text-[var(--muted)]">
                  {t("pages.agents.empty.firstLobster.loading")}
                </div>
              ) : previewError ? (
                <div className="space-y-4 rounded-[24px] border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
                  <p>{previewError}</p>
                  <Button type="button" variant="outline" onClick={() => void loadPreview(true)}>
                    {t("pages.agents.empty.firstLobster.retry")}
                  </Button>
                </div>
              ) : preview ? (
                <div className="mx-auto max-w-[760px] space-y-3">
                  <div className="rounded-[20px] border border-[var(--line)] bg-[var(--surface)]/55 px-4 py-3">
                    <div className="flex items-center justify-between text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--muted)]">
                      <span>{`${currentStepIndex} / ${stepOrder.length}`}</span>
                      <span>{currentStepLabel}</span>
                    </div>
                    <div className={cn("mt-3 grid gap-2", stepOrder.length > 2 ? "grid-cols-4" : "grid-cols-2")}>
                      {stepOrder.map((step) => {
                        const active = currentStep === step;
                        const complete = stepOrder.indexOf(step) < currentStepIndex - 1;
                        return (
                          <div
                            key={step}
                            className={cn(
                              "h-2 rounded-full transition",
                              active || complete ? "bg-[var(--brand-ink)]" : "bg-[var(--line)]",
                            )}
                          />
                        );
                      })}
                    </div>
                  </div>

                  {currentStep === "name" ? (
                    <StepSection
                      step="1"
                      title={t("pages.agents.empty.firstLobster.steps.name.title")}
                      description={t("pages.agents.empty.firstLobster.steps.name.description", { agentName: recommendedAgentName })}
                    >
                      <label className="block space-y-1.5">
                        <span className="text-[13px] font-medium text-[var(--text)]">
                          {t("pages.agents.empty.firstLobster.steps.name.label")}
                        </span>
                        <input
                          type="text"
                          value={openclawName}
                          onChange={(event) => {
                            setOpenclawName(event.target.value);
                            setFormError(null);
                          }}
                          placeholder={t("pages.agents.empty.firstLobster.steps.name.placeholder")}
                          className="h-11 w-full rounded-[16px] border border-[var(--line)] bg-[var(--surface)]/45 px-4 text-sm text-[var(--text)] outline-none transition focus:border-[var(--brand-ink)] focus:bg-white focus:ring-4 focus:ring-black/5"
                        />
                        <p className="text-[11px] leading-5 text-[var(--muted)]">
                          {t("pages.agents.empty.firstLobster.steps.name.hint")}
                        </p>
                      </label>

                      {formError ? (
                        <div className="rounded-[18px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                          {formError}
                        </div>
                      ) : null}

                      <div className="flex justify-end">
                        <Button type="button" className="rounded-full px-5" disabled={nameStepNextDisabled} onClick={handleNextFromName}>
                          {t("pages.agents.empty.firstLobster.actions.next")}
                        </Button>
                      </div>
                    </StepSection>
                  ) : null}

                  {currentStep === "channel" ? (
                    <StepSection
                      step="2"
                      title={t("pages.agents.empty.firstLobster.steps.channel.title")}
                      description={t("pages.agents.empty.firstLobster.steps.channel.description")}
                    >
                      <div className="grid gap-2 sm:grid-cols-2">
                        {orderedSupportedChannels.map((channelConfig) => {
                          const isPrimary = primaryChannel === channelConfig.channel;
                          const visual = CHANNEL_VISUALS[channelConfig.channel];
                          return (
                            <label
                              key={channelConfig.channel}
                              className={cn(
                                "relative flex min-h-[112px] w-full cursor-pointer items-center rounded-[18px] border px-3.5 py-3 pt-8 transition",
                                isPrimary
                                  ? cn("bg-white shadow-[0_12px_28px_rgba(15,23,42,0.06)] ring-2 ring-black/5", visual.outline)
                                  : "border-[var(--line)] bg-[var(--surface)]/36 hover:border-[var(--text)]/20 hover:bg-white",
                              )}
                            >
                              <input
                                type="radio"
                                name="first-lobster-default-channel"
                                className="sr-only"
                                checked={isPrimary}
                                onChange={() => handleSelectPrimaryChannel(channelConfig.channel)}
                              />
                              <div className="flex min-w-0 items-center gap-2.5">
                                <PlatformIcon
                                  channel={channelConfig.channel}
                                  label={channelLabel(channelConfig.channel)}
                                  className="h-11 w-11 rounded-[14px]"
                                />
                                <span className="block truncate text-[19px] font-semibold text-[var(--text)]">
                                  {channelLabel(channelConfig.channel)}
                                </span>
                              </div>
                            </label>
                          );
                        })}
                      </div>

                      {primaryChannel === "weixin" ? (
                        <div className="rounded-[18px] border border-[#07c160]/20 bg-[#f0faf0] px-4 py-4">
                          {weixinQrLoading ? (
                            <p className="text-sm text-[var(--muted)]">{t("pages.agents.empty.firstLobster.weixin.loading")}</p>
                          ) : weixinQrStatus === "confirmed" && weixinAccountId ? (
                            <div className="rounded-[16px] border border-[#07c160]/25 bg-white/80 px-4 py-3">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#07c160]">
                                {t("pages.agents.empty.firstLobster.weixin.confirmedTitle")}
                              </p>
                              <p className="mt-1 text-sm font-medium text-[#0f5132]">
                                {weixinQrMessage || t("pages.agents.empty.firstLobster.weixin.confirmedHint")}
                              </p>
                            </div>
                          ) : weixinQrStatus === "error" ? (
                            <div className="space-y-2">
                              <p className="text-sm text-rose-700">
                                {weixinQrMessage || t("pages.agents.empty.firstLobster.errors.weixinQrFailed")}
                              </p>
                              <Button type="button" variant="outline" size="sm" onClick={() => void handleStartWeixinQr()}>
                                {t("pages.agents.empty.firstLobster.actions.generateWeixinQr")}
                              </Button>
                            </div>
                          ) : weixinQrStatus === "expired" ? (
                            <div className="space-y-2">
                              <p className="text-sm text-amber-700">
                                {weixinQrMessage || t("pages.agents.empty.firstLobster.weixin.expired")}
                              </p>
                              <Button type="button" variant="outline" size="sm" onClick={() => void handleStartWeixinQr()}>
                                {t("pages.agents.empty.firstLobster.weixin.retry")}
                              </Button>
                            </div>
                          ) : weixinQr ? (
                            <div className="space-y-3">
                              <div
                                className={cn(
                                  "rounded-[16px] border px-4 py-3",
                                  weixinQrStatus === "scanned"
                                    ? "border-amber-200 bg-amber-50 text-amber-900"
                                    : "border-sky-200 bg-sky-50 text-sky-900",
                                )}
                              >
                                <p className="text-[11px] font-semibold uppercase tracking-[0.14em]">
                                  {weixinQrStatus === "scanned"
                                    ? t("pages.agents.empty.firstLobster.weixin.scannedTitle")
                                    : t("pages.agents.empty.firstLobster.weixin.waitingTitle")}
                                </p>
                                <p className="mt-1 text-sm font-medium">
                                  {weixinQrStatus === "scanned"
                                    ? (weixinQrMessage || t("pages.agents.empty.firstLobster.weixin.scannedHint"))
                                    : t("pages.agents.empty.firstLobster.weixin.waitingHint")}
                                </p>
                              </div>
                              <div className="flex items-center justify-center rounded-[14px] bg-white p-4">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                  src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(weixinQr.qr_url)}`}
                                  alt="WeChat QR"
                                  width={200}
                                  height={200}
                                  className="h-[200px] w-[200px]"
                                />
                              </div>
                              <p className="text-center text-xs text-[var(--muted)]">
                                {weixinQrStatus === "scanned"
                                  ? (weixinQrMessage || t("pages.agents.empty.firstLobster.weixin.scanned"))
                                  : t("pages.agents.empty.firstLobster.weixin.scanHint")}
                              </p>
                            </div>
                          ) : (
                            <p className="text-sm text-[var(--muted)]">{t("pages.agents.empty.firstLobster.weixin.idle")}</p>
                          )}
                        </div>
                      ) : null}

                      {claimRun && claimStatusTitle && claimStatusDescription ? (
                        <div
                          className={cn(
                            "rounded-[18px] border px-4 py-3",
                            claimRun.status === "failed"
                              ? "border-rose-200 bg-rose-50 text-rose-700"
                              : "border-sky-200 bg-sky-50 text-sky-800",
                          )}
                        >
                          <p className="text-sm font-semibold">{claimStatusTitle}</p>
                          <p className="mt-1 text-sm leading-6">{claimStatusDescription}</p>
                        </div>
                      ) : null}

                      {formError ? (
                        <div className="rounded-[18px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                          {formError}
                        </div>
                      ) : null}

                      {!workspaceReady ? (
                        <div className="rounded-[16px] border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-700">
                          {t("pages.agents.empty.firstLobster.validation.workspaceUnavailable")}
                        </div>
                      ) : null}

                      <div className="flex flex-col gap-2.5 sm:flex-row sm:justify-between">
                        <Button
                          type="button"
                          variant="outline"
                          className="rounded-full px-5"
                          disabled={claimRunActive || submittingDirectClaim}
                          onClick={() => {
                            setFormError(null);
                            setCurrentStep("name");
                          }}
                        >
                          {t("pages.agents.empty.firstLobster.actions.back")}
                        </Button>
                        <Button
                          type="button"
                          className="h-11 rounded-full px-5 text-base sm:min-w-[320px]"
                          disabled={primaryActionDisabled}
                          onClick={() => void handleClaim()}
                        >
                          {primaryChannel === "weixin"
                            ? weixinQrLoading
                              ? t("pages.agents.empty.firstLobster.actions.generatingWeixinQr")
                              : !weixinAccountId
                                ? !weixinQr || weixinQrStatus === "expired" || weixinQrStatus === "error"
                                  ? t("pages.agents.empty.firstLobster.actions.generateWeixinQr")
                                  : t("pages.agents.empty.firstLobster.actions.waitingWeixinQr")
                                : submittingDirectClaim
                                  ? t("pages.agents.empty.firstLobster.actions.claimingWeixin")
                                  : t("pages.agents.empty.firstLobster.actions.claimWeixin")
                            : claimRun?.status === "waiting_login"
                              ? t("pages.agents.empty.firstLobster.actions.waitingLogin")
                              : claimRunActive
                                ? t("pages.agents.empty.firstLobster.actions.claiming")
                                : t("pages.agents.empty.firstLobster.actions.claim")}
                        </Button>
                      </div>
                    </StepSection>
                  ) : null}

                  {currentStep === "pairingHello" ? (
                    <StepSection
                      step="3"
                      title={t("pages.agents.empty.firstLobster.steps.pairingHello.title")}
                      description={t("pages.agents.empty.firstLobster.steps.pairingHello.description", { agentName: effectiveAgentName })}
                      className="bg-[linear-gradient(180deg,rgba(247,250,255,0.98),rgba(255,255,255,0.95))]"
                    >
                      <div className="rounded-[18px] border border-sky-200/80 bg-[linear-gradient(180deg,rgba(235,244,255,0.9),rgba(255,255,255,0.96))] px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#3370ff]">
                          {t("pages.agents.empty.firstLobster.steps.pairingHello.badge")}
                        </p>
                        <p className="mt-2 text-sm leading-7 text-slate-700">
                          {t("pages.agents.empty.firstLobster.steps.pairingHello.body", { agentName: effectiveAgentName })}
                        </p>
                        <div className="mt-3 inline-flex rounded-full border border-[#3370ff]/20 bg-white px-3 py-1.5 text-sm font-semibold text-[#1d4ed8]">
                          {t("pages.agents.empty.firstLobster.steps.pairingHello.message")}
                        </div>
                      </div>

                      <div className="flex flex-col gap-2.5 sm:flex-row sm:justify-between">
                        <Button
                          type="button"
                          variant="outline"
                          className="rounded-full px-5"
                          onClick={openFeishuChat}
                          disabled={!claimRun?.chat_url}
                        >
                          {t("pages.agents.empty.firstLobster.actions.openFeishuChat")}
                        </Button>
                        <Button type="button" className="rounded-full px-5" onClick={handleGoToPairingPaste}>
                          {t("pages.agents.empty.firstLobster.actions.pairingNext")}
                        </Button>
                      </div>
                    </StepSection>
                  ) : null}

                  {currentStep === "pairingPaste" ? (
                    <StepSection
                      step="4"
                      title={t("pages.agents.empty.firstLobster.steps.pairingPaste.title")}
                      description={t("pages.agents.empty.firstLobster.steps.pairingPaste.description")}
                      className="bg-[linear-gradient(180deg,rgba(255,250,244,0.98),rgba(255,255,255,0.96))]"
                    >
                      <div className="space-y-3 rounded-[18px] border border-[var(--line)] bg-white/90 px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
                          {t("pages.agents.empty.firstLobster.steps.pairingPaste.exampleTitle")}
                        </p>
                        <pre className="overflow-x-auto rounded-[16px] border border-[var(--line)] bg-[#171717] px-4 py-3 text-xs leading-6 text-slate-100">
{t("pages.agents.empty.firstLobster.steps.pairingPaste.exampleBlock")}
                        </pre>
                      </div>

                      <label className="block space-y-1.5">
                        <span className="text-[13px] font-medium text-[var(--text)]">
                          {t("pages.agents.empty.firstLobster.steps.pairingPaste.label")}
                        </span>
                        <textarea
                          value={pairingText}
                          onChange={(event) => {
                            setPairingText(event.target.value);
                            setFormError(null);
                          }}
                          placeholder={t("pages.agents.empty.firstLobster.steps.pairingPaste.placeholder")}
                          rows={8}
                          className="min-h-[180px] w-full rounded-[18px] border border-[var(--line)] bg-[var(--surface)]/45 px-4 py-3 text-sm leading-6 text-[var(--text)] outline-none transition focus:border-[var(--brand-ink)] focus:bg-white focus:ring-4 focus:ring-black/5"
                        />
                        <p className="text-[11px] leading-5 text-[var(--muted)]">
                          {t("pages.agents.empty.firstLobster.steps.pairingPaste.hint")}
                        </p>
                      </label>

                      {formError ? (
                        <div className="rounded-[18px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                          {formError}
                        </div>
                      ) : null}

                      <div className="flex flex-col gap-2.5 sm:flex-row sm:justify-between">
                        <Button
                          type="button"
                          variant="outline"
                          className="rounded-full px-5"
                          onClick={() => {
                            setFormError(null);
                            setCurrentStep("pairingHello");
                          }}
                          disabled={submittingPairingConfirm}
                        >
                          {t("pages.agents.empty.firstLobster.actions.back")}
                        </Button>
                        <Button
                          type="button"
                          className="rounded-full px-5"
                          onClick={() => void handleConfirmPairing()}
                          disabled={submittingPairingConfirm || !pairingText.trim()}
                        >
                          {submittingPairingConfirm
                            ? t("pages.agents.empty.firstLobster.actions.completingPairing")
                            : t("pages.agents.empty.firstLobster.actions.completePairing")}
                        </Button>
                      </div>
                    </StepSection>
                  ) : null}
                </div>
              ) : null}
            </div>

            {pairingConfirmed ? (
              <div className="absolute inset-0 z-[92] flex items-center justify-center bg-[rgba(15,23,42,0.28)] px-4 backdrop-blur-[2px]">
                <div className="absolute inset-0" onClick={finishPairingFlow} />
                <div className="relative z-[93] w-full max-w-[420px] rounded-[28px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(246,248,242,0.98))] px-6 py-7 text-center shadow-[0_36px_96px_rgba(15,23,42,0.2)]">
                  <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full border border-emerald-200 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.96),rgba(220,252,231,0.92))] text-[34px] font-semibold text-emerald-600 shadow-[0_18px_30px_rgba(16,185,129,0.18)]">
                    ✓
                  </div>
                  <p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-600">
                    {t("pages.agents.empty.firstLobster.success.badge")}
                  </p>
                  <h3 className="mt-2 font-[var(--font-serif)] text-[30px] leading-none text-[var(--text)]">
                    {t("pages.agents.empty.firstLobster.success.title")}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
                    {t("pages.agents.empty.firstLobster.success.description", { agentName: pairingConfirmed.agent_name })}
                  </p>
                  <div className="mt-6 flex flex-col gap-2.5 sm:flex-row sm:justify-center">
                    <Button
                      type="button"
                      className="rounded-full px-5"
                      onClick={() => {
                        if (openFeishuChat()) {
                          finishPairingFlow();
                        }
                      }}
                    >
                      {t("pages.agents.empty.firstLobster.success.openChat")}
                    </Button>
                    <Button type="button" variant="outline" className="rounded-full px-5" onClick={finishPairingFlow}>
                      {t("pages.agents.empty.firstLobster.success.close")}
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
}

export function AgentsClaimLobsterButton() {
  return <ClaimLobsterEntry variant="toolbar" />;
}

export function AgentsEmptyState() {
  return <ClaimLobsterEntry variant="empty" />;
}
