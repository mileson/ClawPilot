import Link from "next/link";

import { TrainingBoard } from "@/components/training/training-board";
import { PageHeader } from "@/components/layout/page-header";
import { getAgents, getTrainingModuleOverview, getTrainingRuns } from "@/lib/api";
import { buttonVariants } from "@/components/ui/button";
import {
  ControlPlaneAdvancedMode,
  ControlPlaneDelegationPanel,
  ControlPlaneStateLegend,
} from "@/components/control-plane/common-panels";

export const revalidate = 0;

export default async function TrainingPage() {
  const [runs, overview, agents] = await Promise.all([
    getTrainingRuns(),
    getTrainingModuleOverview().catch(() => null),
    getAgents().catch(() => []),
  ]);

  return (
    <section>
      <div className="mb-5 rounded-[28px] border border-[var(--line)] bg-white px-6 py-6 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-[#9b8f7d]">培训与入职</p>
            <PageHeader titleKey="pages.training.title" subtitleKey="pages.training.subtitle" className="mb-0 mt-2" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/add-agent" className={buttonVariants()}>
              给新 Agent 办理入职
            </Link>
            <Link href="/agents" className={buttonVariants({ variant: "outline" })}>
              查看 Agent 工区
            </Link>
          </div>
        </div>
        <div className="mt-4">
          <ControlPlaneStateLegend pageState={overview?.initialized ? "ready" : "notice"} buttonState="default" />
        </div>
      </div>

      {overview ? (
        <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {[
            ["已纳入培训", overview.counts.total],
            ["待训练", overview.counts.pending_training],
            ["训练中", overview.counts.training],
            ["最近已训练", overview.counts.recently_trained],
            ["未入组", overview.counts.not_enrolled],
          ].map(([label, value]) => (
            <div
              key={String(label)}
              className="rounded-[22px] border border-[var(--line)] bg-white px-4 py-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)]"
            >
              <p className="text-[11px] uppercase tracking-[0.16em] text-[var(--muted)]">{label}</p>
              <p className="mt-3 text-3xl font-semibold text-[var(--text)]">{String(value)}</p>
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <TrainingBoard initialRuns={runs} />
        </div>
        <div className="space-y-4">
          <ControlPlaneDelegationPanel
            selected="self"
            promptMap={{
              coach: "请作为教练 Agent，帮我判断当前哪些 Agent 该先训练、哪些要重新训练。",
              manager: "请作为总管 Agent，先判断新增 Agent 应该先走入职还是先走配置补齐。",
              config: "请作为配置 Agent，先检查当前训练模块还缺哪些文档与角色规则。",
            }}
          />
          <ControlPlaneAdvancedMode title="查看技术详情 / 高级模式">
            <div className="space-y-2 text-sm text-[var(--muted)]">
              <p>initialized：{String(overview?.initialized ?? false)}</p>
              <p>needs coach setup：{String(overview?.needs_coach_setup ?? false)}</p>
              <p>online node total：{overview?.online_node_total ?? 0}</p>
              <p>agent total：{agents.length}</p>
            </div>
          </ControlPlaneAdvancedMode>
        </div>
      </div>
    </section>
  );
}
