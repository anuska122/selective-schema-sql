import { describe, expect, it } from "vitest";
import { formatSql, highlightSql } from "./sqlHighlight";

describe("highlightSql", () => {
  it("classifies keywords, functions, strings, numbers and operators", () => {
    const kinds = highlightSql("SELECT COUNT(*) FROM t WHERE c = 'Blue' AND n >= 2")
      .filter((t) => t.text.trim())
      .map((t) => `${t.kind}:${t.text}`);
    expect(kinds).toEqual([
      "keyword:SELECT",
      "function:COUNT",
      "text:(",
      "operator:*",
      "text:)",
      "keyword:FROM",
      "text:t",
      "keyword:WHERE",
      "text:c",
      "operator:=",
      "string:'Blue'",
      "keyword:AND",
      "text:n",
      "operator:>=",
      "number:2",
    ]);
  });

  it("keeps escaped quotes inside one string and loses no characters", () => {
    const sql = "SELECT 'it''s' , x\n  FROM y";
    const tokens = highlightSql(sql);
    expect(tokens.find((t) => t.kind === "string")?.text).toBe("'it''s'");
    expect(tokens.map((t) => t.text).join("")).toBe(sql);
  });
});


describe("formatSql", () => {
  it("puts each clause and join on its own line", () => {
    const sql = "SELECT COUNT(*) FROM superhero s LEFT JOIN colour c ON s.id = c.id JOIN x ON TRUE WHERE c.colour = 'Blue' ORDER BY 1 LIMIT 5";
    expect(formatSql(sql).split("\n")).toEqual([
      "SELECT COUNT(*)",
      "FROM superhero s",
      "LEFT JOIN colour c ON s.id = c.id",
      "JOIN x ON TRUE",
      "WHERE c.colour = 'Blue'",
      "ORDER BY 1",
      "LIMIT 5",
    ]);
  });

  it("never breaks inside strings and leaves formatted SQL alone", () => {
    expect(formatSql("SELECT 'from where' FROM t")).toBe("SELECT 'from where'\nFROM t");
    expect(formatSql("SELECT 1\n  FROM t")).toBe("SELECT 1\n  FROM t");
  });
});
