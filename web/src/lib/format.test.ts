import { describe, expect, it } from "vitest";
import { databaseName } from "./format";

describe("databaseName", () => {
  it("reads naturally", () => {
    expect(databaseName("")).toBe("All tables");
    expect(databaseName("california_schools")).toBe("California schools");
    expect(databaseName("formula_1")).toBe("Formula 1");
  });
});
