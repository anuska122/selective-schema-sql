import { Mark } from "./Mark";

export const EXAMPLES = [
  "How many superheroes have blue eyes?",
  "What is the average AST level of patients?",
  "How many female clients are there?",
  "Which driver won the most races?",
];

export function greeting(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function EmptyState({ hour, onPick }: { hour: number; onPick: (question: string) => void }) {
  return (
    <div className="flex animate-rise flex-col items-center gap-3 text-center">
      <Mark className="size-10" />
      <h1 className="font-serif text-3xl text-stone-800 sm:text-4xl dark:text-stone-100">{greeting(hour)}</h1>
      <p className="text-stone-500 dark:text-stone-400">What would you like to know from your data?</p>
      <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
        {EXAMPLES.map((example, i) => (
          <button
            key={example}
            type="button"
            onClick={() => onPick(example)}
            style={{ animationDelay: `${120 + i * 60}ms` }}
            className="animate-rise rounded-xl border border-stone-200 bg-white/70 px-4 py-3 text-left text-sm text-stone-600 transition hover:-translate-y-0.5 hover:border-stone-300 hover:bg-white hover:shadow-sm dark:border-stone-700 dark:bg-stone-800/40 dark:text-stone-300 dark:hover:bg-stone-800"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
