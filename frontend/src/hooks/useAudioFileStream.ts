import { useRef, useState, useCallback, useEffect } from "react";

export interface AudioFileStreamState {
  status: "idle" | "loading" | "playing" | "paused" | "complete" | "error";
  currentTime: number;
  duration: number;
  chunkCount: number;
  error: string | null;
}

interface UseAudioFileStreamOptions {
  chunkDurationMs?: number;
  onChunk: (chunk: ArrayBuffer, chunkIndex: number, timeOffset: number) => void;
  onError?: (error: string) => void;
  onComplete?: () => void;
}

/**
 * Hook for streaming an audio FILE in real-time chunks via WebSocket.
 *
 * Instead of uploading the entire file and waiting for batch processing,
 * this hook plays the audio through a hidden <audio> element and captures
 * the output via Web Audio API + MediaRecorder, emitting chunks at regular
 * intervals — identical to how video mode works.
 *
 * This enables real-time graph construction for uploaded audio files.
 *
 * Usage:
 *   const { state, loadAudioFile, play, pause, stop } = useAudioFileStream({
 *     chunkDurationMs: 15000,
 *     onChunk: (bytes, idx, offset) => liveStream.sendChunk(bytes, idx, offset),
 *   });
 */
export function useAudioFileStream({
  chunkDurationMs = 15000,
  onChunk,
  onError,
  onComplete,
}: UseAudioFileStreamOptions) {
  const [state, setState] = useState<AudioFileStreamState>({
    status: "idle",
    currentTime: 0,
    duration: 0,
    chunkCount: 0,
    error: null,
  });

  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const destinationRef = useRef<MediaStreamAudioDestinationNode | null>(null);
  const chunkTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeUpdateRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chunkIndexRef = useRef(0);
  const chunkBufferRef = useRef<BlobPart[]>([]);
  const audioUrlRef = useRef<string | null>(null);
  const audioSetupDone = useRef(false);

  const updateState = useCallback((patch: Partial<AudioFileStreamState>) => {
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
    audioSetupDone.current = false;
  }, []);

  /**
   * Load an audio file for streaming playback.
   * Returns a blob URL for optional audio visualization.
   */
  const loadAudioFile = useCallback((file: File): string => {
    cleanup();
    chunkIndexRef.current = 0;
    chunkBufferRef.current = [];

    // Revoke old URL
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
    }

    const url = URL.createObjectURL(file);
    audioUrlRef.current = url;

    // Create a hidden audio element
    const audio = new Audio();
    audio.src = url;
    audio.preload = "auto";
    audioElRef.current = audio;

    // Wait for metadata
    audio.addEventListener("loadedmetadata", () => {
      updateState({
        status: "paused",
        duration: audio.duration || 0,
        currentTime: 0,
        chunkCount: 0,
        error: null,
      });
    });

    audio.addEventListener("ended", () => {
      // Emit remaining audio buffer
      emitRemainingAndComplete();
    });

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
   * Set up audio capture from the audio element.
   */
  const startAudioCapture = useCallback(() => {
    const audio = audioElRef.current;
    if (!audio || audioSetupDone.current) return;
    audioSetupDone.current = true;

    // Create audio context and capture stream from audio element
    const audioCtx = new AudioContext();
    const source = audioCtx.createMediaElementSource(audio);
    const destination = audioCtx.createMediaStreamDestination();

    // Connect to recording destination AND speakers
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
            `[AudioFileStream] Emitting chunk ${chunkIndexRef.current}: ` +
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
      if (audio && !audio.paused) {
        updateState({ currentTime: audio.currentTime });
      }
    }, 250);
  }, [chunkDurationMs, onChunk, updateState]);

  const emitRemainingAndComplete = useCallback(async () => {
    const audio = audioElRef.current;
    if (audio) {
      audio.pause();
    }

    // Emit remaining buffer
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

  /**
   * Start or resume playback.
   */
  const play = useCallback(() => {
    const audio = audioElRef.current;
    if (!audio) return;

    if (!audioSetupDone.current) {
      startAudioCapture();
    } else if (audioContextRef.current?.state === "suspended") {
      audioContextRef.current.resume();
    }

    audio.play().then(() => {
      updateState({ status: "playing" });
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : "Failed to play audio";
      updateState({ status: "error", error: msg });
      onError?.(msg);
    });
  }, [startAudioCapture, updateState, onError]);

  /**
   * Pause playback.
   */
  const pause = useCallback(() => {
    const audio = audioElRef.current;
    if (!audio) return;
    audio.pause();
    updateState({ status: "paused", currentTime: audio.currentTime });
  }, [updateState]);

  /**
   * Stop playback and emit final chunk.
   */
  const stop = useCallback(async () => {
    await emitRemainingAndComplete();
  }, [emitRemainingAndComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanup();
      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current);
      }
    };
  }, [cleanup]);

  return {
    state,
    loadAudioFile,
    play,
    pause,
    stop,
  };
}
