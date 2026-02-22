import React from "react";
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

/**
 * Detail panel shown when a node is selected in the graph.
 * Displays claim text, metadata, fallacies, and fact-check status.
 */
export default function NodeDetail({ selected, onClose }: NodeDetailProps) {
  if (!selected) return null;

  const { node } = selected;

  return (
    <div className="animate-fade-in bg-gray-900 border border-gray-700 rounded-lg p-4 shadow-xl">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <span className="text-xs font-mono text-gray-500">{node.id}</span>
          <span className="mx-2 text-gray-700">·</span>
          <span className="text-xs px-2 py-0.5 bg-gray-800 rounded text-gray-400">
            {CLAIM_TYPE_LABELS[node.claim_type] || node.claim_type}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-300 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Speaker */}
      <div className="text-xs text-gray-500 mb-2">
        Speaker: <span className="text-gray-300 font-medium">{node.speaker.replace("SPEAKER_", "Speaker ")}</span>
        <span className="mx-2">·</span>
        {node.timestamp_start.toFixed(1)}s – {node.timestamp_end.toFixed(1)}s
      </div>

      {/* Claim text */}
      <p className="text-sm text-gray-200 leading-relaxed mb-3 bg-gray-800/50 rounded p-2.5">
        "{node.label}"
      </p>

      {/* Confidence */}
      <div className="flex items-center gap-3 mb-3 text-xs">
        <span className="text-gray-500">Confidence:</span>
        <div className="flex-1 bg-gray-800 rounded-full h-1.5">
          <div
            className="h-1.5 rounded-full bg-blue-500"
            style={{ width: `${node.confidence * 100}%` }}
          />
        </div>
        <span className="text-gray-400">{(node.confidence * 100).toFixed(0)}%</span>
      </div>

      {/* Fact-check */}
      {node.is_factual && node.factcheck_verdict !== "pending" && (
        <div className="mb-3">
          <FactCheckBadge verdict={node.factcheck_verdict} />
        </div>
      )}

      {/* Fallacies */}
      {node.fallacies.length > 0 && (
        <div className="space-y-2">
          <span className="text-xs font-semibold text-red-400 uppercase tracking-wider">
            Fallacies Detected
          </span>
          {node.fallacies.map((f, i) => (
            <div
              key={i}
              className="bg-red-950/20 border border-red-900/30 rounded p-2.5 text-sm"
            >
              <span className="font-medium text-red-300 capitalize">
                {f.fallacy_type.replace(/_/g, " ")}
              </span>
              {f.socratic_question && (
                <p className="text-blue-300 italic mt-1 text-xs">
                  💭 {f.socratic_question}
                </p>
              )}
              {f.explanation && (
                <p className="text-gray-400 mt-1 text-xs">{f.explanation}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
