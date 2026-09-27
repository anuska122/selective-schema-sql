import { describe, expect, it, vi } from "vitest";
import { backendUrl, forward } from "./backend";

describe("backendUrl", () => {
  it("uses the default local backend", () => {
    expect(backendUrl("/ask")).toBe("http://127.0.0.1:8000/ask");
  });

  it("honours BACKEND_URL without a double slash", () => {
    vi.stubEnv("BACKEND_URL", "http://api.internal:9000/");
    expect(backendUrl("/ask")).toBe("http://api.internal:9000/ask");
  });
});

describe("forward", () => {
  it("passes status and body through", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ ok: true }, { status: 201 }));
    const response = await forward("/databases");
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ ok: true });
  });

  it("returns 503 when the backend is down", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const response = await forward("/ask");
    expect(response.status).toBe(503);
    expect((await response.json()).detail).toMatch(/not reachable/);
  });
});

describe("shared token", () => {
  it("adds the token header for the backend when one is configured", async () => {
    vi.stubEnv("API_TOKEN", "shared");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({}));
    await forward("/ask", { method: "POST", headers: { "content-type": "application/json" } });
    const headers = fetchSpy.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers["x-api-token"]).toBe("shared");
    expect(headers["content-type"]).toBe("application/json");
  });

  it("sends no token header when none is configured", async () => {
    vi.stubEnv("API_TOKEN", "");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({}));
    await forward("/databases");
    expect(fetchSpy.mock.calls[0][1]?.headers).toBeUndefined();
  });
});
