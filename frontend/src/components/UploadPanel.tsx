import React, { useState, useRef, useEffect, useCallback } from "react";
import { listJobs } from "../api";
import type { JobMeta } from "../api";

interface UploadPanelProps {
  onUpload: (file: File) => void;
  onDemo: () => void;
  onLoadSnapshot: (jobId: string) => void;
  onStartLive: () => void;
  onStopLive: () => void;
  isLoading: boolean;
  isLive: boolean;
  liveStats?: { nodes: number; chunks: number; duration: number; audioLevel: number };
}

const ACCEPTED_FORMATS = [
  "audio/wav", "audio/mpeg", "audio/mp3", "audio/ogg",
  "audio/flac", "audio/webm", "video/mp4", "video/webm", "video/ogg",
];

function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", {
    day: "2-digit", month: "2-digit", year: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function formatDuration(s: number | null): string {
  if (!s) return "";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m > 0 ? `${m}m${sec}s` : `${sec}s`;
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    complete: "#22c55e",
    error: "#ef4444",
    processing: "#3b82f6",
    transcribing: "#3b82f6",
    extracting: "#f59e0b",
  };
  return (
    <span
      style={{
        display: "inline-block",
        width: 7,
        height: 7,
        borderRadius: "50%",
        backgroundColor: colors[status] || "#6b7280",
        marginRight: 6,
        flexShrink: 0,
      }}
    />
  );
}

/** VU meter bar */
function VuMeter({ level }: { level: number }) {
  const bars = 12;
  return (
    <div className="flex items-end gap-0.5 h-5">
      {Array.from({ length: bars }).map((_, i) => {
        const threshold = i / bars;
        const active = level > threshold;
        const color = i < bars * 0.6 ? "#22c55e" : i < bars * 0.85 ? "#f59e0b" : "#ef4444";
        return (
          <div
            key={i}
            className="w-1 rounded-sm transition-all duration-75"
            style={{
              height: `${40 + (i / bars) * 60}%`,
              backgroundColor: active ? color : "#374151",
            }}
          />
        );
      })}
    </div>
  );
}

