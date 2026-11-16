"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
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
  const [databaseError, setDatabaseError] = useState(false);
  const requestController = useRef<AbortController | null>(null);
  const conversations = useSyncExternalStore(subscribeHistory, getHistory, getServerHistory);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [dbId, setDbId] = useState("");
  const [busy, setBusy] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const hour = useSyncExternalStore(noopSubscribe, currentHour, () => 12);
  const scroller = useRef<HTMLDivElement>(null);

  function closeNavigation() {
    setMobileOpen(false);
    menuButton.current?.focus();
  }

  useEffect(() => {
    if (!mobileOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  const loadDatabases = useCallback(() => {
    listDatabases()
      .then((items) => {
        setDatabases(items);
        setDatabaseError(false);
      })
      .catch(() => {
        setDatabases([]);
        setDatabaseError(true);
      });
  }, []);

  useEffect(() => { loadDatabases(); }, [loadDatabases]);
  useEffect(() => () => requestController.current?.abort(), []);

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
    const controller = new AbortController();
    requestController.current = controller;
    commit(conversation);
    let result;
    try {
      result = await ask(text, dbId, controller.signal);
    } catch (e) {
      result = e as Error;
    }
    if (controller.signal.aborted) result = new Error("Request cancelled. The server may still finish processing it.");
    commit(finishTurn(conversation, pendingId, result));
    requestController.current = null;
    setBusy(false);
  }

  const dbLabel = databaseName(dbId);
  const composer = (
    <Composer value={draft} onChange={setDraft} onSend={() => send(draft)} onCancel={() => requestController.current?.abort()} busy={busy} dbLabel={dbLabel} autoFocus />
  );

  return (
    <div className="flex h-screen">
      {mobileOpen && (
        <button type="button" aria-label="Dismiss navigation" onClick={closeNavigation} className="fixed inset-0 z-30 bg-black/30 md:hidden" />
      )}
      <ChatSidebar
        conversations={conversations}
        activeId={activeId}
        databases={databases}
        dbId={dbId}
        mobileOpen={mobileOpen}
        onClose={closeNavigation}
        onNew={() => {
          setActiveId(null);
          setDraft("");
          closeNavigation();
        }}
        onOpen={(id) => {
          setActiveId(id);
          const conversation = conversations.find((c) => c.id === id);
          const lastQuestion = conversation?.messages.findLast((m) => m.role === "user");
          if (lastQuestion?.role === "user") setDbId(lastQuestion.dbId);
          closeNavigation();
        }}
        onDbChange={setDbId}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {databaseError && (
          <div role="alert" className="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Could not load the database list. Check the query service and try again.
            <button type="button" onClick={loadDatabases} className="ml-2 underline">Retry database list</button>
          </div>
        )}
        <div className="flex items-center gap-2 border-b border-stone-200 px-4 py-3 md:hidden dark:border-stone-800">
          <button
            ref={menuButton} type="button" aria-label="Open navigation"
            aria-controls="chat-navigation" aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(true)} className="rounded px-2 py-1"
          >
            ☰
          </button>
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
