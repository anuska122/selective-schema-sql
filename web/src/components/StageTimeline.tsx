import type { Stage } from "@/lib/types";

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

export function StageTimeline({ stages }: { stages: Stage[] }) {
  const total = stages.reduce((sum, stage) => sum + stage.latency_ms, 0);
  const tokens = stages.reduce((sum, stage) => sum + stage.tokens_in + stage.tokens_out, 0);
  return (
    <div className="flex flex-col gap-1 text-sm">
      {stages.map((stage, i) => (
        <div key={`${stage.name}-${i}`} className="flex justify-between gap-4">
          <span className="text-zinc-700">{stage.name}</span>
          <span className="font-mono text-xs text-zinc-500">
            {formatMs(stage.latency_ms)}
            {stage.llm_calls > 0 && ` · ${stage.tokens_in + stage.tokens_out} tokens`}
          </span>
        </div>
      ))}
      <div className="mt-1 flex justify-between gap-4 border-t border-zinc-200 pt-1 font-medium">
        <span>total</span>
        <span className="font-mono text-xs">
          {formatMs(total)} · {tokens} tokens
        </span>
      </div>
    </div>
  );
}
