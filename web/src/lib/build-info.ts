import "server-only";

import type { AppBuildInfo } from "@/lib/types";

function formatBuildTimeLabel(value: string) {
  if (!value || value === "unknown") return "unknown";

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;

  const formatter = new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  });

  return formatter.format(parsed).replace("/", "-").replace(",", "");
}

export function getBuildInfo(): AppBuildInfo {
  const gitSha = process.env.APP_GIT_SHA?.trim() || "dev-local";
  const builtAt = process.env.APP_BUILD_TIME?.trim() || "unknown";

  return {
    gitSha,
    shortSha: gitSha.slice(0, 8),
    builtAt,
    builtAtLabel: formatBuildTimeLabel(builtAt),
  };
}
