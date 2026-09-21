import { forward } from "@/lib/backend";

const MAX_QUESTION_LENGTH = 2000;

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const question = typeof body?.question === "string" ? body.question.trim() : "";
  const dbId = typeof body?.db_id === "string" ? body.db_id : "";

  if (!question || question.length > MAX_QUESTION_LENGTH) {
    return Response.json({ detail: "Enter a question up to 2000 characters." }, { status: 400 });
  }

  return forward("/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, db_id: dbId }),
  });
}
