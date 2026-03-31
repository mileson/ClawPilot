"use client";

import * as React from "react";
import { SidebarIcon } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";
import { useI18n } from "@/components/i18n/use-locale";

interface SidebarContextValue {
  open: boolean;
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  mobileOpen: boolean;
  setMobileOpen: React.Dispatch<React.SetStateAction<boolean>>;
  isMobile: boolean;
  toggleSidebar: () => void;
}

const SidebarContext = React.createContext<SidebarContextValue | null>(null);

function useSidebar() {
  const context = React.useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within SidebarProvider");
  }
  return context;
}

function SidebarProvider({
  defaultOpen = true,
  children,
}: React.PropsWithChildren<{ defaultOpen?: boolean }>) {
  const [open, setOpen] = React.useState(defaultOpen);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [isMobile, setIsMobile] = React.useState(false);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem("openclaw-sidebar-open");
    if (stored === "0") setOpen(false);
    if (stored === "1") setOpen(true);
  }, []);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("openclaw-sidebar-open", open ? "1" : "0");
  }, [open]);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(max-width: 1023px)");
    const sync = () => {
      const nextMobile = media.matches;
      setIsMobile(nextMobile);
      if (!nextMobile) {
        setMobileOpen(false);
      }
    };
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  const value = React.useMemo(
    () => ({
      open,
      setOpen,
      mobileOpen,
      setMobileOpen,
      isMobile,
      toggleSidebar: () => {
        if (isMobile) {
          setMobileOpen((current) => !current);
          return;
        }
        setOpen((current) => !current);
      },
    }),
    [isMobile, mobileOpen, open],
  );

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
}

function Sidebar({
  className,
  children,
}: React.ComponentProps<"aside">) {
  const { open, mobileOpen, isMobile, setMobileOpen } = useSidebar();

  return (
    <>
      {isMobile ? (
        <div
          aria-hidden="true"
          onClick={() => setMobileOpen(false)}
          className={cn(
            "fixed inset-0 z-40 bg-black/28 backdrop-blur-[2px] transition-opacity duration-200 lg:hidden",
            mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
          )}
        />
      ) : null}
      <aside
        data-state={open ? "expanded" : "collapsed"}
        data-mobile={isMobile ? "true" : "false"}
        className={cn(
          "group/sidebar flex flex-col overflow-hidden border-r border-[var(--line)] bg-[var(--sidebar)] transition-[width,padding,transform] duration-200 ease-out",
          isMobile
            ? cn(
                "fixed inset-y-0 left-0 z-50 w-[320px] max-w-[86vw] px-4 py-4 shadow-[0_28px_72px_rgba(15,23,42,0.24)] lg:hidden",
                mobileOpen ? "translate-x-0" : "-translate-x-full",
              )
            : open
              ? "relative sticky top-0 h-screen w-[260px] shrink-0 p-4"
              : "relative sticky top-0 h-screen w-[77px] shrink-0 px-2.5 py-4",
          className,
        )}
      >
        {children}
      </aside>
    </>
  );
}

function SidebarHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("mb-4", className)} {...props} />;
}

function SidebarContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex min-h-0 flex-1 flex-col overflow-y-auto", className)} {...props} />;
}

function SidebarFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("mt-4", className)} {...props} />;
}

function SidebarInset({ className, ...props }: React.ComponentProps<"main">) {
  return <main className={cn("min-h-0 min-w-0 flex-1 overflow-hidden p-5 lg:p-7", className)} {...props} />;
}

function SidebarTrigger({
  className,
  ...props
}: React.ComponentProps<"button">) {
  const { open, mobileOpen, isMobile, toggleSidebar } = useSidebar();
  const { t } = useI18n();
  const label = isMobile
    ? mobileOpen
      ? t("sidebar.collapseNav")
      : t("sidebar.expandNav")
    : open
      ? t("sidebar.collapse")
      : t("sidebar.expand");
  return (
    <button
      type="button"
      onClick={toggleSidebar}
      className={cn(
        "inline-flex h-5 w-5 items-center justify-center rounded text-[var(--muted)] transition-colors hover:text-[var(--text)]",
        className,
      )}
      aria-label={label}
      title={label}
      {...props}
    >
      <SidebarIcon size={18} />
    </button>
  );
}

function SidebarRail({ className, ...props }: React.ComponentProps<"div">) {
  const { open, isMobile } = useSidebar();
  if (isMobile) return null;
  return (
    <div
      aria-hidden="true"
      className={cn(
        "absolute inset-y-0 right-0 w-px bg-[var(--line)] transition-opacity",
        open ? "opacity-0" : "opacity-100",
        className,
      )}
      {...props}
    />
  );
}

export {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
};
