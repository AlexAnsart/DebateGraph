import React, { useState, useCallback, useMemo, useRef } from "react";
import type {
  GraphSnapshot,
  TranscriptionResult,
  SelectedNode,
  FallacyAnnotation,
} from "./types";
import { loadSnapshot, uploadFile, getJobStatus } from "./api";
import GraphView from "./components/GraphView";
import WaveformView from "./components/WaveformView";
import FallacyPanel from "./components/FallacyPanel";
import RigorScore from "./components/RigorScore";
import NodeDetail from "./components/NodeDetail";
import UploadPanel from "./components/UploadPanel";
import VideoPlayer from "./components/VideoPlayer";
import VideoReviewPlayer from "./components/VideoReviewPlayer";
import type { VideoReviewPlayerHandle } from "./components/VideoReviewPlayer";
import { useLiveStream } from "./hooks/useLiveStream";
import { useVideoStream } from "./hooks/useVideoStream";
import { useAudioFileStream } from "./hooks/useAudioFileStream";
import { SPEAKER_COLORS } from "./types";

type AppMode = "idle" | "upload" | "video" | "audio-stream" | "video-review";

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

  // ── Video-review processing state ────────────────────────────────────────
  const [processingJobId, setProcessingJobId] = useState<string | null>(null);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [processingStatus, setProcessingStatus] = useState("");
  const videoReviewRef = useRef<VideoReviewPlayerHandle>(null);

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

  // ── Video streaming (legacy real-time mode) ──────────────────────────────
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
      liveStream.stop();
    }, [liveStream]),
  });

  // ── Audio file streaming (real-time analysis of uploaded audio) ─────────────
  const audioFileStream = useAudioFileStream({
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
      liveStream.stop();
    }, [liveStream]),
  });

  // ── Derived data ───────────────────────────────────────────────────────────
  const allFallacies = useMemo<FallacyAnnotation[]>(() => {
    if (!graph) return [];
    return graph.nodes.flatMap((n) => n.fallacies);
  }, [graph]);

  const isVideoMode = mode === "video";
  const isVideoReviewMode = mode === "video-review";
  const isAudioStreamMode = mode === "audio-stream";
  const isVideoPlaying = isVideoMode && videoStream.state.status === "playing";
  const isAudioStreamPlaying = isAudioStreamMode && audioFileStream.state.status === "playing";

  // ── Helpers ────────────────────────────────────────────────────────────────

  const isVideoFile = (file: File): boolean => {
    return file.type.startsWith("video/") ||
      /\.(mp4|webm|avi|mkv|mov|m4v)$/i.test(file.name);
  };

  // ── Polling helper ─────────────────────────────────────────────────────────

  const pollUntilComplete = useCallback(async (
    jobId: string,
  ): Promise<{ graph: GraphSnapshot; transcription: TranscriptionResult | null; media_url: string | null }> => {
    const statusLabels: Record<string, string> = {
      processing: "Starting...",
      transcribing: "Transcribing audio (speaker diarization)...",
      extracting: "Extracting claims & detecting fallacies...",
      complete: "Complete!",
    };

    while (true) {
      const status = await getJobStatus(jobId);
      const label = statusLabels[status.status] || status.status;
      setProcessingProgress(status.progress);
      setProcessingStatus(label);

      if (status.status === "complete") {
        return {
          graph: status.graph!,
          transcription: status.transcription ?? null,
          media_url: status.media_url ?? `/api/media/${jobId}`,
        };
      }
      if (status.status === "error") {
        throw new Error(status.error || "Pipeline error");
      }

      await new Promise((r) => setTimeout(r, 1000));
    }
  }, []);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleUpload = useCallback(async (file: File) => {
    // Upload audio or video → backend transcribes → pipeline → review mode
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setAudioUrl(null);
    setVideoUrl(null);
    setMode("upload");
    setProcessingProgress(0);
    setProcessingStatus("Uploading...");

    try {
      const { job_id } = await uploadFile(file);
      setProcessingJobId(job_id);
      setProcessingStatus("Processing...");

      const result = await pollUntilComplete(job_id);

      setGraph(result.graph);
      if (result.transcription) setTranscription(result.transcription);
      setVideoUrl(result.media_url);
      setCurrentTime(0);
      setMode("video-review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Processing failed");
      setMode("idle");
    } finally {
      setProcessingJobId(null);
      setProcessingProgress(0);
      setProcessingStatus("");
    }
  }, [pollUntilComplete]);

  const handleAudioStreamUpload = useCallback(async (file: File) => {
    setError(null);
    setGraph(null);
    setTranscription(null);
    setSelectedNode(null);
    setVideoUrl(null);
    setMode("audio-stream");

    const url = audioFileStream.loadAudioFile(file);
    setAudioUrl(url);

    try {
      liveStream.reset();
      await liveStream.connect();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to connect streaming";
      setError(msg);
    }
  }, [audioFileStream, liveStream]);


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

      // If media file is available, enter video-review mode
      if (result.media_url) {
        setVideoUrl(result.media_url);
        setCurrentTime(0);
        setMode("video-review");
      } else {
        setMode("idle");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load snapshot from DB");
      setMode("idle");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Video controls (legacy real-time mode)
  const handleVideoPlay = useCallback(() => { videoStream.play(); }, [videoStream]);
  const handleVideoPause = useCallback(() => { videoStream.pause(); }, [videoStream]);
  const handleVideoStop = useCallback(async () => {
    await videoStream.stop();
    liveStream.stop();
    setMode("idle");
  }, [videoStream, liveStream]);
  const handleVideoEnded = useCallback(async () => {
    await videoStream.stop();
  }, [videoStream]);
  const handleVideoReady = useCallback((video: HTMLVideoElement) => {
    videoStream.onVideoReady(video);
  }, [videoStream.onVideoReady]);

  // Audio stream controls
  const handleAudioStreamPlay = useCallback(() => { audioFileStream.play(); }, [audioFileStream.play]);
  const handleAudioStreamPause = useCallback(() => { audioFileStream.pause(); }, [audioFileStream.pause]);
  const handleAudioStreamStop = useCallback(async () => {
    await audioFileStream.stop();
    liveStream.stop();
  }, [audioFileStream, liveStream]);

  // Node selection — show detail panel only; do NOT seek (timeline keeps playing)
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
      if (mode === "video-review" && videoReviewRef.current) {
        videoReviewRef.current.seekTo(node.timestamp_start);
      }
    }
  }, [graph, mode]);

  // Close video-review mode
  const handleCloseReview = useCallback(() => {
    setMode("idle");
    setVideoUrl(null);
    setCurrentTime(0);
    setGraphFullscreen(false);
  }, []);

  // ── Status bar text ────────────────────────────────────────────────────────
  const statusText = useMemo(() => {
    if (mode === "video-review") {
      if (!graph) return null;
      const visible = graph.nodes.filter((n) => n.timestamp_start <= currentTime).length;
      return `${visible} / ${graph.nodes.length} claims · ${graph.edges.length} relations · ${allFallacies.length} fallacies`;
    }
    if (mode === "upload" && processingJobId) {
      return processingStatus;
    }
    if (mode === "video") {
      const vs = videoStream.state;
      if (vs.status === "loading") return "Loading video...";
      if (vs.status === "playing") return `Analyzing video — ${liveStream.state.nodeCount} nodes`;
      if (vs.status === "paused") return `Paused — ${liveStream.state.nodeCount} nodes`;
      if (vs.status === "complete") return "Video analysis complete";
    }
    if (mode === "audio-stream") {
      const as_ = audioFileStream.state;
      if (as_.status === "loading") return "Loading audio...";
      if (as_.status === "playing") return `Analyzing audio — ${liveStream.state.nodeCount} nodes`;
      if (as_.status === "paused") return `Paused — ${liveStream.state.nodeCount} nodes`;
      if (as_.status === "complete") return "Audio analysis complete";
    }
    if (isLoading) return "Analyzing...";
    if (graph) return `${graph.nodes.length} claims · ${graph.edges.length} relations · ${allFallacies.length} fallacies`;
    return null;
  }, [mode, processingJobId, processingStatus, currentTime, videoStream.state, audioFileStream.state, liveStream.state.status, liveStream.state.nodeCount, isLoading, graph, allFallacies.length]);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-white tracking-tight">
            <span className="text-blue-400">Debate</span>Graph
          </h1>
          <span className="text-xs text-gray-600 font-mono">v0.6</span>
          {(isVideoPlaying || isAudioStreamPlaying) && (
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
          {isVideoReviewMode && (
            <span className="flex items-center gap-1.5 px-2 py-0.5 bg-emerald-900/30 border border-emerald-800 rounded-full text-xs text-emerald-400">
              REVIEW
            </span>
          )}
          {isAudioStreamMode && (
            <span className="flex items-center gap-1.5 px-2 py-0.5 bg-blue-900/30 border border-blue-800 rounded-full text-xs text-blue-400">
              STREAMING
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          {statusText && (
            <span className="text-xs text-gray-400">{statusText}</span>
          )}
          {/* Video-review mode controls */}
          {isVideoReviewMode && (
            <>
              <button
                onClick={() => setGraphFullscreen(!graphFullscreen)}
                className="px-2 py-1 text-xs text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 rounded transition-colors"
                title={graphFullscreen ? "Show video + graph" : "Full graph view"}
              >
                {graphFullscreen ? "Split View" : "Full Graph"}
              </button>
              <button
                onClick={handleCloseReview}
                className="px-2 py-1 text-xs text-gray-400 hover:text-red-400 border border-gray-700 hover:border-red-700 rounded transition-colors"
                title="Exit review mode"
              >
                Close
              </button>
            </>
          )}
          {/* Legacy video mode controls */}
          {isVideoMode && (
            <>
              <button
                onClick={() => setGraphFullscreen(!graphFullscreen)}
                className="px-2 py-1 text-xs text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 rounded transition-colors"
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
              >
                Close
              </button>
            </>
          )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">

        {/* ────────── VIDEO-REVIEW MODE: split view ────────── */}
        {isVideoReviewMode && !graphFullscreen ? (
          <div className="flex-1 flex overflow-hidden">
            {/* Left: Video + Transcript */}
            <div className="w-1/2 border-r border-gray-800 flex flex-col overflow-hidden">
              {videoUrl && (
                <VideoReviewPlayer
                  ref={videoReviewRef}
                  videoUrl={videoUrl}
                  onTimeUpdate={handleTimeUpdate}
                  graph={graph}
                />
              )}

              {/* Transcript below video */}
              {transcription && transcription.segments.length > 0 && (
                <div className="shrink-0 border-t border-gray-800 bg-gray-950 max-h-48 overflow-y-auto p-3">
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                    Transcript
                  </h3>
                  <div className="space-y-1">
                    {transcription.segments.map((seg, i) => {
                      const isActive = currentTime >= seg.start && currentTime <= seg.end;
                      const speakers = [...new Set(transcription.segments.map((s) => s.speaker))];
                      const speakerIdx = speakers.indexOf(seg.speaker);
                      const speakerColor = SPEAKER_COLORS[speakerIdx % SPEAKER_COLORS.length];
                      return (
                        <div
                          key={i}
                          className={`flex gap-2 text-xs p-1.5 rounded cursor-pointer hover:bg-gray-800/50 ${
                            isActive ? "bg-blue-950/30 ring-1 ring-blue-800" : ""
                          }`}
                          onClick={() => videoReviewRef.current?.seekTo(seg.start)}
                        >
                          <span
                            className="font-mono font-bold shrink-0"
                            style={{ color: speakerColor }}
                          >
                            {seg.speaker.replace("SPEAKER_", "S")}
                          </span>
                          <span className="text-gray-500 font-mono shrink-0">
                            {Math.floor(seg.start / 60)}:{Math.floor(seg.start % 60).toString().padStart(2, "0")}
                          </span>
                          <span className="text-gray-300">{seg.text}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {error && (
                <div className="shrink-0 p-3 bg-red-950/30 border-t border-red-900/50 text-sm text-red-300">
                  <span className="font-medium">Error:</span> {error}
                </div>
              )}
            </div>

            {/* Right: Graph + panels */}
            <div className="w-1/2 flex flex-col overflow-hidden">
              <div className="flex-1 relative">
                <GraphView
                  graph={graph}
                  onNodeSelect={handleNodeSelect}
                  highlightTimestamp={currentTime}
                  maxTimestamp={currentTime}
                />

                {selectedNode && (
                  <div className="absolute top-4 right-4 w-80 z-10 max-h-[calc(100vh-200px)]">
                    <NodeDetail
                      selected={selectedNode}
                      onClose={() => setSelectedNode(null)}
                    />
                  </div>
                )}
              </div>

              {/* Rigor scores + fallacy summary */}
              {graph && (graph.rigor_scores.length > 0 || allFallacies.length > 0) && (
                <div className="shrink-0 border-t border-gray-800 bg-gray-950 max-h-48 overflow-y-auto p-3 space-y-3">
                  {graph.rigor_scores.length > 0 && (
                    <RigorScore scores={graph.rigor_scores} />
                  )}
                  {allFallacies.length > 0 && (
                    <FallacyPanel fallacies={allFallacies} onClaimClick={handleClaimClick} />
                  )}
                </div>
              )}
            </div>
          </div>

        ) : (isVideoMode || isVideoReviewMode) && !graphFullscreen ? (
          /* Legacy video streaming mode: split view */
          <div className="flex-1 flex overflow-hidden">
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
              {transcription && transcription.segments.length > 0 && (
                <div className="shrink-0 border-t border-gray-800 bg-gray-950 max-h-48 overflow-y-auto p-3">
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Transcript</h3>
                  <div className="space-y-1">
                    {transcription.segments.map((seg, i) => (
                      <div key={i} className="flex gap-2 text-xs p-1.5 rounded hover:bg-gray-800/50">
                        <span className="text-blue-400 font-mono font-bold shrink-0">{seg.speaker.replace("SPEAKER_", "S")}</span>
                        <span className="text-gray-300">{seg.text}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {error && (
                <div className="shrink-0 p-3 bg-red-950/30 border-t border-red-900/50 text-sm text-red-300">
                  <span className="font-medium">Error:</span> {error}
                </div>
              )}
            </div>
            <div className="w-1/2 flex flex-col overflow-hidden">
              <div className="flex-1 relative">
                <GraphView graph={graph} onNodeSelect={handleNodeSelect} highlightTimestamp={videoStream.state.currentTime} />
                {selectedNode && (
                  <div className="absolute top-4 right-4 w-80 z-10 max-h-[calc(100vh-200px)]">
                    <NodeDetail selected={selectedNode} onClose={() => setSelectedNode(null)} />
                  </div>
                )}
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
              {allFallacies.length > 0 && (
                <div className="shrink-0 border-t border-gray-800 bg-gray-950 max-h-32 overflow-y-auto p-3">
                  <FallacyPanel fallacies={allFallacies} onClaimClick={handleClaimClick} />
                </div>
              )}
            </div>
          </div>

        ) : (
          /* ────────── Normal modes: sidebar + center graph + right sidebar ────────── */
          <>
            {/* Left Sidebar */}
            <aside className="w-80 bg-gray-950 border-r border-gray-800 p-4 overflow-y-auto shrink-0">
              <UploadPanel
                onUpload={handleUpload}
                onLoadSnapshot={handleLoadSnapshot}
                isLoading={isLoading || !!processingJobId}
              />

              {/* Processing overlay (video batch upload) */}
              {mode === "upload" && processingJobId && (
                <div className="mt-4 bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-3">
                    Processing Video
                  </h3>
                  <div className="flex items-center gap-3 mb-3">
                    <svg className="animate-spin w-5 h-5 text-emerald-400 shrink-0" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span className="text-sm text-gray-300">{processingStatus}</span>
                  </div>
                  <div className="h-2 bg-gray-800 rounded-full overflow-hidden mb-2">
                    <div
                      className="h-full bg-emerald-500 transition-all duration-500"
                      style={{ width: `${processingProgress * 100}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500">
                    Full-file transcription with speaker diarization
                  </p>
                </div>
              )}

              {/* Audio stream controls */}
              {isAudioStreamMode && (
                <div className="mt-4 bg-blue-950/20 border border-blue-900/30 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-3">
                    Real-time Audio Analysis
                  </h3>
                  <div className="flex items-center gap-2 mb-3">
                    <button
                      onClick={audioFileStream.state.status === "playing" ? handleAudioStreamPause : handleAudioStreamPlay}
                      className="w-10 h-10 flex items-center justify-center rounded-full bg-blue-600 hover:bg-blue-700 transition-colors"
                      disabled={audioFileStream.state.status === "loading"}
                    >
                      {audioFileStream.state.status === "playing" ? (
                        <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" /></svg>
                      ) : (
                        <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                      )}
                    </button>
                    <button onClick={handleAudioStreamStop} className="w-10 h-10 flex items-center justify-center rounded-full bg-gray-700 hover:bg-gray-600 transition-colors">
                      <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1" /></svg>
                    </button>
                    <span className="text-xs text-gray-400 font-mono ml-2">
                      {Math.floor(audioFileStream.state.currentTime / 60)}:{Math.floor(audioFileStream.state.currentTime % 60).toString().padStart(2, "0")}
                      {" / "}
                      {Math.floor(audioFileStream.state.duration / 60)}:{Math.floor(audioFileStream.state.duration % 60).toString().padStart(2, "0")}
                    </span>
                  </div>
                  <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden mb-2">
                    <div className="h-full bg-blue-500 transition-all duration-200" style={{ width: audioFileStream.state.duration > 0 ? `${(audioFileStream.state.currentTime / audioFileStream.state.duration) * 100}%` : "0%" }} />
                  </div>
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>{audioFileStream.state.chunkCount} chunks sent</span>
                    <span>{liveStream.state.nodeCount} nodes</span>
                  </div>
                </div>
              )}

              {error && (
                <div className="mt-4 bg-red-950/30 border border-red-900/50 rounded-lg p-3 text-sm text-red-300">
                  <span className="font-medium">Error:</span> {error}
                </div>
              )}

              {isLoading && !processingJobId && (
                <div className="mt-4 text-center py-8">
                  <svg className="animate-spin w-8 h-8 mx-auto text-blue-400 mb-3" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <p className="text-sm text-gray-400">Analyzing debate...</p>
                  <p className="text-xs text-gray-600 mt-1">Transcribing → Extracting claims → Detecting fallacies</p>
                </div>
              )}

              {graph && graph.rigor_scores.length > 0 && (
                <div className="mt-4">
                  <RigorScore scores={graph.rigor_scores} />
                </div>
              )}
            </aside>

            <main className="flex-1 flex flex-col overflow-hidden">
              <div className="flex-1 relative">
                <GraphView
                  graph={graph}
                  onNodeSelect={handleNodeSelect}
                  highlightTimestamp={isAudioStreamMode ? audioFileStream.state.currentTime : currentTime}
                />

                {selectedNode && (
                  <div className="absolute top-4 right-4 w-96 z-10 max-h-[calc(100vh-200px)]">
                    <NodeDetail selected={selectedNode} onClose={() => setSelectedNode(null)} />
                  </div>
                )}

                {/* Audio stream overlay */}
                {isAudioStreamMode && !graph && audioFileStream.state.status !== "idle" && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-center">
                      <div className="w-16 h-16 rounded-full bg-blue-900/20 border-2 border-blue-700 flex items-center justify-center mx-auto mb-4 animate-pulse">
                        <svg className="w-8 h-8 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                        </svg>
                      </div>
                      <p className="text-gray-400 text-sm">{audioFileStream.state.status === "playing" ? "Analyzing audio..." : "Press play to start analysis"}</p>
                      <p className="text-gray-600 text-xs mt-1">Graph builds in real-time as audio plays</p>
                    </div>
                  </div>
                )}

                {/* Video-review fullscreen mode overlay */}
                {isVideoReviewMode && graphFullscreen && (
                  <div className="absolute top-3 right-3 z-10 bg-gray-900/80 backdrop-blur-sm rounded-lg p-2 text-xs text-gray-400">
                    Full graph view — switch to Split View to see video
                  </div>
                )}
              </div>

              {/* Bottom: Waveform */}
              {!isVideoMode && !isVideoReviewMode && (
                <div className="shrink-0 border-t border-gray-800 p-3 bg-gray-950 max-h-80 overflow-y-auto">
                  <WaveformView audioUrl={audioUrl} transcription={transcription} onTimeUpdate={handleTimeUpdate} />
                </div>
              )}
            </main>

            {/* Right Sidebar */}
            <aside className="w-80 bg-gray-950 border-l border-gray-800 p-4 overflow-y-auto shrink-0">
              <FallacyPanel fallacies={allFallacies} onClaimClick={handleClaimClick} />
              {graph && graph.cycles_detected.length > 0 && (
                <div className="mt-4 bg-purple-950/20 border border-purple-900/30 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-2">Circular Reasoning Detected</h3>
                  {graph.cycles_detected.map((cycle, i) => (
                    <div key={i} className="text-xs text-gray-400 mb-1">{cycle.join(" → ")} → {cycle[0]}</div>
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
