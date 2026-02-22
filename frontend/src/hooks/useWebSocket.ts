import { useEffect, useRef, useState, useCallback } from "react";
import type { AnalysisStatus } from "../types";

/**
 * Hook for WebSocket connection to monitor analysis job progress.
 */
export function useWebSocket(jobId: string | null) {
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (!jobId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/${jobId}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      console.log(`[WS] Connected to job ${jobId}`);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "status" || message.type === "done") {
          setStatus(message.data as AnalysisStatus);
        }
        if (message.type === "done") {
          ws.close();
        }
      } catch (e) {
        console.error("[WS] Failed to parse message:", e);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      console.log(`[WS] Disconnected from job ${jobId}`);
    };

    ws.onerror = (error) => {
      console.error("[WS] Error:", error);
      setConnected(false);
    };
  }, [jobId]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return { status, connected };
}
