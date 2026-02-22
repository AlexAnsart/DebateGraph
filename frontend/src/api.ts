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
 * List all jobs.
 */
export async function listJobs(): Promise<
  { job_id: string; status: string; progress: number }[]
> {
  const response = await fetch(`${BASE_URL}/jobs`);
  if (!response.ok) {
    throw new Error("Failed to list jobs");
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
