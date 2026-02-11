import { NextResponse } from "next/server";

const BACKEND =
  process.env.CHAT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

export async function GET(request: Request) {
  try {
    const authHeader = request.headers.get("authorization") || "";
    if (!authHeader) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    const resp = await fetch(`${BACKEND}/api/billing/status`, {
      headers: { Authorization: authHeader },
    });

    const data = await resp.json();
    return NextResponse.json(data, { status: resp.status });
  } catch {
    return NextResponse.json(
      { error: "Failed to fetch billing status" },
      { status: 502 }
    );
  }
}
