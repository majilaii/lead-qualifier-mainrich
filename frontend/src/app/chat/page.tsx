import type { Metadata } from "next";
import ChatInterface from "../components/chat/ChatInterface";

export const metadata: Metadata = {
  title: "Hunt — The Magnet Hunter",
  description:
    "AI-powered company discovery. Describe your ideal customer and we'll find them.",
};

export default function ChatPage() {
  return <ChatInterface />;
}
