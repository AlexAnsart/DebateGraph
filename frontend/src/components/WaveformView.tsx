import React, { useRef, useEffect, useState, useCallback } from "react";
import WaveSurfer from "wavesurfer.js";
import type { TranscriptionResult } from "../types";
import { SPEAKER_COLORS } from "../types";

interface WaveformViewProps {
  audioUrl: string | null;
  transcription: TranscriptionResult | null;
  onTimeUpdate: (time: number) => void;
}

/**
 * Audio waveform visualization with synchronized transcript.
 * Uses WaveSurfer.js for waveform rendering and playback.
 * Highlights the current segment based on playback position.
 */
export default function WaveformView({
  audioUrl,
  transcription,
  onTimeUpdate,
}: WaveformViewProps) {
  const waveformRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // Speaker color mapping
  const getSpeakerColor = useCallback(
    (speaker: string): string => {
      if (!transcription) return SPEAKER_COLORS[0];
      const speakers = [
        ...new Set(transcription.segments.map((s) => s.speaker)),
      ];
      const idx = speakers.indexOf(speaker);
      return SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
    },
    [transcription]
  );

  // Initialize WaveSurfer
  useEffect(() => {
    if (!waveformRef.current || !audioUrl) return;

    const ws = WaveSurfer.create({
      container: waveformRef.current,
      waveColor: "#4b5563",
      progressColor: "#3b82f6",
      cursorColor: "#f59e0b",
      cursorWidth: 2,
      height: 80,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
      backend: "WebAudio",
    });

    ws.load(audioUrl);

    ws.on("ready", () => {
      setDuration(ws.getDuration());
    });

    ws.on("audioprocess", () => {
      const time = ws.getCurrentTime();
      setCurrentTime(time);
      onTimeUpdate(time);
    });

    ws.on("seeking", () => {
      const time = ws.getCurrentTime();
      setCurrentTime(time);
      onTimeUpdate(time);
    });

    ws.on("play", () => setIsPlaying(true));
    ws.on("pause", () => setIsPlaying(false));
    ws.on("finish", () => setIsPlaying(false));

    wsRef.current = ws;

    return () => {
      ws.destroy();
    };
  }, [audioUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  const togglePlay = () => {
    wsRef.current?.playPause();
  };

  const seekTo = (time: number) => {
    if (wsRef.current && duration > 0) {
      wsRef.current.seekTo(time / duration);
    }
  };

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  // Find current segment
  const currentSegment = transcription?.segments.find(
    (seg) => currentTime >= seg.start && currentTime <= seg.end
  );

  return (
    <div className="flex flex-col gap-3">
      {/* Waveform */}
      <div className="bg-gray-900 rounded-lg p-3">
        {audioUrl ? (
          <>
            <div ref={waveformRef} className="w-full" />
            <div className="flex items-center justify-between mt-2">
              <button
                onClick={togglePlay}
                className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-md text-sm font-medium transition-colors"
              >
                {isPlaying ? (
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                )}
                {isPlaying ? "Pause" : "Play"}
              </button>
              <span className="text-xs text-gray-400 font-mono">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
          </>
        ) : (
          <div className="h-20 flex items-center justify-center text-gray-500 text-sm">
            No audio loaded
          </div>
        )}
      </div>

      {/* Transcript segments */}
      {transcription && transcription.segments.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-3 max-h-64 overflow-y-auto">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
            Transcript
          </h3>
          <div className="space-y-1.5">
            {transcription.segments.map((seg, i) => {
              const isActive = currentSegment === seg;
              return (
                <div
                  key={i}
                  onClick={() => seekTo(seg.start)}
                  className={`flex gap-2 p-2 rounded cursor-pointer transition-colors text-sm ${
                    isActive
                      ? "bg-gray-800 ring-1 ring-blue-500/50"
                      : "hover:bg-gray-800/50"
                  }`}
                >
                  <span
                    className="text-xs font-mono font-bold shrink-0 mt-0.5"
                    style={{ color: getSpeakerColor(seg.speaker) }}
                  >
                    {seg.speaker.replace("SPEAKER_", "S")}
                  </span>
                  <span className="text-gray-300 leading-relaxed">
                    {seg.text}
                  </span>
                  <span className="text-xs text-gray-600 font-mono shrink-0 mt-0.5">
                    {formatTime(seg.start)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
