import Link from "next/link";

import type { Agent, NodeConnection, SetupStatus } from "@/lib/types";
import { buttonVariants } from "@/components/ui/button";
import { StartHubCompletionButton } from "@/components/control-plane/start-hub-completion-button";
import { StartHubOpenClawUpdateActions, StartHubSyncAgentsButton } from "@/components/control-plane/start-hub-header-actions";

function stepTone(done: boolean) {
  return done
    ? "border-emerald-200 bg-emerald-50/80 text-emerald-700"
    : "border-amber-200 bg-amber-50/80 text-amber-700";
}

export function StartHubPage({
  setup,
  nodes,
  agents,
}: {
  setup: SetupStatus;
  nodes: NodeConnection[];
  agents: Agent[];
}) {
  const onlineNodes = nodes.filter((node) => node.status === "online").length;
  const currentOpenClawVersion = setup.openclaw_current_version?.trim() || null;
  const latestOpenClawVersion = setup.openclaw_latest_version?.trim() || null;
  const openclawInstalled = Boolean(setup.openclaw_cli_installed || currentOpenClawVersion);
  const openclawUpdateAvailable = Boolean(setup.openclaw_update_available);
  const openclawStepDone = openclawInstalled && (latestOpenClawVersion ? !openclawUpdateAvailable : true);
  const panelInitialized =
    setup.install_result === "success" && Boolean(setup.has_openclaw_config) && Boolean(setup.local_web_ok) && Boolean(setup.local_api_ok);
  const publicAccessReady = setup.public_url_status === "verified" && Boolean(setup.public_url);

  const steps = [
    {
      title: "检查 OpenClaw 是否已安装并更新到最新",
      done: openclawStepDone,
      hint: !openclawInstalled
        ? "当前还没有检测到 OpenClaw CLI，请先完成安装后再继续初始化。"
        : openclawUpdateAvailable && currentOpenClawVersion && latestOpenClawVersion
          ? `已安装 OpenClaw ${currentOpenClawVersion}，最新稳定版是 ${latestOpenClawVersion}，建议先升级后再继续。`
          : currentOpenClawVersion && latestOpenClawVersion
            ? `已检测到 OpenClaw ${currentOpenClawVersion}，当前已是最新稳定版 ${latestOpenClawVersion}。`
            : currentOpenClawVersion
              ? `已检测到 OpenClaw ${currentOpenClawVersion}，可以继续下一步初始化。`
              : "已检测到 OpenClaw CLI，可以继续下一步初始化。",
      actionHref: "/repair",
      actionLabel: !openclawInstalled ? "先检查安装" : openclawUpdateAvailable ? "检查更新状态" : "查看安装状态",
      actionType: "openclaw_update",
    },
    {
      title: "完成面板初始化并打开公网访问",
      done: panelInitialized && publicAccessReady,
      hint: !panelInitialized
        ? "还没有完成面板初始化，请先把本地控制面、openclaw.json 和健康检查跑通。"
        : !publicAccessReady
          ? setup.public_url
            ? `初始化已完成，但公网入口当前仍未验证通过：${setup.public_url}。请继续完成公网配置。`
            : "初始化已完成，但还没有打开公网访问。请继续在面板里开启公网入口。"
          : `面板初始化和公网访问都已完成，当前公网地址是 ${setup.public_url}。`,
      actionHref: "/nodes",
      actionLabel: panelInitialized && publicAccessReady ? "查看公网状态" : "完成初始化",
    },
    {
      title: "连接第一台本地节点",
      done: onlineNodes > 0,
      hint: onlineNodes > 0 ? `当前已有 ${onlineNodes} 台在线节点，本地执行链路已经就绪。` : "还没有在线节点，先把第一台本地节点接进来，后续运行才会真正落地。",
      actionHref: "/nodes",
      actionLabel: onlineNodes > 0 ? "查看节点状态" : "连接本地节点",
    },
    {
      title: "创建第一只 Agent",
      done: agents.length > 0,
      hint: agents.length > 0 ? `当前已有 ${agents.length} 只 Agent，可直接进入工区继续配置和运营。` : "先创建第一只 Agent，后续训练、渠道接入和工作流都会围绕它展开。",
      actionHref: agents.length > 0 ? "/agents" : "/add-agent",
      actionLabel: agents.length > 0 ? "进入 Agent 工区" : "创建第一只 Agent",
      showSyncAction: true,
    },
  ];
  const remainingSteps = steps.filter((item) => !item.done).length;
  const allStepsDone = remainingSteps === 0;

  return (
    <section>
      <article className="rounded-[28px] border border-[var(--line)] bg-white px-5 py-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[#9b8f7d]">首次初始化</p>
          <h2 className="mt-2 text-2xl font-semibold text-[var(--text)]">ClawPilot 初始化配置</h2>
          <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
            先把 OpenClaw 安装检查、面板初始化、公网访问、本地节点和第一只 Agent 跑通，再进入 Agent 工区继续运营。
          </p>
        </div>
        <div className="mt-6 space-y-4">
          {steps.map((step, index) => (
            <article
              key={step.title}
              className="rounded-[24px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4"
            >
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div className="flex min-w-0 gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[var(--line)] bg-white text-sm font-semibold text-[var(--text)]">
                    {index + 1}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                      <h3 className="text-lg font-semibold text-[var(--text)]">{step.title}</h3>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold ${stepTone(step.done)}`}
                      >
                        <span
                          aria-hidden="true"
                          className={`h-2 w-2 rounded-full ${step.done ? "bg-current" : "border border-current bg-transparent"}`}
                        />
                        {step.done ? "已完成" : "未完成"}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-7 text-[var(--muted)]">{step.hint}</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-start justify-end gap-2">
                  {step.actionType === "openclaw_update" ? (
                    <StartHubOpenClawUpdateActions
                      installed={openclawInstalled}
                      updateAvailable={openclawUpdateAvailable}
                      latestVersion={latestOpenClawVersion}
                    />
                  ) : null}
                  {step.showSyncAction ? <StartHubSyncAgentsButton /> : null}
                  {step.actionType !== "openclaw_update" ? (
                    <Link href={step.actionHref} className={buttonVariants({ variant: "outline" })}>
                      {step.actionLabel}
                    </Link>
                  ) : null}
                </div>
              </div>
            </article>
          ))}
        </div>
        <div className="mt-5">
          <StartHubCompletionButton disabled={!allStepsDone} remainingCount={remainingSteps} />
        </div>
      </article>
    </section>
  );
}
