import React, { useState, useCallback, useMemo, useRef } from "react";
import type {
  GraphSnapshot,
  TranscriptionResult,
  SelectedNode,
  FallacyAnnotation,
} from "./types";
import { uploadFile, runDemo, loadSnapshot } from "./api";
import GraphView from "./components/GraphView";
import WaveformView from "./components/WaveformView";
import FallacyPanel from "./components/FallacyPanel";
import RigorScore from "./components/RigorScore";
import NodeDetail from "./components/NodeDetail";
import UploadPanel from "./components/UploadPanel";
import VideoPlayer from "./components/VideoPlayer";
import { useLiveStream } from "./hooks/useLiveStream";
import { useAudioCapture } from "./hooks/useAudioCapture";
import { useVideoStream } from "./hooks/useVideoStream";

type AppMode = "idle" | "upload" | "live" | "video";

export default function App() {
  // ── State ──────────────────────────────────────────────────────────────────
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [transcription, setTranscription] = useState<TranscriptionResult | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [mode, setMode] = useState<AppMode>("idle");
  const [graphFullscreen, setGraphFullscreen] = useState(false);

  // ── Live streaming ─────────────────────────────────────────────────────────
  const liveStream = useLiveStream({
    enableFactcheck: true,
    enableLlmFallacy: true,
    onGraphUpdate: useCallback((g: GraphSnapshot, t: TranscriptionResult | null) => {
      setGraph(g);
      if (t) setTranscription(t);
    }, []),
    onError: useCallback((err: string) => {
      setError(err);
    }, []),
  });

  const chunkIndexRef = useRef(0);

  const audioCapture = useAudioCapture({
    chunkDurationMs: 15000,
    onChunk: useCallback(
      (chunk: ArrayBuffer, chunkIndex: number, timeOffset: number) => {
        liveStream.sendChunk(chunk, chunkIndex, timeOffset);
      },
      [liveStream.sendChunk]
    ),
    onError: useCallback((err: string) => {
      setError(err);
    }, []),
  });

  // ── Video streaming ────────────────────────────────────────────────────────
  const videoStream = useVideoStream({
    chunkDurationMs: 15000,
    onChunk: useCallback(
      (chunk: ArrayBuffer, chunkIndex: number, timeOffset: number) => {
        liveStream.sendChunk(chunk, chunkIndex, timeOffset);
      },
      [liveStream.sendChunk]
    ),
    onError: useCallback((err: string) => {
      setError(err);
    }, []),
    onComplete: useCallback(() => {
      // Video ended — finalize the stream
      liveStream.stop();
    }, [liveStream]),
  });

  // ── Derived data ───────────────────────────────────────────────────────────
  const allFallacies = useMemo<FallacyAnnotation[]>(() => {
    if (!graph) return [];
    return graph.nodes.flatMap((n) => n.fallacies);
  }, [graph]);

  const isLive = mode === "live" && audioCapture.state.isRecording;
  const isVideoMode = mode === "video";
  const isVideoPlaying = isVideoMode && videoStream.state.status === "playing";

  // ── Helpers ────────────────────────────────────────────────────────────────

  const isVideoFile = (file: File): boolean => {
    return file.type.startsWith("video/") ||
      /\.(mp4|webm|avi|mkv|mov|m4v)$/i.test(file.name);
  };

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleVideoUpload = useCallback(async (file: File) => {
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setAudioUrl(null);
    setMode("video");
    setGraphFullscreen(false);

    // Load video into the player
    const url = videoStream.loadVideo(file);
    setVideoUrl(url);

    // Connect WebSocket for live streaming
    try {
      liveStream.reset();
      await liveStream.connect();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to connect streaming";
      setError(msg);
      setMode("idle");
    }
  }, [videoStream, liveStream]);

  const handleUpload = useCallback(async (file: File) => {
    // Check if it's a video file — use video mode
    if (isVideoFile(file)) {
      handleVideoUpload(file);
      return;
    }

    setIsLoading(true);
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setVideoUrl(null);
    setMode("upload");

    try {
      const url = URL.createObjectURL(file);
      setAudioUrl(url);

      const response = await uploadFile(file);

      const pollStatus = async (jobId: string) => {
        const maxAttempts = 180;
        for (let i = 0; i < maxAttempts; i++) {
          await new Promise((r) => setTimeout(r, 1000));
          try {
            const res = await fetch(`/api/status/${jobId}`);
            const status = await res.json();

            if (status.status === "complete" && status.graph) {
              setGraph(status.graph);
              if (status.transcription) setTranscription(status.transcription);
              setIsLoading(false);
              setMode("idle");
              return;
            }

            if (status.status === "error") {
              setError(status.error || "Analysis failed");
              setIsLoading(false);
              setMode("idle");
              return;
            }
          } catch {
            // Continue polling
          }
        }
        setError("Analysis timed out");
        setIsLoading(false);
        setMode("idle");
      };

      pollStatus(response.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setIsLoading(false);
      setMode("idle");
    }
  }, [handleVideoUpload]);

  const handleDemo = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setAudioUrl(null);
    setVideoUrl(null);
    setMode("upload");

    try {
      const result = await runDemo();
      setGraph(result.graph);
      if (result.transcription) setTranscription(result.transcription);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo failed");
    } finally {
      setIsLoading(false);
      setMode("idle");
    }
  }, []);

  const handleLoadSnapshot = useCallback(async (jobId: string) => {
    setIsLoading(true);
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setAudioUrl(null);
    setVideoUrl(null);

    try {
      const result = await loadSnapshot(jobId);
      setGraph(result.graph);
      if (result.transcription) setTranscription(result.transcription);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load snapshot from DB");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleStartLive = useCallback(async () => {
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setAudioUrl(null);
    setVideoUrl(null);
    setMode("live");
    liveStream.reset();
    chunkIndexRef.current = 0;

    try {
      await liveStream.connect();
      await audioCapture.start();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to start live stream";
      setError(msg);
      setMode("idle");
    }
  }, [liveStream, audioCapture]);

  const handleStopLive = useCallback(async () => {
    await audioCapture.stop();
    liveStream.stop();
    setMode("idle");
  }, [audioCapture, liveStream]);

  // Video controls
  const handleVideoPlay = useCallback(() => {
    videoStream.play();
  }, [videoStream]);

  const handleVideoPause = useCallback(() => {
    videoStream.pause();
  }, [videoStream]);

  const handleVideoStop = useCallback(async () => {
    await videoStream.stop();
    liveStream.stop();
    setMode("idle");
  }, [videoStream, liveStream]);

  const handleVideoEnded = useCallback(async () => {
    await videoStream.stop();
    // liveStream.stop() called by onComplete in videoStream
  }, [videoStream]);

  const handleVideoReady = useCallback((video: HTMLVideoElement) => {
    videoStream.onVideoReady(video);
  }, [videoStream]);

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
      setSelectedNode({ node, position: { x: 0, y: 0 } });
    }
  }, [graph]);

  // ── Live stats for UploadPanel ─────────────────────────────────────────────
  const liveStats = useMemo(() => ({
    nodes: liveStream.state.nodeCount,
    chunks: liveStream.state.chunkCount,
    duration: audioCapture.state.duration,
    audioLevel: audioCapture.state.audioLevel,
  }), [liveStream.state, audioCapture.state]);

  // ── Status bar text ────────────────────────────────────────────────────────
  const statusText = useMemo(() => {
    if (mode === "video") {
      const vs = videoStream.state;
      if (vs.status === "loading") return "Loading video…";
      if (vs.status === "playing") return `Analyzing video — ${liveStream.state.nodeCount} nodes`;
      if (vs.status === "paused") return `Paused — ${liveStream.state.nodeCount} nodes`;
      if (vs.status === "complete") return "Video analysis complete";
    }
    if (mode === "live") {
      const s = liveStream.state.status;
      if (s === "connecting") return "Connecting…";
      if (s === "recording") return `Recording — ${liveStats.nodes} nodes`;
      if (s === "processing") return "Processing chunk…";
      if (s === "finalizing") return "Finalizing…";
      if (s === "complete") return "Stream complete";
    }
    if (isLoading) return "Analyzing…";
    if (graph) return `${graph.nodes.length} claims · ${graph.edges.length} relations · ${allFallacies.length} fallacies`;
    return null;
  }, [mode, videoStream.state, liveStream.state.status, liveStream.state.nodeCount, liveStats.nodes, isLoading, graph, allFallacies.length]);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-white tracking-tight">
            <span className="text-blue-400">Debate</span>Graph
          </h1>
          <span className="text-xs text-gray-600 font-mono">v0.4</span>
          {(mode === "live" || isVideoPlaying) && (
            <span className="flex items-center gap-1.5 px-2 py-0.5 bg-red-900/30 border border-red-800 rounded-full text-xs text-red-400">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              LIVE
            </span>
          )}
          {isVideoMode && (
            <span className="flex items-center gap-1.5 px-2 py-0.5 bg-purple-900/30 border border-purple-800 rounded-full text-xs text-purple-400">
              VIDEO
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          {statusText && (
            <span className="text-xs text-gray-400">{statusText}</span>
          )}
          {/* Video mode controls */}
          {isVideoMode && (
            <>
              <button
                onClick={() => setGraphFullscreen(!graphFullscreen)}
                className="px-2 py-1 text-xs text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 rounded transition-colors"
                title={graphFullscreen ? "Show video + graph" : "Full graph view"}
              >
                {graphFullscreen ? "Split View" : "Full Graph"}
              </button>
              <button
                onClick={async () => {
                  await videoStream.stop();
                  liveStream.stop();
                  setMode("idle");
                  setVideoUrl(null);
                  setGraphFullscreen(false);
                }}
                className="px-2 py-1 text-xs text-gray-400 hover:text-red-400 border border-gray-700 hover:border-red-700 rounded transition-colors"
                title="Exit video mode"
              >
                Close
              </button>
            </>
          )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar — hidden in video mode unless fullscreen graph */}
        {(!isVideoMode || graphFullscreen) && (
          <aside className="w-80 bg-gray-950 border-r border-gray-800 p-4 overflow-y-auto shrink-0">
            <UploadPanel
              onUpload={handleUpload}
              onDemo={handleDemo}
              onLoadSnapshot={handleLoadSnapshot}
              onStartLive={handleStartLive}
              onStopLive={handleStopLive}
              isLoading={isLoading}
              isLive={isLive}
              liveStats={liveStats}
            />

            {error && (
              <div className="mt-4 bg-red-950/30 border border-red-900/50 rounded-lg p-3 text-sm text-red-300">
                <span className="font-medium">Error:</span> {error}
              </div>
            )}

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

            {graph && graph.rigor_scores.length > 0 && (
              <div className="mt-4">
                <RigorScore scores={graph.rigor_scores} />
              </div>
            )}
          </aside>
        )}

        {/* Video mode: split view (video left, graph right) */}
        {isVideoMode && !graphFullscreen ? (
          <div className="flex-1 flex overflow-hidden">
            {/* Left: Video Player */}
            <div className="w-1/2 border-r border-gray-800 flex flex-col overflow-hidden">
              {videoUrl && (
                <VideoPlayer
                  videoUrl={videoUrl}
                  isPlaying={videoStream.state.status === "playing"}
                  currentTime={videoStream.state.currentTime}
                  duration={videoStream.state.duration}
                  onVideoReady={handleVideoReady}
                  onPlay={handleVideoPlay}
                  onPause={handleVideoPause}
                  onStop={handleVideoStop}
                  onEnded={handleVideoEnded}
                  chunkCount={videoStream.state.chunkCount}
                  nodeCount={liveStream.state.nodeCount}
                />
              )}

              {/* Transcript below video */}
              {transcription && transcription.segments.length > 0 && (
                <div className="shrink-0 border-t border-gray-800 bg-gray-950 max-h-48 overflow-y-auto p-3">
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                    Transcript
                  </h3>
                  <div className="space-y-1">
                    {transcription.segments.map((seg, i) => (
                      <div key={i} className="flex gap-2 text-xs p-1.5 rounded hover:bg-gray-800/50">
                        <span className="text-blue-400 font-mono font-bold shrink-0">
                          {seg.speaker.replace("SPEAKER_", "S")}
                        </span>
                        <span className="text-gray-300">{seg.text}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Error display in video mode */}
              {error && (
                <div className="shrink-0 p-3 bg-red-950/30 border-t border-red-900/50 text-sm text-red-300">
                  <span className="font-medium">Error:</span> {error}
                </div>
              )}
            </div>

            {/* Right: Graph */}
            <div className="w-1/2 flex flex-col overflow-hidden">
              <div className="flex-1 relative">
                <GraphView
                  graph={graph}
                  onNodeSelect={handleNodeSelect}
                  highlightTimestamp={videoStream.state.currentTime}
                />

                {selectedNode && (
                  <div className="absolute top-4 right-4 w-80 z-10 max-h-[calc(100vh-200px)]">
                    <NodeDetail
                      selected={selectedNode}
                      onClose={() => setSelectedNode(null)}
                    />
                  </div>
                )}

                {/* Waiting overlay */}
                {!graph && videoStream.state.status !== "idle" && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-center">
                      <div className="w-12 h-12 rounded-full bg-purple-900/20 border-2 border-purple-700 flex items-center justify-center mx-auto mb-3 animate-pulse">
                        <svg className="w-6 h-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                      </div>
                      <p className="text-gray-400 text-sm">Press play to start analysis</p>
                      <p className="text-gray-600 text-xs mt-1">Graph builds as video plays</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Fallacy summary in video mode */}
              {allFallacies.length > 0 && (
                <div className="shrink-0 border-t border-gray-800 bg-gray-950 max-h-32 overflow-y-auto p-3">
                  <FallacyPanel fallacies={allFallacies} onClaimClick={handleClaimClick} />
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Normal mode: center graph + sidebars */
          <>
            <main className="flex-1 flex flex-col overflow-hidden">
              <div className="flex-1 relative">
                <GraphView
                  graph={graph}
                  onNodeSelect={handleNodeSelect}
                  highlightTimestamp={currentTime}
                />

                {selectedNode && (
                  <div className="absolute top-4 right-4 w-96 z-10 max-h-[calc(100vh-200px)]">
                    <NodeDetail
                      selected={selectedNode}
                      onClose={() => setSelectedNode(null)}
                    />
                  </div>
                )}

                {/* Live overlay — shows when recording but no graph yet */}
                {mode === "live" && !graph && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-center">
                      <div className="w-16 h-16 rounded-full bg-red-900/20 border-2 border-red-700 flex items-center justify-center mx-auto mb-4 animate-pulse">
                        <svg className="w-8 h-8 text-red-400" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                          <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                        </svg>
                      </div>
                      <p className="text-gray-400 text-sm">Listening…</p>
                      <p className="text-gray-600 text-xs mt-1">
                        Graph will appear after the first 15s chunk
                      </p>
                    </div>
                  </div>
                )}

                {/* Video fullscreen mode: also show graph-only overlay info */}
                {isVideoMode && graphFullscreen && !graph && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-center">
                      <p className="text-gray-400 text-sm">Graph view (fullscreen)</p>
                      <p className="text-gray-600 text-xs mt-1">Switch to split view to see the video</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Bottom: Waveform (not in video fullscreen mode) */}
              {!isVideoMode && (
                <div className="shrink-0 border-t border-gray-800 p-3 bg-gray-950 max-h-80 overflow-y-auto">
                  <WaveformView
                    audioUrl={audioUrl}
                    transcription={transcription}
                    onTimeUpdate={handleTimeUpdate}
                  />
                </div>
              )}
            </main>

            {/* Right Sidebar */}
            <aside className="w-80 bg-gray-950 border-l border-gray-800 p-4 overflow-y-auto shrink-0">
              <FallacyPanel
                fallacies={allFallacies}
                onClaimClick={handleClaimClick}
              />

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
          </>
        )}
      </div>
    </div>
  );
}
