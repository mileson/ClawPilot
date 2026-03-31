import Link from "next/link";

import { TasksBoard } from "@/components/tasks/tasks-board";
import { PageHeader } from "@/components/layout/page-header";
import { getAgents, getTasks } from "@/lib/api";
import { buttonVariants } from "@/components/ui/button";
import {
  ControlPlaneAdvancedMode,
  ControlPlaneDelegationPanel,
  ControlPlaneStateLegend,
} from "@/components/control-plane/common-panels";

export const revalidate = 0;

export default async function TasksPage() {
  const [tasks, agents] = await Promise.all([getTasks(), getAgents().catch(() => [])]);
  const todoCount = tasks.filter((task) => task.status === "todo").length;
  const doingCount = tasks.filter((task) => task.status === "doing").length;
  const reviewCount = tasks.filter((task) => task.status === "review").length;

  return (
    <section>
      <div className="mb-5 rounded-[28px] border border-[var(--line)] bg-white px-6 py-6 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-[#9b8f7d]">协作与批量优化</p>
            <PageHeader titleKey="pages.tasks.title" subtitleKey="pages.tasks.subtitle" className="mb-0 mt-2" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/agents" className={buttonVariants()}>
              选择目标 Agent
            </Link>
            <Link href="/training" className={buttonVariants({ variant: "outline" })}>
              走培训与入职路径
            </Link>
          </div>
        </div>
        <div className="mt-4">
          <ControlPlaneStateLegend pageState={tasks.length ? "ready" : "empty"} buttonState="default" />
        </div>
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        {[
          ["待派发", todoCount],
          ["执行中", doingCount],
          ["待评审", reviewCount],
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

      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <TasksBoard initialTasks={tasks} />
        </div>
        <div className="space-y-4">
          <article className="rounded-[28px] border border-[var(--line)] bg-white px-5 py-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
            <p className="text-xs uppercase tracking-[0.2em] text-[#9b8f7d]">优化内容选择</p>
            <div className="mt-4 grid gap-2 text-sm text-[var(--muted)]">
              {["角色设定", "记忆规则", "技能配置", "任务规则", "培训策略"].map((item) => (
                <label key={item} className="flex items-center gap-2">
                  <input type="checkbox" defaultChecked={item !== "培训策略"} />
                  <span>{item}</span>
                </label>
              ))}
            </div>
            <div className="mt-5 rounded-[22px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
              <p className="text-sm font-semibold text-[var(--text)]">目标范围</p>
              <div className="mt-3 flex flex-wrap gap-2 text-sm">
                <span className="rounded-full border border-[var(--line)] bg-white px-3 py-1">单个 Agent</span>
                <span className="rounded-full border border-[var(--line)] bg-white px-3 py-1">多个 Agent</span>
                <span className="rounded-full border border-[var(--line)] bg-white px-3 py-1">全部 Agent</span>
              </div>
            </div>
            <div className="mt-5 rounded-[22px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4 text-sm text-[var(--muted)]">
              <p className="font-semibold text-[var(--text)]">影响范围预览</p>
              <p className="mt-2">本次会影响 `SOUL.md`、`IDENTITY.md`、`MEMORY.md`、技能规则和任务规则等内容。</p>
            </div>
          </article>

          <ControlPlaneDelegationPanel
            selected="self"
            promptMap={{
              manager: "请作为总管 Agent，帮我决定这次应该优化哪个 Agent、影响范围多大。",
              coach: "请作为教练 Agent，帮我判断哪些优化应该并入训练路径。",
              config: "请作为配置 Agent，根据选中的优化内容给出影响范围预览。",
            }}
          />

          <ControlPlaneAdvancedMode title="查看技术详情 / 高级模式">
            <div className="space-y-2 text-sm text-[var(--muted)]">
              <p>当前 Agent 总数：{agents.length}</p>
              <p>任务总数：{tasks.length}</p>
              <p>待派发：{todoCount}</p>
              <p>执行中：{doingCount}</p>
              <p>待评审：{reviewCount}</p>
            </div>
          </ControlPlaneAdvancedMode>
        </div>
      </div>
    </section>
  );
}
