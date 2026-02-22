import { useRef, useState, useCallback } from "react";

/**
 * Hook for capturing microphone audio via Web Audio API (Phase 3).
 * Currently provides the interface; streaming to backend via WebSocket
 * will be implemented in Phase 3.
 */
export function useAudioCapture() {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      streamRef.current = stream;
      contextRef.current = new AudioContext({ sampleRate: 16000 });

      setIsRecording(true);
      setError(null);

      console.log("[Audio] Microphone capture started");
      // Phase 3: Connect to ScriptProcessorNode or AudioWorklet
      // to chunk audio and send via WebSocket
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to access microphone";
      setError(message);
      console.error("[Audio] Error:", message);
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (contextRef.current) {
      contextRef.current.close();
      contextRef.current = null;
    }
    setIsRecording(false);
    console.log("[Audio] Microphone capture stopped");
  }, []);

  return { isRecording, error, startRecording, stopRecording };
}
