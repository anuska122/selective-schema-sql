"use client";

import { useEffect, useState } from "react";
import { AnswerView } from "@/components/AnswerView";
import { AskForm } from "@/components/AskForm";
import { ask, listDatabases } from "@/lib/api";
import type { AskResponse, Database } from "@/lib/types";

export default function Home() {
  const [databases, setDatabases] = useState<Database[]>([]);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listDatabases()
      .then(setDatabases)
      .catch((e: Error) => setError(e.message));
  }, []);

  async function handleAsk(question: string, dbId: string) {
    setBusy(true);
    setError(null);
    try {
      setAnswer(await ask(question, dbId));
    } catch (e) {
      setAnswer(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold">Ask your database</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Finds the relevant tables, writes the SQL and runs it read-only.
        </p>
      </header>
      <AskForm databases={databases} busy={busy} onAsk={handleAsk} />
      {error && (
        <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}
      {answer && <AnswerView answer={answer} />}
    </main>
  );
}
