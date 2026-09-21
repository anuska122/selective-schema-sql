"use client";

import { useState } from "react";
import type { Database } from "@/lib/types";

export const EXAMPLES = [
  "How many superheroes have blue eyes?",
  "What is the average AST level of patients?",
  "How many female clients are there?",
];

type Props = {
  databases: Database[];
  busy: boolean;
  onAsk: (question: string, dbId: string) => void;
};

export function AskForm({ databases, busy, onAsk }: Props) {
  const [question, setQuestion] = useState("");
  const [dbId, setDbId] = useState("");

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (question.trim()) onAsk(question.trim(), dbId);
      }}
    >
      <label htmlFor="question" className="text-sm font-medium text-zinc-700">
        Question
      </label>
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => setQuestion(example)}
            className="rounded-full border border-zinc-300 px-3 py-1 text-xs text-zinc-700 hover:bg-zinc-100"
          >
            {example}
          </button>
        ))}
      </div>
      <textarea
        id="question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        maxLength={2000}
        rows={3}
        placeholder="How many superheroes have blue eyes?"
        className="w-full rounded-md border border-zinc-300 p-3 text-base focus:border-zinc-900 focus:outline-none"
      />
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="database" className="text-sm text-zinc-700">
          Database
        </label>
        <select
          id="database"
          value={dbId}
          onChange={(event) => setDbId(event.target.value)}
          className="rounded-md border border-zinc-300 px-2 py-1.5 text-sm"
        >
          <option value="">All tables</option>
          {databases.map((db) => (
            <option key={db.db_id} value={db.db_id}>
              {db.db_id} ({db.tables.length})
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="ml-auto rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "Working…" : "Ask"}
        </button>
      </div>
    </form>
  );
}
