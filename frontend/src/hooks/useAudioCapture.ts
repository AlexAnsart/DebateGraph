import { useRef, useState, useCallback, useEffect } from "react";

interface AudioCaptureOptions {
  chunkDurationMs?: number;   // How often to emit a chunk (default: 15000ms = 15s)
  onChunk: (chunk: ArrayBuffer, chunkIndex: number, timeOffset: number) => void;
  onError?: (error: string) => void;
}

interface AudioCaptureState {
  isRecording: boolean;
  error: string | null;
  duration: number;           // seconds recorded so far
  chunkCount: number;
  audioLevel: number;         // 0-1 for VU meter
}

/**
 * Hook for capturing microphone audio and emitting chunks via MediaRecorder.
 *
 * Uses MediaRecorder with WebM/Opus codec (supported in all modern browsers).
 * Emits chunks every `chunkDurationMs` milliseconds.
 *
 * Usage:
 *   const { state, start, stop } = useAudioCapture({
 *     chunkDurationMs: 15000,
 *     onChunk: (bytes, idx, offset) => sendToBackend(bytes),
 *   });
 */
export function useAudioCapture({
  chunkDurationMs = 15000,
  onChunk,
  onError,
}: AudioCaptureOptions) {
  const [state, setState] = useState<AudioCaptureState>({
    isRecording: false,
    error: null,
    duration: 0,
    chunkCount: 0,
    audioLevel: 0,
  });

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const chunkIndexRef = useRef<number>(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const updateState = useCallback((patch: Partial<AudioCaptureState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, []);

  // VU meter animation
  const startVuMeter = useCallback((stream: MediaStream) => {
    try {
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);
      audioContextRef.current = ctx;
      analyserRef.current = analyser;

      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        updateState({ audioLevel: Math.min(1, avg / 128) });
        animFrameRef.current = requestAnimationFrame(tick);
      };
      animFrameRef.current = requestAnimationFrame(tick);
    } catch (e) {
      console.warn("[AudioCapture] VU meter failed:", e);
    }
  }, [updateState]);

  const stopVuMeter = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
    analyserRef.current = null;
    updateState({ audioLevel: 0 });
  }, [updateState]);

  const start = useCallback(async () => {
    if (state.isRecording) return;

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;
      startTimeRef.current = Date.now();
      chunkIndexRef.current = 0;

      // Determine best supported MIME type
      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ].find((m) => MediaRecorder.isTypeSupported(m)) || "";

      console.log("[AudioCapture] Using MIME type:", mimeType || "default");

      const recorder = new MediaRecorder(stream, {
        mimeType: mimeType || undefined,
        audioBitsPerSecond: 32000,
      });

      mediaRecorderRef.current = recorder;

      // Collect chunks within a recording interval
      let chunkBuffer: BlobPart[] = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunkBuffer.push(event.data);
        }
      };

      // Every chunkDurationMs, stop and restart to emit a chunk
      const emitChunk = async () => {
        if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
          return;
        }

        // Stop current recording to flush data
        mediaRecorderRef.current.stop();

        // Wait for all data to be collected
        await new Promise<void>((resolve) => {
          const onStop = () => {
            mediaRecorderRef.current?.removeEventListener("stop", onStop);
            resolve();
          };
          mediaRecorderRef.current?.addEventListener("stop", onStop);
        });

        if (chunkBuffer.length > 0) {
          const blob = new Blob(chunkBuffer, { type: mimeType || "audio/webm" });
          const arrayBuffer = await blob.arrayBuffer();

          if (arrayBuffer.byteLength > 1000) {
            const timeOffset = chunkIndexRef.current * (chunkDurationMs / 1000);
            console.log(
              `[AudioCapture] Emitting chunk ${chunkIndexRef.current}: ` +
              `${(arrayBuffer.byteLength / 1024).toFixed(1)} KB, offset=${timeOffset}s`
            );
            onChunk(arrayBuffer, chunkIndexRef.current, timeOffset);
            chunkIndexRef.current++;
            updateState({ chunkCount: chunkIndexRef.current });
          }
          chunkBuffer = [];
        }

        // Restart recording if still active
        if (streamRef.current?.active) {
          const newRecorder = new MediaRecorder(stream, {
            mimeType: mimeType || undefined,
            audioBitsPerSecond: 32000,
          });
          newRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
              chunkBuffer.push(event.data);
            }
          };
          newRecorder.onstop = () => {};
          mediaRecorderRef.current = newRecorder;
          newRecorder.start(100); // collect data every 100ms
        }
      };

      // Start recording
      recorder.start(100); // collect data every 100ms

      // Set up periodic chunk emission
      const chunkTimer = setInterval(emitChunk, chunkDurationMs);

      // Duration counter
      durationTimerRef.current = setInterval(() => {
        const elapsed = (Date.now() - startTimeRef.current) / 1000;
        updateState({ duration: elapsed });
      }, 1000);

      // Store timer ref for cleanup
      (recorder as any)._chunkTimer = chunkTimer;

      // Start VU meter
      startVuMeter(stream);

      updateState({
        isRecording: true,
        error: null,
        duration: 0,
        chunkCount: 0,
      });

      console.log("[AudioCapture] Recording started");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to access microphone";
      console.error("[AudioCapture] Error:", message);
      updateState({ error: message, isRecording: false });
      onError?.(message);
    }
  }, [state.isRecording, chunkDurationMs, onChunk, onError, startVuMeter, updateState]);

  const stop = useCallback(async (): Promise<ArrayBuffer | null> => {
    if (!state.isRecording) return null;

    console.log("[AudioCapture] Stopping recording...");

    // Clear timers
    const recorder = mediaRecorderRef.current;
    if (recorder && (recorder as any)._chunkTimer) {
      clearInterval((recorder as any)._chunkTimer);
    }
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }

    // Collect final chunk
    let finalBuffer: ArrayBuffer | null = null;
    if (recorder && recorder.state !== "inactive") {
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      await new Promise<void>((resolve) => {
        recorder.onstop = () => resolve();
        recorder.stop();
      });

      if (chunks.length > 0) {
        const blob = new Blob(chunks, { type: "audio/webm" });
        finalBuffer = await blob.arrayBuffer();
        if (finalBuffer.byteLength > 1000) {
          const timeOffset = chunkIndexRef.current * (chunkDurationMs / 1000);
          onChunk(finalBuffer, chunkIndexRef.current, timeOffset);
          chunkIndexRef.current++;
        }
      }
    }

    // Stop all tracks
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;

    stopVuMeter();

    updateState({ isRecording: false, audioLevel: 0 });
    console.log("[AudioCapture] Recording stopped");

    return finalBuffer;
  }, [state.isRecording, chunkDurationMs, onChunk, stopVuMeter, updateState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (durationTimerRef.current) clearInterval(durationTimerRef.current);
      stopVuMeter();
    };
  }, [stopVuMeter]);

  return { state, start, stop };
}
