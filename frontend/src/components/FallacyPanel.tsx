import React from "react";
import type { FallacyAnnotation } from "../types";

interface FallacyPanelProps {
  fallacies: FallacyAnnotation[];
  onClaimClick?: (claimId: string) => void;
}

/** Human-readable labels for fallacy types */
const FALLACY_LABELS: Record<string, string> = {
  strawman: "Strawman",
  goal_post_moving: "Goal Post Moving",
  circular_reasoning: "Circular Reasoning",
  ad_hominem: "Ad Hominem",
  slippery_slope: "Slippery Slope",
  appeal_to_emotion: "Appeal to Emotion",
  false_dilemma: "False Dilemma",
  red_herring: "Red Herring",
  appeal_to_authority: "Appeal to Authority",
  hasty_generalization: "Hasty Generalization",
  tu_quoque: "Tu Quoque",
  equivocation: "Equivocation",
  none: "None",
};

/** Severity color */
function severityColor(severity: number): string {
  if (severity >= 0.7) return "text-red-400";
  if (severity >= 0.4) return "text-amber-400";
  return "text-yellow-400";
}

/** Severity badge */
function severityBadge(severity: number): string {
  if (severity >= 0.7) return "bg-red-900/50 text-red-300 border-red-700/50";
  if (severity >= 0.4) return "bg-amber-900/50 text-amber-300 border-amber-700/50";
  return "bg-yellow-900/50 text-yellow-300 border-yellow-700/50";
}

/**
 * Panel displaying detected fallacies.
 * In "judge" mode: shows direct verdict with explanation.
 * In "socratic" mode: asks questions to guide the user.
 */
export default function FallacyPanel({
  fallacies,
  onClaimClick,
}: FallacyPanelProps) {
  if (fallacies.length === 0) {
    return (
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Fallacy Detection
        </h3>
        <div className="text-center py-6 text-gray-500 text-sm">
          <svg
            className="w-10 h-10 mx-auto mb-2 opacity-30"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          No fallacies detected
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Fallacy Detection
        <span className="ml-2 px-1.5 py-0.5 bg-red-900/50 text-red-300 rounded text-xs">
          {fallacies.length}
        </span>
      </h3>

      <div className="space-y-3">
        {fallacies.map((fallacy, i) => (
          <div
            key={`${fallacy.claim_id}-${fallacy.fallacy_type}-${i}`}
            className="animate-fade-in border border-gray-800 rounded-lg p-3 hover:border-gray-700 transition-colors"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold text-sm text-gray-200">
                {FALLACY_LABELS[fallacy.fallacy_type] || fallacy.fallacy_type}
              </span>
              <span
                className={`text-xs px-2 py-0.5 rounded-full border ${severityBadge(
                  fallacy.severity
                )}`}
              >
                {(fallacy.severity * 100).toFixed(0)}%
              </span>
            </div>

            {/* Socratic question */}
            {fallacy.socratic_question && (
              <div className="bg-blue-950/30 border border-blue-800/30 rounded-md p-2.5 mt-1">
                <p className="text-sm text-blue-300 italic">
                  💭 {fallacy.socratic_question}
                </p>
              </div>
            )}

            {/* Explanation */}
            {fallacy.explanation && (
              <details className="mt-2">
                <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400">
                  Show explanation
                </summary>
                <p className="text-sm text-gray-400 mt-1 leading-relaxed">
                  {fallacy.explanation}
                </p>
              </details>
            )}

            {/* Claim link */}
            <div className="mt-2 flex items-center gap-2">
              <button
                onClick={() => onClaimClick?.(fallacy.claim_id)}
                className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
              >
                → Claim {fallacy.claim_id}
              </button>
              {fallacy.related_claim_ids.length > 0 && (
                <span className="text-xs text-gray-600">
                  + {fallacy.related_claim_ids.length} related
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
