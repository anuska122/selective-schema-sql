import { describe, expect, it } from "vitest";
import { finishTurn, loadConversations, saveConversations, startTurn, titleFrom, upsert } from "./chat";
import type { AskResponse } from "./types";

const ANSWER = { sql: "SELECT 1", rows: [["1"]] } as unknown as AskResponse;

class MemoryStorage {
  data: Record<string, string> = {};
  getItem(key: string) {
    return this.data[key] ?? null;
  }
  setItem(key: string, value: string) {
    this.data[key] = value;
  }
}

describe("chat state", () => {
  it("titles a conversation from its first question", () => {
    expect(titleFrom("  How many   heroes? ")).toBe("How many heroes?");
    expect(titleFrom("x".repeat(80))).toHaveLength(48);
  });

  it("adds a user message and a pending reply, then resolves it", () => {
    const { conversation, pendingId } = startTurn(null, "How many?", "superhero", 1);
    expect(conversation.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(conversation.title).toBe("How many?");

    const done = finishTurn(conversation, pendingId, ANSWER);
    const reply = done.messages[1];
    expect(reply.role === "assistant" && reply.status).toBe("done");

    const failed = finishTurn(conversation, pendingId, new Error("out of quota"));
    const errorReply = failed.messages[1];
    expect(errorReply.role === "assistant" && errorReply.status === "error" && errorReply.error).toBe("out of quota");
  });

  it("keeps follow-up questions in the same conversation", () => {
    const first = startTurn(null, "one", "", 1).conversation;
    const second = startTurn(first, "two", "", 2).conversation;
    expect(second.id).toBe(first.id);
    expect(second.messages).toHaveLength(4);
    expect(second.title).toBe("one");
  });

  it("orders history newest first without duplicates", () => {
    const a = { id: "a", title: "a", messages: [], updatedAt: 1 };
    const b = { id: "b", title: "b", messages: [], updatedAt: 2 };
    expect(upsert(upsert([], a), b).map((c) => c.id)).toEqual(["b", "a"]);
    expect(upsert([b, a], { ...a, updatedAt: 3 }).map((c) => c.id)).toEqual(["a", "b"]);
  });

  it("saves history without pending replies and survives bad storage", () => {
    const storage = new MemoryStorage() as unknown as Storage;
    const { conversation } = startTurn(null, "q", "", 1);
    saveConversations([conversation], storage);
    expect(loadConversations(storage)[0].messages.map((m) => m.role)).toEqual(["user"]);
    (storage as unknown as MemoryStorage).data["sqlagent.conversations"] = "not json";
    expect(loadConversations(storage)).toEqual([]);
  });
});
