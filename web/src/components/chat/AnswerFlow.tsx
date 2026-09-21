"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { joinLabel, resultSummary, usedJoins } from "@/lib/flow";
import type { AskResponse } from "@/lib/types";

export const PHASE_MS = [0, 800, 1500, 2200, 2900];
const CANDIDATE_LIMIT = 10;

type Line = { x1: number; y1: number; x2: number; y2: number };

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function edgePoint(from: DOMRect, to: DOMRect, origin: DOMRect) {
  const horizontal = Math.abs(to.left + to.width / 2 - (from.left + from.width / 2)) > Math.abs(to.top - from.top);
  if (horizontal) {
    const right = to.left > from.left;
    return { x: (right ? from.right : from.left) - origin.left, y: from.top + from.height / 2 - origin.top };
  }
  const down = to.top > from.top;
  return { x: from.left + from.width / 2 - origin.left, y: (down ? from.bottom : from.top) - origin.top };
}

export function AnswerFlow({ answer }: { answer: AskResponse }) {
  const [phase, setPhase] = useState(0);
  const [run, setRun] = useState(0);
  const [lines, setLines] = useState<Line[]>([]);
  const board = useRef<HTMLDivElement>(null);
  const cards = useRef(new Map<string, HTMLDivElement>());

  const selected = answer.details.selected ?? [];
  const candidates = [...new Set([...(answer.details.candidates ?? []).slice(0, CANDIDATE_LIMIT), ...selected])];
  const joins = useMemo(() => usedJoins(answer), [answer]);
  const columns = answer.details.columns ?? {};
  const result = resultSummary(answer);
  const joinColumns = new Set(joins.flatMap((j) => [...j.from_columns.map((c) => `${j.from}.${c}`), ...j.to_columns.map((c) => `${j.to}.${c}`)]));

  useEffect(() => {
    if (prefersReducedMotion()) {
      const id = setTimeout(() => setPhase(PHASE_MS.length - 1), 0);
      return () => clearTimeout(id);
    }
    const timers = PHASE_MS.map((ms, i) => setTimeout(() => setPhase(i), ms));
    return () => timers.forEach(clearTimeout);
  }, [run]);

  const measure = useCallback(() => {
    const origin = board.current?.getBoundingClientRect();
    if (!origin) return;
    setLines(
      joins.flatMap((join) => {
        const a = cards.current.get(join.from)?.getBoundingClientRect();
        const b = cards.current.get(join.to)?.getBoundingClientRect();
        if (!a || !b) return [];
        const start = edgePoint(a, b, origin);
        const end = edgePoint(b, a, origin);
        return [{ x1: start.x, y1: start.y, x2: end.x, y2: end.y }];
      }),
    );
  }, [joins]);

  useLayoutEffect(() => {
    if (phase < 2) return;
    measure();
    if (typeof ResizeObserver === "undefined" || !board.current) return;
    const observer = new ResizeObserver(measure);
    observer.observe(board.current);
    return () => observer.disconnect();
  }, [phase, measure]);

  return (
    <figure className="rounded-2xl border border-stone-200 bg-white/70 p-5 dark:border-stone-700/80 dark:bg-stone-800/30">
      <div className="flex items-center justify-between">
        <figcaption className="text-sm font-medium text-stone-700 dark:text-stone-200">How the answer was found</figcaption>
        <button
          type="button"
          onClick={() => {
            setPhase(0);
            setLines([]);
            setRun((r) => r + 1);
          }}
          className="rounded-md px-2 py-1 text-xs text-stone-500 transition hover:bg-stone-100 hover:text-stone-800 dark:hover:bg-stone-800 dark:hover:text-stone-100"
        >
          ↻ Replay
        </button>
      </div>

      <Step index={1} title="Searched every table" note={`${candidates.length} closest matches`} visible>
        <ul className="flex flex-wrap gap-1.5" aria-label="Tables searched">
          {candidates.map((table, i) => {
            const chosen = selected.includes(table);
            const decided = phase >= 1;
            return (
              <li
                key={table}
                style={{ animationDelay: `${i * 60}ms` }}
                data-chosen={chosen}
                className={`animate-rise rounded-md px-2 py-0.5 font-mono text-xs transition-all duration-500 ${
                  decided && chosen
                    ? "bg-accent-600 text-white shadow-sm shadow-accent-600/30"
                    : decided
                      ? "bg-stone-100 text-stone-400 line-through opacity-50 dark:bg-stone-800 dark:text-stone-500"
                      : "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"
                }`}
              >
                {table}
              </li>
            );
          })}
        </ul>
      </Step>

      <Connector visible={phase >= 2} />

      <Step index={2} title="Joined the tables it needs" note={`${selected.length} table${selected.length === 1 ? "" : "s"}`} visible={phase >= 2}>
        <div ref={board} className="relative">
          <div className="flex flex-wrap justify-center gap-x-24 gap-y-10 py-2">
            {selected.map((table, i) => (
              <div
                key={table}
                ref={(el) => {
                  if (el) cards.current.set(table, el);
                  else cards.current.delete(table);
                }}
                style={{ animationDelay: `${i * 90}ms` }}
                className="animate-rise min-w-36 rounded-xl border border-accent-500/40 bg-white shadow-sm dark:bg-stone-900"
              >
                <div className="rounded-t-xl bg-accent-600 px-3 py-1.5 font-mono text-xs font-semibold text-white">{table}</div>
                <ul className="px-3 py-2">
                  {(columns[table] ?? []).map((column) => {
                    const joined = phase >= 3 && joinColumns.has(`${table}.${column}`);
                    return (
                      <li
                        key={column}
                        data-joined={joined}
                        className={`flex items-center gap-1.5 font-mono text-xs transition-colors duration-500 ${
                          joined ? "font-semibold text-accent-600 dark:text-accent-500" : "text-stone-600 dark:text-stone-300"
                        }`}
                      >
                        <span aria-hidden className={`size-1.5 rounded-full ${joined ? "bg-accent-500" : "bg-stone-300 dark:bg-stone-600"}`} />
                        {column}
                      </li>
                    );
                  })}
                  {(columns[table] ?? []).length === 0 && <li className="text-xs text-stone-400">no columns read</li>}
                </ul>
              </div>
            ))}
          </div>
          {phase >= 3 && joins.length > 0 && (
            <ul aria-label="Joins" className="mt-3 flex flex-col items-center gap-1">
              {joins.map((join) => (
                <li key={joinLabel(join)} className="animate-rise font-mono text-[11px] text-stone-500 dark:text-stone-400">
                  <span className="text-accent-600 dark:text-accent-500">⟷</span> {joinLabel(join)}
                  {join.inferred && <span className="ml-1 text-stone-400">(inferred key)</span>}
                </li>
              ))}
            </ul>
          )}
          {phase >= 3 && lines.length > 0 && (
            <svg aria-hidden className="pointer-events-none absolute inset-0 size-full overflow-visible">
              {lines.map((line, i) => (
                <g key={i}>
                  <line
                    x1={line.x1}
                    y1={line.y1}
                    x2={line.x2}
                    y2={line.y2}
                    className="stroke-accent-500 animate-[draw_0.7s_ease-out_both]"
                    strokeWidth={2}
                    strokeDasharray={400}
                  />
                  <line
                    x1={line.x1}
                    y1={line.y1}
                    x2={line.x2}
                    y2={line.y2}
                    className="stroke-white/80 animate-[flow_0.8s_linear_infinite] [animation-delay:0.7s] dark:stroke-stone-900/80"
                    strokeWidth={2}
                    strokeDasharray="4 12"
                  />
                </g>
              ))}
            </svg>
          )}
        </div>
      </Step>

      <Connector visible={phase >= 4} />

      <Step index={3} title="Ran the query" note={answer.error ? "failed" : "read-only"} visible={phase >= 4}>
        <div className="flex animate-pop items-baseline gap-3">
          <span className={`font-serif tabular-nums ${answer.error ? "text-2xl text-red-600" : "text-4xl text-stone-900 dark:text-stone-50"}`}>
            {result.headline}
          </span>
          <span className="font-mono text-xs text-stone-500">{result.caption}</span>
        </div>
      </Step>
    </figure>
  );
}

function Step({ index, title, note, visible, children }: { index: number; title: string; note: string; visible: boolean; children: React.ReactNode }) {
  if (!visible) return null;
  return (
    <section className="mt-4 animate-rise">
      <div className="mb-2.5 flex items-center gap-2">
        <span className="grid size-5 place-items-center rounded-full bg-stone-100 text-[10px] font-semibold text-stone-600 dark:bg-stone-800 dark:text-stone-300">
          {index}
        </span>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-500">{title}</h3>
        <span className="text-xs text-stone-400">· {note}</span>
      </div>
      {children}
    </section>
  );
}

function Connector({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div aria-hidden className="ml-2.5 mt-3 h-6 w-px origin-top animate-[grow-y_0.4s_ease-out_both] bg-gradient-to-b from-accent-500 to-transparent" />
  );
}
