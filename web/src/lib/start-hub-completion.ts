const START_HUB_COMPLETION_EVENT = "openclaw-start-hub-completion-change";

export const START_HUB_COMPLETION_COOKIE = "openclaw_start_hub_completed";
export const START_HUB_COMPLETION_COOKIE_VALUE = "1";
const START_HUB_COMPLETION_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

function canUseBrowserCookies() {
  return typeof document !== "undefined" && typeof window !== "undefined";
}

function emitStartHubCompletionChanged() {
  if (!canUseBrowserCookies()) return;
  window.dispatchEvent(new Event(START_HUB_COMPLETION_EVENT));
}

function readCookieValue(cookieSource: string, name: string): string | null {
  for (const part of cookieSource.split(";")) {
    const [rawName, ...rest] = part.trim().split("=");
    if (rawName !== name) continue;
    return rest.join("=") || "";
  }
  return null;
}

export function isStartHubCompletionValue(value: string | null | undefined) {
  return value === START_HUB_COMPLETION_COOKIE_VALUE;
}

export function getStoredStartHubCompleted() {
  if (!canUseBrowserCookies()) return false;
  return isStartHubCompletionValue(readCookieValue(document.cookie || "", START_HUB_COMPLETION_COOKIE));
}

export function subscribeStoredStartHubCompleted(onStoreChange: () => void) {
  if (!canUseBrowserCookies()) return () => {};
  window.addEventListener(START_HUB_COMPLETION_EVENT, onStoreChange);
  return () => {
    window.removeEventListener(START_HUB_COMPLETION_EVENT, onStoreChange);
  };
}

export function setStoredStartHubCompleted(completed: boolean) {
  if (!canUseBrowserCookies()) return;
  if (completed) {
    document.cookie =
      `${START_HUB_COMPLETION_COOKIE}=${START_HUB_COMPLETION_COOKIE_VALUE}; ` +
      `Path=/; Max-Age=${START_HUB_COMPLETION_COOKIE_MAX_AGE}; SameSite=Lax`;
  } else {
    document.cookie = `${START_HUB_COMPLETION_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
  }
  emitStartHubCompletionChanged();
}
