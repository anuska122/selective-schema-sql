import { type Conversation, loadConversations, saveConversations } from "./chat";

const EMPTY: Conversation[] = [];
const listeners = new Set<() => void>();
let cache: Conversation[] | null = null;

export function getHistory(): Conversation[] {
  if (cache === null) cache = loadConversations();
  return cache;
}

export function getServerHistory(): Conversation[] {
  return EMPTY;
}

export function setHistory(next: Conversation[]): void {
  cache = next;
  saveConversations(next);
  listeners.forEach((listener) => listener());
}

export function subscribeHistory(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
