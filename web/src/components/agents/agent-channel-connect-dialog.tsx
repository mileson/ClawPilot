"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createPortal } from "react-dom";
import { CaretDownIcon, CaretRightIcon, CheckCircleIcon, MagicWandIcon, XIcon } from "@phosphor-icons/react";

import { autoCreateFeishuApp, confirmAgentFeishuPairing, connectAgentFeishuChannel, syncAgents } from "@/lib/api";
import type { Agent, AgentFeishuPairingConfirmResult } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function AgentChannelConnectDialog({
  agent,
  open,
  onOpenChange,
}: {
  agent: Agent;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [operatorOpenId, setOperatorOpenId] = useState("");
  const [identityKey, setIdentityKey] = useState("default");
  const [submitting, setSubmitting] = useState(false);
  const [autoCreating, setAutoCreating] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [chatUrl, setChatUrl] = useState<string | null>(null);
  const [needsPairing, setNeedsPairing] = useState(false);
  const [pairingText, setPairingText] = useState("");
  const [pairingConfirming, setPairingConfirming] = useState(false);
  const [pairingConfirmed, setPairingConfirmed] = useState<AgentFeishuPairingConfirmResult | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onOpenChange(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpenChange, open]);

  useEffect(() => {
    if (!open || typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSuccessMessage(null);
    setChatUrl(null);
    setNeedsPairing(false);
    setPairingText("");
    setPairingConfirmed(null);
    setManualOpen(false);
    setAppId("");
    setAppSecret("");
    setOperatorOpenId("");
    setIdentityKey("default");
  }, [open]);

  if (!open || !mounted || typeof document === "undefined") return null;

  const connectedChannels = agent.connected_channels || [];
  const channelStatusLabel =
    agent.channel_status === "missing" ? "待配置渠道" : agent.channel_status === "warning" ? "渠道异常" : "已接入渠道";
  const parsedPairing = parseFeishuPairingText(pairingText);

  async function handleManualSubmit() {
    if (!appId.trim() || !appSecret.trim()) {
      setError("请先填写 appId 和 appSecret，再执行手动接入。");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const result = await connectAgentFeishuChannel(agent.agent_id, {
        app_id: appId.trim(),
        app_secret: appSecret.trim(),
        operator_open_id: operatorOpenId.trim() || undefined,
        identity_key: identityKey.trim() || "default",
      });
      setNeedsPairing(result.warnings.includes("feishu_identity_pending_pairing"));
      setPairingConfirmed(null);
      setSuccessMessage(
        result.warnings.includes("feishu_identity_pending_pairing")
          ? "渠道已接入，但还需要完成一次私聊或 pairing 才能补齐 Feishu 身份。"
          : "Feishu 渠道已接入完成。",
      );
      await syncAgents();
      router.refresh();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "接入 Feishu 渠道失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAutoCreate() {
    setAutoCreating(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const result = await autoCreateFeishuApp({
        app_name: agent.display_name || agent.agent_id,
        app_description: `${agent.display_name || agent.agent_id} 的 Feishu 渠道接入`,
        menu_name: "ClawPilot",
      });
      if (result.status !== "success" || !result.app_id || !result.app_secret) {
        throw new Error(result.message || "自动创建 Feishu 应用失败");
      }
      setAppId(result.app_id);
      setAppSecret(result.app_secret);
      const connected = await connectAgentFeishuChannel(agent.agent_id, {
        app_id: result.app_id,
        app_secret: result.app_secret,
        identity_key: identityKey.trim() || "default",
      });
      setChatUrl(result.chat_url || null);
      setNeedsPairing(connected.warnings.includes("feishu_identity_pending_pairing"));
      setPairingConfirmed(null);
      setSuccessMessage(
        connected.warnings.includes("feishu_identity_pending_pairing")
          ? "飞书机器人已自动创建并接入当前 Agent。下一步请打开飞书私聊它，完成 pairing / 身份补全。"
          : "飞书机器人已自动创建并接入当前 Agent。",
      );
      if (result.chat_url) {
        window.open(result.chat_url, "_blank", "noopener,noreferrer");
      }
      await syncAgents();
      router.refresh();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "自动创建并接入 Feishu 渠道失败");
    } finally {
      setAutoCreating(false);
    }
  }

  async function handlePairingConfirm() {
    if (!pairingText.trim()) {
      setError("请先粘贴机器人回复的整段文本，再继续自动配对。");
      return;
    }
    setPairingConfirming(true);
    setError(null);
    try {
      const result = await confirmAgentFeishuPairing(agent.agent_id, {
        pairing_text: pairingText.trim(),
      });
      setPairingConfirmed(result);
      setNeedsPairing(false);
      setSuccessMessage("飞书身份补全已完成，当前 Agent 的 Feishu 渠道已就绪。");
      await syncAgents();
      router.refresh();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "自动完成 Feishu pairing 失败");
    } finally {
      setPairingConfirming(false);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/30 px-4 py-6 backdrop-blur-sm">
      <div className="absolute inset-0" onClick={() => onOpenChange(false)} />
      <section className="relative z-[91] w-full max-w-2xl rounded-[30px] border border-[var(--line)] bg-white p-6 shadow-[0_28px_80px_rgba(15,23,42,0.18)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-[var(--muted)]">接入渠道</p>
            <h2 className="mt-2 text-xl font-semibold text-[var(--text)]">
              {agent.display_name} ({agent.agent_id})
            </h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              直接复用当前 Agent 名称。当前自动接入优先支持 Feishu。
            </p>
          </div>
          <Button type="button" variant="outline" size="icon" className="rounded-full" onClick={() => onOpenChange(false)}>
            <XIcon size={16} />
          </Button>
        </div>

        <div className="mt-5 rounded-[22px] border border-[var(--line)] bg-[var(--surface)]/35 p-4">
          <p className="text-sm font-medium text-[var(--text)]">当前渠道状态</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant={agent.channel_status === "warning" ? "probation" : agent.channel_status === "missing" ? "suspended" : "active"}>
              {channelStatusLabel}
            </Badge>
            {connectedChannels.map((item) => (
              <Badge key={`${item.channel}:${item.account_id || "none"}`} variant="neutral">
                {item.primary ? "主渠道 · " : ""}
                {item.channel}
              </Badge>
            ))}
          </div>
        </div>

        <div className="mt-5 rounded-[24px] border border-[var(--line)] bg-[linear-gradient(180deg,rgba(17,17,19,0.98),rgba(33,33,37,0.98))] p-5 text-white shadow-[0_20px_45px_rgba(15,23,42,0.16)]">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-white/80">
                <MagicWandIcon size={14} />
                一键自动化
              </div>
              <h3 className="text-xl font-semibold">自动创建飞书机器人并接入当前 Agent</h3>
              <p className="max-w-xl text-sm leading-7 text-white/72">
                不需要预先填写任何输入内容。系统会直接复用本地浏览器登录态自动创建 Feishu 机器人，并把 appId / appSecret 回填后接入当前 Agent。
              </p>
            </div>
            <Button type="button" variant="outline" className="border-white/20 bg-white/10 !text-white hover:bg-white/15 hover:!text-white disabled:!text-white" onClick={() => void handleAutoCreate()} disabled={submitting || autoCreating}>
              {autoCreating ? "自动创建中..." : "一键自动化创建飞书机器人"}
            </Button>
          </div>
        </div>

        <div className="mt-5 rounded-[22px] border border-dashed border-[var(--line)] bg-[var(--surface)]/35 p-4 text-sm leading-7 text-[var(--muted)]">
          自动创建成功后会为该 Agent 写入 Feishu account 与 binding。若当前还没补齐 operator 身份，系统会先以“已接入但待配对”的 warning 状态收口，后续去飞书私聊机器人即可继续补齐。
        </div>

        {error ? <p className="mt-4 text-sm text-rose-600">{error}</p> : null}
        {successMessage ? (
          <div className="mt-4 rounded-[22px] border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-800">
            <div className="flex items-start gap-3">
              <CheckCircleIcon size={18} className="mt-0.5 shrink-0" />
              <div className="space-y-2">
                <p className="font-medium">{successMessage}</p>
                {needsPairing ? (
                  <p className="leading-7">
                    如果卡片状态仍显示“渠道异常”，通常只是还缺最后一步身份补全。打开飞书对话，给机器人发一条消息，或继续执行 pairing approve。
                  </p>
                ) : null}
                {chatUrl ? (
                  <div className="pt-1">
                    <Button type="button" variant="outline" onClick={() => window.open(chatUrl, "_blank", "noopener,noreferrer")}>
                      打开飞书对话
                    </Button>
                  </div>
                ) : null}
                {needsPairing ? (
                  <div className="space-y-3 rounded-[18px] border border-emerald-200 bg-white/75 px-3 py-3 text-emerald-900">
                    <div className="space-y-1">
                      <p className="text-sm font-medium">粘贴飞书机器人回复的整段内容</p>
                      <p className="text-xs leading-6 text-emerald-800/80">
                        系统会自动提取 `Feishu user id` 和 `Pairing code`，并执行标准化 pairing 配置。
                      </p>
                    </div>
                    <textarea
                      value={pairingText}
                      onChange={(event) => setPairingText(event.target.value)}
                      placeholder={"OpenClaw: access not configured.\nYour Feishu user id: ou_xxx\nPairing code: ABCD1234\nAsk the bot owner to approve with:\nopenclaw pairing approve feishu ABCD1234"}
                      className="min-h-[132px] w-full rounded-2xl border border-emerald-200 bg-white px-4 py-3 text-sm text-[var(--text)] outline-none"
                    />
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-3 py-3">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-emerald-700/80">Feishu user id</p>
                        <p className="mt-2 break-all text-sm font-medium text-emerald-900">{parsedPairing.userOpenId || "未识别"}</p>
                      </div>
                      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-3 py-3">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-emerald-700/80">Pairing code</p>
                        <p className="mt-2 break-all text-sm font-medium text-emerald-900">{parsedPairing.pairingCode || "未识别"}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" onClick={() => void handlePairingConfirm()} disabled={pairingConfirming || !parsedPairing.valid}>
                        {pairingConfirming ? "自动配对中..." : "自动提取并完成配对"}
                      </Button>
                    </div>
                    {pairingConfirmed ? (
                      <div className="rounded-2xl border border-emerald-200 bg-emerald-100 px-3 py-3 text-sm">
                        已完成配对：{pairingConfirmed.user_open_id} / {pairingConfirmed.pairing_code}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-5 rounded-[22px] border border-[var(--line)] bg-white">
          <button
            type="button"
            onClick={() => setManualOpen((current) => !current)}
            className="flex w-full items-center justify-between gap-3 px-4 py-4 text-left"
          >
            <div>
              <p className="text-sm font-medium text-[var(--text)]">手动录入</p>
              <p className="mt-1 text-sm text-[var(--muted)]">只有自动创建不可用时，才需要手动填写 appId / appSecret。</p>
            </div>
            {manualOpen ? <CaretDownIcon size={18} className="text-[var(--muted)]" /> : <CaretRightIcon size={18} className="text-[var(--muted)]" />}
          </button>

          {manualOpen ? (
            <div className="grid gap-4 border-t border-[var(--line)] px-4 py-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium text-[var(--text)]">appId</label>
                <input
                  value={appId}
                  onChange={(event) => setAppId(event.target.value)}
                  placeholder="cli_xxx"
                  className="w-full rounded-2xl border border-[var(--line)] bg-[var(--surface)]/50 px-4 py-3 text-sm outline-none"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-[var(--text)]">appSecret</label>
                <input
                  value={appSecret}
                  onChange={(event) => setAppSecret(event.target.value)}
                  placeholder="******"
                  className="w-full rounded-2xl border border-[var(--line)] bg-[var(--surface)]/50 px-4 py-3 text-sm outline-none"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-[var(--text)]">operator open_id（可选）</label>
                <input
                  value={operatorOpenId}
                  onChange={(event) => setOperatorOpenId(event.target.value)}
                  placeholder="ou_xxx"
                  className="w-full rounded-2xl border border-[var(--line)] bg-[var(--surface)]/50 px-4 py-3 text-sm outline-none"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-[var(--text)]">identity key</label>
                <input
                  value={identityKey}
                  onChange={(event) => setIdentityKey(event.target.value)}
                  placeholder="default"
                  className="w-full rounded-2xl border border-[var(--line)] bg-[var(--surface)]/50 px-4 py-3 text-sm outline-none"
                />
              </div>
              <div className="md:col-span-2">
                <Button type="button" onClick={() => void handleManualSubmit()} disabled={submitting || autoCreating}>
                  {submitting ? "保存中..." : "手动保存渠道"}
                </Button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

function parseFeishuPairingText(value: string) {
  const text = String(value || "").trim();
  if (!text) {
    return { userOpenId: "", pairingCode: "", valid: false };
  }
  const openIdMatch = text.match(/Your\s+Feishu\s+user\s+id:\s*(ou_[A-Za-z0-9]+)/i);
  const codeMatch =
    text.match(/Pairing\s+code:\s*([A-Z0-9]+)/i) ||
    text.match(/openclaw\s+pairing\s+approve\s+feishu\s+([A-Z0-9]+)/i);
  const userOpenId = openIdMatch?.[1]?.trim() || "";
  const pairingCode = codeMatch?.[1]?.trim().toUpperCase() || "";
  return {
    userOpenId,
    pairingCode,
    valid: Boolean(userOpenId && pairingCode),
  };
}
