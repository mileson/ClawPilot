"use client";

import Link from "next/link";
import { useSyncExternalStore, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import type { Icon } from "@phosphor-icons/react";
import {
  ChartLineUpIcon,
  ClockCountdownIcon,
  FilesIcon,
  FolderOpenIcon,
  GearSixIcon,
  PlusCircleIcon,
  RocketLaunchIcon,
  ShieldCheckeredIcon,
  ToolboxIcon,
  UsersIcon,
  WrenchIcon,
} from "@phosphor-icons/react";

import { cn } from "@/lib/utils";
import { getStoredStartHubCompleted, subscribeStoredStartHubCompleted } from "@/lib/start-hub-completion";
import { useSidebar } from "@/components/ui/sidebar";
import { useI18n } from "@/components/i18n/use-locale";
import { RescueCenterNavIcon } from "@/components/layout/rescue-center-nav-icon";

// ── Edition gate ──
// NEXT_PUBLIC_EDITION=public → 公开版（只显示 core 导航）
// 未设置或其他值 → 私有版（显示全部导航）
const isPublicEdition = process.env.NEXT_PUBLIC_EDITION === "public";

interface NavLink {
  href: string;
  label: string;
  icon?: Icon;
  renderIcon?: (active: boolean) => ReactNode;
}

interface NavGroup {
  label: string;
  links: NavLink[];
}

export function SidebarNav({ initialStartHubCompleted = false }: { initialStartHubCompleted?: boolean }) {
  const pathname = usePathname();
  const { open, isMobile, setMobileOpen } = useSidebar();
  const { t } = useI18n();
  const expanded = open || isMobile;
  const startHubCompleted = useSyncExternalStore(
    subscribeStoredStartHubCompleted,
    getStoredStartHubCompleted,
    () => initialStartHubCompleted,
  );

  const groups: NavGroup[] = [
    {
      label: t("nav.group.start"),
      links: startHubCompleted ? [] : [{ href: "/start", label: t("nav.start"), icon: RocketLaunchIcon }],
    },
    {
      label: t("nav.group.agentManagement"),
      links: isPublicEdition
        ? [
            // @tier:core
            { href: "/agents", label: t("nav.agents"), icon: UsersIcon },
            { href: "/add-agent", label: t("nav.addAgent"), icon: PlusCircleIcon },
          ]
        : [
            { href: "/agents", label: t("nav.agents"), icon: UsersIcon },
            { href: "/add-agent", label: t("nav.addAgent"), icon: PlusCircleIcon },
            // @tier:ee
            { href: "/agent-configs", label: t("nav.agentConfigs"), icon: FilesIcon },
            { href: "/lobster-toolkit", label: t("nav.lobsterToolkit"), icon: ToolboxIcon },
          ],
    },
    {
      label: t("nav.group.agentTasks"),
      links: isPublicEdition
        ? [
            // @tier:core
            { href: "/training", label: t("nav.training"), icon: UsersIcon },
          ]
        : [
            // @tier:ee
            { href: "/schedule-timeline", label: t("nav.scheduleTimeline"), icon: ClockCountdownIcon },
            { href: "/training", label: t("nav.training"), icon: UsersIcon },
          ],
    },
    ...(isPublicEdition
      ? [
          {
            label: t("nav.group.agentTasks"),
            links: [
              // @tier:core — Tasks 在公开版放这里
              { href: "/tasks", label: t("nav.tasks"), icon: FilesIcon },
            ],
          },
        ]
      : [
          {
            label: t("nav.group.runtimeRepair"),
            links: [
              // @tier:internal
              { href: "/repair", label: t("nav.repair"), icon: WrenchIcon },
              { href: "/tasks", label: t("nav.tasks"), icon: FilesIcon },
              {
                href: "/rescue-center",
                label: t("nav.rescueCenter"),
                renderIcon: (active: boolean) => <RescueCenterNavIcon active={active} />,
              },
            ],
          },
        ]),
    ...(isPublicEdition
      ? []
      : [
          {
            label: t("nav.group.insights"),
            links: [
              // @tier:ee
              { href: "/data-analysis", label: t("nav.dataAnalysis"), icon: ChartLineUpIcon },
            ],
          },
        ]),
    ...(isPublicEdition
      ? []
      : [
          {
            label: t("nav.group.management"),
            links: [
              // @tier:ee / @tier:internal
              { href: "/accounts", label: t("nav.accounts"), icon: UsersIcon },
              { href: "/roles", label: t("nav.roles"), icon: ShieldCheckeredIcon },
              { href: "/openclaw", label: t("nav.openclaw"), icon: FolderOpenIcon },
              { href: "/system-settings", label: t("nav.systemSettings"), icon: GearSixIcon },
            ],
          },
        ]),
  ].filter((group) => group.links.length > 0);

  return (
    <nav className="space-y-4">
      {groups.map((group) => (
        <div key={group.label} className="space-y-1">
          {expanded ? (
            <p className="px-3 pb-0.5 text-[11px] font-medium tracking-wide text-[var(--muted)]/60 uppercase">
              {group.label}
            </p>
          ) : (
            <div className="mx-auto my-1 h-px w-6 bg-[var(--line)]" />
          )}
          {group.links.map((item) => {
            const active = pathname === item.href;
            let iconNode: ReactNode = null;
            if (item.renderIcon) {
              iconNode = item.renderIcon(active);
            } else if (item.icon) {
              const Icon = item.icon;
              iconNode = <Icon size={20} weight={active ? "fill" : "regular"} />;
            }
            return (
              <Link
                key={item.href}
                href={item.href}
                title={expanded ? undefined : item.label}
                onClick={() => {
                  if (isMobile) setMobileOpen(false);
                }}
                className={cn(
                  "flex items-center border text-sm transition",
                  expanded ? "gap-3 rounded-2xl px-3.5 py-2.5" : "mx-auto h-12 w-12 justify-center rounded-2xl px-0 py-0",
                  active
                    ? "border-neutral-200 bg-white text-neutral-900 shadow-[0_10px_22px_rgba(15,23,42,0.05)]"
                    : "border-transparent text-neutral-600 hover:border-white/80 hover:bg-white",
                )}
              >
                {iconNode}
                {expanded ? <span className="truncate">{item.label}</span> : null}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
