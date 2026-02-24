import React from "react";
import type { FactCheckVerdict, FactCheckResult } from "../types";
import { VERDICT_COLORS, VERDICT_ICONS } from "../types";

interface FactCheckBadgeProps {
  verdict: FactCheckVerdict;
  factcheck?: FactCheckResult | null;
  // Legacy props (kept for backward compat)
  confidence?: number;
  sources?: string[];
  explanation?: string;
  compact?: boolean;
  expanded?: boolean;
}

const VERDICT_LABELS: Record<FactCheckVerdict, string> = {
  supported: "Supported",
  refuted: "Refuted",
  unverifiable: "Unverifiable",
  partially_true: "Partially True",
  pending: "Pending",
};

/**
 * Badge component showing the fact-check verdict for a claim.
 * Compact mode: small colored circle with tooltip.
 * Full mode: card with verdict, confidence, full explanation, and source links.
 */
export default function FactCheckBadge({
  verdict,
  factcheck,
  confidence: confidenceProp,
  sources: sourcesProp,
  explanation: explanationProp,
  compact = false,
  expanded = false,
}: FactCheckBadgeProps) {
  const color = VERDICT_COLORS[verdict];
  const icon = VERDICT_ICONS[verdict];
  const label = VERDICT_LABELS[verdict];

  // Prefer factcheck object fields, fall back to legacy props
  const confidence = factcheck?.confidence ?? confidenceProp;
  const sources = factcheck?.sources ?? sourcesProp ?? [];
  const explanation = factcheck?.explanation ?? explanationProp ?? "";

  if (compact) {
    return (
      <span
        className="inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold cursor-help"
        style={{
          backgroundColor: `${color}20`,
          color: color,
          border: `1px solid ${color}40`,
        }}
        title={`Fact-check: ${label}${explanation ? " — " + explanation.slice(0, 100) : ""}`}
      >
        {icon}
      </span>
    );
  }

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{
        backgroundColor: `${color}10`,
        borderColor: `${color}30`,
      }}
    >
      {/* Verdict header */}
      <div className="flex items-center gap-2 px-3 py-2">
        <span
          className="inline-flex items-center justify-center w-6 h-6 rounded-full text-sm font-bold shrink-0"
          style={{ backgroundColor: `${color}20`, color }}
        >
          {icon}
        </span>
        <span className="font-semibold text-sm" style={{ color }}>
          {label}
        </span>
        {confidence != null && confidence > 0 && (
          <span className="text-xs text-gray-500 ml-auto shrink-0">
            {(confidence * 100).toFixed(0)}% confidence
          </span>
        )}
      </div>

      {/* Explanation — always shown in full */}
      {explanation && (
        <div className="px-3 pb-2">
          <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
            {explanation}
          </p>
        </div>
      )}

      {/* Sources */}
      {sources.length > 0 && (
        <div className="px-3 pb-3 border-t border-gray-800/50 pt-2">
          <span className="text-xs text-gray-500 block mb-1">Sources:</span>
          <div className="space-y-1">
            {sources.map((src, i) => {
              let hostname = src;
              try { hostname = new URL(src).hostname; } catch {}
              return (
                <a
                  key={i}
                  href={src}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-xs text-blue-400 hover:text-blue-300 underline truncate"
                  title={src}
                >
                  {hostname}
                </a>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
