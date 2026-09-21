import { formatSql, highlightSql, type SqlToken } from "@/lib/sqlHighlight";
import { CopyButton } from "./CopyButton";

const COLORS: Record<SqlToken["kind"], string> = {
  keyword: "text-[#d19a66] font-semibold",
  function: "text-[#61afef]",
  string: "text-[#98c379]",
  number: "text-[#e5c07b]",
  operator: "text-[#c678dd]",
  text: "text-stone-200",
};

export function SqlView({ sql }: { sql: string | null }) {
  if (!sql) return <p className="text-sm text-stone-500">No SQL was produced.</p>;
  const pretty = formatSql(sql);
  return (
    <div className="overflow-hidden rounded-xl bg-[#1f1e1d] ring-1 ring-stone-800">
      <div className="flex items-center justify-between border-b border-stone-800 px-4 py-1.5">
        <span className="font-mono text-xs text-stone-400">sql</span>
        <CopyButton text={pretty} />
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words p-4 font-mono text-[13px] leading-relaxed">
        <code>
          {highlightSql(pretty).map((token, i) => (
            <span key={i} className={COLORS[token.kind]}>
              {token.text}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}
