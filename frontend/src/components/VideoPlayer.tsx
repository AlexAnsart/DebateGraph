import React, { useRef, useCallback, useEffect } from "react";

interface VideoPlayerProps {
  videoUrl: string;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  onVideoReady: (video: HTMLVideoElement) => void;
  onPlay: () => void;
  onPause: () => void;
  onStop: () => void;
  onEnded: () => void;
  chunkCount: number;
  nodeCount: number;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Video player component for the video analysis mode.
 * Displays the video with custom controls and streaming stats.
 */
export default function VideoPlayer({
  videoUrl,
  isPlaying,
  currentTime,
  duration,
  onVideoReady,
  onPlay,
  onPause,
  onStop,
  onEnded,
  chunkCount,
  nodeCount,
}: VideoPlayerProps) {
  const videoElRef = useRef<HTMLVideoElement>(null);
  const readyFired = useRef(false);

  const handleLoadedMetadata = useCallback(() => {
    if (videoElRef.current && !readyFired.current) {
      readyFired.current = true;
      onVideoReady(videoElRef.current);
    }
  }, [onVideoReady]);

  // Reset readyFired when videoUrl changes
  useEffect(() => {
    readyFired.current = false;
  }, [videoUrl]);

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="flex flex-col h-full bg-gray-950">
      {/* Video element */}
      <div className="flex-1 relative flex items-center justify-center overflow-hidden bg-black/80">
        <video
          ref={videoElRef}
          src={videoUrl}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={onEnded}
          className="max-w-full max-h-full object-contain"
          playsInline
          preload="auto"
        />

        {/* Overlay: waiting state when video is loaded but not yet playing */}
        {!isPlaying && duration > 0 && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-1.5 bg-gray-900/80 border border-gray-700 rounded-full text-xs text-gray-300 backdrop-blur-sm pointer-events-none">
            <svg className="w-3.5 h-3.5 text-blue-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
            Press play to start analysis
          </div>
        )}

        {/* Overlay: LIVE analysis indicator */}
        {isPlaying && (
          <div className="absolute top-3 right-3 flex items-center gap-1.5 px-2 py-1 bg-red-900/70 border border-red-700 rounded-full text-xs text-red-300 backdrop-blur-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            Analyzing
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-gray-800">
        <div
          className="h-full bg-blue-500 transition-all duration-200"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-t border-gray-800">
        <div className="flex items-center gap-2">
          {/* Play/Pause button */}
          <button
            onClick={isPlaying ? onPause : onPlay}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-blue-600 hover:bg-blue-700 transition-colors"
          >
            {isPlaying ? (
              <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
              </svg>
            ) : (
              <svg className="w-4 h-4 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>

          {/* Stop button */}
          <button
            onClick={onStop}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-gray-700 hover:bg-gray-600 transition-colors"
            title="Stop analysis"
          >
            <svg className="w-3.5 h-3.5 text-white" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="1" />
            </svg>
          </button>

          {/* Time display */}
          <span className="text-xs text-gray-400 font-mono ml-2">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{chunkCount} chunks</span>
          <span>{nodeCount} nodes</span>
        </div>
      </div>
    </div>
  );
}
