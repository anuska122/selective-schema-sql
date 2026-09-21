export function Mark({ className = "size-7" }: { className?: string }) {
  return (
    <span className={`grid shrink-0 place-items-center rounded-lg bg-clay-600 text-white ${className}`} aria-hidden>
      <svg viewBox="0 0 24 24" className="size-[60%]" fill="none" stroke="currentColor" strokeWidth="2.2">
        <ellipse cx="12" cy="5.5" rx="7.5" ry="2.8" />
        <path d="M4.5 5.5v6c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8v-6M4.5 11.5v6c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8v-6" />
      </svg>
    </span>
  );
}
