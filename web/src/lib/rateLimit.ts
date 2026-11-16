const WINDOW_MS = 60 * 60 * 1000;
const DEFAULT_LIMIT = 5;
const MAX_TRACKED_CLIENTS = 10_000;

const hits = new Map<string, number[]>();

function limit(): number {
  const configured = Number(process.env.RATE_LIMIT_PER_HOUR);
  return Number.isFinite(configured) && configured > 0 ? configured : DEFAULT_LIMIT;
}

export function clientId(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return forwarded || request.headers.get("x-real-ip") || "unknown";
}

export function trustedClientId(request: Request): string {
  return process.env.TRUST_PROXY_HEADERS === "1" ? clientId(request) : "unknown";
}

export function allow(id: string, now = Date.now()): boolean {
  const recent = (hits.get(id) ?? []).filter((at) => now - at < WINDOW_MS);
  if (recent.length >= limit()) {
    hits.set(id, recent);
    return false;
  }
  recent.push(now);
  hits.set(id, recent);
  if (hits.size > MAX_TRACKED_CLIENTS) {
    for (const [key, times] of hits) {
      if (times.every((at) => now - at >= WINDOW_MS)) hits.delete(key);
    }
  }
  return true;
}

export function reset(): void {
  hits.clear();
}
