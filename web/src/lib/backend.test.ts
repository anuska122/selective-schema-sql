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
