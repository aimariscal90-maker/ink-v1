// src/api.ts

// ⚠️ IMPORTANTE: en Codespaces, "localhost:8000" no funciona desde el navegador.
// Copia la URL del puerto 8000 que te da Codespaces, algo tipo:
// https://<nombre>-8000.app.github.dev
// y ponla aquí:

// Use Vite environment variable `VITE_API_BASE_URL` for flexibility in development/production.
// If not set, an empty string will make requests relative to the current origin (so Vite's proxy works).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export interface CreateJobResponse {
  job_id: string;
  status: string;
  type: string;
  output_format: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: string;
  type: string;
  output_format: string;
  num_pages: number | null;
  error_message: string | null;
  output_path: string | null;
}

export async function uploadFile(file: File): Promise<CreateJobResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/v1/jobs`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Error creando job: ${res.status} ${text}`);
  }

  return res.json();
}

export async function processJob(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/process`, {
    method: "POST",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Error procesando job: ${res.status} ${text}`);
  }

  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Error consultando job: ${res.status} ${text}`);
  }
  return res.json();
}

export async function downloadJob(jobId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/download`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Error descargando resultado: ${res.status} ${text}`);
  }
  return res.blob();
}
