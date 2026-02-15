import { NextResponse } from "next/server";

export const runtime = "nodejs";

const BACKEND =
  process.env.CHAT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * Stripe webhook passthrough — forward raw body + signature header to backend.
 * No auth required (Stripe uses its own signature verification).
 * 
 * CRITICAL: Must forward the raw body exactly as received for signature
 * verification to pass. Using request.text() preserves the original payload.
 */
export async function POST(request: Request) {
  try {
    const body = await request.text();
    const sig = request.headers.get("stripe-signature") || "";
    const contentType = request.headers.get("content-type") || "application/json";

    const resp = await fetch(`${BACKEND}/api/billing/webhook`, {
      method: "POST",
      headers: {
        "Content-Type": contentType,
        "stripe-signature": sig,
      },
      body,
    });

    // Handle non-JSON responses gracefully
    const text = await resp.text();
    try {
      const data = JSON.parse(text);
      return NextResponse.json(data, { status: resp.status });
    } catch {
      return new NextResponse(text, { status: resp.status });
    }
  } catch (e) {
    console.error("Webhook forwarding error:", e);
    return NextResponse.json(
      { error: "Webhook forwarding failed" },
      { status: 502 }
    );
  }
}
