import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DEFAULT_PROXY_BASE = "http://127.0.0.1:8088";
const PROXY_ATTEMPT_TIMEOUT_MS = 2500;
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function resolveProxyBase() {
  return process.env.OPENCLAW_PROXY_BASE || process.env.OPENCLAW_API_BASE || DEFAULT_PROXY_BASE;
}

function isLoopbackHost(hostname: string) {
  const normalized = String(hostname || "").trim().toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}

function resolveProxyBases(request: Request) {
  const configuredBase = resolveProxyBase();
  const incomingHost = new URL(request.url).hostname;
  if (!isLoopbackHost(incomingHost) || configuredBase === DEFAULT_PROXY_BASE) {
    return [configuredBase];
  }
  return [configuredBase, DEFAULT_PROXY_BASE];
}

function buildTargetUrl(request: Request, path: string[], proxyBase: string) {
  const target = new URL(`/api/${path.join("/")}`, proxyBase);
  const incoming = new URL(request.url);
  target.search = incoming.search;
  return target;
}

function buildProxyHeaders(request: Request) {
  const headers = new Headers(request.headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }
  return headers;
}

async function proxyRequest(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path = [] } = await context.params;
  const method = request.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";
  const body = hasBody ? await request.arrayBuffer() : undefined;

  let response: Response | null = null;
  let lastError: unknown = null;
  let lastTarget = "";
  for (const proxyBase of resolveProxyBases(request)) {
    const targetUrl = buildTargetUrl(request, path, proxyBase);
    lastTarget = targetUrl.toString();
    try {
      response = await fetch(targetUrl, {
        method,
        headers: buildProxyHeaders(request),
        body,
        redirect: "manual",
        cache: "no-store",
        signal: AbortSignal.timeout(PROXY_ATTEMPT_TIMEOUT_MS),
      });
      break;
    } catch (error) {
      lastError = error;
    }
  }

  if (!response) {
    return NextResponse.json(
      {
        detail: {
          code: "proxy_unreachable",
          message: lastError instanceof Error ? lastError.message : "proxy_unreachable",
          details: {
            target: lastTarget,
          },
        },
      },
      { status: 502 },
    );
  }

  const headers = new Headers(response.headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}

export async function PUT(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}

export async function PATCH(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}

export async function DELETE(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}

export async function HEAD(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}

export async function OPTIONS(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}
