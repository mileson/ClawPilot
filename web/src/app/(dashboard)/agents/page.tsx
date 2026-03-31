import Link from "next/link";

import { AgentsBackendUnavailable } from "@/components/agents/agents-backend-unavailable";
import { AgentSetupHome } from "@/components/agents/agent-setup-home";
import { AgentsViewModePanel } from "@/components/agents/agents-view-mode-panel";
import { AgentsEmptyState } from "@/components/agents/agents-empty-state";
import { WeixinBridgePanel } from "@/components/agents/weixin-bridge-panel";
import { PageHeader } from "@/components/layout/page-header";
import { buttonVariants } from "@/components/ui/button";
import { getAgentScheduledJobs, getAgents, getSetupStatus, getSystemSettings, getTasks, getTrainingRuns } from "@/lib/api";
import { cn } from "@/lib/utils";

export const revalidate = 0;
const DEFAULT_SERVER_API_BASE = process.env.OPENCLAW_API_BASE || "http://127.0.0.1:8088";

export default async function AgentsPage() {
  let agents: Awaited<ReturnType<typeof getAgents>> = [];
  let setup: Awaited<ReturnType<typeof getSetupStatus>> | null = null;
  let systemSettings: Awaited<ReturnType<typeof getSystemSettings>> | null = null;
  let trainingRuns: Awaited<ReturnType<typeof getTrainingRuns>> = [];
  let tasks: Awaited<ReturnType<typeof getTasks>> = [];
  let loadError: string | null = null;

  try {
    [agents, setup, systemSettings, trainingRuns, tasks] = await Promise.all([
      getAgents(),
      getSetupStatus(),
      getSystemSettings().catch(() => null),
      getTrainingRuns().catch(() => []),
      getTasks().catch(() => []),
    ]);
  } catch (error) {
    loadError = error instanceof Error ? error.message : "fetch failed";
  }

  if (loadError || !setup) {
    return (
      <section>
        <PageHeader titleKey="pages.agents.title" subtitleKey="pages.agents.subtitle" />
        <AgentsBackendUnavailable apiBase={DEFAULT_SERVER_API_BASE} errorMessage={loadError || "fetch failed"} />
      </section>
    );
  }

  if (!setup.has_openclaw_config) {
    return <AgentSetupHome setup={setup} />;
  }

  const workingCount = agents.filter((agent) => agent.runtime_status === "working").length;
  const idleCount = agents.filter((agent) => agent.runtime_status === "idle").length;
  const offlineCount = agents.filter((agent) => agent.runtime_status === "offline").length;
  const crashedCount = agents.filter((agent) => agent.runtime_status === "crashed").length;
  const trainingAgentIds = new Set(trainingRuns.map((run) => run.agent_id));
  const trainingCountByAgent = new Map<string, number>();
  const latestTrainingAtByAgent = new Map<string, string | null>();
  const openTaskCountByAgent = new Map<string, number>();
  for (const run of trainingRuns) {
    trainingCountByAgent.set(run.agent_id, (trainingCountByAgent.get(run.agent_id) || 0) + 1);
    const existing = latestTrainingAtByAgent.get(run.agent_id);
    const candidate = run.updated_at || null;
    if (!existing || (candidate && candidate > existing)) {
      latestTrainingAtByAgent.set(run.agent_id, candidate);
    }
  }
  for (const task of tasks) {
    if (!["todo", "doing", "review"].includes(task.status)) continue;
    openTaskCountByAgent.set(task.assignee_agent_id, (openTaskCountByAgent.get(task.assignee_agent_id) || 0) + 1);
  }
  const scheduledJobsByAgent = new Map<string, number>();
  await Promise.all(
    agents.map(async (agent) => {
      try {
        const payload = await getAgentScheduledJobs(agent.agent_id);
        scheduledJobsByAgent.set(agent.agent_id, payload.jobs.length);
      } catch {
        scheduledJobsByAgent.set(agent.agent_id, 0);
      }
    }),
  );
  const missingIdentityAgents = agents.filter((agent) => !agent.identity_complete);
  const riskyAgents = agents.filter(
    (agent) => agent.runtime_status === "crashed" || agent.runtime_status === "offline" || !agent.identity_complete,
  );

  return (
    <section>
      <div className="mb-5 rounded-[28px] border border-[var(--line)] bg-white px-6 py-6 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-[#9b8f7d]">Agent 工区</p>
            <PageHeader titleKey="pages.agents.title" subtitleKey="pages.agents.subtitle" className="mb-0 mt-2" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/add-agent" className={buttonVariants()}>
              新增 Agent
            </Link>
            <Link href="/training" className={buttonVariants({ variant: "outline" })}>
              发起培训
            </Link>
            <Link href="/agent-configs" className={buttonVariants({ variant: "outline" })}>
              配置与模板
            </Link>
          </div>
        </div>
      </div>

      {riskyAgents.length > 0 ? (
        <div className="mb-5 rounded-[24px] border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          <p className="font-semibold">当前有 {riskyAgents.length} 个 Agent 需要优先处理</p>
          <p className="mt-2 leading-7">
            {missingIdentityAgents.length > 0 ? `其中 ${missingIdentityAgents.length} 个还没补齐身份配置。` : ""}
            {crashedCount + offlineCount > 0
              ? ` ${crashedCount + offlineCount} 个处于异常或离线状态，建议优先进入修复问题页。`
              : ""}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/repair" className={cn(buttonVariants({ variant: "outline" }), "inline-flex")}>
              去修复问题
            </Link>
            <Link href="/training" className={cn(buttonVariants({ variant: "outline" }), "inline-flex")}>
              批量发起培训
            </Link>
          </div>
        </div>
      ) : null}

      {agents.length === 0 ? (
        <AgentsEmptyState />
      ) : (
        <>
          <AgentsViewModePanel
            systemSettings={systemSettings}
            stats={[
              { label: "全部 Agent", value: agents.length },
              { label: "工作中", value: workingCount },
              { label: "空闲中", value: idleCount },
              { label: "异常 / 离线", value: offlineCount + crashedCount },
              { label: "已进入训练记录", value: trainingAgentIds.size },
            ]}
            items={agents.map((agent) => ({
              agent,
              summary: {
                trainingCount: trainingCountByAgent.get(agent.agent_id) || 0,
                latestTrainingAt: latestTrainingAtByAgent.get(agent.agent_id) || null,
                scheduledJobCount: scheduledJobsByAgent.get(agent.agent_id) || 0,
                openTaskCount: openTaskCountByAgent.get(agent.agent_id) || 0,
              },
            }))}
          />
          {agents.some((a) => a.channel === "openclaw-weixin" || a.channel === "weixin") ? (
            <div className="mt-4">
              <WeixinBridgePanel />
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
