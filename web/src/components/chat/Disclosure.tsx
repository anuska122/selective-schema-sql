"use client";

import { useState, type ReactNode } from "react";

export function Disclosure({ label, meta, defaultOpen = false, children }: { label: string; meta?: ReactNode; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-stone-200 bg-white/60 dark:border-stone-700/80 dark:bg-stone-800/30">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-sm text-stone-600 transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white"
      >
        <svg viewBox="0 0 24 24" className={`size-3.5 transition-transform duration-200 ${open ? "rotate-90" : ""}`} fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
          <path d="M9 6l6 6-6 6" />
        </svg>
        <span className="font-medium">{label}</span>
        {meta && <span className="ml-auto text-xs text-stone-400">{meta}</span>}
      </button>
      <div className={`grid transition-[grid-template-rows] duration-300 ease-out ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
        <div className="overflow-hidden">
          <div className="px-3.5 pb-3.5">{children}</div>
        </div>
      </div>
    </div>
  );
}
