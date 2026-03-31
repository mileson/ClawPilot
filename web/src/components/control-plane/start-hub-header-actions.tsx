"use client";

import Link from "next/link";
import { startTransition, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowClockwiseIcon, PlugChargingIcon, RocketLaunchIcon } from "@phosphor-icons/react";

import { getControlPlaneAction, startControlPlaneAction, syncAgents } from "@/lib/api";
import { Button, buttonVariants } from "@/components/ui/button";
import type { ControlPlaneActionAccepted, ControlPlaneJobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export function StartHubSyncAgentsButton({
  className,
}: {
  className?: string;
}) {
  const router = useRouter();
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  async function handleSyncAgents() {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await syncAgents();
      setSyncMessage(`已同步 ${result.synced} 个 Agent`);
      startTransition(() => {
        router.refresh();
      });
    } catch (error) {
      setSyncMessage(error instanceof Error ? error.message : "同步 Agent 失败");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className={cn("flex flex-col items-start gap-2", className)}>
      <Button type="button" variant="outline" onClick={() => void handleSyncAgents()} disabled={syncing}>
        <ArrowClockwiseIcon size={16} className={syncing ? "animate-spin" : undefined} />
        {syncing ? "同步中" : "同步 Agent"}
      </Button>
      {syncMessage ? (
        <p className="text-xs leading-5 text-[var(--muted)]">
          {syncMessage}
        </p>
      ) : null}
    </div>
  );
}

function resolveOpenClawUpdateMessage(
  action: "install_openclaw" | "update_status" | "update_install",
  job: ControlPlaneJobStatus,
) {
  const detail = (job.detail || {}) as Record<string, unknown>;
  const result = detail.result as Record<string, unknown> | undefined;
  const summarySource =
    (result?.after as Record<string, unknown> | undefined) ||
    (result?.summary as Record<string, unknown> | undefined) ||
    {};
  const currentVersion = typeof summarySource.openclaw_current_version === "string" ? summarySource.openclaw_current_version : null;
  const latestVersion = typeof summarySource.openclaw_latest_version === "string" ? summarySource.openclaw_latest_version : null;
  const updateAvailable = Boolean(summarySource.openclaw_update_available);

  if (action === "install_openclaw") {
    if (currentVersion) {
      return `OpenClaw 安装已完成，当前版本 ${currentVersion}`;
    }
    return "OpenClaw 安装已完成";
  }

  if (action === "update_install") {
    if (currentVersion && latestVersion && currentVersion === latestVersion) {
      return `OpenClaw 已升级到最新稳定版 ${latestVersion}`;
    }
    if (currentVersion) {
      return `OpenClaw 已完成升级，当前版本 ${currentVersion}`;
    }
    return "OpenClaw 升级已完成";
  }

  if (updateAvailable && currentVersion && latestVersion) {
    return `检测到可升级版本：当前 ${currentVersion}，最新 ${latestVersion}`;
  }
  if (currentVersion && latestVersion) {
    return `当前已是最新稳定版：${currentVersion}`;
  }
  if (currentVersion) {
    return `已完成版本检查：当前版本 ${currentVersion}`;
  }
  return "已完成 OpenClaw 更新检查";
}

export function StartHubOpenClawUpdateActions({
  installed,
  updateAvailable,
  latestVersion,
  className,
}: {
  installed: boolean;
  updateAvailable: boolean;
  latestVersion?: string | null;
  className?: string;
}) {
  const router = useRouter();
  const [loadingAction, setLoadingAction] = useState<"install_openclaw" | "update_status" | "update_install" | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function pollJob(
    accepted: ControlPlaneActionAccepted,
    action: "install_openclaw" | "update_status" | "update_install",
  ) {
    let finished = false;
    while (!finished) {
      const payload = await getControlPlaneAction(accepted.job_id);
      if (payload.status === "completed") {
        setMessage(resolveOpenClawUpdateMessage(action, payload));
        startTransition(() => {
          router.refresh();
        });
        finished = true;
      } else if (payload.status === "failed") {
        setMessage(payload.error_message || "OpenClaw 更新动作执行失败");
        finished = true;
      } else {
        await new Promise((resolve) => window.setTimeout(resolve, 900));
      }
    }
  }

  async function runAction(action: "install_openclaw" | "update_status" | "update_install") {
    setLoadingAction(action);
    setMessage(null);
    try {
      const accepted = await startControlPlaneAction(action);
      await pollJob(accepted, action);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "OpenClaw 更新动作执行失败");
    } finally {
      setLoadingAction(null);
    }
  }

  if (!installed) {
    return (
      <div className={cn("flex flex-col items-start gap-2", className)}>
        <Button
          type="button"
          onClick={() => {
            if (window.confirm("这会自动安装最新稳定版 OpenClaw CLI，确定继续吗？")) {
              void runAction("install_openclaw");
            }
          }}
          disabled={loadingAction !== null}
        >
          <RocketLaunchIcon size={16} />
          {loadingAction === "install_openclaw" ? "安装中..." : "一键安装 OpenClaw"}
        </Button>
        {message ? <p className="text-xs leading-5 text-[var(--muted)]">{message}</p> : null}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col items-start gap-2", className)}>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => void runAction("update_status")}
          disabled={loadingAction !== null}
        >
          <ArrowClockwiseIcon size={16} className={loadingAction === "update_status" ? "animate-spin" : undefined} />
          {loadingAction === "update_status" ? "检查中..." : "检查更新状态"}
        </Button>
        {updateAvailable ? (
          <Button
            type="button"
            onClick={() => {
              if (window.confirm(`这会执行 OpenClaw CLI 自动升级${latestVersion ? `到 ${latestVersion}` : ""}，确定继续吗？`)) {
                void runAction("update_install");
              }
            }}
            disabled={loadingAction !== null}
          >
            <RocketLaunchIcon size={16} />
            {loadingAction === "update_install" ? "升级中..." : latestVersion ? `升级到 ${latestVersion}` : "立即升级"}
          </Button>
        ) : null}
      </div>
      {message ? <p className="text-xs leading-5 text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}

export function StartHubHeaderActions() {
  return (
    <div className="flex flex-col items-start gap-4">
      <div className="flex flex-wrap gap-2">
        <Link href="/nodes" className={buttonVariants()}>
          <PlugChargingIcon size={16} />
          连接本地节点
        </Link>
        <Link href="/add-agent" className={buttonVariants({ variant: "outline" })}>
          <RocketLaunchIcon size={16} />
          新增 Agent
        </Link>
        <StartHubSyncAgentsButton />
      </div>
    </div>
  );
}
