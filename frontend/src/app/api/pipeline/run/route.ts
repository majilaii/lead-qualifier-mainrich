const BACKEND_URL = process.env.CHAT_BACKEND_URL || "http://localhost:8000";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const authHeader = request.headers.get("authorization") || "";

    const backendResponse = await fetch(`${BACKEND_URL}/api/pipeline/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body: JSON.stringify(body),
      // Long timeout — pipeline can take minutes for large batches
      signal: AbortSignal.timeout(600000), // 10 min
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
    console.error("Pipeline proxy error:", error);
    return new Response(
      JSON.stringify({ error: "Pipeline service unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}
