import type { Stage } from "@/lib/types";

const LABELS: Record<string, string> = {
  retrieve: "Find tables",
  select: "Choose tables",
  select_failed: "Choose tables (fallback)",
  generate: "Write SQL",
  repair: "Repair SQL",
};

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

export function StageTimeline({ stages }: { stages: Stage[] }) {
  const total = stages.reduce((sum, stage) => sum + stage.latency_ms, 0);
  const tokens = stages.reduce((sum, stage) => sum + stage.tokens_in + stage.tokens_out, 0);
  return (
    <div className="flex flex-col gap-3">
      {stages.map((stage, i) => (
        <div key={`${stage.name}-${i}`} className="flex flex-col gap-1">
          <div className="flex justify-between text-sm">
            <span className="text-stone-700 dark:text-stone-300">{LABELS[stage.name] ?? stage.name}</span>
            <span className="font-mono text-xs text-stone-500">
              {formatMs(stage.latency_ms)}
              {stage.llm_calls > 0 && ` · ${stage.tokens_in + stage.tokens_out} tokens`}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-stone-100 dark:bg-stone-800">
            <div
              className={`h-full origin-left animate-[grow_0.8s_cubic-bezier(0.22,1,0.36,1)_both] rounded-full ${stage.llm_calls > 0 ? "bg-clay-500" : "bg-stone-400"}`}
              style={{ width: `${total ? Math.max(2, (stage.latency_ms / total) * 100) : 0}%` }}
            />
          </div>
        </div>
      ))}
      <div className="flex justify-between border-t border-stone-100 pt-2 text-sm font-medium dark:border-stone-800">
        <span className="text-stone-900 dark:text-stone-100">Total</span>
        <span className="font-mono text-xs text-stone-700 dark:text-stone-300">
          {formatMs(total)} · {tokens} tokens
        </span>
      </div>
    </div>
  );
}
