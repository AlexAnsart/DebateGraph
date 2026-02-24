import React, { useState } from "react";
import type { SelectedNode } from "../types";
import FactCheckBadge from "./FactCheckBadge";

interface NodeDetailProps {
  selected: SelectedNode | null;
  onClose: () => void;
}

const CLAIM_TYPE_LABELS: Record<string, string> = {
  premise: "Premise",
  conclusion: "Conclusion",
  concession: "Concession",
  rebuttal: "Rebuttal",
};

const CLAIM_TYPE_COLORS: Record<string, string> = {
  premise: "#3b82f6",
  conclusion: "#f59e0b",
  concession: "#10b981",
  rebuttal: "#ef4444",
};

/**
 * Detail panel shown when a node is selected in the graph.
 * Shows the FULL untruncated claim text, all metadata, fallacies, and fact-check.
 */
export default function NodeDetail({ selected, onClose }: NodeDetailProps) {
  const [showFullFactcheck, setShowFullFactcheck] = useState(false);

  if (!selected) return null;

  const { node } = selected;
  // Always show the full text — fall back to label if full_text not available
  const displayText = node.full_text || node.label;
  const typeColor = CLAIM_TYPE_COLORS[node.claim_type] || "#6b7280";

  return (
    <div className="animate-fade-in bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden max-h-[85vh] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="text-xs font-semibold px-2 py-0.5 rounded-full"
            style={{ backgroundColor: typeColor + "22", color: typeColor }}
          >
            {CLAIM_TYPE_LABELS[node.claim_type] || node.claim_type}
          </span>
          <span className="text-xs font-mono text-gray-600 truncate">{node.id}</span>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-300 transition-colors ml-2 shrink-0"
          title="Close"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Scrollable content */}
      <div className="overflow-y-auto flex-1 p-4 space-y-4">

        {/* Speaker + timestamp */}
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" />
            <span className="text-gray-300 font-medium">
              {node.speaker.replace("SPEAKER_", "Speaker ")}
            </span>
          </span>
          <span>·</span>
          <span>{node.timestamp_start.toFixed(1)}s – {node.timestamp_end.toFixed(1)}s</span>
          {node.is_factual && (
            <>
              <span>·</span>
              <span className="text-emerald-400 font-medium">Factual claim</span>
            </>
          )}
        </div>

        {/* Full claim text — always complete, no truncation */}
        <div className="bg-gray-800/60 rounded-lg p-3 border border-gray-700/50">
          <p className="text-sm text-gray-100 leading-relaxed whitespace-pre-wrap break-words">
            "{displayText}"
          </p>
        </div>

        {/* Confidence bar */}
        <div className="flex items-center gap-3 text-xs">
          <span className="text-gray-500 shrink-0">Confidence</span>
          <div className="flex-1 bg-gray-800 rounded-full h-1.5">
            <div
              className="h-1.5 rounded-full transition-all"
              style={{
                width: `${node.confidence * 100}%`,
                backgroundColor: node.confidence > 0.7 ? "#22c55e" : node.confidence > 0.4 ? "#f59e0b" : "#ef4444",
              }}
            />
          </div>
          <span className="text-gray-400 shrink-0">{(node.confidence * 100).toFixed(0)}%</span>
        </div>

        {/* Fact-check */}
        {node.is_factual && node.factcheck_verdict !== "pending" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Fact-check
              </span>
              {node.factcheck?.explanation && (
                <button
                  onClick={() => setShowFullFactcheck(!showFullFactcheck)}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  {showFullFactcheck ? "Less" : "More"}
                </button>
              )}
            </div>
            <FactCheckBadge
              verdict={node.factcheck_verdict}
              factcheck={node.factcheck}
              expanded={showFullFactcheck}
            />
          </div>
        )}

        {/* Fallacies */}
        {node.fallacies.length > 0 && (
          <div className="space-y-2">
            <span className="text-xs font-semibold text-red-400 uppercase tracking-wider">
              Fallacies Detected ({node.fallacies.length})
            </span>
            {node.fallacies.map((f, i) => (
              <div
                key={i}
                className="bg-red-950/20 border border-red-900/30 rounded-lg p-3 space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-red-300 capitalize">
                    {f.fallacy_type.replace(/_/g, " ")}
                  </span>
                  <span
                    className="text-xs px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor:
                        f.severity >= 0.7 ? "#7f1d1d" :
                        f.severity >= 0.4 ? "#78350f" : "#713f12",
                      color:
                        f.severity >= 0.7 ? "#fca5a5" :
                        f.severity >= 0.4 ? "#fbbf24" : "#fde68a",
                    }}
                  >
                    {(f.severity * 100).toFixed(0)}%
                  </span>
                </div>
                {f.socratic_question && (
                  <p className="text-blue-300 italic text-xs leading-relaxed">
                    💭 {f.socratic_question}
                  </p>
                )}
                {f.explanation && (
                  <p className="text-gray-400 text-xs leading-relaxed">
                    {f.explanation}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
