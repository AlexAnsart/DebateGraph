import React, {
  useRef,
  useState,
  useEffect,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react";
import type { GraphSnapshot } from "../types";

export interface VideoReviewPlayerHandle {
  seekTo: (time: number) => void;
}

interface VideoReviewPlayerProps {
  videoUrl: string;
  onTimeUpdate: (currentTime: number) => void;
  graph: GraphSnapshot | null;
}

/**
 * Video player for review mode.
 * Supports free seeking — no streaming, no MediaRecorder.
 * Drives graph filtering via onTimeUpdate callback.
 */
const VideoReviewPlayer = forwardRef<
  VideoReviewPlayerHandle,
  VideoReviewPlayerProps
>(function VideoReviewPlayer({ videoUrl, onTimeUpdate, graph }, ref) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // Expose seekTo to parent
  useImperativeHandle(ref, () => ({
    seekTo: (time: number) => {
      if (videoRef.current) {
        videoRef.current.currentTime = time;
        setCurrentTime(time);
        onTimeUpdate(time);
      }
    },
  }));

  const handleTimeUpdate = useCallback(() => {
    if (videoRef.current) {
      const t = videoRef.current.currentTime;
      setCurrentTime(t);
      onTimeUpdate(t);
    }
  }, [onTimeUpdate]);

  const handleLoadedMetadata = useCallback(() => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  }, []);

  const handlePlay = useCallback(() => {
    videoRef.current?.play();
    setIsPlaying(true);
  }, []);

  const handlePause = useCallback(() => {
    videoRef.current?.pause();
    setIsPlaying(false);
  }, []);

  const handleEnded = useCallback(() => {
    setIsPlaying(false);
  }, []);

  const handleProgressClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!videoRef.current || duration <= 0) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const fraction = Math.max(
        0,
        Math.min(1, (e.clientX - rect.left) / rect.width)
      );
      const seekTime = fraction * duration;
      videoRef.current.currentTime = seekTime;
      setCurrentTime(seekTime);
      onTimeUpdate(seekTime);
    },
    [duration, onTimeUpdate]
  );

  // Count visible nodes at current time
  const visibleNodeCount = graph
    ? graph.nodes.filter((n) => n.timestamp_start <= currentTime).length
    : 0;

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="flex flex-col h-full bg-gray-950">
      {/* Video */}
      <div className="flex-1 relative bg-black flex items-center justify-center min-h-0">
        <video
          ref={videoRef}
          src={videoUrl}
          className="w-full h-full object-contain"
          preload="auto"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleEnded}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
        />
      </div>

      {/* Controls */}
      <div className="shrink-0 bg-gray-900 border-t border-gray-800 px-4 py-3">
        {/* Progress bar (clickable for seeking) */}
        <div
          className="h-2 bg-gray-800 rounded-full cursor-pointer relative mb-3 group"
          onClick={handleProgressClick}
        >
          <div
            className="h-full bg-blue-500 rounded-full transition-[width] duration-75"
            style={{ width: `${progress}%` }}
          />
          {/* Scrubber handle */}
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-blue-400 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ left: `calc(${progress}% - 6px)` }}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* Play/Pause */}
            <button
              onClick={isPlaying ? handlePause : handlePlay}
              className="w-9 h-9 flex items-center justify-center rounded-full bg-blue-600 hover:bg-blue-700 transition-colors"
            >
              {isPlaying ? (
                <svg
                  className="w-4 h-4 text-white"
                  fill="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
                </svg>
              ) : (
                <svg
                  className="w-4 h-4 text-white ml-0.5"
                  fill="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path d="M8 5v14l11-7z" />
                </svg>
              )}
            </button>

            {/* Time display */}
            <span className="text-xs text-gray-400 font-mono">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span>
              {visibleNodeCount}
              {graph ? ` / ${graph.nodes.length}` : ""} claims
            </span>
          </div>
        </div>
      </div>
    </div>
  );
});

export default VideoReviewPlayer;
