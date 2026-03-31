"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/components/i18n/use-locale";
import type { LeaderboardEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

type RankedAgent = LeaderboardEntry & {
  avatar_src: string;
};

interface LeaderboardPageProps {
  rows: LeaderboardEntry[];
}

function createFallbackAvatar(name: string, seed: string) {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) hash = (hash * 33 + seed.charCodeAt(index)) >>> 0;
  const hue = hash % 360;
  const initial = (name.trim()[0] || "A").toUpperCase();
  const svg = `
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
    <rect width="96" height="96" rx="28" fill="hsl(${hue} 58% 90%)" />
    <text x="50%" y="50%" dominant-baseline="central" text-anchor="middle"
      font-size="40" font-family="ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif"
      fill="hsl(${hue} 36% 28%)">${initial}</text>
  </svg>
  `.trim();
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function resolveAvatarSrc(row: LeaderboardEntry): string {
  if (row.avatar_url && /^(https?:)?\/\//.test(row.avatar_url)) return row.avatar_url;
  if (row.avatar_hint && /^(https?:)?\/\//.test(row.avatar_hint)) return row.avatar_hint;
  if (row.avatar_url && row.avatar_url.startsWith("data:image/")) return row.avatar_url;
  if (row.avatar_hint && row.avatar_hint.startsWith("data:image/")) return row.avatar_hint;
  return createFallbackAvatar(row.display_name, row.agent_id);
}

function decorateRows(rows: LeaderboardEntry[]): RankedAgent[] {
  return rows.map((row) => ({
    ...row,
    avatar_src: resolveAvatarSrc(row),
  }));
}

function SummaryMetric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-white/90 px-4 py-3 shadow-sm">
      <div className="text-sm font-medium text-[var(--muted)]">{label}</div>
      <div className="mt-2 flex items-end justify-between gap-3">
        <div className="text-2xl font-semibold text-[var(--text)]">{value}</div>
        <div className="text-[11px] tracking-[0.18em] text-[var(--muted)] uppercase">{hint}</div>
      </div>
    </div>
  );
}

function AvatarBadge({
  row,
  sizeClass,
  iconClass,
  shellClass,
  feishuLabel,
}: {
  row: RankedAgent;
  sizeClass: string;
  iconClass: string;
  shellClass: string;
  feishuLabel: string;
}) {
  return (
    <div className={cn("relative shrink-0 rounded-[26px] p-1.5 shadow-[0_16px_30px_rgba(15,23,42,0.08)]", shellClass, sizeClass)}>
      <img
        src={row.avatar_src}
        alt={row.display_name}
        className="h-full w-full rounded-[22px] border border-white/80 object-cover"
      />
      {row.channel === "feishu" ? (
        <span className="absolute -bottom-1 -right-1 flex h-8 w-8 items-center justify-center rounded-full border border-white bg-white shadow-sm">
          <img src="/platforms/feishu.png" alt={feishuLabel} className={cn("object-contain", iconClass)} />
        </span>
      ) : null}
    </div>
  );
}

function PodiumCard({
  row,
  label,
  shell,
  glow,
  accent,
  badge,
  score,
  lift,
  avatar,
  avatarIcon,
  fallbackRole,
  feishuLabel,
}: {
  row: RankedAgent;
  label: string;
  shell: string;
  glow: string;
  accent: string;
  badge: string;
  score: string;
  lift: string;
  avatar: string;
  avatarIcon: string;
  fallbackRole: string;
  feishuLabel: string;
}) {
  return (
    <article
      className={cn(
        "group relative overflow-hidden rounded-[24px] border bg-white/92 p-3 shadow-[0_14px_30px_rgba(15,23,42,0.05)] transition duration-300 hover:-translate-y-0.5 hover:shadow-[0_20px_40px_rgba(15,23,42,0.08)]",
        shell,
        lift,
      )}
    >
      <div className={cn("pointer-events-none absolute inset-0 bg-gradient-to-br opacity-80", glow)} />
      <div className={cn("absolute left-0 top-0 h-full w-1", accent)} />

      <div className="relative flex h-full flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <Badge className={cn("rounded-full px-2.5 py-0.5 text-[10px] tracking-[0.2em]", badge)} variant="neutral">
            TOP {row.rank}
          </Badge>
          <div className="text-right leading-none">
            <div className="text-[10px] tracking-[0.24em] text-[var(--muted)] uppercase">{label}</div>
            <div className={cn("mt-1 text-2xl font-semibold", score)}>{row.points}</div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <AvatarBadge row={row} sizeClass="h-14 w-14" iconClass={avatarIcon} shellClass={cn("bg-gradient-to-br", avatar)} feishuLabel={feishuLabel} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-xl font-semibold leading-none text-[var(--text)]">{row.display_name}</div>
            <div className="mt-1 line-clamp-1 text-sm text-[var(--muted)]">{row.role || row.role_summary || fallbackRole}</div>
          </div>
        </div>
      </div>
    </article>
  );
}

function TopThreeRail({
  topThreePoints,
  topName,
  title,
  subtitle,
  totalLabel,
  leaderLabel,
  emptyLabel,
}: {
  topThreePoints: number;
  topName: string | null;
  title: string;
  subtitle: string;
  totalLabel: string;
  leaderLabel: string;
  emptyLabel: string;
}) {
  return (
    <div className="flex h-full flex-col justify-between rounded-[24px] border border-[var(--line)]/80 bg-white/80 px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] backdrop-blur">
      <div>
        <div className="text-[10px] tracking-[0.26em] text-[var(--muted)] uppercase">{title}</div>
        <div className="mt-2 font-[var(--font-serif)] text-xl font-semibold text-[var(--text)]">{subtitle}</div>
      </div>

      <div className="mt-4 space-y-2.5">
        <div className="rounded-2xl border border-[var(--line)]/80 bg-[var(--surface)]/70 px-3 py-2.5">
          <div className="text-[10px] tracking-[0.18em] text-[var(--muted)] uppercase">{totalLabel}</div>
          <div className="mt-1 text-2xl font-semibold text-[var(--text)]">{topThreePoints}</div>
        </div>
        <div className="rounded-2xl border border-dashed border-[var(--line)]/80 px-3 py-2.5 text-xs text-[var(--muted)]">
          {leaderLabel}
          <span className="mt-1 block truncate text-sm font-medium text-[var(--text)]">{topName || emptyLabel}</span>
        </div>
      </div>
    </div>
  );
}

function RankingRow({
  row,
  fallbackRole,
  feishuLabel,
  pointsLabel,
}: {
  row: RankedAgent;
  fallbackRole: string;
  feishuLabel: string;
  pointsLabel: string;
}) {
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-[var(--line)] bg-white/90 px-4 py-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-[0_14px_28px_rgba(15,23,42,0.07)]">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--surface)] text-sm font-semibold text-[var(--text)]">
        #{row.rank}
      </div>
      <AvatarBadge
        row={row}
        sizeClass="h-14 w-14"
        iconClass="h-3.5 w-3.5"
        shellClass="bg-gradient-to-br from-white via-[var(--surface)] to-[var(--surface)]"
        feishuLabel={feishuLabel}
      />
      <div className="min-w-0 flex-1">
        <div className="truncate font-semibold text-[var(--text)]">{row.display_name}</div>
        <div className="mt-1 text-sm text-[var(--muted)]">{row.role || row.role_summary || fallbackRole}</div>
      </div>
      <div className="text-right">
        <div className="text-2xl font-semibold text-[var(--text)]">{row.points}</div>
        <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">{pointsLabel}</div>
      </div>
    </div>
  );
}

