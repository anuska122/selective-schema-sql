"use client";

import { useState } from "react";

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="rounded-md px-2 py-0.5 text-xs text-stone-400 transition hover:bg-stone-800 hover:text-stone-100"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
