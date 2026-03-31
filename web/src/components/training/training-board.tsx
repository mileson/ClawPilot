"use client";

import { useMemo, useState } from "react";

import { useI18n } from "@/components/i18n/use-locale";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createTrainingRun,
  gateTrainingRun,
  getTrainingRuns,
  onboardingConfirm,
} from "@/lib/api";
import type { TrainingRun } from "@/lib/types";

export function TrainingBoard({ initialRuns }: { initialRuns: TrainingRun[] }) {
  const { t } = useI18n();
  const [runs, setRuns] = useState(initialRuns);
  const [agentId, setAgentId] = useState("");
  const phaseLabel = useMemo(
    () => ({
      exam: t("training.phase.exam"),
      observe: t("training.phase.observe"),
      gate: t("training.phase.gate"),
    }),
    [t],
  );
  const resultLabel = useMemo(
    () => ({
      GRADUATE: t("training.result.graduate"),
      REMEDIATE: t("training.result.remediate"),
    }),
    [t],
  );

  async function reload() {
    setRuns(await getTrainingRuns());
  }

  async function onConfirm() {
    if (!agentId) return;
    await onboardingConfirm({
      agent_id: agentId,
      agent_name: t("training.onboarding.agentName", { agentId }),
      role_summary: t("training.onboarding.roleSummary"),
      creator_type: "human",
      creator_id: "supervisor",
      trigger_training: true,
      observe_days: 14,
    });
    setAgentId("");
    await reload();
  }

  async function onCreateRun() {
    if (!agentId) return;
    await createTrainingRun({ agent_id: agentId, phase: "exam", status: "planned" });
    setAgentId("");
    await reload();
  }

  async function onGate(run: TrainingRun, result: "GRADUATE" | "REMEDIATE") {
    const score = Number(
      window.prompt(
        t("training.prompts.scoreTitle"),
        result === "GRADUATE" ? t("training.prompts.scorePassDefault") : t("training.prompts.scoreFailDefault"),
      ) ?? "80",
    );
    if (!Number.isFinite(score)) return;
    await gateTrainingRun(run.run_id, {
      result,
      score: Math.trunc(score),
      report_url: null,
    });
    await reload();
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("training.onboarding.title")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-xs text-[var(--muted)]">
            {t("training.onboarding.agentId")}
            <input
              className="h-9 w-64 rounded-lg border border-[var(--line)] bg-white px-3 text-sm text-[var(--text)]"
              value={agentId}
              onChange={(evt) => setAgentId(evt.target.value)}
              placeholder={t("training.onboarding.agentPlaceholder")}
            />
          </label>
          <Button onClick={onConfirm}>
            {t("training.onboarding.confirm")}
          </Button>
          <Button variant="outline" onClick={onCreateRun}>
            {t("training.onboarding.manual")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("training.runs.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--line)] text-left text-[var(--muted)]">
                  <th className="px-2 py-2">{t("training.runs.headers.runId")}</th>
                  <th className="px-2 py-2">{t("training.runs.headers.agent")}</th>
                  <th className="px-2 py-2">{t("training.runs.headers.phase")}</th>
                  <th className="px-2 py-2">{t("training.runs.headers.status")}</th>
                  <th className="px-2 py-2">{t("training.runs.headers.result")}</th>
                  <th className="px-2 py-2">{t("training.runs.headers.gate")}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.run_id} className="border-b border-[var(--line)]/70">
                    <td className="px-2 py-2">{run.run_id}</td>
                    <td className="px-2 py-2">{run.agent_id}</td>
                    <td className="px-2 py-2">{phaseLabel[run.phase]}</td>
                    <td className="px-2 py-2">{run.status}</td>
                    <td className="px-2 py-2">{run.result ? resultLabel[run.result] : t("common.none")}</td>
                    <td className="px-2 py-2">
                      {run.phase !== "gate" ? (
                        <div className="flex gap-1">
                          <Button size="sm" onClick={() => onGate(run, "GRADUATE")}>{t("training.actions.approve")}</Button>
                          <Button size="sm" variant="outline" onClick={() => onGate(run, "REMEDIATE")}>{t("training.actions.reject")}</Button>
                        </div>
                      ) : (
                        t("common.none")
                      )}
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
