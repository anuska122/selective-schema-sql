import { describe, expect, it, vi } from "vitest";
import { getHistory, getServerHistory, setHistory, subscribeHistory } from "./historyStore";

describe("history store", () => {
  it("notifies subscribers and persists changes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeHistory(listener);
    const conversation = { id: "c", title: "t", messages: [], updatedAt: 1 };
    setHistory([conversation]);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(getHistory()).toEqual([conversation]);
    expect(JSON.parse(localStorage.getItem("sqlagent.conversations")!)).toHaveLength(1);
    unsubscribe();
    setHistory([]);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(getServerHistory()).toEqual([]);
  });
});
