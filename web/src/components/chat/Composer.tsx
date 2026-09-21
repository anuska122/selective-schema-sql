"use client";

import { useEffect, useRef } from "react";

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  busy: boolean;
  dbLabel: string;
  autoFocus?: boolean;
};

const MAX_HEIGHT = 220;

export function Composer({ value, onChange, onSend, busy, dbLabel, autoFocus }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !busy;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend();
      }}
      className="rounded-2xl border border-stone-300 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.04)] transition focus-within:border-stone-400 focus-within:shadow-[0_4px_20px_rgba(0,0,0,0.07)] dark:border-stone-700 dark:bg-[#30302e] dark:focus-within:border-stone-500"
    >
      <label htmlFor="question" className="sr-only">
        Question
      </label>
      <textarea
        id="question"
        ref={ref}
        value={value}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            if (canSend) onSend();
          }
        }}
        maxLength={2000}
        rows={1}
        placeholder="Ask a question about your data…"
        className="block max-h-[220px] w-full resize-none bg-transparent px-4 pt-4 text-[15px] leading-relaxed text-stone-800 placeholder:text-stone-400 focus:outline-none dark:text-stone-100"
      />
      <div className="flex items-center gap-2 px-3 pb-3 pt-2">
        <span className="rounded-md border border-stone-200 px-2 py-0.5 text-xs text-stone-500 dark:border-stone-700 dark:text-stone-400">
          {dbLabel}
        </span>
        <button
          type="submit"
          aria-label="Send"
          disabled={!canSend}
          className="ml-auto grid size-8 place-items-center rounded-lg bg-accent-600 text-white transition hover:bg-accent-700 disabled:cursor-not-allowed disabled:bg-stone-300 dark:disabled:bg-stone-700"
        >
          {busy ? (
            <span className="size-3 rounded-[3px] bg-white" />
          ) : (
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          )}
        </button>
      </div>
    </form>
  );
}
