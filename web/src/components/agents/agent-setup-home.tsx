"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowClockwiseIcon, ArrowRightIcon, CheckCircleIcon, CopyIcon } from "@phosphor-icons/react";

import { useI18n } from "@/components/i18n/use-locale";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { createNode, getNodes } from "@/lib/api";
import type { NodeBootstrapResult, NodeStatus, NodeType, SetupStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AgentSetupHomeProps {
  setup: SetupStatus;
}

function detectLocalNodeType(): NodeType {
  if (typeof navigator === "undefined") {
    return "linux";
  }

  const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
  const platform = nav.userAgentData?.platform || navigator.platform || navigator.userAgent;
  return /mac/i.test(platform) ? "macos" : "linux";
}

function defaultLocalRoot() {
  return "~/.openclaw";
}

function escapeForDoubleQuotedValue(value: string) {
  return value.replace(/(["\\`])/g, "\\$1");
}

function normalizeRootForShell(value: string) {
  if (value === "~") return "$HOME";
  if (value.startsWith("~/")) return `$HOME/${value.slice(2)}`;
  return value;
}

function buildLocalInstallCommand(scriptUrl: string, expectedRoot: string) {
  const root = escapeForDoubleQuotedValue(normalizeRootForShell(expectedRoot));
  return `export OPENCLAW_ROOT="${root}"; curl -fsSL '${scriptUrl}' | bash`;
}

function statusLabel(status: NodeStatus, t: (key: string) => string) {
  if (status === "online") return t("agentSetup.status.online");
  if (status === "offline") return t("agentSetup.status.offline");
  return t("agentSetup.status.pending");
}

function healthLabel(value: boolean | null | undefined, t: (key: string) => string) {
  if (value === true) return t("agentSetup.summary.healthOk");
  if (value === false) return t("agentSetup.summary.healthFailed");
  return t("agentSetup.summary.healthUnknown");
}

function publicStatusLabel(setup: SetupStatus, t: (key: string) => string) {
  if (!setup.public_url_enabled) {
    return t("agentSetup.summary.publicStatuses.notRequested");
  }

  switch (setup.public_url_status) {
    case "verified":
      return t("agentSetup.summary.publicStatuses.verified");
    case "pending":
      return t("agentSetup.summary.publicStatuses.pending");
    case "unavailable":
      return t("agentSetup.summary.publicStatuses.unavailable");
    case "disabled":
      return t("agentSetup.summary.publicStatuses.disabled");
    default:
      return t("agentSetup.summary.publicStatuses.unknown");
  }
}

function publicProviderLabel(provider: string | null | undefined, t: (key: string) => string) {
  if (!provider) {
    return t("agentSetup.summary.notConfigured");
  }

  if (provider === "quick" || provider === "cloudflared-quick") {
    return t("agentSetup.summary.providerQuick");
  }

  return provider;
}

export function AgentSetupHome({ setup }: AgentSetupHomeProps) {
  const { t } = useI18n();
  const [localNodeType, setLocalNodeType] = useState<NodeType>("linux");
  const [displayName, setDisplayName] = useState("");
  const [expectedRoot, setExpectedRoot] = useState(defaultLocalRoot());
  const [submitting, setSubmitting] = useState(false);
  const [waitingNodeId, setWaitingNodeId] = useState<string | null>(null);
  const [waitingStatus, setWaitingStatus] = useState<NodeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [latestBootstrap, setLatestBootstrap] = useState<NodeBootstrapResult | null>(null);

  useEffect(() => {
    const detected = detectLocalNodeType();
    setLocalNodeType(detected);
    setExpectedRoot((current) => (current.trim() ? current : defaultLocalRoot()));
  }, []);

  useEffect(() => {
    if (!waitingNodeId) {
      return;
    }

    let stopped = false;

    const poll = async () => {
      try {
        const response = await getNodes();
        const current = response.items.find((item) => item.node_id === waitingNodeId);
        if (!current || stopped) {
          return;
        }

        setWaitingStatus(current.status);
        if (current.status === "online") {
          stopped = true;
          window.clearInterval(intervalId);
          setCopyMessage(t("agentSetup.messages.nodeOnline"));
          window.setTimeout(() => window.location.reload(), 800);
        }
      } catch {
        if (!stopped) {
          setError(t("agentSetup.errors.pollFailed"));
        }
      }
    };

    void poll();
    const intervalId = window.setInterval(() => void poll(), 3000);

    return () => {
      stopped = true;
      window.clearInterval(intervalId);
    };
  }, [waitingNodeId, t]);

  const bootstrapScriptUrl = latestBootstrap?.bootstrap_script_url || null;
  const localInstallCommand = useMemo(() => {
    if (!bootstrapScriptUrl) return null;
    return buildLocalInstallCommand(bootstrapScriptUrl, expectedRoot.trim());
  }, [bootstrapScriptUrl, expectedRoot]);

  async function handleCopy(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopyMessage(t("agentSetup.messages.copied", { label }));
      window.setTimeout(() => setCopyMessage(null), 1800);
    } catch {
      setError(t("agentSetup.errors.copyFailed", { label }));
    }
  }

  async function handleCreateNode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setCopyMessage(null);
    setWaitingNodeId(null);
    setWaitingStatus(null);

    try {
      const result = await createNode({
        display_name: displayName.trim(),
        node_type: localNodeType,
        expected_openclaw_root: expectedRoot.trim(),
      });

      if (!result.bootstrap_ready) {
        setLatestBootstrap(null);
        setWaitingNodeId(null);
        setWaitingStatus(null);
        setError(result.bootstrap_reason || t("agentSetup.errors.bootstrapUnavailable"));
        return;
      }

      setLatestBootstrap(result);
      setWaitingNodeId(result.node.node_id);
      setWaitingStatus(result.node.status);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : t("agentSetup.errors.generateFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  function handleResetGeneratedCommand() {
    setLatestBootstrap(null);
    setWaitingNodeId(null);
    setWaitingStatus(null);
    setError(null);
    setCopyMessage(null);
  }

  const commandToCopy = localInstallCommand;
  const showGeneratedCommand = Boolean(latestBootstrap);
  const trimmedDisplayName = displayName.trim();
  const trimmedExpectedRoot = expectedRoot.trim();
  const missingRequiredFields = [
    !trimmedDisplayName ? t("agentSetup.fields.nodeName") : null,
    !trimmedExpectedRoot ? t("agentSetup.fields.rootPath") : null,
  ].filter((value): value is string => Boolean(value));
  const formReady = missingRequiredFields.length === 0;
  const canSubmitForm = setup.bootstrap_ready && formReady && !submitting;
  const ctaHighlighted = submitting || canSubmitForm;
  const currentAccessStep = waitingNodeId ? 2 : showGeneratedCommand ? 1 : 0;
  const accessSteps = [
    {
      title: t("agentSetup.steps.info.title"),
      description: t("agentSetup.steps.info.description"),
    },
    {
      title: t("agentSetup.steps.execute.title"),
      description: t("agentSetup.steps.execute.description"),
    },
    {
      title: t("agentSetup.steps.wait.title"),
      description: t("agentSetup.steps.wait.description"),
    },
  ] as const;
  const ctaLabel = !setup.bootstrap_ready
    ? t("agentSetup.cta.unavailable")
    : submitting
      ? t("agentSetup.cta.generating")
      : formReady
        ? t("agentSetup.cta.ready")
        : t("agentSetup.cta.fillMore");
  const ctaTitle = !setup.bootstrap_ready
    ? t("agentSetup.cta.unavailableHint")
    : submitting
      ? t("agentSetup.cta.generatingHint")
      : formReady
        ? t("agentSetup.cta.readyHint")
        : t("agentSetup.cta.missingHint", { count: missingRequiredFields.length });
  const ctaDescription = !setup.bootstrap_ready
    ? t("agentSetup.cta.unavailableDesc")
    : submitting
      ? t("agentSetup.cta.generatingDesc")
      : formReady
        ? t("agentSetup.cta.readyDesc")
        : t("agentSetup.cta.missingDesc", {
            fields: missingRequiredFields.join(t("agentSetup.listSeparator")),
          });

  const promptText = setup.bootstrap_prompt?.trim() || t("agentSetup.promptEmpty");
  const localWebUrl = setup.local_web_url?.trim() || "";
  const localApiHealthUrl = setup.local_api_health_url?.trim() || "";
  const publicUrl = setup.public_url?.trim() || "";
  const publicStatusText = publicStatusLabel(setup, t);
  const publicProviderText = publicProviderLabel(setup.public_url_provider, t);
  const setupIssues = useMemo(() => {
    const items: string[] = [];
    if (!setup.has_openclaw_config) {
      items.push(t("agentSetup.issues.missingConfig"));
    }
    if (setup.node_total === 0) {
      items.push(t("agentSetup.issues.noNodes"));
    }
    if (!setup.bootstrap_ready && setup.bootstrap_reason) {
      items.push(setup.bootstrap_reason);
    }
    return items;
  }, [setup, t]);

  return (
    <section className="space-y-6 pb-10">
      <header className="space-y-4">
        <div className="flex justify-center">
          <div className="inline-flex rounded-full border border-[var(--line)] bg-white px-3 py-1 text-xs font-medium tracking-[0.18em] text-[var(--muted)]">
            {t("agentSetup.header.kicker")}
          </div>
        </div>
        <div className="mx-auto max-w-4xl space-y-3 text-center">
          <h1 className="font-[var(--font-serif)] text-4xl font-semibold text-[var(--text)] md:text-5xl">
            {t("agentSetup.header.title")}
          </h1>
          <p className="mx-auto max-w-3xl text-sm leading-7 text-[var(--muted)] md:text-[15px]">
            {t("agentSetup.header.subtitle")}
          </p>
        </div>
      </header>

      {error ? (
        <div className="rounded-[24px] border border-rose-300 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</div>
      ) : null}

      {copyMessage ? (
        <div className="rounded-[24px] border border-emerald-300 bg-emerald-50 px-5 py-4 text-sm text-emerald-700">{copyMessage}</div>
      ) : null}

      {waitingNodeId ? (
        <div className="flex items-center gap-3 rounded-[24px] border border-sky-200 bg-sky-50 px-5 py-4 text-sm text-sky-800">
          <ArrowClockwiseIcon size={18} className="animate-spin" />
          <div>
            <p className="font-medium">{t("agentSetup.waiting.title")}</p>
            <p className="mt-1">
              {t("agentSetup.waiting.status", {
                nodeId: waitingNodeId,
                status: statusLabel(waitingStatus || "pending", t),
              })}
            </p>
          </div>
        </div>
      ) : null}

      <Card className="rounded-[30px] border-white/80 shadow-[0_20px_60px_rgba(15,23,42,0.06)]">
        <CardHeader>
          <CardTitle className="text-2xl text-[var(--text)]">{t("agentSetup.summary.title")}</CardTitle>
          <CardDescription>{t("agentSetup.summary.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-[22px] border border-[var(--line)] bg-[var(--surface)]/70 px-4 py-3">
              <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.config")}</div>
              <div className="mt-2 text-sm font-semibold text-[var(--text)]">
                {setup.has_openclaw_config ? t("agentSetup.summary.found") : t("agentSetup.summary.missing")}
              </div>
            </div>
            <div className="rounded-[22px] border border-[var(--line)] bg-[var(--surface)]/70 px-4 py-3">
              <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.nodes")}</div>
              <div className="mt-2 text-sm font-semibold text-[var(--text)]">{setup.node_total}</div>
            </div>
            <div className="rounded-[22px] border border-[var(--line)] bg-[var(--surface)]/70 px-4 py-3">
              <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.bootstrap")}</div>
              <div className="mt-2 text-sm font-semibold text-[var(--text)]">
                {setup.bootstrap_ready ? t("agentSetup.summary.ready") : t("agentSetup.summary.unavailable")}
              </div>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-[minmax(0,1.3fr)_minmax(0,0.9fr)]">
            <div className="rounded-[24px] border border-[var(--line)] bg-white px-4 py-4 text-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium text-[var(--text)]">{t("agentSetup.summary.localAccess")}</div>
              </div>
              <div className="mt-3 space-y-3">
                <div className="rounded-[20px] border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.localWeb")}</div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!localWebUrl}
                      onClick={() => localWebUrl && void handleCopy(localWebUrl, t("agentSetup.summary.localWebCopyLabel"))}
                    >
                      <CopyIcon size={14} />
                      {t("common.copy")}
                    </Button>
                  </div>
                  <div className="mt-2 break-all font-mono text-xs leading-6 text-[var(--text)]">
                    {localWebUrl || t("agentSetup.summary.notAvailable")}
                  </div>
                </div>

                <div className="rounded-[20px] border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.localApi")}</div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!localApiHealthUrl}
                      onClick={() =>
                        localApiHealthUrl && void handleCopy(localApiHealthUrl, t("agentSetup.summary.localApiCopyLabel"))
                      }
                    >
                      <CopyIcon size={14} />
                      {t("common.copy")}
                    </Button>
                  </div>
                  <div className="mt-2 break-all font-mono text-xs leading-6 text-[var(--text)]">
                    {localApiHealthUrl || t("agentSetup.summary.notAvailable")}
                  </div>
                </div>

                <div className="rounded-[20px] border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-3">
                  <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.localHealth")}</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--text)]">
                    <span className="rounded-full border border-[var(--line)] bg-white px-3 py-1">
                      {t("agentSetup.summary.localWebCheck")}: {healthLabel(setup.local_web_ok, t)}
                    </span>
                    <span className="rounded-full border border-[var(--line)] bg-white px-3 py-1">
                      {t("agentSetup.summary.localApiCheck")}: {healthLabel(setup.local_api_ok, t)}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-[24px] border border-[var(--line)] bg-white px-4 py-4 text-sm">
              <div className="font-medium text-[var(--text)]">{t("agentSetup.summary.publicAccess")}</div>
              <div className="mt-3 space-y-3">
                <div className="rounded-[20px] border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-3">
                  <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.publicStatus")}</div>
                  <div className="mt-2 text-sm font-semibold text-[var(--text)]">{publicStatusText}</div>
                  {setup.public_url_reason ? (
                    <div className="mt-2 text-xs leading-5 text-[var(--muted)]">
                      {t("agentSetup.summary.publicReason")}: {setup.public_url_reason}
                    </div>
                  ) : null}
                </div>

                <div className="rounded-[20px] border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-3">
                  <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.publicProvider")}</div>
                  <div className="mt-2 text-sm font-semibold text-[var(--text)]">{publicProviderText}</div>
                </div>

                <div className="rounded-[20px] border border-[var(--line)] bg-[var(--surface)]/70 px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{t("agentSetup.summary.publicUrl")}</div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!publicUrl}
                      onClick={() => publicUrl && void handleCopy(publicUrl, t("agentSetup.summary.publicUrlCopyLabel"))}
                    >
                      <CopyIcon size={14} />
                      {t("common.copy")}
                    </Button>
                  </div>
                  <div className="mt-2 break-all font-mono text-xs leading-6 text-[var(--text)]">
                    {publicUrl || t("agentSetup.summary.notGenerated")}
                  </div>
                  {!setup.public_url_enabled ? (
                    <div className="mt-2 text-xs leading-5 text-[var(--muted)]">
                      {t("agentSetup.summary.publicHint")}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-[22px] border border-[var(--line)] bg-white px-4 py-3 text-sm">
            <div className="font-medium text-[var(--text)]">{t("agentSetup.summary.blockers")}</div>
            {setupIssues.length === 0 ? (
              <p className="mt-1 text-[var(--muted)]">{t("agentSetup.summary.noBlockers")}</p>
            ) : (
              <ul className="mt-2 space-y-1 text-[var(--muted)]">
                {setupIssues.map((item) => (
                  <li key={item}>- {item}</li>
                ))}
              </ul>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-[30px] border-white/80 shadow-[0_20px_60px_rgba(15,23,42,0.06)]">
        <CardHeader>
          <CardTitle className="text-2xl text-[var(--text)]">{t("agentSetup.prompt.title")}</CardTitle>
          <CardDescription>{t("agentSetup.prompt.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-[var(--muted)]">{t("agentSetup.prompt.notice")}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => promptText && void handleCopy(promptText, t("agentSetup.prompt.copyLabel"))}
            >
              <CopyIcon size={14} />
              {t("agentSetup.prompt.copy")}
            </Button>
          </div>
          <textarea
            value={promptText}
            readOnly
            className="min-h-[220px] w-full rounded-[24px] border border-[var(--line)] bg-white px-4 py-3 font-mono text-xs leading-6 text-[var(--text)] outline-none"
          />
        </CardContent>
      </Card>

      <Card className="rounded-[30px] border-white/80 shadow-[0_20px_60px_rgba(15,23,42,0.06)]">
        <CardHeader>
          <CardTitle className="text-2xl text-[var(--text)]">
            {showGeneratedCommand ? t("agentSetup.command.title") : t("agentSetup.command.titleFallback")}
          </CardTitle>
          <CardDescription>
            {showGeneratedCommand
              ? t("agentSetup.command.descriptionReady")
              : !setup.bootstrap_ready
                ? t("agentSetup.command.descriptionUnavailable")
                : t("agentSetup.command.descriptionDefault")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {!showGeneratedCommand ? (
            <form className="space-y-4" onSubmit={handleCreateNode}>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-2 text-sm">
                  <span className="font-medium text-[var(--text)]">{t("agentSetup.form.nodeName")}</span>
                  <input
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    placeholder={t("agentSetup.form.nodePlaceholder")}
                    className="h-12 w-full rounded-2xl border border-[var(--line)] bg-white px-4 text-sm text-[var(--text)] outline-none transition focus:border-neutral-400"
                    required
                  />
                </label>

                <label className="space-y-2 text-sm">
                  <span className="font-medium text-[var(--text)]">{t("agentSetup.form.rootLabel")}</span>
                  <input
                    value={expectedRoot}
                    onChange={(event) => setExpectedRoot(event.target.value)}
                    placeholder="~/.openclaw"
                    className="h-12 w-full rounded-2xl border border-[var(--line)] bg-white px-4 text-sm text-[var(--text)] outline-none transition focus:border-neutral-400"
                    required
                  />
                </label>
              </div>

              <div className="rounded-[24px] border border-[var(--line)] bg-[var(--surface)]/82 px-4 py-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-stretch">
                  {accessSteps.map((step, index) => {
                    const reached = index < currentAccessStep;
                    const current = index === currentAccessStep;
                    return (
                      <div key={step.title} className="flex min-w-0 flex-1 items-center gap-3">
                        <div
                          className={cn(
                            "flex min-w-0 flex-1 items-start gap-3 rounded-[22px] border px-4 py-4 transition",
                            reached
                              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                              : current
                                ? "border-neutral-950 bg-white text-[var(--text)] shadow-[0_10px_24px_rgba(15,23,42,0.06)]"
                                : "border-[var(--line)] bg-white/70 text-[var(--muted)]",
                          )}
                        >
                          <div
                            className={cn(
                              "grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-semibold",
                              reached
                                ? "bg-emerald-600 text-white"
                                : current
                                  ? "bg-neutral-950 text-white"
                                  : "bg-[var(--surface)] text-[var(--muted)]",
                            )}
                          >
                            {reached ? <CheckCircleIcon size={18} weight="bold" /> : index + 1}
                          </div>
                          <div className="min-w-0">
                            <p className={cn("text-sm font-semibold", current || reached ? "text-[inherit]" : "text-[var(--text)]")}>{step.title}</p>
                            <p className="mt-1 text-xs leading-5 opacity-80">{step.description}</p>
                          </div>
                        </div>
                        {index < accessSteps.length - 1 ? <div className="hidden h-px w-5 shrink-0 bg-[var(--line)] md:block" /> : null}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div
                aria-live="polite"
                className={cn(
                  "rounded-[26px] border px-4 py-4 transition duration-200 md:px-5",
                  ctaHighlighted
                    ? "border-neutral-950 bg-[linear-gradient(135deg,rgba(15,23,42,0.06),rgba(255,255,255,0.98)_55%)] shadow-[0_18px_40px_rgba(15,23,42,0.08)]"
                    : "border-[var(--line)] bg-white",
                )}
              >
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0 space-y-2">
                    <div
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
                        ctaHighlighted
                          ? "border-neutral-950/10 bg-neutral-950 text-white"
                          : "border-[var(--line)] bg-[var(--surface)] text-[var(--muted)]",
                      )}
                    >
                      {submitting ? <ArrowClockwiseIcon size={14} className="animate-spin" /> : null}
                      {!submitting && formReady && setup.bootstrap_ready ? <CheckCircleIcon size={14} weight="fill" /> : null}
                      <span>
                        {submitting
                          ? t("agentSetup.cta.processing")
                          : canSubmitForm
                            ? t("agentSetup.cta.clickable")
                            : !setup.bootstrap_ready
                              ? t("agentSetup.cta.disabled")
                              : t("agentSetup.cta.fillMore")}
                      </span>
                    </div>
                    <div>
                      <p className="text-base font-semibold text-[var(--text)]">{ctaTitle}</p>
                      <p className="mt-1 text-sm leading-6 text-[var(--muted)]">{ctaDescription}</p>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    size="lg"
                    disabled={!canSubmitForm}
                    className={cn(
                      "h-12 w-full rounded-[18px] px-6 text-sm font-semibold transition md:min-w-[220px] md:w-auto",
                      submitting
                        ? "bg-[var(--brand-ink)] text-white shadow-[0_16px_34px_rgba(15,23,42,0.18)] disabled:opacity-100"
                        : canSubmitForm
                          ? "shadow-[0_16px_34px_rgba(15,23,42,0.18)] hover:-translate-y-0.5 hover:bg-black"
                          : "bg-neutral-200 text-neutral-500 hover:bg-neutral-200",
                    )}
                  >
                    {submitting ? <ArrowClockwiseIcon size={16} className="animate-spin" /> : null}
                    <span>{ctaLabel}</span>
                    {!submitting && canSubmitForm ? <ArrowRightIcon size={16} /> : null}
                  </Button>
                </div>
              </div>
            </form>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-base font-semibold text-[var(--text)]">{t("agentSetup.command.title")}</p>
                  <p className="mt-1 text-sm text-[var(--muted)]">{t("agentSetup.command.descriptionReady")}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" variant="secondary" size="sm" onClick={handleResetGeneratedCommand}>
                    {t("agentSetup.command.reset")}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!commandToCopy}
                    onClick={() => commandToCopy && void handleCopy(commandToCopy, t("agentSetup.command.copyLabel"))}
                  >
                    <CopyIcon size={14} />
                    {t("common.copy")}
                  </Button>
                </div>
              </div>

              <div className="space-y-3 rounded-[28px] border border-[var(--line)] bg-[var(--surface)]/85 p-4">
                <textarea
                  value={commandToCopy || t("agentSetup.command.unavailable")}
                  readOnly
                  className="min-h-[140px] w-full rounded-[24px] border border-[var(--line)] bg-white px-4 py-3 font-mono text-xs leading-6 text-[var(--text)] outline-none"
                />
                {latestBootstrap ? (
                  <div className="flex flex-wrap items-center gap-3 rounded-[22px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                    <CheckCircleIcon size={18} />
                    <span>
                      {t("agentSetup.command.created", {
                        name: latestBootstrap.node.display_name,
                        status: statusLabel(latestBootstrap.node.status, t),
                      })}
                    </span>
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
