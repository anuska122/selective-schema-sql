"use client";

import { useEffect, useState } from "react";

export const STEPS = ["Finding relevant tables", "Choosing the tables to use", "Writing the SQL", "Checking and running it"];
const STEP_MS = 700;

export function PendingSteps() {
  const [active, setActive] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setActive((i) => Math.min(i + 1, STEPS.length - 1)), STEP_MS);
    return () => clearInterval(timer);
  }, []);
  return (
    <ol role="status" aria-live="polite" className="flex flex-col gap-2">
      {STEPS.slice(0, active + 1).map((step, i) => (
        <li key={step} className="flex animate-rise items-center gap-2.5 text-sm">
          {i < active ? (
            <span className="text-clay-600" aria-hidden>
              ✓
            </span>
          ) : (
            <span className="flex gap-0.5" aria-hidden>
              {[0, 1, 2].map((d) => (
                <span key={d} className="size-1.5 animate-blink rounded-full bg-clay-600" style={{ animationDelay: `${d * 150}ms` }} />
              ))}
            </span>
          )}
          <span className={i < active ? "text-stone-400" : "text-stone-700 dark:text-stone-200"}>{step}</span>
        </li>
      ))}
    </ol>
  );
}
