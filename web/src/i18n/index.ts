import enUS from "@/i18n/messages/en-US.json";
import zhCN from "@/i18n/messages/zh-CN.json";

export const MESSAGES = {
  "en-US": enUS,
  "zh-CN": zhCN,
} as const;

export type Locale = keyof typeof MESSAGES;

export const SUPPORTED_LOCALES: Locale[] = ["zh-CN", "en-US"];
export const DEFAULT_LOCALE: Locale = "zh-CN";

export type TranslateParams = Record<string, string | number>;
export type Translator = (key: string, params?: TranslateParams) => string;

function getMessage(locale: Locale, key: string): string | null {
  const segments = key.split(".");
  let current: unknown = MESSAGES[locale];
  for (const segment of segments) {
    if (!current || typeof current !== "object") return null;
    current = (current as Record<string, unknown>)[segment];
  }
  return typeof current === "string" ? current : null;
}

function formatMessage(template: string, params?: TranslateParams): string {
  if (!params) return template;
  return Object.entries(params).reduce(
    (result, [name, value]) => result.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

export function createTranslator(locale: Locale): Translator {
  return (key, params) => {
    const message = getMessage(locale, key) ?? getMessage(DEFAULT_LOCALE, key) ?? key;
    return formatMessage(message, params);
  };
}

export function normalizeLocale(input?: string | null): Locale | null {
  if (!input) return null;
  const lower = input.toLowerCase();
  if (lower.startsWith("zh")) return "zh-CN";
  if (lower.startsWith("en")) return "en-US";
  return null;
}

export function detectBrowserLocale(): Locale {
  if (typeof navigator === "undefined") return DEFAULT_LOCALE;
  const candidates = [...(navigator.languages ?? []), navigator.language].filter(Boolean);
  for (const candidate of candidates) {
    const normalized = normalizeLocale(candidate);
    if (normalized) return normalized;
  }
  return DEFAULT_LOCALE;
}

export function getLocaleLabel(locale: Locale, t: Translator) {
  return t(`locale.name.${locale}`);
}
