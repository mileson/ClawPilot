import { cn } from "@/lib/utils";

export type ControlPlanePageState = "loading" | "ready" | "notice" | "error" | "empty" | "blocked";
export type ControlPlaneButtonState = "default" | "disabled" | "running" | "success" | "partial" | "failed";

const PAGE_STATE_META: Record<ControlPlanePageState, { label: string; tone: string }> = {
  loading: { label: "加载中", tone: "border-sky-200 bg-sky-50 text-sky-700" },
  ready: { label: "正常可用", tone: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  notice: { label: "有提醒", tone: "border-amber-200 bg-amber-50 text-amber-800" },
  error: { label: "有异常", tone: "border-rose-200 bg-rose-50 text-rose-700" },
  empty: { label: "空状态", tone: "border-neutral-200 bg-neutral-100 text-neutral-700" },
  blocked: { label: "阻断状态", tone: "border-red-200 bg-red-50 text-red-700" },
};

const BUTTON_STATE_META: Record<ControlPlaneButtonState, { label: string; tone: string }> = {
  default: { label: "默认", tone: "border-[var(--line)] bg-white text-[var(--text)]" },
  disabled: { label: "禁用", tone: "border-[var(--line)] bg-[var(--surface)] text-[var(--muted)]" },
  running: { label: "执行中", tone: "border-sky-200 bg-sky-50 text-sky-700" },
  success: { label: "成功", tone: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  partial: { label: "部分成功", tone: "border-amber-200 bg-amber-50 text-amber-800" },
  failed: { label: "失败", tone: "border-rose-200 bg-rose-50 text-rose-700" },
};

export function ControlPlaneStateLegend({
  pageState,
  buttonState,
}: {
  pageState: ControlPlanePageState;
  buttonState: ControlPlaneButtonState;
}) {
  const pageMeta = PAGE_STATE_META[pageState];
  const buttonMeta = BUTTON_STATE_META[buttonState];
  return (
    <div className="flex flex-wrap gap-2">
      <span className={cn("inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium", pageMeta.tone)}>
        {pageMeta.label}
      </span>
      <span className={cn("inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium", buttonMeta.tone)}>
        按钮：{buttonMeta.label}
      </span>
    </div>
  );
}

export function ControlPlaneAdvancedMode({
  title = "查看技术详情 / 高级模式",
  children,
  defaultOpen = false,
}: {
  title?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      className="rounded-[28px] border border-[var(--line)] bg-white px-5 py-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]"
      open={defaultOpen}
    >
      <summary className="cursor-pointer list-none text-sm font-semibold text-[var(--text)]">{title}</summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}
