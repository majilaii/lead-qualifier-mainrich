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

/* ─── Mock Fallback (when backend is not running) ─── */

function generateMockResponse(messages: Message[]): {
  message: string;
  readiness: Readiness;
} {
  const userMessages = messages.filter((m) => m.role === "user");
  const turnCount = userMessages.length;
  const lastUserMessage = userMessages[userMessages.length - 1]?.content || "";

  const readiness: Readiness = {
    industry: turnCount >= 1,
    companyProfile: turnCount >= 2,
    technologyFocus: turnCount >= 3,
    qualifyingCriteria: turnCount >= 4,
    isReady: turnCount >= 4,
  };

  const snippet =
    lastUserMessage.length > 80
      ? lastUserMessage.slice(0, 80) + "..."
      : lastUserMessage;

  switch (turnCount) {
    case 1:
      return {
        message: `Got it — I'm picking up the direction from "${snippet}"\n\nTo sharpen the search, a couple of follow-ups:\n\n**Company profile** — Are you targeting early-stage startups, growth-stage companies, or established manufacturers? Any geographic focus (US, Europe, Asia, worldwide)?\n\n**Scale** — Roughly how many companies are you hoping to find? This helps me calibrate how broad or niche to search.`,
        readiness,
      };
    case 2:
      return {
        message: `Good, that narrows it down. Now let's get specific about the technology:\n\n**What products or components** should these companies be working with? For example: brushless motors, permanent magnets, gearboxes, actuators, linear drives, sensors, etc.\n\n**What should their website signal?** Product pages with technical specs? In-house manufacturing? R&D team pages? The more specific, the better my queries will be.`,
        readiness,
      };
    case 3:
      return {
        message: `Almost there — one more piece and I can build the search plan.\n\n**What makes a company a great fit?** What would you see on their website that tells you they're worth reaching out to? For example: they manufacture their own hardware, they have a products page with specs, they mention specific materials or components.\n\n**What's a dealbreaker?** Anything that should immediately disqualify a company — for example: pure software/SaaS, consulting firms, companies that only resell other people's products.`,
        readiness,
      };
    case 4:
      return {
        message: `I have a clear picture now. Here's the search plan:\n\n**Target profile:**\nBased on our conversation, I'll search for companies matching your criteria across the web using semantic search.\n\n**Queries I'll generate:**\n1. Primary industry + product search\n2. Technology-specific company search\n3. Emerging companies / startup search\n4. Geographic-focused search\n\n**Qualifying signals I'll look for:**\n- Manufacturing or R&D capabilities\n- Technical product pages\n- Component or material mentions\n\n**Disqualifiers:**\n- Pure software/SaaS companies\n- Resellers without own products\n- Consulting or services-only firms\n\nType **"go"** to launch the search, or tell me if you want to adjust anything.`,
        readiness,
      };
    default:
      if (/\b(go|search|launch|start|find)\b/i.test(lastUserMessage)) {
        return {
          message: `Searching across the web...\n\nThis is a **preview mock** — the real search integration with Exa AI is coming next. When connected, this will:\n\n1. Generate 4-8 semantic search queries from our conversation\n2. Search millions of web pages via Exa neural search\n3. Deduplicate and rank results\n4. Crawl each company's website\n5. Qualify them against your criteria using AI\n6. Return a scored list of matches\n\nThe backend pipeline is ready — we just need to wire it up. Stay tuned.`,
          readiness,
        };
      }
      return {
        message: `I've already gathered enough context to search. Here's what I have:\n\n- **Industry:** Captured from your first message\n- **Company profile:** Size, stage, and geography preferences noted\n- **Technology focus:** Specific products and components identified\n- **Qualifying criteria:** Signals and dealbreakers defined\n\nType **"go"** to launch the search, or tell me what you'd like to adjust.`,
        readiness,
      };
  }
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

      // Backend returned an error — fall through to mock
      console.warn(
        `Backend returned ${backendResponse.status}, falling back to mock`
      );
    } catch {
      // Backend not reachable — fall through to mock
      console.warn("Backend not reachable, using mock responses");
    }

    // Fallback: mock response
    const delay = 300 + Math.random() * 500;
    await new Promise((resolve) => setTimeout(resolve, delay));

    const { message, readiness } = generateMockResponse(sanitizedMessages);
    return NextResponse.json({ message, readiness });
  } catch {
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
