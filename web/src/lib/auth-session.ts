import type { Account } from "@/lib/types";

export const DEFAULT_POST_AUTH_PATH = "/accounts";
const SESSION_STORAGE_KEY = "oc_session";
const ACCOUNT_STORAGE_KEY = "oc_account";
const ACCOUNT_META_EVENT = "openclaw-account-meta-change";
let cachedAccountRaw: string | null | undefined;
let cachedAccountMeta: StoredAccountMeta | null = null;

export type StoredAccountMeta = Pick<Account, "must_change_password"> & Partial<Account>;

function canUseBrowserStorage() {
  return typeof window !== "undefined";
}

function emitStoredAccountMetaChanged() {
  if (!canUseBrowserStorage()) return;
  window.dispatchEvent(new Event(ACCOUNT_META_EVENT));
}

export function getStoredSessionToken(): string | null {
  if (!canUseBrowserStorage()) return null;
  return window.localStorage.getItem(SESSION_STORAGE_KEY);
}

export function clearStoredSession() {
  if (!canUseBrowserStorage()) return;
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEY);
  cachedAccountRaw = null;
  cachedAccountMeta = null;
  emitStoredAccountMetaChanged();
}

export function getStoredAccountMeta(): StoredAccountMeta | null {
  if (!canUseBrowserStorage()) return null;
  const raw = window.localStorage.getItem(ACCOUNT_STORAGE_KEY);
  if (raw === cachedAccountRaw) {
    return cachedAccountMeta;
  }
  cachedAccountRaw = raw;
  if (!raw) return null;
  try {
    cachedAccountMeta = JSON.parse(raw) as StoredAccountMeta;
    return cachedAccountMeta;
  } catch {
    cachedAccountMeta = null;
    return null;
  }
}

export function setStoredAccountMeta(account: Account | StoredAccountMeta) {
  if (!canUseBrowserStorage()) return;
  const raw = JSON.stringify(account);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEY, raw);
  cachedAccountRaw = raw;
  cachedAccountMeta = account as StoredAccountMeta;
  emitStoredAccountMetaChanged();
}

export function subscribeStoredAccountMeta(onStoreChange: () => void) {
  if (!canUseBrowserStorage()) return () => {};
  const handleStorage = (event: StorageEvent) => {
    if (!event.key || event.key === ACCOUNT_STORAGE_KEY) {
      onStoreChange();
    }
  };
  window.addEventListener(ACCOUNT_META_EVENT, onStoreChange);
  window.addEventListener("storage", handleStorage);
  return () => {
    window.removeEventListener(ACCOUNT_META_EVENT, onStoreChange);
    window.removeEventListener("storage", handleStorage);
  };
}

export function markStoredAccountPasswordChangeRequired() {
  const account = getStoredAccountMeta();
  if (!account) return;
  setStoredAccountMeta({ ...account, must_change_password: true });
}

export function sanitizeNextPath(raw: string | null | undefined, fallback = DEFAULT_POST_AUTH_PATH): string {
  if (!raw) return fallback;
  const next = raw.trim();
  if (!next.startsWith("/")) return fallback;
  if (next.startsWith("//")) return fallback;
  if (next.startsWith("/login")) return fallback;
  return next;
}

export function resolvePostAuthPath(raw: string | null | undefined, fallback = DEFAULT_POST_AUTH_PATH): string {
  const next = sanitizeNextPath(raw, fallback);
  if (next.startsWith("/account/password")) return fallback;
  return next;
}

export function buildNextPath(
  pathname: string,
  searchParams?: URLSearchParams | { toString(): string } | null,
): string {
  const query = searchParams?.toString();
  if (!query) return pathname;
  return `${pathname}?${query}`;
}

export function buildAuthRedirectPath(target: "/login" | "/account/password", nextPath: string): string {
  const safeNext = sanitizeNextPath(nextPath);
  return `${target}?next=${encodeURIComponent(safeNext)}`;
}
