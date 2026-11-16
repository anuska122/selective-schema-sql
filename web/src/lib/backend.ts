const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
const TIMEOUT_MS = 120_000;

export function backendUrl(path: string): string {
  const base = process.env.BACKEND_URL ?? DEFAULT_BACKEND_URL;
  return `${base.replace(/\/$/, "")}${path}`;
}

function withToken(headers: HeadersInit | undefined): HeadersInit | undefined {
  const token = process.env.API_TOKEN;
  if (!token) return headers;
  return { ...(headers as Record<string, string> | undefined), "x-api-token": token };
}

export async function forward(path: string, init?: RequestInit): Promise<Response> {
  try {
    const response = await fetch(backendUrl(path), {
      ...init,
      headers: withToken(init?.headers),
      cache: "no-store",
      signal: init?.signal
        ? AbortSignal.any([init.signal, AbortSignal.timeout(TIMEOUT_MS)])
        : AbortSignal.timeout(TIMEOUT_MS),
    });
    const body = await response.text();
    return new Response(body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: "The query service is not reachable." }, { status: 503 });
  }
}
