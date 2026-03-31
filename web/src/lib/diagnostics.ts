"use client";

type DiagnosticLogLevel = "info" | "warn" | "error";

export type DiagnosticDetailValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | DiagnosticDetailValue[]
  | { [key: string]: DiagnosticDetailValue };

export type ClientDiagnosticLogPayload = {
  category: string;
  event: string;
  level?: DiagnosticLogLevel;
  trace_id?: string | null;
  request_path?: string | null;
  detail?: Record<string, DiagnosticDetailValue>;
};

const CLIENT_API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";
const LOCAL_BUFFER_KEY = "oc_diagnostic_buffer";
const LOCAL_BUFFER_LIMIT = 50;

function resolveDiagnosticApiUrl(path: string): string {
  return CLIENT_API_BASE ? `${CLIENT_API_BASE}${path}` : path;
}

function appendFallbackDiagnosticLog(entry: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(LOCAL_BUFFER_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    const items = Array.isArray(parsed) ? (parsed as Array<Record<string, unknown>>) : [];
    items.unshift(entry);
    window.localStorage.setItem(LOCAL_BUFFER_KEY, JSON.stringify(items.slice(0, LOCAL_BUFFER_LIMIT)));
  } catch {
    // 忽略本地兜底写入失败，避免影响主流程。
  }
}

export function createDiagnosticTraceId(prefix = "trace"): string {
  const randomPart = Math.random().toString(36).slice(2, 8);
  return `${prefix}_${Date.now()}_${randomPart}`;
}

export async function recordClientDiagnosticLog(payload: ClientDiagnosticLogPayload): Promise<void> {
  if (typeof window === "undefined") return;
  const createdAt = new Date().toISOString();
  const entry = {
    source: "client" as const,
    category: payload.category,
    event: payload.event,
    level: payload.level || "info",
    trace_id: payload.trace_id || null,
    request_path: payload.request_path || window.location.pathname || null,
    detail: {
      ...(payload.detail || {}),
      client_logged_at: createdAt,
    },
    created_at: createdAt,
  };
  const token = window.localStorage.getItem("oc_session");
  if (!token) {
    appendFallbackDiagnosticLog(entry);
    return;
  }
  try {
    const response = await fetch(resolveDiagnosticApiUrl("/api/diagnostic-logs"), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        source: entry.source,
        category: entry.category,
        event: entry.event,
        level: entry.level,
        trace_id: entry.trace_id,
        request_path: entry.request_path,
        detail: entry.detail,
      }),
      cache: "no-store",
    });
    if (!response.ok) {
      appendFallbackDiagnosticLog({ ...entry, post_status: response.status });
    }
  } catch {
    appendFallbackDiagnosticLog(entry);
  }
}
