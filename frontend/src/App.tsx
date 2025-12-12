// src/App.tsx

import { useState } from "react";
import {
  uploadFile,
  processJob,
  getJobStatus,
  downloadJob,
} from "./api";


import type { CreateJobResponse, JobStatusResponse } from "./api";

type Step =
  | "idle"
  | "uploading"
  | "processing"
  | "waiting"
  | "downloading"
  | "done"
  | "error";

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [step, setStep] = useState<Step>("idle");
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setJobId(null);
    setJobStatus(null);
    setStep("idle");
    setError(null);
    setMessage("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!file) {
      setError("Selecciona un archivo PDF o CBR primero.");
      return;
    }

    try {
      setError(null);
      setMessage("Subiendo archivo...");
      setStep("uploading");

      // 1) Subir archivo → crear job
      const createRes: CreateJobResponse = await uploadFile(file);
      setJobId(createRes.job_id);
      setMessage(`Job creado: ${createRes.job_id}. Iniciando procesamiento...`);

      // 2) Lanzar procesamiento
      setStep("processing");
      await processJob(createRes.job_id);

      // 3) Polling de estado hasta completed/failed
      setStep("waiting");
      await pollUntilFinished(createRes.job_id);

      // 4) Si todo ok, descargar automáticamente
      if (jobStatus?.status === "completed") {
        setStep("downloading");
        await handleDownload(createRes.job_id);
        setStep("done");
        setMessage("Traducción completada y archivo descargado.");
      }
    } catch (err: any) {
      console.error(err);
      setError(err?.message ?? "Error inesperado");
      setStep("error");
    }
  };

  const pollUntilFinished = async (id: string) => {
    const maxAttempts = 30; // 30 * 2s = 60s máximo
    const delayMs = 2000;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const status = await getJobStatus(id);
      setJobStatus(status);

      if (status.status === "completed") {
        setMessage("Job completado. Preparando descarga...");
        return;
      }

      if (status.status === "failed") {
        throw new Error(status.error_message || "El procesamiento ha fallado.");
      }

      setMessage(`Procesando... intento ${attempt}/${maxAttempts}`);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }

    throw new Error("Timeout esperando a que termine el job.");
  };

  const handleDownload = async (id: string) => {
    const blob = await downloadJob(id);
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `ink-translated-${id}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  const isBusy =
    step === "uploading" || step === "processing" || step === "waiting" || step === "downloading";

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>Ink v1 — Traductor de Cómics</h1>
        <p style={styles.subtitle}>
          Sube tu cómic en PDF (MVP) y te devolvemos una versión traducida al castellano.
        </p>

        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>
            Archivo:
            <input
              type="file"
              accept=".pdf,.cbr,.cbz,.zip"
              onChange={handleFileChange}
              disabled={isBusy}
              style={styles.input}
            />
          </label>

          <button type="submit" disabled={!file || isBusy} style={styles.button}>
            {isBusy ? "Procesando..." : "Traducir cómic"}
          </button>
        </form>

        {message && <p style={styles.message}>{message}</p>}

        {error && <p style={styles.error}>⚠️ {error}</p>}

        {jobId && (
          <div style={styles.jobBox}>
            <p>
              <strong>Job ID:</strong> {jobId}
            </p>
            {jobStatus && (
              <>
                <p>
                  <strong>Estado:</strong> {jobStatus.status}
                </p>
                {jobStatus.num_pages != null && (
                  <p>
                    <strong>Páginas:</strong> {jobStatus.num_pages}
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {step === "done" && jobId && (
          <button
            style={styles.secondaryButton}
            onClick={() => handleDownload(jobId)}
          >
            Descargar de nuevo
          </button>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#0f172a",
    color: "#e5e7eb",
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    padding: "1rem",
  },
  card: {
    width: "100%",
    maxWidth: "600px",
    background: "#020617",
    borderRadius: "16px",
    padding: "24px",
    boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
    border: "1px solid #1f2937",
  },
  title: {
    fontSize: "1.8rem",
    marginBottom: "0.5rem",
  },
  subtitle: {
    fontSize: "0.95rem",
    color: "#9ca3af",
    marginBottom: "1.5rem",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
    marginBottom: "1rem",
  },
  label: {
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
    fontSize: "0.9rem",
  },
  input: {
    padding: "0.4rem",
    background: "#020617",
    borderRadius: "8px",
    border: "1px solid #374151",
    color: "#e5e7eb",
    fontSize: "0.9rem",
  },
  button: {
    padding: "0.7rem 1rem",
    borderRadius: "999px",
    border: "none",
    background: "#22c55e",
    color: "#022c22",
    fontWeight: 600,
    fontSize: "0.95rem",
    cursor: "pointer",
  },
  secondaryButton: {
    marginTop: "0.5rem",
    padding: "0.5rem 0.8rem",
    borderRadius: "999px",
    border: "1px solid #4b5563",
    background: "transparent",
    color: "#e5e7eb",
    fontSize: "0.85rem",
    cursor: "pointer",
  },
  message: {
    fontSize: "0.9rem",
    color: "#9ca3af",
  },
  error: {
    marginTop: "0.5rem",
    fontSize: "0.9rem",
    color: "#f87171",
  },
  jobBox: {
    marginTop: "0.75rem",
    padding: "0.75rem",
    borderRadius: "8px",
    background: "#020617",
    border: "1px solid #1f2937",
    fontSize: "0.85rem",
  },
};

export default App;
