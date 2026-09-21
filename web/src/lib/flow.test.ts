import { describe, expect, it } from "vitest";
import { joinLabel, resultSummary, usedJoins } from "./flow";
import type { AskResponse, Join } from "./types";

const EYE: Join = { from: "superhero", from_columns: ["eye_colour_id"], to: "colour", to_columns: ["id"], inferred: false };
const HAIR: Join = { ...EYE, from_columns: ["hair_colour_id"] };

function answer(details: AskResponse["details"], extra: Partial<AskResponse> = {}): AskResponse {
  return { question: "", sql: "", columns: ["count"], rows: [["234"]], truncated: false, error: null, stages: [], details, ...extra };
}

describe("flow", () => {
  it("keeps the join the query used when several keys link two tables", () => {
    const joins = usedJoins(answer({ joins: [HAIR, EYE], columns: { superhero: ["eye_colour_id"], colour: ["id", "colour"] } }));
    expect(joins).toEqual([EYE]);
  });

  it("falls back to the first key when the query's columns are unknown", () => {
    expect(usedJoins(answer({ joins: [HAIR, EYE] }))).toEqual([HAIR]);
    expect(usedJoins(answer({}))).toEqual([]);
  });

  it("labels joins, including composite keys", () => {
    expect(joinLabel(EYE)).toBe("superhero.eye_colour_id = colour.id");
    expect(joinLabel({ ...EYE, from_columns: ["a", "b"], to_columns: ["x", "y"] })).toBe(
      "superhero.a = colour.x and superhero.b = colour.y",
    );
  });

  it("summarises single values, row sets and failures", () => {
    expect(resultSummary(answer({}))).toEqual({ headline: "234", caption: "count" });
    expect(resultSummary(answer({}, { columns: ["a", "b"], rows: [["1", "2"], ["3", "4"]], truncated: true }))).toEqual({
      headline: "2+",
      caption: "rows · a, b",
    });
    expect(resultSummary(answer({}, { error: "boom" })).headline).toBe("No result");
  });
});
