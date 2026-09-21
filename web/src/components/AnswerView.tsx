import type { AskResponse } from "@/lib/types";
import { CopyButton } from "./CopyButton";
import { ResultsTable } from "./ResultsTable";
import { StageTimeline } from "./StageTimeline";

export function AnswerView({ answer }: { answer: AskResponse }) {
  const selected = answer.details.selected ?? [];
  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="mb-2 text-sm font-medium text-zinc-700">SQL</h2>
        <div className="relative">
          <pre className="overflow-x-auto rounded-md bg-zinc-900 p-4 pr-16 text-sm text-zinc-100">
            {answer.sql ?? "No SQL was produced."}
          </pre>
          {answer.sql && (
            <div className="absolute right-2 top-2">
              <CopyButton text={answer.sql} />
            </div>
          )}
        </div>
      </div>

      {answer.error ? (
        <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          {answer.error}
        </p>
      ) : (
        <div>
          <h2 className="mb-2 text-sm font-medium text-zinc-700">Result</h2>
          <ResultsTable columns={answer.columns} rows={answer.rows} truncated={answer.truncated} />
        </div>
      )}

      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <h2 className="mb-2 text-sm font-medium text-zinc-700">Tables used</h2>
          <ul className="flex flex-wrap gap-2">
            {selected.map((table) => (
              <li key={table} className="rounded bg-zinc-100 px-2 py-0.5 font-mono text-xs">
                {table}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="mb-2 text-sm font-medium text-zinc-700">Stages</h2>
          <StageTimeline stages={answer.stages} />
        </div>
      </div>
    </section>
  );
}
