"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  createTranslator,
  detectBrowserLocale,
  normalizeLocale,
  type Locale,
  type Translator,
} from "@/i18n";

const STORAGE_PREFERRED = "openclaw.locale.preferred";
const STORAGE_BANNER_DISMISSED = "openclaw.locale.bannerDismissedFor";

interface I18nContextValue {
  locale: Locale;
  browserLocale: Locale;
  preferredLocale: Locale | null;
  bannerVisible: boolean;
  hydrated: boolean;
  availableLocales: Locale[];
  setPreferredLocale: (locale: Locale) => void;
  dismissBanner: () => void;
  switchToBrowserLocale: () => void;
  t: Translator;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function readStoredLocale(key: string): Locale | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(key);
  return normalizeLocale(raw);
}

function writeStoredLocale(key: string, locale: Locale | null) {
  if (typeof window === "undefined") return;
  if (locale) {
    window.localStorage.setItem(key, locale);
  } else {
    window.localStorage.removeItem(key);
  }
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [hydrated, setHydrated] = useState(false);
  const [browserLocale, setBrowserLocale] = useState<Locale>(DEFAULT_LOCALE);
  const [preferredLocale, setPreferredLocaleState] = useState<Locale | null>(null);
  const [locale, setLocale] = useState<Locale>(DEFAULT_LOCALE);
  const [bannerDismissedFor, setBannerDismissedFor] = useState<Locale | null>(null);
  const [bannerVisible, setBannerVisible] = useState(false);

  const t = useMemo(() => createTranslator(locale), [locale]);

  const syncBannerVisibility = useCallback(
    (nextPreferred: Locale | null, nextSystem: Locale, dismissedFor: Locale | null) => {
      if (!nextPreferred) {
        setBannerVisible(false);
        return;
      }
      const shouldShow = nextPreferred !== nextSystem && dismissedFor !== nextSystem;
      setBannerVisible(shouldShow);
    },
    [],
  );

  useEffect(() => {
    const browser = detectBrowserLocale();
    const storedPreferred = readStoredLocale(STORAGE_PREFERRED);
    const storedDismissed = readStoredLocale(STORAGE_BANNER_DISMISSED);
    const effectiveLocale = storedPreferred ?? browser;

    setBrowserLocale(browser);
    setPreferredLocaleState(storedPreferred);
    setBannerDismissedFor(storedDismissed);
    setLocale(effectiveLocale);
    syncBannerVisibility(storedPreferred, browser, storedDismissed);
    setHydrated(true);
  }, [syncBannerVisibility]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.title = t("meta.title");
    const description = document.querySelector("meta[name=\"description\"]");
    if (description) {
      description.setAttribute("content", t("meta.description"));
    }
  }, [t]);

  const setPreferredLocale = useCallback(
    (nextLocale: Locale) => {
      setPreferredLocaleState(nextLocale);
      setLocale(nextLocale);
      writeStoredLocale(STORAGE_PREFERRED, nextLocale);
      syncBannerVisibility(nextLocale, browserLocale, bannerDismissedFor);
    },
    [bannerDismissedFor, browserLocale, syncBannerVisibility],
  );

  const switchToBrowserLocale = useCallback(() => {
    setPreferredLocale(browserLocale);
    setBannerVisible(false);
  }, [setPreferredLocale, browserLocale]);

  const dismissBanner = useCallback(() => {
    writeStoredLocale(STORAGE_BANNER_DISMISSED, browserLocale);
    setBannerDismissedFor(browserLocale);
    setBannerVisible(false);
  }, [browserLocale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      browserLocale,
      preferredLocale,
      bannerVisible,
      hydrated,
      availableLocales: SUPPORTED_LOCALES,
      setPreferredLocale,
      dismissBanner,
      switchToBrowserLocale,
      t,
    }),
    [
      bannerVisible,
      browserLocale,
      hydrated,
      locale,
      preferredLocale,
      setPreferredLocale,
      t,
      dismissBanner,
      switchToBrowserLocale,
    ],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return context;
}

export { I18nContext };
