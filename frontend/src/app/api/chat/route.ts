import { NextResponse } from "next/server";

/* ─── Types ─── */

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

interface Readiness {
  industry: boolean;
  companyProfile: boolean;
  technologyFocus: boolean;
  qualifyingCriteria: boolean;
  isReady: boolean;
}

/* ─── Backend URL ─── */

const BACKEND_URL = process.env.CHAT_BACKEND_URL || "http://localhost:8000";

/* ─── Input Sanitization (defense-in-depth, also done in backend) ─── */

const MAX_MESSAGE_LENGTH = 2000;
const MAX_MESSAGES = 50;

function sanitizeInput(text: string): string {
  let clean = text.trim().slice(0, MAX_MESSAGE_LENGTH);

  clean = clean.replace(
    /ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)/gi,
    "[filtered]"
  );
  clean = clean.replace(
    /\[INST\]|\[\/INST\]|<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>/gi,
    ""
  );
  clean = clean.replace(/<[^>]*>/g, "");
  clean = clean.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");

  return clean;
}

function validateMessages(messages: unknown): messages is Message[] {
  if (!Array.isArray(messages)) return false;
  if (messages.length > MAX_MESSAGES) return false;
  return messages.every(
    (msg) =>
      typeof msg === "object" &&
      msg !== null &&
      typeof (msg as Message).role === "string" &&
      ["user", "assistant"].includes((msg as Message).role) &&
      typeof (msg as Message).content === "string"
  );
}

/* ─── Route Handler ─── */

export async function POST(request: Request) {
  try {
    const body = await request.json();

    // Validate message structure
    if (!validateMessages(body.messages)) {
      return NextResponse.json(
        { error: "Invalid message format" },
        { status: 400 }
      );
    }

    // Sanitize user messages
    const sanitizedMessages = body.messages.map((msg: Message) => ({
      ...msg,
      content: msg.role === "user" ? sanitizeInput(msg.content) : msg.content,
    }));

    // Try the Python backend first
    try {
      const backendPayload = {
        messages: sanitizedMessages.map((m: Message) => ({
          role: m.role,
          content: m.content,
        })),
      };

      const backendResponse = await fetch(`${BACKEND_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(backendPayload),
        signal: AbortSignal.timeout(70000), // 70s timeout — thinking models can be slow
      });

      if (backendResponse.ok) {
        const data = await backendResponse.json();
        return NextResponse.json({
          message: data.message,
          readiness: data.readiness,
          extractedContext: data.extracted_context,
        });
      }

      // Backend returned an error
      console.warn(`Backend returned ${backendResponse.status}`);
      return NextResponse.json(
        { error: "The AI backend returned an error. Please try again." },
        { status: backendResponse.status }
      );
    } catch (err) {
      // Backend not reachable
      console.warn("Backend not reachable:", err);
      return NextResponse.json(
        {
          error:
            "Unable to reach the AI backend — it may be restarting. Please wait a moment and try again.",
        },
        { status: 503 }
      );
    }
  } catch {
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
