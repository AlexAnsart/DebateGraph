import React, { useState, useCallback, useMemo } from "react";
import type {
  GraphSnapshot,
  TranscriptionResult,
  SelectedNode,
  FallacyAnnotation,
} from "./types";
import { uploadFile, runDemo, loadLatestSnapshot } from "./api";
import GraphView from "./components/GraphView";
import WaveformView from "./components/WaveformView";
import FallacyPanel from "./components/FallacyPanel";
import RigorScore from "./components/RigorScore";
import NodeDetail from "./components/NodeDetail";
import UploadPanel from "./components/UploadPanel";

/**
 * Main application component.
 * Layout: Left sidebar (upload + controls) | Center (graph) | Right sidebar (analysis)
 * Bottom: Waveform + transcript
 */
export default function App() {
  // ─── State ──────────────────────────────────────────────
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [transcription, setTranscription] = useState<TranscriptionResult | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState<number>(0);

  // ─── Derived Data ───────────────────────────────────────
  const allFallacies = useMemo<FallacyAnnotation[]>(() => {
    if (!graph) return [];
    return graph.nodes.flatMap((n) => n.fallacies);
  }, [graph]);

  // ─── Handlers ───────────────────────────────────────────

  const handleUpload = useCallback(async (file: File) => {
    setIsLoading(true);
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);

    try {
      // Create a local URL for the audio waveform
      const url = URL.createObjectURL(file);
      setAudioUrl(url);

      const response = await uploadFile(file);

      // Poll for status
      const pollStatus = async (jobId: string) => {
        const maxAttempts = 120; // 2 minutes max
        for (let i = 0; i < maxAttempts; i++) {
          await new Promise((r) => setTimeout(r, 1000));
          try {
            const res = await fetch(`/api/status/${jobId}`);
            const status = await res.json();

            if (status.status === "complete" && status.graph) {
              setGraph(status.graph);
              if (status.transcription) {
                setTranscription(status.transcription);
              }
              setIsLoading(false);
              return;
            }

            if (status.status === "error") {
              setError(status.error || "Analysis failed");
              setIsLoading(false);
              return;
            }
          } catch {
            // Continue polling
          }
        }
        setError("Analysis timed out");
        setIsLoading(false);
      };

      pollStatus(response.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setIsLoading(false);
    }
  }, []);

  const handleDemo = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setAudioUrl(null);

    try {
      const result = await runDemo();
      setGraph(result.graph);
      if (result.transcription) setTranscription(result.transcription);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo failed");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleLoadLatest = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setAudioUrl(null);

    try {
      const result = await loadLatestSnapshot();
      setGraph(result.graph);
      if (result.transcription) setTranscription(result.transcription);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load snapshot");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleNodeSelect = useCallback((selected: SelectedNode | null) => {
    setSelectedNode(selected);
  }, []);

  const handleTimeUpdate = useCallback((time: number) => {
    setCurrentTime(time);
  }, []);

  const handleClaimClick = useCallback((claimId: string) => {
    if (!graph) return;
    const node = graph.nodes.find((n) => n.id === claimId);
    if (node) {
      setSelectedNode({
        node,
        position: { x: 0, y: 0 },
      });
    }
  }, [graph]);

  // ─── Render ─────────────────────────────────────────────

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-white tracking-tight">
            <span className="text-blue-400">Debate</span>Graph
          </h1>
          <span className="text-xs text-gray-600 font-mono">v0.2</span>
        </div>

        <div className="flex items-center gap-4">
          {/* Stats */}
          {graph && (
            <div className="flex items-center gap-3 text-xs text-gray-500">
              <span>{graph.nodes.length} claims</span>
              <span>{graph.edges.length} relations</span>
              <span>{allFallacies.length} fallacies</span>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <aside className="w-80 bg-gray-950 border-r border-gray-800 p-4 overflow-y-auto shrink-0">
          <UploadPanel
            onUpload={handleUpload}
            onDemo={handleDemo}
            onLoadLatest={handleLoadLatest}
            isLoading={isLoading}
          />

          {/* Error display */}
          {error && (
            <div className="mt-4 bg-red-950/30 border border-red-900/50 rounded-lg p-3 text-sm text-red-300">
              <span className="font-medium">Error:</span> {error}
            </div>
          )}

          {/* Loading indicator */}
          {isLoading && (
            <div className="mt-4 text-center py-8">
              <svg className="animate-spin w-8 h-8 mx-auto text-blue-400 mb-3" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <p className="text-sm text-gray-400">Analyzing debate...</p>
              <p className="text-xs text-gray-600 mt-1">
                Transcribing → Extracting claims → Detecting fallacies
              </p>
            </div>
          )}

          {/* Rigor Scores */}
          {graph && graph.rigor_scores.length > 0 && (
            <div className="mt-4">
              <RigorScore scores={graph.rigor_scores} />
            </div>
          )}
        </aside>

        {/* Center: Graph */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 relative">
            <GraphView
              graph={graph}
              onNodeSelect={handleNodeSelect}
              highlightTimestamp={currentTime}
            />

            {/* Node Detail Overlay */}
            {selectedNode && (
              <div className="absolute top-4 right-4 w-80 z-10">
                <NodeDetail
                  selected={selectedNode}
                  onClose={() => setSelectedNode(null)}
                />
              </div>
            )}
          </div>

          {/* Bottom: Waveform */}
          <div className="shrink-0 border-t border-gray-800 p-3 bg-gray-950 max-h-80 overflow-y-auto">
            <WaveformView
              audioUrl={audioUrl}
              transcription={transcription}
              onTimeUpdate={handleTimeUpdate}
            />
          </div>
        </main>

        {/* Right Sidebar */}
        <aside className="w-80 bg-gray-950 border-l border-gray-800 p-4 overflow-y-auto shrink-0">
          <FallacyPanel
            fallacies={allFallacies}
            onClaimClick={handleClaimClick}
          />

          {/* Cycles detected */}
          {graph && graph.cycles_detected.length > 0 && (
            <div className="mt-4 bg-purple-950/20 border border-purple-900/30 rounded-lg p-4">
              <h3 className="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-2">
                Circular Reasoning Detected
              </h3>
              {graph.cycles_detected.map((cycle, i) => (
                <div key={i} className="text-xs text-gray-400 mb-1">
                  {cycle.join(" → ")} → {cycle[0]}
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
