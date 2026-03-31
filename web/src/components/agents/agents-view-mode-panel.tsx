"use client";

import { useSyncExternalStore } from "react";

import { AgentWorkspaceCard, type AgentCardViewMode } from "@/components/agents/agent-workspace-card";
import { useI18n } from "@/components/i18n/use-locale";
import { Button } from "@/components/ui/button";
import type { Agent, SystemSettings } from "@/lib/types";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "openclaw-agents-view-mode";
const STORAGE_EVENT = "openclaw-agents-view-mode-change";

interface AgentCardSummary {
  trainingCount?: number;
  scheduledJobCount?: number;
  openTaskCount?: number;
  latestTrainingAt?: string | null;
}

interface AgentsViewModePanelProps {
  items: Array<{
    agent: Agent;
    summary: AgentCardSummary | null;
  }>;
  stats: Array<{
    label: string;
    value: string | number;
  }>;
  systemSettings?: SystemSettings | null;
}

function getStoredAgentsViewMode(): AgentCardViewMode {
  if (typeof window === "undefined") return "patrol";
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw === "manage" ? "manage" : "patrol";
  } catch {
    return "patrol";
  }
}

function subscribeStoredAgentsViewMode(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => {};
  const handleStorage = (event: StorageEvent) => {
    if (!event.key || event.key === STORAGE_KEY) {
      onStoreChange();
    }
  };
  window.addEventListener(STORAGE_EVENT, onStoreChange);
  window.addEventListener("storage", handleStorage);
  return () => {
    window.removeEventListener(STORAGE_EVENT, onStoreChange);
    window.removeEventListener("storage", handleStorage);
  };
}

export function AgentsViewModePanel({ items, stats, systemSettings }: AgentsViewModePanelProps) {
  const { t } = useI18n();
  const viewMode = useSyncExternalStore<AgentCardViewMode>(
    subscribeStoredAgentsViewMode,
    getStoredAgentsViewMode,
    () => "patrol",
  );

  function handleChange(nextMode: AgentCardViewMode) {
    try {
      window.localStorage.setItem(STORAGE_KEY, nextMode);
      window.dispatchEvent(new Event(STORAGE_EVENT));
    } catch {
      // Ignore storage write failures and keep the current snapshot.
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-1 flex-wrap gap-2">
          {stats.map((item) => (
            <div
              key={item.label}
              className="flex h-[74px] w-[92px] shrink-0 flex-col items-center justify-center rounded-[18px] border border-[var(--line)] bg-white px-2 py-2 text-center shadow-[0_8px_20px_rgba(15,23,42,0.04)]"
            >
              <p className="text-[28px] font-semibold leading-none text-[var(--text)]">{String(item.value)}</p>
              <p className="mt-1.5 text-[9px] uppercase tracking-[0.12em] text-[var(--muted)]">{item.label}</p>
            </div>
          ))}
        </div>

        <div className="flex justify-end">
          <div className="inline-flex rounded-full border border-[var(--line)] bg-white p-1 shadow-[0_10px_24px_rgba(15,23,42,0.04)]">
            <Button
              type="button"
              variant={viewMode === "patrol" ? "default" : "ghost"}
              size="sm"
              className={cn("rounded-full", viewMode === "patrol" ? "" : "text-[var(--muted)]")}
              onClick={() => handleChange("patrol")}
            >
              {t("pages.agents.viewMode.patrol")}
            </Button>
            <Button
              type="button"
              variant={viewMode === "manage" ? "default" : "ghost"}
              size="sm"
              className={cn("rounded-full", viewMode === "manage" ? "" : "text-[var(--muted)]")}
              onClick={() => handleChange("manage")}
            >
              {t("pages.agents.viewMode.manage")}
            </Button>
          </div>
        </div>
      </div>

      <div
        className={cn(
          "grid grid-cols-1 gap-3 sm:grid-cols-2",
          viewMode === "patrol" ? "lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6" : "lg:grid-cols-4",
        )}
      >
        {items.map(({ agent, summary }) => (
          <AgentWorkspaceCard
            key={agent.agent_id}
            agent={agent}
            systemSettings={systemSettings}
            summary={summary}
            viewMode={viewMode}
          />
        ))}
      </div>
    </div>
  );
}
