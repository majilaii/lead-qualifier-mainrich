import { NextResponse } from "next/server";

const BACKEND_URL = process.env.CHAT_BACKEND_URL || "http://localhost:8000";

interface SupportRequestBody {
  question: string;
  sessionId?: string;
  maxSources?: number;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as SupportRequestBody;
    const question = (body.question || "").trim();

    if (!question) {
      return NextResponse.json({ error: "Question is required" }, { status: 400 });
    }

    const auth = request.headers.get("authorization");
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (auth) headers.Authorization = auth;

    const backendResponse = await fetch(`${BACKEND_URL}/api/support/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        question,
        session_id: body.sessionId,
        max_sources: body.maxSources ?? 6,
      }),
      signal: AbortSignal.timeout(70000),
    });

    const data = await backendResponse.json().catch(() => ({}));
    if (!backendResponse.ok) {
      return NextResponse.json(
        { error: data?.detail || data?.error || "Support chat failed" },
        { status: backendResponse.status }
      );
    }

    return NextResponse.json({
      sessionId: data.session_id,
      answer: data.answer,
      confidence: data.confidence,
      needsHuman: data.needs_human,
    });
  } catch {
    return NextResponse.json(
      { error: "Support service unavailable" },
      { status: 503 }
    );
  }
}
