"use client";

import Link from "next/link";
import { CheckCircleIcon, HourglassIcon, WarningCircleIcon } from "@phosphor-icons/react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
export {
  ControlPlaneAdvancedMode,
  ControlPlaneStateLegend,
  type ControlPlaneButtonState,
  type ControlPlanePageState,
} from "@/components/control-plane/common-panels-static";

const DELEGATION_OPTIONS = [
  {
    id: "self",
    title: "我自己处理",
    desc: "继续停留在当前页面，自己完成这一步。",
  },
  {
    id: "manager",
    title: "交给总管 Agent",
    desc: "更适合先做全局判断和下一步规划。",
  },
  {
    id: "coach",
    title: "交给教练 Agent",
    desc: "更适合入职、训练和能力门禁场景。",
  },
  {
    id: "config",
    title: "交给配置 Agent",
    desc: "更适合文档、规则、配置项和模板补齐。",
  },
  {
    id: "ops",
    title: "交给运维 Agent",
    desc: "更适合本地服务、节点、隧道和修复问题。",
  },
] as const;

export function ControlPlaneDelegationPanel({
  title = "自己处理 / 交给指定 Agent",
  selected,
  onSelect,
  promptMap,
}: {
  title?: string;
  selected: string;
  onSelect?: (value: string) => void;
  promptMap?: Partial<Record<(typeof DELEGATION_OPTIONS)[number]["id"], string>>;
}) {
  return (
    <article className="rounded-[28px] border border-[var(--line)] bg-white px-5 py-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
      <p className="text-xs uppercase tracking-[0.2em] text-[#9b8f7d]">{title}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {DELEGATION_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onSelect?.(option.id)}
            className={cn(
              "rounded-[22px] border px-4 py-4 text-left transition",
              selected === option.id
                ? "border-[#ead8b8] bg-[#fff8ee]"
                : "border-[var(--line)] bg-[var(--surface)] hover:bg-white",
            )}
          >
            <p className="text-sm font-semibold text-[var(--text)]">{option.title}</p>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{option.desc}</p>
            {option.id !== "self" && promptMap?.[option.id] ? (
              <div className="mt-3">
                <Link
                  href={`/rescue-center?prompt=${encodeURIComponent(promptMap[option.id] || "")}`}
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                >
                  直接交给它
                </Link>
              </div>
            ) : null}
          </button>
        ))}
      </div>
    </article>
  );
}

export function ControlPlaneActionFeedback({
  job,
  successHint,
}: {
  job:
    | {
        status: "accepted" | "running" | "completed" | "failed";
        accepted_at?: string | null;
        started_at?: string | null;
        first_progress_at?: string | null;
        completed_at?: string | null;
        error_message?: string | null;
      }
    | null
    | undefined;
  successHint?: string;
}) {
  if (!job) return null;
  const icon =
    job.status === "completed" ? <CheckCircleIcon size={16} /> : job.status === "failed" ? <WarningCircleIcon size={16} /> : <HourglassIcon size={16} />;
  const tone =
    job.status === "completed"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : job.status === "failed"
        ? "border-rose-200 bg-rose-50 text-rose-700"
        : "border-sky-200 bg-sky-50 text-sky-700";
  return (
    <div className={cn("rounded-[22px] border px-4 py-4 text-sm", tone)}>
      <div className="flex items-center gap-2 font-semibold">
        {icon}
        <span>当前状态：{job.status}</span>
      </div>
      <div className="mt-3 space-y-1 text-sm">
        {job.accepted_at ? <p>已受理：{job.accepted_at}</p> : null}
        {job.started_at ? <p>开始执行：{job.started_at}</p> : null}
        {job.first_progress_at ? <p>首个进度：{job.first_progress_at}</p> : null}
        {job.completed_at ? <p>完成时间：{job.completed_at}</p> : null}
        {job.error_message ? <p>错误：{job.error_message}</p> : null}
        {job.status === "completed" && successHint ? <p>{successHint}</p> : null}
      </div>
    </div>
  );
}
