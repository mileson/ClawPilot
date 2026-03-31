"use client";

import { useSyncExternalStore } from "react";
import { ListIcon, SidebarIcon } from "@phosphor-icons/react";
import Image from "next/image";
import { usePathname } from "next/navigation";

import { LanguageBanner } from "@/components/i18n/language-banner";
import { useI18n } from "@/components/i18n/use-locale";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { getStoredAccountMeta, subscribeStoredAccountMeta } from "@/lib/auth-session";
import { cn } from "@/lib/utils";

interface DashboardShellProps {
  children: React.ReactNode;
  startHubCompleted?: boolean;
}

const SIDEBAR_BRAND_ICON_SRC = "/branding/clawpilot-sidebar.png";

export function DashboardShell({ children, startHubCompleted = false }: DashboardShellProps) {
  return (
    <SidebarProvider defaultOpen>
      <div className="h-screen overflow-hidden bg-[var(--background)]">
        <div className="mx-auto flex h-screen max-w-[1560px]">
          <Sidebar>
            <SidebarHeader>
              <SidebarBrand />
            </SidebarHeader>

            <SidebarContent>
              <SidebarNav initialStartHubCompleted={startHubCompleted} />
            </SidebarContent>

            <SidebarFooter className="-mx-4 -mb-4 border-t border-[var(--line)] px-4 py-5 group-data-[mobile=true]/sidebar:-mx-5 group-data-[mobile=true]/sidebar:px-4">
              <SidebarAccountSummary />
            </SidebarFooter>

            <SidebarRail />
          </Sidebar>

          <SidebarInset className="overflow-y-auto p-0">
            <div className="min-h-0 min-w-0 px-3 py-5 lg:px-4 lg:py-6">
              <LanguageBanner className="-mx-3 mb-4 px-3 lg:-mx-4 lg:px-4" />
              <MobileTopbar />
              {children}
            </div>
          </SidebarInset>
        </div>
      </div>
    </SidebarProvider>
  );
}

function SidebarBrand() {
  const { open, setOpen, isMobile } = useSidebar();
  const { t } = useI18n();
  const expanded = open || isMobile;

  return (
    <div className={expanded ? "space-y-4" : "flex justify-center"}>
      {expanded ? (
        <div className="relative flex items-center gap-3 px-1 py-1">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-7 w-7 place-items-center overflow-hidden rounded-lg">
              <Image src={SIDEBAR_BRAND_ICON_SRC} alt="ClawPilot" width={28} height={28} priority />
            </div>
            <p className="truncate text-[16px] font-semibold text-[var(--text)]">{t("brand.name")}</p>
          </div>
          <SidebarTrigger className="absolute right-[-2px] top-1/2 -translate-y-1/2 shrink-0" />
        </div>
      ) : (
        <div className="relative h-[34px] w-[34px]">
          <div className="grid h-[34px] w-[34px] place-items-center overflow-hidden rounded-xl transition duration-200 group-hover/sidebar:scale-95 group-hover/sidebar:opacity-0">
            <Image src={SIDEBAR_BRAND_ICON_SRC} alt="ClawPilot" width={34} height={34} priority />
          </div>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="absolute inset-0 grid place-items-center rounded-xl border border-neutral-200 bg-white text-[var(--text)] opacity-0 shadow-[0_16px_36px_rgba(15,23,42,0.08)] transition duration-200 group-hover/sidebar:opacity-100"
            aria-label={t("sidebar.expand")}
            title={t("sidebar.expand")}
          >
            <SidebarIcon size={20} />
          </button>
        </div>
      )}
    </div>
  );
}

