import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(request: Request) {
  try {
    const authHeader = request.headers.get("authorization") || "";

    // No token → skip the backend call entirely
    if (!authHeader) {
      return NextResponse.json(
        { error: "No auth token" },
        { status: 401 }
      );
    }

    const resp = await fetch(`${BACKEND}/api/usage`, {
      headers: {
        Authorization: authHeader,
      },
    });

    const data = await resp.json();
    return NextResponse.json(data, { status: resp.status });
  } catch {
    return NextResponse.json(
      { error: "Failed to fetch usage data" },
      { status: 502 }
    );
  }
}
