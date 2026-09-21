import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AskResponse } from "@/lib/types";
import { AnswerView } from "./AnswerView";
import { AskForm } from "./AskForm";
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
  details: { selected: ["colour", "superhero"] },
};

describe("AskForm", () => {
  it("submits the trimmed question with the chosen database", async () => {
    const onAsk = vi.fn();
    render(<AskForm databases={[{ db_id: "superhero", tables: ["colour"] }]} busy={false} onAsk={onAsk} />);
    await userEvent.type(screen.getByLabelText("Question"), "  blue eyes?  ");
    await userEvent.selectOptions(screen.getByLabelText("Database"), "superhero");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(onAsk).toHaveBeenCalledWith("blue eyes?", "superhero");
  });

  it("disables the button while busy or empty", () => {
    const { rerender } = render(<AskForm databases={[]} busy={false} onAsk={vi.fn()} />);
    expect(screen.getByRole("button")).toBeDisabled();
    rerender(<AskForm databases={[]} busy onAsk={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
  });
});

describe("ResultsTable", () => {
  it("says when there are no rows", () => {
    render(<ResultsTable columns={["a"]} rows={[]} truncated={false} />);
    expect(screen.getByText("The query returned no rows.")).toBeInTheDocument();
  });

  it("notes truncation", () => {
    render(<ResultsTable columns={["a"]} rows={[["1"]]} truncated />);
    expect(screen.getByText("Showing the first 1 rows.")).toBeInTheDocument();
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

describe("AnswerView", () => {
  it("shows SQL, rows and chosen tables", () => {
    render(<AnswerView answer={ANSWER} />);
    expect(screen.getByText("SELECT colour FROM colour")).toBeInTheDocument();
    expect(screen.getByText("Blue")).toBeInTheDocument();
    expect(screen.getByText("superhero")).toBeInTheDocument();
  });

  it("shows the error instead of a result table", () => {
    render(<AnswerView answer={{ ...ANSWER, error: "db_error: boom", sql: null }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("db_error: boom");
    expect(screen.getByText("No SQL was produced.")).toBeInTheDocument();
    expect(screen.queryByText("Blue")).not.toBeInTheDocument();
  });
});
