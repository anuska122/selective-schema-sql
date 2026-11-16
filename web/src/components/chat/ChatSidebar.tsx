import type { Conversation } from "@/lib/chat";
import { databaseName } from "@/lib/format";
import type { Database } from "@/lib/types";
import { Mark } from "./Mark";

type Props = {
  conversations: Conversation[];
  activeId: string | null;
  databases: Database[];
  dbId: string;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDbChange: (dbId: string) => void;
  mobileOpen?: boolean;
  onClose?: () => void;
};

export function ChatSidebar({
  conversations, activeId, databases, dbId, onNew, onOpen, onDbChange,
  mobileOpen = false, onClose,
}: Props) {
  return (
    <aside
      id="chat-navigation"
      aria-label="Question navigation"
      className={`${mobileOpen ? "flex fixed inset-y-0 left-0 z-40 shadow-xl" : "hidden"} w-72 shrink-0 flex-col border-r border-stone-200 bg-[#f3f1ec] md:static md:flex md:shadow-none dark:border-stone-800 dark:bg-[#1f1e1d]`}
    >
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-5">
        <Mark />
        <span className="font-serif text-lg text-stone-800 dark:text-stone-100">Ask your database</span>
        {mobileOpen && (
          <button type="button" autoFocus onClick={onClose} className="ml-auto rounded px-2 py-1 md:hidden" aria-label="Close navigation">
            ×
          </button>
        )}
      </div>

      <div className="px-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-stone-700 transition hover:bg-stone-200/70 dark:text-stone-200 dark:hover:bg-stone-800"
        >
          <span className="grid size-5 place-items-center rounded-full bg-accent-600 text-xs text-white" aria-hidden>
            +
          </span>
          New question
        </button>
      </div>

      <div className="mt-4 px-4">
        <label htmlFor="sidebar-database" className="text-xs font-medium text-stone-500">
          Database
        </label>
        <select
          id="sidebar-database"
          value={dbId}
          onChange={(event) => onDbChange(event.target.value)}
          className="mt-1.5 w-full rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-accent-500/30 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200"
        >
          <option value="">All tables</option>
          {databases.map((db) => (
            <option key={db.db_id} value={db.db_id}>
              {databaseName(db.db_id)}
            </option>
          ))}
        </select>
      </div>

      <nav aria-label="Recent questions" className="mt-6 flex min-h-0 flex-1 flex-col px-2">
        <h2 className="px-2 pb-1.5 text-xs font-medium text-stone-500">Recents</h2>
        <ul className="flex flex-col gap-0.5 overflow-y-auto pb-4">
          {conversations.length === 0 && <li className="px-2 py-1 text-sm text-stone-400">No questions yet</li>}
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onOpen(c.id)}
                aria-current={c.id === activeId ? "page" : undefined}
                className={`w-full truncate rounded-lg px-2.5 py-1.5 text-left text-sm transition ${
                  c.id === activeId
                    ? "bg-stone-200/90 text-stone-900 dark:bg-stone-800 dark:text-stone-100"
                    : "text-stone-600 hover:bg-stone-200/60 dark:text-stone-400 dark:hover:bg-stone-800/60"
                }`}
              >
                {c.title}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <p className="border-t border-stone-200 px-4 py-3 text-xs text-stone-400 dark:border-stone-800">Read-only · BIRD databases</p>
    </aside>
  );
}
