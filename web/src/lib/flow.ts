import type { AskResponse, Join } from "./types";

export function usedJoins(answer: AskResponse): Join[] {
  const joins = answer.details.joins ?? [];
  const columns = answer.details.columns ?? {};
  const byPair = new Map<string, Join[]>();
  for (const join of joins) {
    const key = [join.from, join.to].sort().join("|");
    byPair.set(key, [...(byPair.get(key) ?? []), join]);
  }
  return [...byPair.values()].map((candidates) => {
    const inQuery = candidates.find(
      (j) =>
        j.from_columns.every((c) => columns[j.from]?.includes(c)) && j.to_columns.every((c) => columns[j.to]?.includes(c)),
    );
    return inQuery ?? candidates[0];
  });
}

export function joinLabel(join: Join): string {
  return join.from_columns.map((c, i) => `${join.from}.${c} = ${join.to}.${join.to_columns[i]}`).join(" and ");
}

export function resultSummary(answer: AskResponse): { headline: string; caption: string } {
  if (answer.error) return { headline: "No result", caption: "the query failed" };
  if (answer.rows.length === 1 && answer.columns.length === 1) {
    return { headline: answer.rows[0][0], caption: answer.columns[0] };
  }
  const count = `${answer.rows.length}${answer.truncated ? "+" : ""}`;
  return { headline: count, caption: `row${answer.rows.length === 1 ? "" : "s"} · ${answer.columns.join(", ")}` };
}
