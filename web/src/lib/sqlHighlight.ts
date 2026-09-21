export type SqlToken = { kind: "keyword" | "function" | "string" | "number" | "operator" | "text"; text: string };

const KEYWORDS = new Set(
  (
    "select from where join inner left right full outer cross on and or not in is null as group by order " +
    "having limit offset distinct case when then else end with union all like ilike between exists asc desc " +
    "cast true false"
  ).split(" "),
);
const FUNCTIONS = new Set("count sum avg min max round coalesce nullif lower upper substring extract strftime length".split(" "));
const TOKEN = /('(?:[^']|'')*')|(\d+(?:\.\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|(<=|>=|<>|!=|[=<>*+\-/%])|(\s+|.)/g;

export function highlightSql(sql: string): SqlToken[] {
  const tokens: SqlToken[] = [];
  for (const match of sql.matchAll(TOKEN)) {
    const [text, string, number, word, operator] = match;
    if (string) tokens.push({ kind: "string", text });
    else if (number) tokens.push({ kind: "number", text });
    else if (word && KEYWORDS.has(word.toLowerCase())) tokens.push({ kind: "keyword", text });
    else if (word && FUNCTIONS.has(word.toLowerCase())) tokens.push({ kind: "function", text });
    else if (operator) tokens.push({ kind: "operator", text });
    else tokens.push({ kind: "text", text });
  }
  return tokens;
}

const CLAUSES = new Set(["from", "where", "group", "order", "having", "limit", "union"]);
const JOIN_STARTERS = new Set(["left", "right", "inner", "full", "cross"]);

export function formatSql(sql: string): string {
  if (sql.includes("\n")) return sql;
  const tokens = highlightSql(sql);
  const out: string[] = [];
  tokens.forEach((token, i) => {
    const word = token.kind === "keyword" ? token.text.toLowerCase() : "";
    const previousWord = tokens
      .slice(0, i)
      .reverse()
      .find((t) => t.text.trim())
      ?.text.toLowerCase();
    const startsJoin = JOIN_STARTERS.has(word) || (word === "join" && !JOIN_STARTERS.has(previousWord ?? ""));
    const breakHere = (CLAUSES.has(word) || startsJoin) && i > 0 && !tokens[i - 1].text.trim();
    if (breakHere) {
      out.pop();
      out.push("\n");
    }
    out.push(token.text);
  });
  return out.join("");
}
