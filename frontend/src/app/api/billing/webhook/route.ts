import { NextResponse } from "next/server";

const BACKEND =
  process.env.CHAT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * Stripe webhook passthrough — forward raw body + signature header to backend.
 * No auth required (Stripe uses its own signature verification).
 */
export async function POST(request: Request) {
  try {
    const body = await request.text();
    const sig = request.headers.get("stripe-signature") || "";

    const resp = await fetch(`${BACKEND}/api/billing/webhook`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "stripe-signature": sig,
      },
      body,
    });

    const data = await resp.json();
    return NextResponse.json(data, { status: resp.status });
  } catch {
    return NextResponse.json(
      { error: "Webhook forwarding failed" },
      { status: 502 }
    );
  }
}
