"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { CheckCircleIcon } from "@phosphor-icons/react";

import { setStoredStartHubCompleted } from "@/lib/start-hub-completion";
import { Button } from "@/components/ui/button";

export function StartHubCompletionButton({
  disabled,
  remainingCount,
}: {
  disabled: boolean;
  remainingCount: number;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  function handleComplete() {
    if (disabled || isPending) return;
    setStoredStartHubCompleted(true);
    startTransition(() => {
      router.push("/agents");
      router.refresh();
    });
  }

  const description = disabled
    ? `还有 ${remainingCount} 个步骤未完成，全部完成后才能结束开始使用流程。`
    : "完成后会隐藏“开始使用”入口，后续默认进入 Agent 工区。";

  return (
    <div className="rounded-[24px] border border-[var(--line)] bg-[var(--surface)] px-5 py-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-[var(--text)]">最后一步</p>
          <p className="text-sm leading-6 text-[var(--muted)]">{description}</p>
        </div>
        <Button
          type="button"
          size="lg"
          onClick={handleComplete}
          disabled={disabled || isPending}
          className="min-w-[140px]"
        >
          <CheckCircleIcon size={18} weight="fill" />
          {isPending ? "正在完成…" : "完成配置"}
        </Button>
      </div>
    </div>
  );
}
