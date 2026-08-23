"use client";

import { Badge } from "@/components/ui/badge";

interface ToolTraceBadgeProps {
  trace: string[];
}

const TOOL_LABELS: Record<string, { label: string; color: string }> = {
  document_search: { label: "Document search", color: "bg-blue-900/60 text-blue-300 border-blue-700" },
  query_operational_data: { label: "Structured data", color: "bg-green-900/60 text-green-300 border-green-700" },
  rank_precedence: { label: "Precedence check", color: "bg-purple-900/60 text-purple-300 border-purple-700" },
  propose_action: { label: "Action proposed", color: "bg-orange-900/60 text-orange-300 border-orange-700" },
  execute_action: { label: "Action executed", color: "bg-red-900/60 text-red-300 border-red-700" },
  draft_answer: { label: "Answer drafted", color: "bg-gray-800 text-gray-300 border-gray-600" },
  classify_and_route: { label: "Classified", color: "bg-gray-800 text-gray-400 border-gray-600" },
};

export function ToolTraceBadge({ trace }: ToolTraceBadgeProps) {
  if (!trace || trace.length === 0) return null;

  // Filter out noise nodes for display
  const displayTrace = trace.filter(
    (t) => !t.includes("classify_and_route") && !t.includes("draft_answer")
  );

  if (displayTrace.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1 text-xs">
      {displayTrace.map((tool, i) => {
        const info = TOOL_LABELS[tool] ?? { label: tool, color: "bg-gray-800 text-gray-400 border-gray-600" };
        return (
          <span key={i} className="flex items-center gap-1">
            <span
              className={`px-2 py-0.5 rounded-full border text-xs ${info.color} transition-all`}
            >
              {info.label}
            </span>
            {i < displayTrace.length - 1 && (
              <span className="text-gray-600">→</span>
            )}
          </span>
        );
      })}
    </div>
  );
}
