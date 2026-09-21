"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { Composer } from "@/components/chat/Composer";
import { EmptyState } from "@/components/chat/EmptyState";
import { Mark } from "@/components/chat/Mark";
import { AssistantMessage, UserMessage } from "@/components/chat/Messages";
import { ask, listDatabases } from "@/lib/api";
import { databaseName } from "@/lib/format";
import { type Conversation, finishTurn, startTurn, upsert } from "@/lib/chat";
import { getHistory, getServerHistory, setHistory, subscribeHistory } from "@/lib/historyStore";
import type { Database } from "@/lib/types";

const noopSubscribe = () => () => {};
const currentHour = () => new Date().getHours();

export default function Home() {
  const [databases, setDatabases] = useState<Database[]>([]);
  const conversations = useSyncExternalStore(subscribeHistory, getHistory, getServerHistory);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [dbId, setDbId] = useState("");
  const [busy, setBusy] = useState(false);
  const hour = useSyncExternalStore(noopSubscribe, currentHour, () => 12);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listDatabases()
      .then(setDatabases)
      .catch(() => setDatabases([]));
  }, []);

  const active = useMemo(() => conversations.find((c) => c.id === activeId) ?? null, [conversations, activeId]);
  const messages = active?.messages ?? [];

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, busy]);

  function commit(conversation: Conversation) {
    setHistory(upsert(getHistory(), conversation));
  }

  async function send(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    const { conversation, pendingId } = startTurn(active, text, dbId);
    setActiveId(conversation.id);
    setDraft("");
    setBusy(true);
    commit(conversation);
    let result;
    try {
      result = await ask(text, dbId);
    } catch (e) {
      result = e as Error;
    }
    commit(finishTurn(conversation, pendingId, result));
    setBusy(false);
  }

  const dbLabel = databaseName(dbId);
  const composer = (
    <Composer value={draft} onChange={setDraft} onSend={() => send(draft)} busy={busy} dbLabel={dbLabel} autoFocus />
  );

  return (
    <div className="flex h-screen">
      <ChatSidebar
        conversations={conversations}
        activeId={activeId}
        databases={databases}
        dbId={dbId}
        onNew={() => {
          setActiveId(null);
          setDraft("");
        }}
        onOpen={setActiveId}
        onDbChange={setDbId}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-stone-200 px-4 py-3 md:hidden dark:border-stone-800">
          <Mark className="size-6" />
          <span className="font-serif text-stone-800 dark:text-stone-100">Ask your database</span>
          <button type="button" onClick={() => setActiveId(null)} className="ml-auto text-sm text-accent-600">
            New
          </button>
        </div>

        {messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10">
            <div className="flex w-full max-w-2xl flex-col gap-8">
              <EmptyState hour={hour} onPick={send} />
              {composer}
            </div>
          </div>
        ) : (
          <>
            <div ref={scroller} className="flex-1 overflow-y-auto">
              <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-10">
                {messages.map((m) =>
                  m.role === "user" ? <UserMessage key={m.id} text={m.text} /> : <AssistantMessage key={m.id} message={m} />,
                )}
              </div>
            </div>
            <div className="mx-auto w-full max-w-3xl px-4 pb-4">
              {composer}
              <p className="mt-2 text-center text-xs text-stone-400">
                Answers come from generated SQL and can be wrong. Check the SQL for anything important.
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