export function LeaderboardPageContent({ rows }: LeaderboardPageProps) {
  const { t } = useI18n();
  const rankedRows = decorateRows(rows);
  const podiumRows = rankedRows.filter((row) => row.rank <= 3);
  const listRows = rankedRows.filter((row) => row.rank > 3);
  const totalPoints = rankedRows.reduce((sum, row) => sum + row.points, 0);
  const topThreePoints = podiumRows.reduce((sum, row) => sum + row.points, 0);
  const topName = podiumRows[0]?.display_name ?? null;

  const podiumCopy = {
    1: {
      label: t("pages.leaderboard.podium.first"),
      shell: "border-amber-300/80 bg-[linear-gradient(145deg,rgba(255,251,235,0.98),rgba(248,244,225,0.92))]",
      glow: "from-amber-200/45 via-amber-100/20 to-transparent",
      accent: "bg-amber-500",
      badge: "border-amber-200 bg-amber-50 text-amber-900",
      score: "text-amber-950",
      lift: "md:-translate-y-3",
      avatar: "from-rose-100 via-rose-50 to-amber-50 text-rose-950",
      avatarIcon: "h-4.5 w-4.5",
    },
    2: {
      label: t("pages.leaderboard.podium.second"),
      shell: "border-slate-300/80 bg-[linear-gradient(145deg,rgba(249,250,251,0.98),rgba(237,242,247,0.9))]",
      glow: "from-slate-200/45 via-slate-100/20 to-transparent",
      accent: "bg-slate-500",
      badge: "border-slate-200 bg-slate-100 text-slate-800",
      score: "text-slate-900",
      lift: "md:translate-y-2",
      avatar: "from-indigo-100 via-indigo-50 to-slate-50 text-indigo-950",
      avatarIcon: "h-4 w-4",
    },
    3: {
      label: t("pages.leaderboard.podium.third"),
      shell: "border-orange-300/80 bg-[linear-gradient(145deg,rgba(255,247,237,0.98),rgba(250,241,230,0.92))]",
      glow: "from-orange-200/40 via-orange-100/15 to-transparent",
      accent: "bg-orange-500",
      badge: "border-orange-200 bg-orange-50 text-orange-900",
      score: "text-orange-950",
      lift: "md:translate-y-5",
      avatar: "from-sky-100 via-sky-50 to-orange-50 text-sky-950",
      avatarIcon: "h-4 w-4",
    },
  } as const;

  return (
    <section>
      <header className="mb-6">
        <h1 className="font-[var(--font-serif)] text-3xl font-semibold">{t("pages.leaderboard.title")}</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">{t("pages.leaderboard.subtitle")}</p>
      </header>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <SummaryMetric label={t("pages.leaderboard.metrics.activeAgents")} value={`${rankedRows.length}`} hint={t("pages.leaderboard.metrics.activeHint")} />
        <SummaryMetric label={t("pages.leaderboard.metrics.leaderPoints")} value={`${rankedRows[0]?.points ?? 0}`} hint={t("pages.leaderboard.metrics.leaderHint")} />
        <SummaryMetric label={t("pages.leaderboard.metrics.topThree")} value={`${topThreePoints}`} hint={t("pages.leaderboard.metrics.topThreeHint")} />
      </div>

      <Card className="mt-5 overflow-hidden border-none bg-[linear-gradient(180deg,rgba(255,248,233,0.82)_0%,rgba(255,255,255,0.92)_40%,rgba(246,248,252,0.96)_100%)] shadow-[0_18px_44px_rgba(15,23,42,0.06)]">
        <CardContent className="p-3.5 md:p-4">
          {podiumRows.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-[220px_minmax(0,1fr)]">
              <TopThreeRail
                topThreePoints={topThreePoints}
                topName={topName}
                title={t("pages.leaderboard.topThree.title")}
                subtitle={t("pages.leaderboard.topThree.subtitle")}
                totalLabel={t("pages.leaderboard.topThree.totalLabel")}
                leaderLabel={t("pages.leaderboard.topThree.leaderLabel")}
                emptyLabel={t("common.none")}
              />

              <div className="mx-auto grid w-full max-w-5xl grid-cols-1 gap-3 md:grid-cols-[0.92fr_1.08fr_0.92fr] md:items-stretch">
                {podiumRows.map((row) => {
                  const tone = podiumCopy[Math.min(3, Math.max(1, row.rank)) as 1 | 2 | 3];
                  return (
                    <PodiumCard
                      key={row.agent_id}
                      row={row}
                      fallbackRole={t("pages.leaderboard.fallbackLeading")}
                      feishuLabel={t("common.platforms.feishu")}
                      {...tone}
                    />
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-[var(--line)] bg-white/70 px-4 py-10 text-center text-sm text-[var(--muted)]">
              {t("pages.leaderboard.emptyTopThree")}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">{t("pages.leaderboard.moreTitle")}</CardTitle>
          <CardDescription>{t("pages.leaderboard.moreDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {listRows.length > 0 ? (
            listRows.map((row) => (
              <RankingRow
                key={row.agent_id}
                row={row}
                fallbackRole={t("pages.leaderboard.fallbackWaiting")}
                feishuLabel={t("common.platforms.feishu")}
                pointsLabel={t("pages.leaderboard.pointsLabel")}
              />
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-[var(--line)] bg-[var(--surface)] px-4 py-10 text-center text-sm text-[var(--muted)]">
              {t("pages.leaderboard.emptyList", { totalPoints })}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
