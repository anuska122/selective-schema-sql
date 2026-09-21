import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Message } from "@/lib/chat";
import type { AskResponse } from "@/lib/types";
import { ChatSidebar } from "./chat/ChatSidebar";
import { Composer } from "./chat/Composer";
import { Disclosure } from "./chat/Disclosure";
import { EmptyState, EXAMPLES, greeting } from "./chat/EmptyState";
import { AssistantMessage, UserMessage } from "./chat/Messages";
import { STEPS } from "./chat/PendingSteps";
import { ResultsTable } from "./ResultsTable";
import { formatMs, StageTimeline } from "./StageTimeline";

const STAGE = { llm_calls: 0, model: null, tokens_in: 0, tokens_out: 0, cached_tokens: 0, wait_ms: 0 };

const ANSWER: AskResponse = {
  question: "q",
  sql: "SELECT colour FROM colour",
  columns: ["colour"],
  rows: [["Blue"]],
  truncated: false,
  error: null,
  stages: [
    { ...STAGE, name: "retrieve", latency_ms: 500 },
    { ...STAGE, name: "generate", latency_ms: 1300, llm_calls: 1, tokens_in: 900, tokens_out: 100 },
  ],
  details: { selected: ["colour", "superhero"], validation: "ok" },
};

function done(answer: AskResponse = ANSWER): Extract<Message, { role: "assistant" }> {
  return { id: "a", role: "assistant", status: "done", answer };
}

function ControlledComposer({ onSend = vi.fn(), busy = false }: { onSend?: (q: string) => void; busy?: boolean }) {
  const [value, setValue] = useState("");
  return <Composer value={value} onChange={setValue} onSend={() => onSend(value)} busy={busy} dbLabel="All tables" />;
}

describe("Composer", () => {
  it("sends on Enter and keeps Shift+Enter for new lines", async () => {
    const onSend = vi.fn();
    render(<ControlledComposer onSend={onSend} />);
    const box = screen.getByLabelText("Question");
    await userEvent.type(box, "first line{Shift>}{Enter}{/Shift}second");
    expect(onSend).not.toHaveBeenCalled();
    expect(box).toHaveValue("first line\nsecond");
    await userEvent.type(box, "{Enter}");
    expect(onSend).toHaveBeenCalledWith("first line\nsecond");
  });

  it("cannot send when empty or busy", async () => {
    const onSend = vi.fn();
    const { rerender } = render(<ControlledComposer onSend={onSend} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Question"), "hi");
    rerender(<ControlledComposer onSend={onSend} busy />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Question"), "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });
});

describe("EmptyState", () => {
  it("greets by time of day", () => {
    expect(greeting(8)).toBe("Good morning");
    expect(greeting(14)).toBe("Good afternoon");
    expect(greeting(21)).toBe("Good evening");
  });

  it("sends an example when picked", async () => {
    const onPick = vi.fn();
    render(<EmptyState hour={9} onPick={onPick} />);
    expect(screen.getByRole("heading", { name: "Good morning" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: EXAMPLES[0] }));
    expect(onPick).toHaveBeenCalledWith(EXAMPLES[0]);
  });
});

describe("ChatSidebar", () => {
  it("starts a new question, opens history and changes database", async () => {
    const onNew = vi.fn();
    const onOpen = vi.fn();
    const onDbChange = vi.fn();
    render(
      <ChatSidebar
        conversations={[{ id: "c1", title: "Blue eyes?", messages: [], updatedAt: 1 }]}
        activeId="c1"
        databases={[{ db_id: "superhero", tables: ["colour"] }]}
        dbId=""
        onNew={onNew}
        onOpen={onOpen}
        onDbChange={onDbChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /New question/ }));
    expect(onNew).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Blue eyes?" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("button", { name: "Blue eyes?" }));
    expect(onOpen).toHaveBeenCalledWith("c1");
    await userEvent.selectOptions(screen.getByLabelText("Database"), "superhero");
    expect(onDbChange).toHaveBeenCalledWith("superhero");
  });

  it("says when there is no history", () => {
    render(
      <ChatSidebar conversations={[]} activeId={null} databases={[]} dbId="" onNew={vi.fn()} onOpen={vi.fn()} onDbChange={vi.fn()} />,
    );
    expect(screen.getByText("No questions yet")).toBeInTheDocument();
  });
});

describe("Messages", () => {
  it("shows the user's question", () => {
    render(<UserMessage text="How many?" />);
    expect(screen.getByText("How many?")).toBeInTheDocument();
  });

  it("shows live steps while pending", async () => {
    vi.useFakeTimers();
    render(<AssistantMessage message={{ id: "p", role: "assistant", status: "pending" }} />);
    expect(screen.getByRole("status")).toHaveTextContent(STEPS[0]);
    await act(async () => {
      vi.advanceTimersByTime(700 * 5);
    });
    expect(screen.getByRole("status")).toHaveTextContent(STEPS[STEPS.length - 1]);
    vi.useRealTimers();
  });

  it("shows the answer with SQL and trace behind disclosures", async () => {
    const { container } = render(<AssistantMessage message={done()} />);
    expect(screen.getByText("Blue")).toBeInTheDocument();
    const sqlToggle = screen.getByRole("button", { name: /SQL/ });
    expect(sqlToggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(sqlToggle);
    expect(sqlToggle).toHaveAttribute("aria-expanded", "true");
    expect(container.querySelector("code")?.textContent).toBe("SELECT colour\nFROM colour");
    expect(screen.getByText("checked before running")).toBeInTheDocument();
    expect(screen.getByText("1.8s · 2 tables")).toBeInTheDocument();
    expect(screen.getByText("superhero")).toBeInTheDocument();
  });

  it("shows execution errors and request errors", () => {
    render(<AssistantMessage message={done({ ...ANSWER, error: "db_error: boom" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("db_error: boom");
    render(<AssistantMessage message={{ id: "e", role: "assistant", status: "error", error: "out of quota" }} />);
    expect(screen.getAllByRole("alert")[1]).toHaveTextContent("out of quota");
  });
});

describe("Disclosure", () => {
  it("toggles its content", async () => {
    render(
      <Disclosure label="Details" meta="3 items">
        <p>inside</p>
      </Disclosure>,
    );
    const toggle = screen.getByRole("button", { name: /Details/ });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("3 items")).toBeInTheDocument();
  });
});

describe("ResultsTable", () => {
  it("says when there are no rows", () => {
    render(<ResultsTable columns={["a"]} rows={[]} truncated={false} />);
    expect(screen.getByText("The query returned no rows.")).toBeInTheDocument();
  });

  it("notes truncation", () => {
    render(<ResultsTable columns={["a"]} rows={[["1"], ["2"]]} truncated />);
    expect(screen.getByText("Showing the first 2 rows.")).toBeInTheDocument();
  });

  it("shows a single value as a headline number", () => {
    render(<ResultsTable columns={["count"]} rows={[["234"]]} truncated={false} />);
    expect(screen.getByText("234")).toHaveClass("text-6xl");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("StageTimeline", () => {
  it("formats durations", () => {
    expect(formatMs(42.4)).toBe("42ms");
    expect(formatMs(1300)).toBe("1.3s");
  });

  it("totals latency and tokens", () => {
    render(<StageTimeline stages={ANSWER.stages} />);
    expect(screen.getByText("1.8s · 1000 tokens")).toBeInTheDocument();
    expect(screen.getByText("500ms")).toBeInTheDocument();
  });
});