function SidebarAccountSummary() {
  const { open, isMobile } = useSidebar();
  const { t } = useI18n();
  const account = useSyncExternalStore(subscribeStoredAccountMeta, getStoredAccountMeta, () => null);
  const expanded = open || isMobile;

  if (!account) return null;

  const name = resolveAccountName(account);
  const initials = buildAccountInitials(name);

  return (
    <section
      title={name}
      className={cn(
        expanded ? "flex items-center gap-2 px-0.5" : "mx-auto grid h-9 w-9 place-items-center",
      )}
    >
      <div className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-full bg-[var(--line)] text-xs font-semibold text-[var(--muted)]">
        {initials}
      </div>
      {expanded ? (
        <>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] leading-snug font-semibold text-[var(--text)]">{name}</p>
            <p className="truncate text-[11px] leading-snug text-[var(--muted)]">{t("sidebar.membership.freePlan")}</p>
          </div>
          <button
            type="button"
            className="inline-flex h-7 w-16 shrink-0 cursor-pointer items-center justify-center rounded-full border border-[var(--line)] bg-transparent text-[11px] font-semibold text-[var(--text)] transition-colors hover:bg-[var(--surface)]"
            aria-label={t("sidebar.membership.upgrade")}
            title={t("sidebar.membership.upgrade")}
          >
            {t("sidebar.membership.upgrade")}
          </button>
        </>
      ) : null}
    </section>
  );
}

function MobileTopbar() {
  const pathname = usePathname();
  const { isMobile, setMobileOpen } = useSidebar();
  const { t } = useI18n();

  if (!isMobile) return null;

  const currentLabel =
    pathname === "/start"
      ? t("nav.start")
      : pathname === "/agents"
      ? t("nav.agents")
      : pathname === "/add-agent"
        ? t("nav.addAgent")
      : pathname === "/schedule-timeline"
        ? t("nav.scheduleTimeline")
      : pathname === "/lobster-toolkit"
        ? t("nav.lobsterToolkit")
      : pathname === "/agent-configs"
        ? t("nav.agentConfigs")
      : pathname === "/repair"
        ? t("nav.repair")
      : pathname === "/rescue-center"
        ? t("nav.rescueCenter")
      : pathname === "/accounts"
        ? t("nav.accounts")
      : pathname === "/roles"
        ? t("nav.roles")
      : pathname === "/data-analysis"
        ? t("nav.dataAnalysis")
      : pathname === "/system-settings"
        ? t("nav.systemSettings")
      : pathname === "/openclaw"
        ? t("nav.openclaw")
      : pathname === "/tasks"
        ? t("nav.tasks")
      : pathname === "/training"
        ? t("nav.training")
      : pathname === "/leaderboard"
        ? t("nav.leaderboard")
        : t("brand.name");

  return (
    <div className="sticky top-0 z-30 -mx-3 mb-4 border-b border-[var(--line)] bg-[var(--background)]/92 px-3 py-3 backdrop-blur lg:hidden">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="grid h-11 w-11 place-items-center rounded-2xl border border-neutral-200 bg-white text-[var(--text)] shadow-[0_8px_22px_rgba(15,23,42,0.05)] transition hover:bg-[var(--surface)]"
          aria-label={t("sidebar.openNav")}
          title={t("sidebar.openNav")}
        >
          <ListIcon size={20} />
        </button>
        <div className="grid h-11 w-11 place-items-center overflow-hidden rounded-2xl">
          <Image src={SIDEBAR_BRAND_ICON_SRC} alt="ClawPilot" width={44} height={44} priority />
        </div>
        <div className="min-w-0">
          <p className="truncate text-[17px] font-semibold text-[var(--text)]">{t("brand.name")}</p>
          <p className="truncate text-xs text-[var(--muted)]">{currentLabel}</p>
        </div>
      </div>
    </div>
  );
}
function resolveAccountName(account: ReturnType<typeof getStoredAccountMeta>) {
  return account?.display_name?.trim() || account?.username?.trim() || "?";
}

function buildAccountInitials(name: string) {
  const normalized = name.trim();
  if (!normalized) return "?";
  const parts = normalized.split(/\s+/).filter(Boolean);
  if (parts.length > 1) {
    return parts
      .slice(0, 2)
      .map((part) => Array.from(part)[0]?.toUpperCase() || "")
      .join("");
  }
  return Array.from(normalized)[0]?.toUpperCase() || "?";
}
