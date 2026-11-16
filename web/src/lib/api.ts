import type { AskResponse, Database } from "./types";

async function readError(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`;
}

export async function ask(question: string, dbId: string, signal?: AbortSignal): Promise<AskResponse> {
  const response = await fetch("/api/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, db_id: dbId }),
    signal,
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function listDatabases(): Promise<Database[]> {
  const response = await fetch("/api/databases");
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}
