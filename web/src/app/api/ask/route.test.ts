import { describe, expect, it, vi } from "vitest";
import { POST } from "./route";

function post(body: unknown) {
  return POST(new Request("http://localhost/api/ask", { method: "POST", body: JSON.stringify(body) }));
}

describe("POST /api/ask", () => {
  it("rejects empty and oversized questions without calling the backend", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    expect((await post({ question: "   " })).status).toBe(400);
    expect((await post({ question: "x".repeat(2001) })).status).toBe(400);
    expect((await post("not an object")).status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards a trimmed question and database to the backend", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ sql: "SELECT 1" }));
    const response = await post({ question: "  how many?  ", db_id: "financial", extra: "ignored" });
    expect(response.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/ask");
    expect(JSON.parse(init!.body as string)).toEqual({ question: "how many?", db_id: "financial" });
  });
});
