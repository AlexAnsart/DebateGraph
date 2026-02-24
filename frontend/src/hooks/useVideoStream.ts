import { useRef, useState, useCallback, useEffect } from "react";

export interface VideoStreamState {
  status: "idle" | "loading" | "playing" | "paused" | "complete" | "error";
  currentTime: number;
  duration: number;
  chunkCount: number;
  error: string | null;
}

interface UseVideoStreamOptions {
  chunkDurationMs?: number;
  onChunk: (chunk: ArrayBuffer, chunkIndex: number, timeOffset: number) => void;
  onError?: (error: string) => void;
  onComplete?: () => void;
}

/**
 * Hook for streaming audio from a video file in chunks.
 *
 * Uses a hidden <video> element to play the video, captures audio via
 * MediaRecorder + captureStream, and emits chunks at regular intervals.
 * This allows real-time graph construction as the video plays.
 *
 * Usage:
 *   const { state, loadVideo, play, pause, stop, videoRef } = useVideoStream({
 *     chunkDurationMs: 15000,
 *     onChunk: (bytes, idx, offset) => sendToBackend(bytes),
 *   });
 */
export function useVideoStream({
  chunkDurationMs = 15000,
  onChunk,
  onError,
  onComplete,
}: UseVideoStreamOptions) {
  const [state, setState] = useState<VideoStreamState>({
    status: "idle",
    currentTime: 0,
    duration: 0,
    chunkCount: 0,
    error: null,
  });

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const destinationRef = useRef<MediaStreamAudioDestinationNode | null>(null);
  const chunkTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeUpdateRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chunkIndexRef = useRef(0);
  const chunkBufferRef = useRef<BlobPart[]>([]);
  const isPlayingRef = useRef(false);
  const videoUrlRef = useRef<string | null>(null);

  const updateState = useCallback((patch: Partial<VideoStreamState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, []);

  const cleanup = useCallback(() => {
    if (chunkTimerRef.current) {
      clearInterval(chunkTimerRef.current);
      chunkTimerRef.current = null;
    }
    if (timeUpdateRef.current) {
      clearInterval(timeUpdateRef.current);
      timeUpdateRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try { mediaRecorderRef.current.stop(); } catch {}
    }
    mediaRecorderRef.current = null;
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    destinationRef.current = null;
    isPlayingRef.current = false;
  }, []);

  /**
   * Load a video file and prepare for streaming.
   * Returns the video element for rendering.
   */
  const loadVideo = useCallback((file: File): string => {
    cleanup();
    chunkIndexRef.current = 0;
    chunkBufferRef.current = [];

    // Revoke old URL
    if (videoUrlRef.current) {
      URL.revokeObjectURL(videoUrlRef.current);
    }

    const url = URL.createObjectURL(file);
    videoUrlRef.current = url;
    updateState({
      status: "loading",
      currentTime: 0,
      duration: 0,
      chunkCount: 0,
      error: null,
    });

    return url;
  }, [cleanup, updateState]);

  /**
   * Called after the video element is mounted and metadata is loaded.
   * Sets up audio capture from the video.
   */
  const onVideoReady = useCallback((video: HTMLVideoElement) => {
    videoRef.current = video;
    updateState({
      status: "paused",
      duration: video.duration || 0,
    });
  }, [updateState]);

  /**
   * Start recording audio from the video and emitting chunks.
   */
  const startAudioCapture = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;

    // Create audio context and capture stream from video
    const audioCtx = new AudioContext();
    const source = audioCtx.createMediaElementSource(video);
    const destination = audioCtx.createMediaStreamDestination();

    // Also connect to speakers so the user hears the video
    source.connect(destination);
    source.connect(audioCtx.destination);

    audioContextRef.current = audioCtx;
    destinationRef.current = destination;

    // Determine MIME type
    const mimeType = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4",
    ].find((m) => MediaRecorder.isTypeSupported(m)) || "";

    const recorder = new MediaRecorder(destination.stream, {
      mimeType: mimeType || undefined,
      audioBitsPerSecond: 32000,
    });

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        chunkBufferRef.current.push(event.data);
      }
    };

    recorder.start(100); // collect data every 100ms
    mediaRecorderRef.current = recorder;

    // Emit chunks periodically
    const emitChunk = async () => {
      if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") return;

      const buffer = chunkBufferRef.current;
      chunkBufferRef.current = [];

      if (buffer.length > 0) {
        const blob = new Blob(buffer, { type: mimeType || "audio/webm" });
        const arrayBuffer = await blob.arrayBuffer();

        if (arrayBuffer.byteLength > 500) {
          const timeOffset = chunkIndexRef.current * (chunkDurationMs / 1000);
          console.log(
            `[VideoStream] Emitting chunk ${chunkIndexRef.current}: ` +
            `${(arrayBuffer.byteLength / 1024).toFixed(1)} KB, offset=${timeOffset}s`
          );
          onChunk(arrayBuffer, chunkIndexRef.current, timeOffset);
          chunkIndexRef.current++;
          updateState({ chunkCount: chunkIndexRef.current });
        }
      }
    };

    chunkTimerRef.current = setInterval(emitChunk, chunkDurationMs);

    // Track current time
    timeUpdateRef.current = setInterval(() => {
      if (video && !video.paused) {
        updateState({ currentTime: video.currentTime });
      }
    }, 250);
  }, [chunkDurationMs, onChunk, updateState]);

  /**
   * Start or resume playback. On first play, sets up audio capture.
   */
  const play = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;

    if (!audioContextRef.current) {
      // First play — set up audio capture
      startAudioCapture();
    } else if (audioContextRef.current.state === "suspended") {
      audioContextRef.current.resume();
    }

    video.play().then(() => {
      isPlayingRef.current = true;
      updateState({ status: "playing" });
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : "Failed to play video";
      updateState({ status: "error", error: msg });
      onError?.(msg);
    });
  }, [startAudioCapture, updateState, onError]);

  /**
   * Pause playback. Audio capture pauses automatically since no audio flows.
   */
  const pause = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;

    video.pause();
    isPlayingRef.current = false;
    updateState({ status: "paused", currentTime: video.currentTime });
  }, [updateState]);

  /**
   * Stop playback and emit final chunk.
   */
  const stop = useCallback(async () => {
    const video = videoRef.current;
    if (video) {
      video.pause();
    }

    // Emit any remaining buffered audio
    if (chunkBufferRef.current.length > 0) {
      const blob = new Blob(chunkBufferRef.current, { type: "audio/webm" });
      const arrayBuffer = await blob.arrayBuffer();
      if (arrayBuffer.byteLength > 500) {
        const timeOffset = chunkIndexRef.current * (chunkDurationMs / 1000);
        onChunk(arrayBuffer, chunkIndexRef.current, timeOffset);
        chunkIndexRef.current++;
      }
      chunkBufferRef.current = [];
    }

    cleanup();
    updateState({ status: "complete" });
    onComplete?.();
  }, [chunkDurationMs, onChunk, cleanup, updateState, onComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanup();
      if (videoUrlRef.current) {
        URL.revokeObjectURL(videoUrlRef.current);
      }
    };
  }, [cleanup]);

  return {
    state,
    loadVideo,
    onVideoReady,
    play,
    pause,
    stop,
    videoRef,
  };
}