export default function UploadPanel({
  onUpload,
  onDemo,
  onLoadSnapshot,
  onStartLive,
  onStopLive,
  isLoading,
  isLive,
  liveStats,
}: UploadPanelProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [jobs, setJobs] = useState<JobMeta[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [jobsLoading, setJobsLoading] = useState(false);
  const [showJobs, setShowJobs] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchJobs = useCallback(async () => {
    setJobsLoading(true);
    try {
      const data = await listJobs();
      setJobs(data);
      if (data.length > 0 && !selectedJobId) {
        const firstComplete = data.find((j) => j.status === "complete");
        if (firstComplete) setSelectedJobId(firstComplete.id);
      }
    } catch {
      // DB might not be available
    } finally {
      setJobsLoading(false);
    }
  }, [selectedJobId]);

  useEffect(() => { fetchJobs(); }, []);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) setSelectedFile(file);
  };
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };
  const handleSubmit = () => { if (selectedFile) onUpload(selectedFile); };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const completedJobs = jobs.filter((j) => j.status === "complete");
  const selectedJob = jobs.find((j) => j.id === selectedJobId);

  return (
    <div className="space-y-4">

      {/* ── LIVE MODE PANEL ── */}
      <div className={`rounded-xl border-2 transition-all duration-300 overflow-hidden
        ${isLive
          ? "border-red-500 bg-red-950/10"
          : "border-gray-700 hover:border-gray-600"
        }`}
      >
        {isLive ? (
          /* Recording state */
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
                <span className="text-sm font-semibold text-red-400">LIVE</span>
                {liveStats && (
                  <span className="text-xs text-gray-500">
                    {formatDuration(liveStats.duration)}
                  </span>
                )}
              </div>
              <button
                onClick={onStopLive}
                className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white text-xs font-semibold rounded-lg transition-colors"
              >
                Stop
              </button>
            </div>

            {/* VU meter */}
            {liveStats && (
              <div className="flex items-center gap-3">
                <VuMeter level={liveStats.audioLevel} />
                <div className="text-xs text-gray-500 space-x-3">
                  <span>{liveStats.chunks} chunks</span>
                  <span>{liveStats.nodes} nodes</span>
                </div>
              </div>
            )}

            <p className="text-xs text-gray-500">
              Listening… Graph updates every ~15s
            </p>
          </div>
        ) : (
          /* Start live button */
          <button
            onClick={onStartLive}
            disabled={isLoading}
            className={`w-full flex items-center justify-center gap-3 p-4 transition-all
              ${isLoading
                ? "opacity-50 cursor-not-allowed"
                : "hover:bg-gray-900/50 cursor-pointer"
              }`}
          >
            <div className="w-10 h-10 rounded-full bg-red-900/30 border-2 border-red-700 flex items-center justify-center shrink-0">
              <svg className="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
              </svg>
            </div>
            <div className="text-left">
              <p className="text-sm font-semibold text-gray-200">Live Analysis</p>
              <p className="text-xs text-gray-500">Record microphone in real-time</p>
            </div>
          </button>
        )}
      </div>

      {/* ── DIVIDER ── */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-gray-800" />
        <span className="text-xs text-gray-600">or upload file</span>
        <div className="flex-1 h-px bg-gray-800" />
      </div>

      {/* ── DROP ZONE ── */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`
          border-2 border-dashed rounded-xl p-5 text-center cursor-pointer
          transition-all duration-200
          ${isDragging
            ? "border-blue-500 bg-blue-950/20"
            : "border-gray-700 hover:border-gray-600 hover:bg-gray-900/50"
          }
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_FORMATS.join(",")}
          onChange={handleFileSelect}
          className="hidden"
        />
        <svg className="w-8 h-8 mx-auto mb-2 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p className="text-sm text-gray-400 mb-1">
          {isDragging ? "Drop your file here" : "Drag & drop audio/video, or click"}
        </p>
        <p className="text-xs text-gray-600">WAV, MP3, OGG, FLAC, WebM, MP4</p>
      </div>

      {/* Selected file info */}
      {selectedFile && (
        <div className="flex items-center justify-between bg-gray-900 rounded-lg p-3">
          <div className="flex items-center gap-2">
            <svg className="w-6 h-6 text-blue-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
            <div>
              <p className="text-sm text-gray-200 font-medium truncate max-w-[160px]">{selectedFile.name}</p>
              <p className="text-xs text-gray-500">{formatFileSize(selectedFile.size)}</p>
            </div>
          </div>
          <button onClick={() => setSelectedFile(null)} className="text-gray-500 hover:text-gray-300">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={handleSubmit}
          disabled={!selectedFile || isLoading}
          className={`flex-1 py-2.5 px-3 rounded-lg font-medium text-sm transition-all
            ${selectedFile && !isLoading
              ? "bg-blue-600 hover:bg-blue-700 text-white"
              : "bg-gray-800 text-gray-500 cursor-not-allowed"
            }`}
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Analyzing…
            </span>
          ) : "Analyze"}
        </button>
        <button
          onClick={onDemo}
          disabled={isLoading}
          className={`py-2.5 px-3 rounded-lg font-medium text-sm transition-all
            ${isLoading ? "bg-gray-800 text-gray-500 cursor-not-allowed"
              : "bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700"}`}
        >
          ⚡ Demo
        </button>
      </div>

      {/* Load from DB */}
      <div className="border border-gray-800 rounded-xl overflow-hidden">
        <button
          onClick={() => { setShowJobs(!showJobs); if (!showJobs) fetchJobs(); }}
          className="w-full flex items-center justify-between px-4 py-3 bg-gray-900 hover:bg-gray-800 transition-colors text-sm font-medium text-gray-300"
        >
          <span className="flex items-center gap-2">
            <span>📊</span>
            <span>Load from Database</span>
            {completedJobs.length > 0 && (
              <span className="px-1.5 py-0.5 bg-emerald-900/50 text-emerald-400 rounded text-xs">
                {completedJobs.length}
              </span>
            )}
          </span>
          <svg
            className={`w-4 h-4 text-gray-500 transition-transform ${showJobs ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showJobs && (
          <div className="bg-gray-950 p-3 space-y-3">
            {jobsLoading ? (
              <p className="text-xs text-gray-500 text-center py-3">Loading jobs…</p>
            ) : jobs.length === 0 ? (
              <p className="text-xs text-gray-500 text-center py-3">
                No jobs in database yet.<br />
                <span className="text-gray-600">Upload a file to get started.</span>
              </p>
            ) : (
              <>
                <div className="space-y-1">
                  {jobs.map((job) => (
                    <button
                      key={job.id}
                      onClick={() => setSelectedJobId(job.id)}
                      disabled={job.status !== "complete"}
                      className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all text-xs
                        ${selectedJobId === job.id
                          ? "border-blue-600 bg-blue-950/30"
                          : job.status === "complete"
                            ? "border-gray-800 hover:border-gray-700 hover:bg-gray-900"
                            : "border-gray-800 opacity-50 cursor-not-allowed"
                        }`}
                    >
                      <div className="flex items-center gap-1 mb-1">
                        <StatusDot status={job.status} />
                        <span className="font-medium text-gray-200 truncate max-w-[160px]">
                          {job.audio_filename || `Job ${job.id.slice(0, 8)}`}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-gray-500 pl-3">
                        <span>{formatDate(job.created_at)}</span>
                        {job.duration_s && <span>· {formatDuration(job.duration_s)}</span>}
                        {job.num_nodes != null && (
                          <span>· {job.num_nodes}n {job.num_edges}e</span>
                        )}
                        {job.num_fallacies != null && job.num_fallacies > 0 && (
                          <span className="text-amber-600">· {job.num_fallacies}⚠</span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>

                {selectedJob && selectedJob.status === "complete" && (
                  <div className="space-y-2">
                    <div className="bg-gray-900 rounded-lg p-2.5 text-xs text-gray-400 space-y-1">
                      <div className="flex justify-between">
                        <span>Nodes</span>
                        <span className="text-gray-200">{selectedJob.num_nodes ?? "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Edges</span>
                        <span className="text-gray-200">{selectedJob.num_edges ?? "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Fallacies</span>
                        <span className={selectedJob.num_fallacies ? "text-amber-400" : "text-gray-200"}>
                          {selectedJob.num_fallacies ?? "—"}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>Fact-checks</span>
                        <span className="text-gray-200">{selectedJob.num_factchecks ?? "—"}</span>
                      </div>
                    </div>

                    <button
                      onClick={() => onLoadSnapshot(selectedJobId)}
                      disabled={isLoading}
                      className={`w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-all
                        ${isLoading
                          ? "bg-gray-800 text-gray-500 cursor-not-allowed"
                          : "bg-emerald-700 hover:bg-emerald-600 text-white"
                        }`}
                    >
                      Load Graph
                    </button>
                  </div>
                )}

                <button
                  onClick={fetchJobs}
                  className="w-full text-xs text-gray-600 hover:text-gray-400 py-1 transition-colors"
                >
                  ↻ Refresh list
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* DB Viewer link */}
      <a
        href="http://localhost:8000/db"
        target="_blank"
        rel="noopener noreferrer"
        className="block w-full text-center py-2 px-4 rounded-lg text-xs text-gray-500 hover:text-gray-300 border border-gray-800 hover:border-gray-700 transition-all"
      >
        🗄️ Open DB Viewer
      </a>
    </div>
  );
}
