import { createTranslator, DEFAULT_LOCALE, detectBrowserLocale, normalizeLocale, type Locale } from "@/i18n";

const STORAGE_PREFERRED = "openclaw.locale.preferred";

export function getRuntimeLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const stored = window.localStorage.getItem(STORAGE_PREFERRED);
  const normalizedStored = normalizeLocale(stored);
  if (normalizedStored) return normalizedStored;
  return detectBrowserLocale();
}

export function tRuntime(key: string, params?: Record<string, string | number>) {
  const locale = getRuntimeLocale();
  return createTranslator(locale)(key, params);
}
