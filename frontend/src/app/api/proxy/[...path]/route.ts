/**
 * Catch-all backend proxy — forwards /api/proxy/... to the Python backend.
 *
 * This allows "use client" components to call the backend through the
 * Next.js server (which knows the real CHAT_BACKEND_URL) instead of
 * needing to know the backend URL directly.
 *
 * Supports GET, POST, PATCH, PUT, DELETE with auth header forwarding.
 * SSE streams are piped chunk-by-chunk to avoid buffering issues.
 */

import { NextRequest, NextResponse } from "next/server";

/* Force Node.js runtime — SSE streams can run for minutes and must not be
   killed by the default edge/serverless timeout. */
export const runtime = "nodejs";
/* Disable body size limit (SSE has no predetermined length). */
export const maxDuration = 600; // seconds

const BACKEND =
  process.env.CHAT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

async function proxyRequest(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const backendPath = `/api/${path.join("/")}`;
  const url = new URL(backendPath, BACKEND);

  // Forward query string
  const search = request.nextUrl.searchParams.toString();
  if (search) url.search = search;

  // Forward headers (auth, content-type)
  const headers: Record<string, string> = {};
  const auth = request.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;
  const ct = request.headers.get("content-type");
  if (ct) headers["Content-Type"] = ct;

  // Build fetch options
  const fetchOpts: RequestInit = {
    method: request.method,
    headers,
    // SSE streams (pipeline) can run for minutes — use longer timeout for GET requests
    // that may be SSE subscriptions, shorter for regular requests
    signal: AbortSignal.timeout(request.method === "GET" ? 600_000 : 120_000),
  };

  // Forward body for non-GET methods
  if (request.method !== "GET" && request.method !== "HEAD") {
    fetchOpts.body = await request.text();
  }

  try {
    const backendRes = await fetch(url.toString(), fetchOpts);

    // Stream SSE responses through — pipe chunk-by-chunk to avoid buffering
    if (
      backendRes.headers.get("content-type")?.includes("text/event-stream")
    ) {
      const backendBody = backendRes.body;
      if (!backendBody) {
        return NextResponse.json({ error: "No stream body" }, { status: 502 });
      }

      // Create a ReadableStream that reads from the backend and forwards
      // each chunk immediately, ensuring no buffering.
      const stream = new ReadableStream({
        async start(controller) {
          const reader = backendBody.getReader();
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) {
                controller.close();
                break;
              }
              controller.enqueue(value);
            }
          } catch (err) {
            controller.error(err);
          }
        },
        cancel() {
          backendBody.cancel();
        },
      });

      return new Response(stream, {
        status: backendRes.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache, no-transform",
          Connection: "keep-alive",
          "X-Accel-Buffering": "no",
        },
      });
    }

    // Forward JSON / text / CSV responses
    const contentType = backendRes.headers.get("content-type") || "application/json";
    const responseHeaders: Record<string, string> = {
      "Content-Type": contentType,
    };
    // Forward Content-Disposition for file downloads (CSV export, etc.)
    const disposition = backendRes.headers.get("content-disposition");
    if (disposition) {
      responseHeaders["Content-Disposition"] = disposition;
    }

    const body = await backendRes.text();
    return new NextResponse(body, {
      status: backendRes.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error(`Proxy error [${request.method} ${backendPath}]:`, error);
    return NextResponse.json(
      { error: "Backend service unavailable" },
      { status: 503 }
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PATCH = proxyRequest;
export const PUT = proxyRequest;
export const DELETE = proxyRequest;
