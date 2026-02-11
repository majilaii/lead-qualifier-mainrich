import { NextResponse } from "next/server";

const BACKEND_URL = process.env.CHAT_BACKEND_URL || "http://localhost:8000";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const authHeader = request.headers.get("authorization") || "";

    const backendResponse = await fetch(`${BACKEND_URL}/api/chat/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60000), // 60s — query generation + Exa search
    });

    if (!backendResponse.ok) {
      // Forward 429 quota responses as-is so the frontend gets used/limit/action/plan
      if (backendResponse.status === 429) {
        const err = await backendResponse.json().catch(() => ({ error: "quota_exceeded" }));
        return NextResponse.json(err, { status: 429 });
      }
      const err = await backendResponse.text();
      return NextResponse.json(
        { error: `Search failed: ${err}` },
        { status: backendResponse.status }
      );
    }

    const data = await backendResponse.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Search proxy error:", error);
    return NextResponse.json(
      { error: "Search service unavailable" },
      { status: 503 }
    );
  }
}
