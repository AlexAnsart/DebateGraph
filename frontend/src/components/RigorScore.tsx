import React from "react";
import type { SpeakerRigorScore } from "../types";
import { SPEAKER_COLORS } from "../types";

interface RigorScoreProps {
  scores: SpeakerRigorScore[];
}

function scoreColor(score: number): string {
  if (score >= 0.7) return "#22c55e";
  if (score >= 0.4) return "#f59e0b";
  return "#ef4444";
}

function MetricRow({
  label,
  value,
  negative = false,
}: {
  label: string;
  value: string;
  negative?: boolean;
}) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className={negative ? "text-red-400" : "text-gray-300"}>
        {value}
      </span>
    </div>
  );
}

/**
 * Composite rigor score display for each debate participant.
 * Formula: R = 0.4 * supported_ratio - 0.3 * fallacy_penalty
 *        + 0.2 * factcheck_rate + 0.1 * consistency
 */
export default function RigorScore({ scores }: RigorScoreProps) {
  if (scores.length === 0) {
    return null;
  }

  // Sort by overall score descending
  const sorted = [...scores].sort((a, b) => b.overall_score - a.overall_score);

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Rigor Scores
      </h3>

      <div className="space-y-4">
        {sorted.map((score, i) => {
          const color = SPEAKER_COLORS[i % SPEAKER_COLORS.length];
          const pct = Math.round(score.overall_score * 100);

          return (
            <div key={score.speaker} className="space-y-2">
              {/* Speaker header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm font-medium text-gray-200">
                    {score.speaker.replace("SPEAKER_", "Speaker ")}
                  </span>
                </div>
                <span
                  className="text-lg font-bold"
                  style={{ color: scoreColor(score.overall_score) }}
                >
                  {pct}%
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-gray-800 rounded-full h-2">
                <div
                  className="h-2 rounded-full transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: scoreColor(score.overall_score),
                  }}
                />
              </div>

              {/* Breakdown */}
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <MetricRow
                  label="Supported claims"
                  value={`${(score.supported_ratio * 100).toFixed(0)}%`}
                />
                <MetricRow
                  label="Fallacies"
                  value={String(score.fallacy_count)}
                  negative={score.fallacy_count > 0}
                />
                <MetricRow
                  label="Fact-check rate"
                  value={`${(score.factcheck_positive_rate * 100).toFixed(0)}%`}
                />
                <MetricRow
                  label="Consistency"
                  value={`${(score.internal_consistency * 100).toFixed(0)}%`}
                />
                <MetricRow
                  label="Response rate"
                  value={`${(score.direct_response_rate * 100).toFixed(0)}%`}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
