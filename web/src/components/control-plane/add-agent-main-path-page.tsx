"use client";

import { useMemo, useState } from "react";
import { CopyIcon, FilesIcon, RocketLaunchIcon, SparkleIcon } from "@phosphor-icons/react";

import type { Agent } from "@/lib/types";
import { AgentConfigMultiAgentSettings } from "@/components/agents/agent-config-multi-agent";

type CreateMode = "blank" | "copy" | "template";
type ExecuteMode = "self" | "coach" | "config" | "evolution";

const EXECUTE_MODE_OPTIONS: Array<{ id: ExecuteMode; title: string; desc: string }> = [
  { id: "self", title: "我自己继续处理", desc: "自己填写基础信息并直接发起创建。" },
  { id: "coach", title: "交给教练 Agent", desc: "更适合希望把后续训练与入职流程一起交接出去。" },
  { id: "config", title: "交给配置 Agent", desc: "更适合先补文档、补人格文件和默认规则。" },
  { id: "evolution", title: "交给进化 Agent", desc: "更适合把新 Agent 直接纳入后续批量优化队列。" },
];

export function AddAgentMainPathPage({ agents }: { agents: Agent[] }) {
  const [mode, setMode] = useState<CreateMode>("blank");
  const [sourceAgentId, setSourceAgentId] = useState<string>(agents[0]?.agent_id || "");
  const [executeMode, setExecuteMode] = useState<ExecuteMode>("self");
  const [agentName, setAgentName] = useState("");
  const [roleSummary, setRoleSummary] = useState("");
  const [primaryChannel, setPrimaryChannel] = useState("feishu");
  const [defaultModel, setDefaultModel] = useState("zai/glm-5");
  const [inheritSkills, setInheritSkills] = useState(mode === "copy");
  const [inheritSchedules, setInheritSchedules] = useState(mode === "copy");
  const [inheritDocs, setInheritDocs] = useState(true);
  const [inheritTrainingPlan, setInheritTrainingPlan] = useState(false);
  const [inheritAvatar, setInheritAvatar] = useState(mode === "copy");

  const sourceAgent = useMemo(
    () => agents.find((agent) => agent.agent_id === sourceAgentId) || null,
    [agents, sourceAgentId],
  );

  const inheritedSummary = sourceAgent
    ? [
        `技能 ${sourceAgent.skills?.length || 0} 个`,
        `核心工作 ${sourceAgent.core_work?.length || 0} 项`,
        `模型 ${sourceAgent.config_model_label || sourceAgent.model_label || "未配置"}`,
        `当前运行态 ${sourceAgent.runtime_status || "未知"}`,
      ]
    : [];

  const inheritancePreview = [
    inheritSkills ? "技能配置" : null,
    inheritSchedules ? "定时任务" : null,
    inheritDocs ? "默认文档" : null,
    inheritTrainingPlan ? "培训计划" : null,
    inheritAvatar ? "动态形象 / 头像" : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <section className="space-y-6">
      <header className="rounded-[28px] border border-[var(--line)] bg-white px-6 py-6 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
        <p className="text-xs uppercase tracking-[0.24em] text-[#9b8f7d]">新增 Agent</p>
        <h1 className="mt-3 font-[var(--font-serif)] text-4xl font-semibold text-[var(--text)]">先决定怎么创建，再决定谁来执行</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-[var(--muted)]">
          这条主路径把原先分散在弹窗里的创建动作拉直了。你可以先选空白创建、复制已有 Agent，或者从模板出发，再决定由谁继续执行。
        </p>
      </header>

      <section className="grid gap-4 lg:grid-cols-3">
        <button
          type="button"
          onClick={() => setMode("blank")}
          className={`rounded-[24px] border px-5 py-5 text-left transition ${mode === "blank" ? "border-[#ead8b8] bg-[#fff8ee]" : "border-[var(--line)] bg-white hover:bg-[var(--surface)]"}`}
        >
          <RocketLaunchIcon size={20} className="text-[#8c6834]" />
          <h2 className="mt-4 text-xl font-semibold text-[var(--text)]">空白创建</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">从最小必填信息开始，适合全新岗位或全新职责。</p>
        </button>
        <button
          type="button"
          onClick={() => setMode("copy")}
          className={`rounded-[24px] border px-5 py-5 text-left transition ${mode === "copy" ? "border-[#ead8b8] bg-[#fff8ee]" : "border-[var(--line)] bg-white hover:bg-[var(--surface)]"}`}
        >
          <CopyIcon size={20} className="text-[#8c6834]" />
          <h2 className="mt-4 text-xl font-semibold text-[var(--text)]">复制已有 Agent</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">直接复用已有 Agent 的技能、文档风格和部分规则，再按需微调。</p>
        </button>
        <button
          type="button"
          onClick={() => setMode("template")}
          className={`rounded-[24px] border px-5 py-5 text-left transition ${mode === "template" ? "border-[#ead8b8] bg-[#fff8ee]" : "border-[var(--line)] bg-white hover:bg-[var(--surface)]"}`}
        >
          <SparkleIcon size={20} className="text-[#8c6834]" />
          <h2 className="mt-4 text-xl font-semibold text-[var(--text)]">使用模板</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">优先复用官方默认模板和标准初始化结构，再按业务补内容。</p>
        </button>
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <article className="rounded-[28px] border border-[var(--line)] bg-white px-5 py-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
          <p className="text-xs uppercase tracking-[0.2em] text-[#9b8f7d]">基础信息</p>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            <label className="grid gap-2 text-sm text-[var(--muted)]">
              名称
              <input
                value={agentName}
                onChange={(event) => setAgentName(event.target.value)}
                placeholder="例如：客户成功 Agent"
                className="h-11 rounded-2xl border border-[var(--line)] bg-white px-3 text-[var(--text)]"
              />
            </label>
            <label className="grid gap-2 text-sm text-[var(--muted)]">
              主要渠道
              <select
                value={primaryChannel}
                onChange={(event) => setPrimaryChannel(event.target.value)}
                className="h-11 rounded-2xl border border-[var(--line)] bg-white px-3 text-[var(--text)]"
              >
                <option value="feishu">Feishu</option>
                <option value="weixin">WeChat</option>
                <option value="telegram">Telegram</option>
              </select>
            </label>
            <label className="grid gap-2 text-sm text-[var(--muted)] md:col-span-2">
              岗位职责
              <textarea
                value={roleSummary}
                onChange={(event) => setRoleSummary(event.target.value)}
                placeholder="一句话描述这个 Agent 的核心职责"
                className="min-h-[96px] rounded-2xl border border-[var(--line)] bg-white px-3 py-3 text-[var(--text)]"
              />
            </label>
            <label className="grid gap-2 text-sm text-[var(--muted)]">
              默认模型
              <input
                value={defaultModel}
                onChange={(event) => setDefaultModel(event.target.value)}
                className="h-11 rounded-2xl border border-[var(--line)] bg-white px-3 text-[var(--text)]"
              />
            </label>
          </div>

          <p className="text-xs uppercase tracking-[0.2em] text-[#9b8f7d]">继承内容预览</p>
          <h2 className="mt-2 text-2xl font-semibold text-[var(--text)]">
            {mode === "blank" ? "当前选择：空白创建" : mode === "copy" ? "当前选择：复制已有 Agent" : "当前选择：模板创建"}
          </h2>
          {mode === "copy" ? (
            <>
              <label className="mt-5 grid gap-2 text-sm text-[var(--muted)]">
                选择源 Agent
                <select
                  value={sourceAgentId}
                  onChange={(event) => setSourceAgentId(event.target.value)}
                  className="h-11 rounded-2xl border border-[var(--line)] bg-white px-3 text-[var(--text)]"
                >
                  {agents.map((agent) => (
                    <option key={agent.agent_id} value={agent.agent_id}>
                      {agent.display_name} ({agent.agent_id})
                    </option>
                  ))}
                </select>
              </label>
              <div className="mt-4 rounded-[22px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
                <p className="text-sm font-semibold text-[var(--text)]">{sourceAgent?.display_name || "未选择源 Agent"}</p>
                <div className="mt-3 space-y-2 text-sm text-[var(--muted)]">
                  {inheritedSummary.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              </div>
            </>
          ) : mode === "template" ? (
            <div className="mt-5 rounded-[22px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4 text-sm leading-7 text-[var(--muted)]">
              <p>模板创建会优先复用官方初始化文件、默认工作区结构和标准人格文档，不直接继承现有 Agent 的私有内容。</p>
              <p className="mt-2">适合需要一套干净、可控、便于后续交接的新 Agent。</p>
            </div>
          ) : (
            <div className="mt-5 rounded-[22px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4 text-sm leading-7 text-[var(--muted)]">
              <p>空白创建只要求你先填最少必要信息。更细的文档、人设、技能和训练安排会放到后续步骤或高级模式。</p>
            </div>
          )}

          <div className="mt-5 rounded-[22px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
            <p className="text-sm font-semibold text-[var(--text)]">继承内容选择</p>
            <div className="mt-3 grid gap-2 text-sm text-[var(--muted)] md:grid-cols-2">
              {[
                ["技能", inheritSkills, setInheritSkills],
                ["定时任务", inheritSchedules, setInheritSchedules],
                ["默认文档", inheritDocs, setInheritDocs],
                ["培训计划", inheritTrainingPlan, setInheritTrainingPlan],
                ["动态形象", inheritAvatar, setInheritAvatar],
              ].map(([label, checked, setter]) => (
                <label key={String(label)} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={Boolean(checked)}
                    onChange={(event) => (setter as (value: boolean) => void)(event.target.checked)}
                  />
                  <span>{String(label)}</span>
                </label>
              ))}
            </div>
            <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
              当前将继承：{inheritancePreview.length ? inheritancePreview.join("、") : "不继承现有资产"}
            </p>
          </div>

          <div className="mt-5 rounded-[22px] border border-[var(--line)] bg-white px-4 py-4">
            <p className="text-sm font-semibold text-[var(--text)]">创建结果会展示什么</p>
            <div className="mt-3 space-y-2 text-sm text-[var(--muted)]">
              <p>1. 是否创建成功</p>
              <p>2. 是否已经交接给指定执行者</p>
              <p>3. 下一步建议该去工区、培训、还是继续补配置</p>
            </div>
          </div>
        </article>

        <article className="rounded-[28px] border border-[var(--line)] bg-white px-5 py-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
          <p className="text-xs uppercase tracking-[0.2em] text-[#9b8f7d]">执行方式</p>
          <h2 className="mt-2 text-2xl font-semibold text-[var(--text)]">决定谁来继续处理这个创建流程</h2>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {EXECUTE_MODE_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setExecuteMode(option.id)}
                className={`rounded-[22px] border px-4 py-4 text-left transition ${executeMode === option.id ? "border-[#ead8b8] bg-[#fff8ee]" : "border-[var(--line)] bg-[var(--surface)] hover:bg-white"}`}
              >
                <p className="text-sm font-semibold text-[var(--text)]">{option.title}</p>
                <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{option.desc}</p>
              </button>
            ))}
          </div>
          <div className="mt-6 rounded-[22px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
            <p className="text-sm font-semibold text-[var(--text)]">当前执行方式：{EXECUTE_MODE_OPTIONS.find((item) => item.id === executeMode)?.title}</p>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              实际创建仍复用现有多 Agent onboarding 能力；这一层先把创建方式、继承预览和执行责任人统一到同一条主路径里。
            </p>
          </div>
        </article>
      </section>

      <section className="rounded-[28px] border border-[var(--line)] bg-white px-5 py-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
        <div className="flex items-center gap-3">
          <FilesIcon size={18} className="text-[#8c6834]" />
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-[#9b8f7d]">实际创建容器</p>
            <h2 className="mt-1 text-2xl font-semibold text-[var(--text)]">开始填写基础信息并发起创建</h2>
          </div>
        </div>
        <details className="mt-5 rounded-[22px] border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
          <summary className="cursor-pointer list-none text-sm font-semibold text-[var(--text)]">高级配置</summary>
          <div className="mt-4 grid gap-3 md:grid-cols-2 text-sm text-[var(--muted)]">
            <div className="rounded-[18px] border border-[var(--line)] bg-white px-3 py-3">
              <p className="font-semibold text-[var(--text)]">高阶初始化控制</p>
              <p className="mt-2 leading-6">后续可继续控制人格文档生成、群组加入、doctor / probe 与 gateway restart 策略。</p>
            </div>
            <div className="rounded-[18px] border border-[var(--line)] bg-white px-3 py-3">
              <p className="font-semibold text-[var(--text)]">继承边界</p>
              <p className="mt-2 leading-6">这里先把“继承什么”拉到主路径里。更细的字段仍交给下方 onboarding 容器执行。</p>
            </div>
          </div>
        </details>
        <div className="mt-5">
          <AgentConfigMultiAgentSettings agents={agents} />
        </div>
      </section>
    </section>
  );
}
