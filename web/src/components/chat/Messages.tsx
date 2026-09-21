import type { Message } from "@/lib/chat";
import { ResultsTable } from "../ResultsTable";
import { SqlView } from "../SqlView";
import { formatMs, StageTimeline } from "../StageTimeline";
import { AnswerFlow } from "./AnswerFlow";
import { Disclosure } from "./Disclosure";
import { Mark } from "./Mark";
import { PendingSteps } from "./PendingSteps";

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex animate-rise justify-end">
      <p className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-[#f0eee6] px-4 py-2.5 text-[15px] leading-relaxed text-stone-800 dark:bg-[#1a1918] dark:text-stone-100">
        {text}
      </p>
    </div>
  );
}

export function AssistantMessage({ message }: { message: Extract<Message, { role: "assistant" }> }) {
  return (
    <div className="flex animate-rise gap-3.5">
      <Mark className="mt-0.5 size-7" />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        {message.status === "pending" && <PendingSteps />}
        {message.status === "error" && (
          <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            {message.error}
          </p>
        )}
        {message.status === "done" && <Answer message={message} />}
      </div>
    </div>
  );
}

function Answer({ message }: { message: Extract<Message, { status: "done" }> }) {
  const { answer } = message;
  const total = answer.stages.reduce((sum, s) => sum + s.latency_ms, 0);
  const tokens = answer.stages.reduce((sum, s) => sum + s.tokens_in + s.tokens_out, 0);
  const isTable = !answer.error && !(answer.rows.length === 1 && answer.columns.length === 1);
  return (
    <>
      <AnswerFlow answer={answer} />
      {answer.error && (
        <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {answer.error}
        </p>
      )}
      {isTable && <ResultsTable columns={answer.columns} rows={answer.rows} truncated={answer.truncated} />}
      <Disclosure label="SQL" meta={answer.details.validation === "ok" ? "checked before running" : undefined}>
        <SqlView sql={answer.sql} />
      </Disclosure>
      <Disclosure label="Timing" meta={`${formatMs(total)} · ${tokens} tokens`}>
        <StageTimeline stages={answer.stages} />
      </Disclosure>
    </>
  );
}
