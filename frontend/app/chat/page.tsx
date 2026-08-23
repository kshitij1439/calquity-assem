"use client";

import { useState, useRef, useEffect } from "react";
import { AccountSwitcher } from "@/components/account-switcher";
import { ToolTraceBadge } from "@/components/tool-trace-badge";
import { ConfirmActionDialog } from "@/components/confirm-action-dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import dynamic from "next/dynamic";

const MascotViewport = dynamic(() => import("../components/MascotViewport"), {
  ssr: false,
});

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolTrace?: string[];
  sources?: string[];
  confidence?: "high" | "medium" | "low";
  escalate?: boolean;
  escalationReason?: string;
  pendingAction?: {
    action_type: string;
    draft_description: string;
    confirmation_token: string;
    expires_at: string;
  } | null;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState("groq/compound");
  const [account, setAccount] = useState<{ id: string; name: string; role: string }>({
    id: "ACCT-001",
    name: "Northstar Logistics",
    role: "staff",
  });
  const [threadId, setThreadId] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<Message["pendingAction"] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: input.trim() };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Account-ID": account.id,
          "X-User-Role": account.role,
        },
        body: JSON.stringify({ message: userMsg.content, thread_id: threadId, model: selectedModel }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Server error");
      }

      const data = await res.json();
      if (data.thread_id) setThreadId(data.thread_id);

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.answer,
        toolTrace: data.tool_trace,
        sources: data.sources_used,
        confidence: data.confidence,
        escalate: data.escalate,
        escalationReason: data.escalation_reason,
        pendingAction: data.pending_action,
      };
      setMessages((m) => [...m, assistantMsg]);

      if (data.pending_action) {
        setConfirmAction(data.pending_action);
      }
    } catch (err: any) {
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `Error: ${err.message}. Please try again or contact support.`,
          confidence: "low",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (token: string) => {
    try {
      const res = await fetch(`${API_BASE}/confirm-action`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Account-ID": account.id,
          "X-User-Role": account.role,
        },
        body: JSON.stringify({ confirmation_token: token }),
      });
      const data = await res.json();
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.message ?? "Action executed successfully.",
        },
      ]);
    } catch {
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: "assistant", content: "Failed to execute action." },
      ]);
    } finally {
      setConfirmAction(null);
    }
  };

  const confidenceBadgeVariant = (c?: string) => {
    if (c === "high") return "default";
    if (c === "medium") return "secondary";
    return "destructive";
  };

  return (
    <div className="h-screen max-h-screen bg-gray-950 flex flex-col overflow-hidden w-full">
      {/* Header */}
      <header className="shrink-0 border-b border-gray-800 bg-gray-900/80 backdrop-blur px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            <div className="w-8 h-8 rounded-lg overflow-hidden bg-indigo-950/60 border border-indigo-500/30 flex items-center justify-center">
              <MascotViewport />
            </div>
            <span className="text-white font-semibold text-sm">ParcelPilot</span>
          </Link>
          <span className="text-gray-600">/</span>
          <span className="text-gray-400 text-sm">Support Chat</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1">
            <span className="text-xs text-gray-400 font-medium">Model:</span>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="bg-transparent text-xs text-indigo-400 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="groq/compound" className="bg-gray-900 text-white">Groq Model (Default)</option>
              <option value="gemini-2.5-flash" className="bg-gray-900 text-white">Gemini 2.5 Flash</option>
            </select>
          </div>
          <AccountSwitcher account={account} onChange={setAccount} />
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 && (
            <div className="text-center py-12 space-y-4">
              <div className="w-28 h-28 mx-auto relative flex items-center justify-center overflow-hidden rounded-3xl bg-indigo-950/40 border border-indigo-500/30 shadow-xl shadow-indigo-500/10">
                <MascotViewport />
              </div>
              <h2 className="text-white font-semibold text-xl">ParcelPilot Support Agent</h2>
              <p className="text-gray-400 text-sm max-w-sm mx-auto">
                Ask about orders, cancellations, SLA status, service credits, or policy questions.
              </p>
              <div className="flex flex-wrap gap-2 justify-center pt-2">
                {[
                  "Can Northstar cancel ORD-1001 without a fee?",
                  "What's the P1 SLA for Northstar?",
                  "Is there a service credit for a 3-hour late pickup?",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="text-xs bg-gray-800 text-gray-300 px-3 py-1.5 rounded-full hover:bg-gray-700 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] space-y-2 ${msg.role === "user" ? "items-end" : "items-start"} flex flex-col`}>
                {/* Bubble */}
                <div
                  className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                    msg.role === "user"
                      ? "bg-indigo-600 text-white rounded-br-sm"
                      : "bg-gray-800 text-gray-100 rounded-bl-sm"
                  }`}
                >
                  {msg.content}
                </div>

                {/* Tool trace */}
                {msg.toolTrace && msg.toolTrace.length > 0 && (
                  <ToolTraceBadge trace={msg.toolTrace} />
                )}

                {/* Meta badges */}
                {msg.role === "assistant" && (
                  <div className="flex flex-wrap gap-1.5 items-center">
                    {msg.confidence && (
                      <Badge variant={confidenceBadgeVariant(msg.confidence)} className="text-xs">
                        Confidence: {msg.confidence}
                      </Badge>
                    )}
                    {msg.escalate && (
                      <Badge variant="destructive" className="text-xs">
                        ⚠ Escalation recommended
                      </Badge>
                    )}
                  </div>
                )}

                {/* Sources */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="text-xs text-gray-500 space-y-0.5">
                    <span className="font-medium text-gray-400">Sources: </span>
                    {[...new Set(msg.sources)].map((s) => (
                      <span key={s} className="inline-block bg-gray-800/60 px-2 py-0.5 rounded mr-1">
                        {s.replace(/_/g, " ").replace(".pdf", "")}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-800 rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-gray-800 bg-gray-900/80 backdrop-blur px-4 py-4">
        <div className="max-w-3xl mx-auto flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
            placeholder="Ask about orders, policies, SLAs, cancellations..."
            disabled={loading}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors disabled:opacity-50"
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors"
          >
            Send
          </button>
        </div>
      </div>

      {/* Confirm action dialog */}
      {confirmAction && (
        <ConfirmActionDialog
          proposal={confirmAction}
          onConfirm={handleConfirm}
          onCancel={() => setConfirmAction(null)}
        />
      )}
    </div>
  );
}
