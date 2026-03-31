"use client";

import { useMemo, useState } from "react";

import { useI18n } from "@/components/i18n/use-locale";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  dispatchTask,
  getTasks,
  postTask,
  reviewTask,
  submitTask,
} from "@/lib/api";
import type { Task } from "@/lib/types";

interface CreateTaskForm {
  title: string;
  creator_type: "human" | "agent";
  creator_id: string;
  assignee_agent_id: string;
  priority: "low" | "medium" | "high" | "urgent";
  expected_output: string;
  acceptance_criteria: string;
  description: string;
}

const defaultForm: CreateTaskForm = {
  title: "",
  creator_type: "human",
  creator_id: "supervisor",
  assignee_agent_id: "",
  priority: "medium",
  expected_output: "",
  acceptance_criteria: "",
  description: "",
};

export function TasksBoard({ initialTasks }: { initialTasks: Task[] }) {
  const { t } = useI18n();
  const [tasks, setTasks] = useState<Task[]>(initialTasks);
  const [form, setForm] = useState<CreateTaskForm>(defaultForm);
  const [loading, setLoading] = useState(false);

  const pending = useMemo(() => tasks.filter((task) => ["todo", "doing", "review"].includes(task.status)), [tasks]);
  const statusLabel = useMemo(
    () => ({
      todo: t("tasks.status.todo"),
      doing: t("tasks.status.doing"),
      review: t("tasks.status.review"),
      done: t("tasks.status.done"),
      rejected: t("tasks.status.rejected"),
    }),
    [t],
  );

  async function reload() {
    const list = await getTasks();
    setTasks(list);
  }

  async function onCreate(evt: React.FormEvent<HTMLFormElement>) {
    evt.preventDefault();
    setLoading(true);
    try {
      await postTask({ ...form, description: form.description || null, deadline_at: null });
      setForm(defaultForm);
      await reload();
    } finally {
      setLoading(false);
    }
  }

  async function onTaskAction(task: Task, action: "dispatch-send" | "dispatch-spawn" | "submit" | "approve" | "reject") {
    if (action === "dispatch-send") await dispatchTask(task.task_id, "send");
    if (action === "dispatch-spawn") await dispatchTask(task.task_id, "spawn");
    if (action === "submit") {
      const summary = window.prompt(t("tasks.prompts.submitSummaryTitle"), t("tasks.prompts.submitSummaryDefault"));
      if (!summary) return;
      await submitTask(task.task_id, task.assignee_agent_id, summary);
    }
    if (action === "approve") {
      const score = Number(window.prompt(t("tasks.prompts.scoreTitle"), t("tasks.prompts.scoreDefault")) ?? "10");
      if (!Number.isFinite(score)) return;
      const message = window.prompt(t("tasks.prompts.receiptTitle"), t("tasks.prompts.receiptDefault"));
      if (!message) return;
      await reviewTask(task.task_id, {
        reviewer_id: "human-reviewer",
        decision: "approved",
        score_delta: Math.trunc(score),
        receipt: {
          recipient_type: task.creator_type === "human" ? "human" : "agent",
          recipient_id: task.creator_id,
          message,
          include_creator_agent_id: task.creator_type === "agent",
        },
      });
    }
    if (action === "reject") {
      const comment = window.prompt(t("tasks.prompts.rejectTitle"), t("tasks.prompts.rejectDefault"));
      if (!comment) return;
      await reviewTask(task.task_id, {
        reviewer_id: "human-reviewer",
        decision: "rejected",
        score_delta: 0,
        review_comment: comment,
      });
    }
    await reload();
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("tasks.create.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid grid-cols-1 gap-3 md:grid-cols-2" onSubmit={onCreate}>
            <Input label={t("tasks.create.fields.title")} value={form.title} onChange={(v) => setForm((s) => ({ ...s, title: v }))} required />
            <Input
              label={t("tasks.create.fields.assignee")}
              value={form.assignee_agent_id}
              onChange={(v) => setForm((s) => ({ ...s, assignee_agent_id: v }))}
              required
            />
            <Input
              label={t("tasks.create.fields.expectedOutput")}
              value={form.expected_output}
              onChange={(v) => setForm((s) => ({ ...s, expected_output: v }))}
              required
            />
            <Input
              label={t("tasks.create.fields.acceptanceCriteria")}
              value={form.acceptance_criteria}
              onChange={(v) => setForm((s) => ({ ...s, acceptance_criteria: v }))}
              required
            />
            <div className="md:col-span-2">
              <Input label={t("tasks.create.fields.description")} value={form.description} onChange={(v) => setForm((s) => ({ ...s, description: v }))} />
            </div>
            <div className="md:col-span-2">
              <Button type="submit" disabled={loading}>
                {loading ? t("common.submitting") : t("tasks.create.submit")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("tasks.list.title", { count: pending.length })}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--line)] text-left text-[var(--muted)]">
                  <th className="px-2 py-2">{t("tasks.list.headers.task")}</th>
                  <th className="px-2 py-2">{t("tasks.list.headers.assignee")}</th>
                  <th className="px-2 py-2">{t("tasks.list.headers.status")}</th>
                  <th className="px-2 py-2">{t("tasks.list.headers.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.task_id} className="border-b border-[var(--line)]/70 align-top">
                    <td className="px-2 py-2">
                      <p className="font-medium">{task.title}</p>
                      <p className="text-xs text-[var(--muted)]">{task.task_id}</p>
                    </td>
                    <td className="px-2 py-2">{task.assignee_agent_id}</td>
                    <td className="px-2 py-2">{statusLabel[task.status]}</td>
                    <td className="px-2 py-2">
                      <div className="flex flex-wrap gap-1">
                        {task.status === "todo" && (
                          <>
                            <Button size="sm" variant="outline" onClick={() => onTaskAction(task, "dispatch-send")}>
                              {t("tasks.actions.send")}
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => onTaskAction(task, "dispatch-spawn")}>
                              {t("tasks.actions.spawn")}
                            </Button>
                          </>
                        )}
                        {task.status === "doing" && (
                          <Button size="sm" variant="outline" onClick={() => onTaskAction(task, "submit")}>
                            {t("tasks.actions.submit")}
                          </Button>
                        )}
                        {task.status === "review" && (
                          <>
                            <Button size="sm" onClick={() => onTaskAction(task, "approve")}>
                              {t("tasks.actions.approve")}
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => onTaskAction(task, "reject")}>
                              {t("tasks.actions.reject")}
                            </Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  required,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  return (
    <label className="grid gap-1 text-xs text-[var(--muted)]">
      <span>{label}</span>
      <input
        className="h-9 rounded-lg border border-[var(--line)] bg-white px-3 text-sm text-[var(--text)]"
        value={value}
        required={required}
        onChange={(evt) => onChange(evt.target.value)}
      />
    </label>
  );
}
