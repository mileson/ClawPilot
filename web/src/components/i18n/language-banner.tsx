"use client";

import { Button } from "@/components/ui/button";
import { getLocaleLabel } from "@/i18n";
import { useI18n } from "@/components/i18n/use-locale";
import { cn } from "@/lib/utils";

export function LanguageBanner({ className }: { className?: string }) {
  const { bannerVisible, dismissBanner, hydrated, switchToBrowserLocale, browserLocale, t } = useI18n();

  if (!hydrated || !bannerVisible) return null;

  const browserLabel = getLocaleLabel(browserLocale, t);

  return (
    <div
      className={cn(
        "rounded-[20px] border border-transparent bg-slate-700 px-4 py-3 text-sm text-white shadow-[0_10px_30px_rgba(15,23,42,0.18)]",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 text-sm font-medium">
          {t("banner.message", { browserLanguage: browserLabel })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            className="h-8 rounded-full bg-white px-3 text-xs font-semibold text-slate-800 shadow-none hover:bg-white/90"
            onClick={switchToBrowserLocale}
          >
            {t("banner.switch", { browserLanguage: browserLabel })}
          </Button>
          <button
            type="button"
            onClick={dismissBanner}
            className="text-xs font-medium text-white/80 underline-offset-4 hover:text-white hover:underline"
          >
            {t("banner.dismiss")}
          </button>
        </div>
      </div>
    </div>
  );
}
