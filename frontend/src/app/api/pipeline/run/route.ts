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
      signal: AbortSignal.timeout(30000), // 30s — POST now returns immediately
    });

    if (!backendResponse.ok) {
      // Forward 429 quota responses with JSON content-type so frontend gets used/limit/action/plan
      if (backendResponse.status === 429) {
        const err = await backendResponse.json().catch(() => ({ error: "quota_exceeded" }));
        return new Response(JSON.stringify(err), {
          status: 429,
          headers: { "Content-Type": "application/json" },
        });
      }
      const err = await backendResponse.text();
      return new Response(err, { status: backendResponse.status });
    }

    // POST now returns JSON { search_id } — forward it
    const data = await backendResponse.json();
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Pipeline proxy error:", error);
    return new Response(
      JSON.stringify({ error: "Pipeline service unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}
