import React from "react";
import type { FactCheckVerdict } from "../types";
import { VERDICT_COLORS, VERDICT_ICONS } from "../types";

interface FactCheckBadgeProps {
  verdict: FactCheckVerdict;
  confidence?: number;
  sources?: string[];
  explanation?: string;
  compact?: boolean;
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
 * Compact mode shows just the icon; full mode shows label + details.
 */
export default function FactCheckBadge({
  verdict,
  confidence,
  sources,
  explanation,
  compact = false,
}: FactCheckBadgeProps) {
  const color = VERDICT_COLORS[verdict];
  const icon = VERDICT_ICONS[verdict];
  const label = VERDICT_LABELS[verdict];

  if (compact) {
    return (
      <span
        className="inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold"
        style={{
          backgroundColor: `${color}20`,
          color: color,
          border: `1px solid ${color}40`,
        }}
        title={`Fact-check: ${label}`}
      >
        {icon}
      </span>
    );
  }

  return (
    <div
      className="rounded-lg p-3 border"
      style={{
        backgroundColor: `${color}10`,
        borderColor: `${color}30`,
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span
          className="inline-flex items-center justify-center w-6 h-6 rounded-full text-sm font-bold"
          style={{
            backgroundColor: `${color}20`,
            color: color,
          }}
        >
          {icon}
        </span>
        <span className="font-semibold text-sm" style={{ color }}>
          {label}
        </span>
        {confidence != null && confidence > 0 && (
          <span className="text-xs text-gray-500 ml-auto">
            {(confidence * 100).toFixed(0)}% confidence
          </span>
        )}
      </div>

      {explanation && (
        <p className="text-sm text-gray-400 mt-1 leading-relaxed">
          {explanation}
        </p>
      )}

      {sources && sources.length > 0 && (
        <div className="mt-2">
          <span className="text-xs text-gray-500">Sources:</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {sources.map((src, i) => (
              <a
                key={i}
                href={src}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-400 hover:text-blue-300 underline truncate max-w-[200px]"
              >
                {new URL(src).hostname}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
