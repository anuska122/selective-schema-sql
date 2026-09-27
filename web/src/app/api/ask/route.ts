import { forward } from "@/lib/backend";
import { allow, clientId } from "@/lib/rateLimit";

const MAX_QUESTION_LENGTH = 2000;
const MAX_BODY_BYTES = 16_384;

export async function POST(request: Request) {
  if (!allow(clientId(request))) {
    return Response.json({ detail: "Too many questions from here. Try again later." }, { status: 429 });
  }
  const raw = await request.text();
  if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) {
    return Response.json({ detail: "Request too large." }, { status: 413 });
  }
  const body = (() => {
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  })();
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
