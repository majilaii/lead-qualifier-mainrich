const BACKEND_URL = process.env.CHAT_BACKEND_URL || "http://localhost:8000";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const backendResponse = await fetch(`${BACKEND_URL}/api/enrich`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120000), // 2 min
    });

    if (!backendResponse.ok) {
      const err = await backendResponse.text();
      return new Response(err, { status: backendResponse.status });
    }

    // Forward the SSE stream through
    return new Response(backendResponse.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    console.error("Enrich proxy error:", error);
    return new Response(
      JSON.stringify({ error: "Enrichment service unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}
