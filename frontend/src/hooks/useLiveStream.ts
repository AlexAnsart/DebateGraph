import { useRef, useState, useCallback, useEffect } from "react";
import type { GraphSnapshot, TranscriptionResult } from "../types";

export type LiveStreamStatus =
  | "idle"
  | "connecting"
  | "recording"
  | "processing"
  | "finalizing"
  | "complete"
  | "error";

export interface LiveStreamState {
  status: LiveStreamStatus;
  graph: GraphSnapshot | null;
  transcription: TranscriptionResult | null;
  error: string | null;
  chunkCount: number;
  nodeCount: number;
  sessionId: string | null;
  lastUpdate: number | null;
}

interface UseLiveStreamOptions {
  enableFactcheck?: boolean;
  enableLlmFallacy?: boolean;
  onGraphUpdate?: (graph: GraphSnapshot, transcription: TranscriptionResult | null) => void;
  onError?: (error: string) => void;
}

/**
 * Hook for managing a live streaming WebSocket session.
 *
 * Usage:
 *   const { state, sendChunk, stop } = useLiveStream({ onGraphUpdate });
 *   // Connect and start:
 *   await connect();
 *   // Send audio chunks:
 *   sendChunk(audioBytes, chunkIndex, timeOffset);
 *   // Stop:
 *   stop();
 */
export function useLiveStream(options: UseLiveStreamOptions = {}) {
  const {
    enableFactcheck = true,
    enableLlmFallacy = true,
    onGraphUpdate,
    onError,
  } = options;

  const [state, setState] = useState<LiveStreamState>({
    status: "idle",
    graph: null,
    transcription: null,
    error: null,
    chunkCount: 0,
    nodeCount: 0,
    sessionId: null,
    lastUpdate: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string>(
    Math.random().toString(36).slice(2, 10)
  );

  const updateState = useCallback((patch: Partial<LiveStreamState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, []);

  const connect = useCallback((): Promise<void> => {
    return new Promise((resolve, reject) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      updateState({ status: "connecting", error: null });

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      const url = `${protocol}//${host}/ws/stream`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("[LiveStream] WebSocket connected");
        // Send start message
        ws.send(
          JSON.stringify({
            type: "start",
            session_id: sessionIdRef.current,
            enable_factcheck: enableFactcheck,
            enable_llm_fallacy: enableLlmFallacy,
            audio_format: "webm",
            chunk_duration: 15.0,
          })
        );
        updateState({ status: "recording", sessionId: sessionIdRef.current });
        resolve();
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleMessage(msg);
        } catch (e) {
          console.error("[LiveStream] Failed to parse message:", e);
        }
      };

      ws.onclose = (event) => {
        console.log("[LiveStream] WebSocket closed", event.code, event.reason);
        if (state.status === "recording" || state.status === "processing") {
          updateState({ status: "idle" });
        }
      };

      ws.onerror = (error) => {
        console.error("[LiveStream] WebSocket error:", error);
        const msg = "WebSocket connection failed";
        updateState({ status: "error", error: msg });
        onError?.(msg);
        reject(new Error(msg));
      };
    });
  }, [enableFactcheck, enableLlmFallacy, onError, updateState]);

  const handleMessage = useCallback(
    (msg: Record<string, unknown>) => {
      const type = msg.type as string;

      switch (type) {
        case "stream_started":
          updateState({
            status: "recording",
            sessionId: msg.session_id as string,
          });
          break;

        case "chunk_received":
          updateState({
            chunkCount: (msg.chunk_index as number) + 1,
            status: "processing",
          });
          break;

        case "transcription_update":
          // Partial transcription update — update transcript display
          if (msg.new_segments) {
            setState((prev) => {
              const existingSegs = prev.transcription?.segments ?? [];
              const newSegs = msg.new_segments as TranscriptionResult["segments"];
              const allSegs = [...existingSegs, ...newSegs];
              return {
                ...prev,
                transcription: {
                  segments: allSegs,
                  language: "en",
                  num_speakers: new Set(allSegs.map((s) => s.speaker)).size,
                },
                lastUpdate: Date.now(),
              };
            });
          }
          break;

        case "graph_update": {
          const graph = msg.graph as GraphSnapshot;
          const transcriptionData = msg.transcription as {
            segments: TranscriptionResult["segments"];
            language: string;
            num_speakers: number;
          } | null;
          const transcription: TranscriptionResult | null = transcriptionData
            ? {
                segments: transcriptionData.segments,
                language: transcriptionData.language,
                num_speakers: transcriptionData.num_speakers,
              }
            : null;

          setState((prev) => ({
            ...prev,
            graph,
            transcription: transcription ?? prev.transcription,
            nodeCount: graph.nodes.length,
            status: "recording",
            lastUpdate: Date.now(),
          }));

          onGraphUpdate?.(graph, transcription);
          break;
        }

        case "finalizing":
          updateState({ status: "finalizing" });
          break;

        case "stream_complete": {
          const graph = msg.graph as GraphSnapshot;
          const transcriptionData = msg.transcription as {
            segments: TranscriptionResult["segments"];
            language: string;
            num_speakers: number;
          } | null;
          const transcription: TranscriptionResult | null = transcriptionData
            ? {
                segments: transcriptionData.segments,
                language: transcriptionData.language,
                num_speakers: transcriptionData.num_speakers,
              }
            : null;

          setState((prev) => ({
            ...prev,
            status: "complete",
            graph,
            transcription: transcription ?? prev.transcription,
            nodeCount: graph.nodes.length,
            lastUpdate: Date.now(),
          }));

          onGraphUpdate?.(graph, transcription);
          break;
        }

        case "error": {
          const errMsg = (msg.message as string) || "Stream error";
          updateState({ status: "error", error: errMsg });
          onError?.(errMsg);
          break;
        }

        case "pong":
          break;

        default:
          console.debug("[LiveStream] Unknown message type:", type, msg);
      }
    },
    [onGraphUpdate, onError, updateState]
  );

  const sendChunk = useCallback(
    (audioBytes: ArrayBuffer, chunkIndex: number, timeOffset: number) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.warn("[LiveStream] WebSocket not open, cannot send chunk");
        return;
      }
      ws.send(audioBytes);
    },
    []
  );

  const stop = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
      updateState({ status: "finalizing" });
    }
  }, [updateState]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    updateState({ status: "idle" });
  }, [updateState]);

  const reset = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    sessionIdRef.current = Math.random().toString(36).slice(2, 10);
    setState({
      status: "idle",
      graph: null,
      transcription: null,
      error: null,
      chunkCount: 0,
      nodeCount: 0,
      sessionId: null,
      lastUpdate: null,
    });
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return {
    state,
    connect,
    sendChunk,
    stop,
    disconnect,
    reset,
  };
}
