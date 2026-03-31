"use client";

import { useI18n } from "@/components/i18n/use-locale";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  titleKey: string;
  subtitleKey?: string;
  className?: string;
}

export function PageHeader({ titleKey, subtitleKey, className }: PageHeaderProps) {
  const { t } = useI18n();

  return (
    <header className={cn("mb-4", className)}>
      <h1 className="font-[var(--font-serif)] text-3xl font-semibold text-[var(--text)]">{t(titleKey)}</h1>
      {subtitleKey ? <p className="mt-1 text-sm text-[var(--muted)]">{t(subtitleKey)}</p> : null}
    </header>
  );
}
