import { beforeEach, describe, expect, it, vi } from "vitest";
import { allow, clientId, reset } from "./rateLimit";

describe("clientId", () => {
  it("takes the first forwarded address", () => {
    const request = new Request("http://localhost", {
      headers: { "x-forwarded-for": "203.0.113.7, 10.0.0.1" },
    });
    expect(clientId(request)).toBe("203.0.113.7");
  });

  it("falls back to x-real-ip, then to a shared bucket", () => {
    expect(clientId(new Request("http://localhost", { headers: { "x-real-ip": "198.51.100.4" } }))).toBe(
      "198.51.100.4",
    );
    expect(clientId(new Request("http://localhost"))).toBe("unknown");
  });
});

describe("allow", () => {
  beforeEach(reset);

  it("permits the configured number of questions per hour", () => {
    vi.stubEnv("RATE_LIMIT_PER_HOUR", "2");
    expect(allow("a")).toBe(true);
    expect(allow("a")).toBe(true);
    expect(allow("a")).toBe(false);
  });

  it("counts each client separately", () => {
    vi.stubEnv("RATE_LIMIT_PER_HOUR", "1");
    expect(allow("a")).toBe(true);
    expect(allow("b")).toBe(true);
    expect(allow("a")).toBe(false);
  });

  it("forgets hits older than the window", () => {
    vi.stubEnv("RATE_LIMIT_PER_HOUR", "1");
    const start = Date.now();
    expect(allow("a", start)).toBe(true);
    expect(allow("a", start + 59 * 60 * 1000)).toBe(false);
    expect(allow("a", start + 61 * 60 * 1000)).toBe(true);
  });

  it("falls back to the default when the limit is unset or invalid", () => {
    vi.stubEnv("RATE_LIMIT_PER_HOUR", "not a number");
    for (let i = 0; i < 5; i++) expect(allow("a")).toBe(true);
    expect(allow("a")).toBe(false);
  });
});
