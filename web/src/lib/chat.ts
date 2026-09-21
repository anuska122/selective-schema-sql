import type { AskResponse } from "./types";

export type Message =
  | { id: string; role: "user"; text: string; dbId: string }
  | { id: string; role: "assistant"; status: "pending" }
  | { id: string; role: "assistant"; status: "done"; answer: AskResponse }
  | { id: string; role: "assistant"; status: "error"; error: string };

export type Conversation = { id: string; title: string; messages: Message[]; updatedAt: number };

const TITLE_LENGTH = 48;
const STORAGE_KEY = "sqlagent.conversations";
const MAX_STORED = 30;

let counter = 0;
export function newId(): string {
  counter += 1;
  return `${Date.now().toString(36)}-${counter}`;
}

export function titleFrom(question: string): string {
  const text = question.trim().replace(/\s+/g, " ");
  return text.length > TITLE_LENGTH ? `${text.slice(0, TITLE_LENGTH - 1)}…` : text;
}

export function startTurn(conversation: Conversation | null, question: string, dbId: string, now = Date.now()) {
  const pendingId = newId();
  const base = conversation ?? { id: newId(), title: titleFrom(question), messages: [], updatedAt: now };
  const next: Conversation = {
    ...base,
    updatedAt: now,
    messages: [
      ...base.messages,
      { id: newId(), role: "user", text: question, dbId },
      { id: pendingId, role: "assistant", status: "pending" },
    ],
  };
  return { conversation: next, pendingId };
}

export function finishTurn(conversation: Conversation, pendingId: string, result: AskResponse | Error): Conversation {
  const resolved: Message =
    result instanceof Error
      ? { id: pendingId, role: "assistant", status: "error", error: result.message }
      : { id: pendingId, role: "assistant", status: "done", answer: result };
  return { ...conversation, messages: conversation.messages.map((m) => (m.id === pendingId ? resolved : m)) };
}

export function upsert(conversations: Conversation[], conversation: Conversation): Conversation[] {
  return [conversation, ...conversations.filter((c) => c.id !== conversation.id)].sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );
}

export function loadConversations(storage: Storage | undefined = globalThis.localStorage): Conversation[] {
  try {
    const parsed = JSON.parse(storage?.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveConversations(conversations: Conversation[], storage: Storage | undefined = globalThis.localStorage) {
  try {
    const settled = conversations
      .map((c) => ({ ...c, messages: c.messages.filter((m) => !(m.role === "assistant" && m.status === "pending")) }))
      .slice(0, MAX_STORED);
    storage?.setItem(STORAGE_KEY, JSON.stringify(settled));
  } catch {
    // storage full or unavailable: history just isn't kept
  }
}
