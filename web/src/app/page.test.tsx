import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "./page";
import { ask, listDatabases } from "@/lib/api";
import { setHistory } from "@/lib/historyStore";

vi.mock("@/lib/api", () => ({ ask: vi.fn(), listDatabases: vi.fn() }));

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: vi.fn() });
  setHistory([]);
  vi.mocked(listDatabases).mockResolvedValue([{ db_id: "financial", tables: ["account"] }]);
});

describe("question navigation", () => {
  it("opens mobile navigation, changes database, and closes with Escape", async () => {
    render(<Home />);
    const menu = screen.getByRole("button", { name: "Open navigation" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveFocus();
    await screen.findByRole("option", { name: "Financial" });
    await userEvent.selectOptions(screen.getByLabelText("Database"), "financial");
    await userEvent.keyboard("{Escape}");
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveFocus();
    expect(screen.getByLabelText("Database")).toHaveValue("financial");
  });

  it("opens a saved question with its original database", async () => {
    setHistory([{ id: "saved", title: "Saved question", updatedAt: 1, messages: [
      { id: "q", role: "user", text: "Which accounts?", dbId: "financial" },
    ] }]);
    render(<Home />);
    await screen.findByRole("option", { name: "Financial" });
    await userEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    await userEvent.click(screen.getByRole("button", { name: "Saved question" }));
    expect(screen.getByText("Which accounts?")).toBeInTheDocument();
    expect(screen.getByLabelText("Database")).toHaveValue("financial");
    expect(screen.getByRole("button", { name: "Open navigation" })).toHaveAttribute("aria-expanded", "false");
  });

  it("closes navigation using its close button and backdrop", async () => {
    render(<Home />);
    const menu = screen.getByRole("button", { name: "Open navigation" });
    await userEvent.click(menu);
    await userEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(menu).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(menu);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss navigation" }));
    await waitFor(() => expect(menu).toHaveAttribute("aria-expanded", "false"));
  });
});


describe("request recovery", () => {
  it("shows database-loading errors and retries", async () => {
    vi.mocked(listDatabases).mockRejectedValueOnce(new Error("service unavailable"));
    render(<Home />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the database list");
    await userEvent.click(screen.getByRole("button", { name: "Retry database list" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(screen.getByRole("option", { name: "Financial" })).toBeInTheDocument();
  });

  it("cancels a pending request and restores the composer", async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(ask).mockImplementationOnce((_question, _db, requestSignal) => {
      signal = requestSignal;
      return new Promise((_resolve, reject) => {
        requestSignal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      });
    });
    render(<Home />);
    await userEvent.type(screen.getByLabelText("Question"), "How many accounts?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel request" }));
    expect(signal?.aborted).toBe(true);
    expect(await screen.findByRole("alert")).toHaveTextContent("Request cancelled");
    expect(screen.queryByRole("button", { name: "Cancel request" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Question"), "Try again");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });
});
