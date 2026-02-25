/**
 * API client for communicating with the DebateGraph backend.
 */

import type {
  UploadResponse,
  AnalysisStatus,
  DemoResponse,
  HealthResponse,
} from "./types";

const BASE_URL = "/api";

/**
 * Upload an audio/video file for analysis.
 */
export async function uploadFile(
  file: File,
  settings?: {
    num_speakers?: number;
    language?: string;
  }
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (settings?.num_speakers) {
    formData.append("num_speakers", String(settings.num_speakers));
  }
  if (settings?.language) {
    formData.append("language", settings.language);
  }

  const response = await fetch(`${BASE_URL}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(error.detail || "Upload failed");
  }

  return response.json();
}

/**
 * Get the status of an analysis job.
 */
export async function getJobStatus(jobId: string): Promise<AnalysisStatus> {
  const response = await fetch(`${BASE_URL}/status/${jobId}`);
  if (!response.ok) {
    throw new Error("Failed to fetch job status");
  }
  return response.json();
}

/**
 * Run the demo analysis (no file upload needed).
 */
export async function runDemo(): Promise<DemoResponse> {
  const response = await fetch(`${BASE_URL}/demo`, { method: "POST" });
  if (!response.ok) {
    throw new Error("Demo failed");
  }
  return response.json();
}

/**
 * Load the latest pre-computed snapshot (from a previous analysis run).
 */
export async function loadLatestSnapshot(): Promise<DemoResponse> {
  const response = await fetch(`${BASE_URL}/snapshot/latest`);
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("No pre-computed snapshot available. Upload a file or run the demo first.");
    }
    throw new Error("Failed to load snapshot");
  }
  return response.json();
}

/**
 * Check backend health.
 */
export async function checkHealth(): Promise<HealthResponse> {
  const response = await fetch(`${BASE_URL}/health`);
  if (!response.ok) {
    throw new Error("Backend unreachable");
  }
  return response.json();
}

/**
 * Job metadata returned by GET /api/jobs
 */
export interface JobMeta {
  id: string;
  status: string;
  created_at: string;
  audio_filename: string | null;
  duration_s: number | null;
  progress: number;
  error: string | null;
  num_nodes: number | null;
  num_edges: number | null;
  num_fallacies: number | null;
  num_factchecks: number | null;
  speakers: string[] | null;
}

/**
 * List all jobs with metadata (from PostgreSQL).
 */
export async function listJobs(): Promise<JobMeta[]> {
  const response = await fetch(`${BASE_URL}/jobs`);
  if (!response.ok) {
    throw new Error("Failed to list jobs");
  }
  return response.json();
}

/**
 * Load a specific graph snapshot from the database by job ID.
 */
export async function loadSnapshot(jobId: string): Promise<DemoResponse & { job_id: string; audio_filename?: string; media_url?: string }> {
  const response = await fetch(`${BASE_URL}/snapshot/${jobId}`);
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("Snapshot not found in database.");
    }
    if (response.status === 400) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Job not complete yet.");
    }
    throw new Error("Failed to load snapshot");
  }
  return response.json();
}

/**
 * Delete a job.
 */
export async function deleteJob(
  jobId: string
): Promise<{ status: string; message: string }> {
  const response = await fetch(`${BASE_URL}/jobs/${jobId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("Failed to delete job");
  }
  return response.json();
}
