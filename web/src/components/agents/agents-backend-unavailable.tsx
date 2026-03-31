"use client";

import { useI18n } from "@/components/i18n/use-locale";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface AgentsBackendUnavailableProps {
  apiBase: string;
  errorMessage: string;
}

export function AgentsBackendUnavailable({
  apiBase,
  errorMessage,
}: AgentsBackendUnavailableProps) {
  const { t } = useI18n();
  const startupCommand = [
    "cd /Users/mileson/Workspace/Engineer/Web应用/clawpilot",
    "source .venv/bin/activate",
    "OPENCLAW_HOST_ROOT=\"$HOME/.openclaw\" OPENCLAW_CONFIG_PATH=\"$HOME/.openclaw/openclaw.json\" OPENCLAW_LOCAL_BASE_URL=\"http://127.0.0.1:8088\" uvicorn app.main:app --host 127.0.0.1 --port 8088",
  ].join("\n");

  return (
    <Card className="rounded-[28px] border-amber-200 bg-[linear-gradient(180deg,rgba(255,251,235,0.96),rgba(255,255,255,0.98))] shadow-[0_18px_50px_rgba(180,83,9,0.08)]">
      <CardHeader className="gap-3 border-b border-amber-100 pb-5">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-amber-500 text-sm font-semibold text-white">
            !
          </span>
          <div className="space-y-1">
            <CardTitle className="text-[22px] text-[var(--text)]">
              {t("pages.agents.unreachable.title")}
            </CardTitle>
            <CardDescription className="text-sm leading-7">
              {t("pages.agents.unreachable.description")}
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5 pt-5">
        <div className="rounded-[20px] border border-amber-100 bg-white/90 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">
            {t("pages.agents.unreachable.apiLabel")}
          </p>
          <p className="mt-2 break-all text-sm font-medium text-[var(--text)]">{apiBase}</p>
          <p className="mt-2 text-sm leading-7 text-[var(--muted)]">
            {t("pages.agents.unreachable.apiHint")}
          </p>
        </div>

        <div className="rounded-[20px] border border-amber-100 bg-white/90 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-[var(--muted)]">
            {t("pages.agents.unreachable.errorLabel")}
          </p>
          <p className="mt-2 break-words text-sm text-[var(--text)]">{errorMessage}</p>
        </div>

        <div className="rounded-[20px] border border-[var(--line)] bg-[#101927] p-4 text-white">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-300">
            {t("pages.agents.unreachable.commandLabel")}
          </p>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words text-xs leading-6 text-slate-100">
            {startupCommand}
          </pre>
          <p className="mt-3 text-xs leading-6 text-slate-300">
            {t("pages.agents.unreachable.commandHint")}
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Button type="button" className="rounded-full" onClick={() => window.location.reload()}>
            {t("pages.agents.unreachable.reload")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
