import { useMemo, useState } from "react";

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
  | "starting"
  | "waiting"
  | "downloading"
  | "done"
  | "error";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatSeconds(s: number) {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${r}s`;
}

function formatMs(ms?: number | null) {
  if (ms == null) return "-";
  return `${(ms / 1000).toFixed(2)}s`;
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);

  const [step, setStep] = useState<Step>("idle");
  const [message, setMessage] = useState<string>("");

  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);

  const [error, setError] = useState<string | null>(null);

  const isBusy = useMemo(() => {
    return (
      step === "uploading" ||
      step === "starting" ||
      step === "waiting" ||
      step === "downloading"
    );
  }, [step]);

  const progressInfo = useMemo(() => {
    if (!jobStatus?.progress_total || jobStatus.progress_total <= 0) return null;

    const total = jobStatus.progress_total;
    const current = Math.min(jobStatus.progress_current ?? 0, total);
    let percent = Math.max(0, Math.min(100, Math.round((current / total) * 100)));

    let text: string;
    switch (jobStatus.progress_stage) {
      case "import":
        text = `Importando ${current} / ${total}`;
        break;
      case "ocr":
        text = `OCR ${current} / ${total}`;
        break;
      case "translate":
        text = `Traduciendo ${current} / ${total}`;
        break;
      case "render":
        text = `Renderizando ${current} / ${total}`;
        break;
      case "export":
        text = "Exportando…";
        percent = 100;
        break;
      case "completed":
        text = `Completado ${total} / ${total}`;
        percent = 100;
        break;
      default:
        text = `Procesando ${current} / ${total}`;
    }

    return { text, percent };
  }, [jobStatus]);

  const pollUntilFinished = async (id: string) => {
    // 10 minutos por defecto. OCR + traducción puede tardar.
    const maxMs = 10 * 60 * 1000;
    const startedAt = Date.now();

    let delayMs = 2000;
    const maxDelayMs = 10000;

    while (true) {
      const status = await getJobStatus(id);
      setJobStatus(status);

      if (status.status === "completed") {
        setMessage("Job completado. Preparando descarga...");
        return "completed" as const;
      }

      if (status.status === "failed") {
        throw new Error(status.error_message || "El procesamiento ha fallado.");
      }

      const elapsedMs = Date.now() - startedAt;
      if (elapsedMs > maxMs) {
        // NO es un error fatal: el job puede seguir.
        setMessage(
          "Sigue procesando. Puedes esperar más o actualizar el estado cuando quieras."
        );
        return "still_processing" as const;
      }

      const elapsedS = Math.round(elapsedMs / 1000);
      setMessage(
        `Procesando... (${formatSeconds(elapsedS)}). Actualizando en ${Math.round(
          delayMs / 1000
        )}s...`
      );

      await sleep(delayMs);
      delayMs = Math.min(maxDelayMs, Math.round(delayMs * 1.2));
    }
  };

  const handleDownload = async (id: string) => {
    const blob = await downloadJob(id);
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `ink-${id}.pdf`; // MVP: PDF
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
  };

  const handleSubmit = async () => {
    setError(null);

    if (!file) {
      setError("Selecciona un archivo PDF primero.");
      setStep("error");
      return;
    }

    try {
      setStep("uploading");
      setMessage("Subiendo archivo...");

      const created: CreateJobResponse = await uploadFile(file);

      setJobId(created.job_id);
      setMessage(`Job creado: ${created.job_id}. Iniciando procesamiento...`);

      setStep("starting");
      await processJob(created.job_id); // 202: se lanza en background

      setStep("waiting");
      setMessage("Procesando...");

      const result = await pollUntilFinished(created.job_id);

      if (result === "completed") {
        setStep("downloading");
        setMessage("Descargando resultado...");
        await handleDownload(created.job_id);

        setStep("done");
        setMessage("Traducción completada y archivo descargado.");
        return;
      }

      // still_processing: dejamos al usuario decidir
      setStep("waiting");
      setMessage(
        "El job sigue procesando. Pulsa “Actualizar estado” en unos segundos, o “Seguir esperando”."
      );
    } catch (e: any) {
      setStep("error");
      setError(e?.message ?? "Error inesperado");
    }
  };

  const handleRefresh = async () => {
    if (!jobId) return;

    try {
      setError(null);
      setStep("waiting");
      setMessage("Actualizando estado...");

      const s = await getJobStatus(jobId);
      setJobStatus(s);

      if (s.status === "completed") {
        setMessage("Job completado. Descargando...");
        setStep("downloading");
        await handleDownload(jobId);
        setStep("done");
        setMessage("Descargado.");
        return;
      }

      if (s.status === "failed") {
        setStep("error");
        setError(s.error_message || "Job fallido.");
        return;
      }

      setMessage("Sigue procesando. Vuelve a actualizar en unos segundos.");
    } catch (e: any) {
      setStep("error");
      setError(e?.message ?? "Error actualizando estado");
    }
  };

  const handleContinueWaiting = async () => {
    if (!jobId) return;

    try {
      setError(null);
      setStep("waiting");
      setMessage("Esperando a que termine...");

      const result = await pollUntilFinished(jobId);

      if (result === "completed") {
        setStep("downloading");
        setMessage("Descargando resultado...");
        await handleDownload(jobId);
        setStep("done");
        setMessage("Traducción completada y archivo descargado.");
        return;
      }

      setStep("waiting");
      setMessage("Sigue procesando. Puedes seguir esperando cuando quieras.");
    } catch (e: any) {
      setStep("error");
      setError(e?.message ?? "Error esperando");
    }
  };

  const styles = useMemo(() => {
    return {
      page: {
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "flex-start",
        padding: "3rem 1.25rem",
        background:
          "radial-gradient(1200px 800px at 20% 10%, rgba(88, 101, 242, 0.18), transparent 55%), radial-gradient(900px 600px at 80% 30%, rgba(34, 197, 94, 0.14), transparent 55%), #0b1020",
        color: "#e5e7eb",
        fontFamily:
          'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif',
      } as React.CSSProperties,
      card: {
        width: "min(680px, 100%)",
        borderRadius: "18px",
        padding: "28px",
        background: "rgba(13, 18, 40, 0.78)",
        border: "1px solid rgba(255,255,255,0.08)",
        boxShadow: "0 18px 50px rgba(0,0,0,0.45)",
        backdropFilter: "blur(10px)",
      } as React.CSSProperties,
      title: {
        fontSize: "44px",
        lineHeight: 1.05,
        margin: 0,
        fontWeight: 800,
        letterSpacing: "-0.02em",
      } as React.CSSProperties,
      subtitle: {
        marginTop: "10px",
        marginBottom: "24px",
        color: "rgba(229,231,235,0.78)",
        fontSize: "16px",
        lineHeight: 1.5,
      } as React.CSSProperties,
      label: {
        fontSize: "14px",
        color: "rgba(229,231,235,0.9)",
        marginBottom: "8px",
      } as React.CSSProperties,
      fileRow: {
        display: "flex",
        gap: "12px",
        alignItems: "center",
        marginBottom: "18px",
      } as React.CSSProperties,
      fileInput: {
        flex: 1,
        padding: "10px",
        borderRadius: "12px",
        border: "1px solid rgba(255,255,255,0.14)",
        background: "rgba(0,0,0,0.22)",
        color: "#e5e7eb",
      } as React.CSSProperties,
      primaryButton: {
        width: "100%",
        padding: "14px 16px",
        borderRadius: "999px",
        border: "none",
        cursor: isBusy ? "not-allowed" : "pointer",
        fontWeight: 800,
        fontSize: "18px",
        background: isBusy ? "rgba(34,197,94,0.55)" : "#22c55e",
        color: "#06110a",
        boxShadow: "0 14px 36px rgba(34,197,94,0.25)",
      } as React.CSSProperties,
      secondaryButton: {
        padding: "10px 12px",
        borderRadius: "12px",
        border: "1px solid rgba(255,255,255,0.14)",
        background: "rgba(255,255,255,0.06)",
        color: "#e5e7eb",
        cursor: isBusy ? "not-allowed" : "pointer",
        fontWeight: 700,
      } as React.CSSProperties,
      info: {
        marginTop: "16px",
        color: "rgba(229,231,235,0.86)",
        fontSize: "14px",
        lineHeight: 1.45,
      } as React.CSSProperties,
      warn: {
        marginTop: "14px",
        color: "rgba(250, 204, 21, 0.95)",
        fontSize: "14px",
        fontWeight: 700,
      } as React.CSSProperties,
      error: {
        marginTop: "14px",
        color: "rgba(248,113,113,0.95)",
        fontSize: "14px",
        fontWeight: 700,
      } as React.CSSProperties,
      jobBox: {
        marginTop: "18px",
        padding: "16px",
        borderRadius: "14px",
        border: "1px solid rgba(255,255,255,0.12)",
        background: "rgba(0,0,0,0.22)",
      } as React.CSSProperties,
      jobLine: {
        margin: 0,
        fontSize: "14px",
        color: "rgba(229,231,235,0.9)",
      } as React.CSSProperties,
      statusPill: {
        display: "inline-flex",
        padding: "4px 10px",
        borderRadius: "999px",
        fontSize: "12px",
        fontWeight: 800,
        background: "rgba(59,130,246,0.16)",
        border: "1px solid rgba(59,130,246,0.22)",
        color: "#bfdbfe",
        marginLeft: "8px",
      } as React.CSSProperties,
      progressBox: {
        marginTop: "10px",
        padding: "12px",
        borderRadius: "10px",
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.06)",
      } as React.CSSProperties,
      detailBox: {
        marginTop: "12px",
        padding: "12px",
        borderRadius: "10px",
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.04)",
      } as React.CSSProperties,
      detailTitle: {
        margin: 0,
        fontSize: "14px",
        fontWeight: 800,
        color: "rgba(229,231,235,0.9)",
      } as React.CSSProperties,
      detailList: {
        margin: "6px 0 0 16px",
        padding: 0,
        color: "rgba(229,231,235,0.86)",
        fontSize: "14px",
        lineHeight: 1.4,
      } as React.CSSProperties,
      progressText: {
        fontSize: "14px",
        marginBottom: "8px",
        color: "rgba(229,231,235,0.9)",
      } as React.CSSProperties,
      progressBar: {
        position: "relative",
        width: "100%",
        height: "10px",
        borderRadius: "999px",
        background: "rgba(255,255,255,0.08)",
        overflow: "hidden",
      } as React.CSSProperties,
      progressFill: {
        position: "absolute",
        left: 0,
        top: 0,
        height: "100%",
        borderRadius: "999px",
        background:
          "linear-gradient(90deg, rgba(59,130,246,0.9), rgba(34,197,94,0.9))",
        transition: "width 0.3s ease",
      } as React.CSSProperties,
    };
  }, [isBusy]);

  const statusLabel = jobStatus?.status ?? (jobId ? "uploaded" : "-");

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>Ink v1 — Traductor de Cómics</h1>
        <p style={styles.subtitle}>
          Sube tu cómic en PDF (MVP) y te devolvemos una versión traducida al
          castellano.
        </p>

        <div style={{ marginBottom: "10px" }}>
          <div style={styles.label}>Archivo:</div>
          <div style={styles.fileRow}>
            <input
              type="file"
              accept=".pdf"
              style={styles.fileInput}
              disabled={isBusy}
              onChange={(e) => {
                setError(null);
                const f = e.target.files?.[0] ?? null;
                setFile(f);
              }}
            />
          </div>
        </div>

        <button style={styles.primaryButton} disabled={isBusy} onClick={handleSubmit}>
          {isBusy ? "Procesando..." : "Traducir cómic"}
        </button>

        {message && <div style={styles.info}>{message}</div>}

        {jobId && (
          <div style={styles.jobBox}>
            <p style={styles.jobLine}>
              <strong>Job ID:</strong> {jobId}
            </p>
            <p style={styles.jobLine}>
              <strong>Estado:</strong>
              <span style={styles.statusPill}>{statusLabel}</span>
            </p>
            {jobStatus?.num_pages != null && (
              <p style={styles.jobLine}>
                <strong>Páginas:</strong> {jobStatus.num_pages}
              </p>
            )}

            {progressInfo && (
              <div style={styles.progressBox}>
                <div style={styles.progressText}>{progressInfo.text}</div>
                <div style={styles.progressBar}>
                  <div
                    style={{
                      ...styles.progressFill,
                      width: `${progressInfo.percent}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {jobStatus && (
              <div style={styles.detailBox}>
                <p style={styles.detailTitle}>Detalles</p>
                <p style={styles.jobLine}>
                  <strong>Etapa:</strong> {jobStatus.progress_stage ?? "-"}
                </p>
                <p style={styles.jobLine}>
                  <strong>Progreso:</strong> {jobStatus.progress_current} /
                  {" "}
                  {jobStatus.progress_total ?? "-"}
                </p>
                {jobStatus.regions_total !== undefined && (
                  <p style={styles.jobLine}>
                    <strong>Regiones:</strong> {jobStatus.regions_total}
                  </p>
                )}
                {jobStatus.status === "completed" && (
                  <div style={{ marginTop: "8px" }}>
                    <p style={styles.jobLine}>
                      <strong>Tiempos:</strong>
                    </p>
                    <ul style={styles.detailList}>
                      <li>Import: {formatMs(jobStatus.timing_import_ms)}</li>
                      <li>OCR: {formatMs(jobStatus.timing_ocr_ms)}</li>
                      <li>
                        Traducción: {formatMs(jobStatus.timing_translate_ms)}
                      </li>
                      <li>Render: {formatMs(jobStatus.timing_render_ms)}</li>
                      <li>Export: {formatMs(jobStatus.timing_export_ms)}</li>
                    </ul>
                    <p style={styles.jobLine}>
                      <strong>QA retries:</strong> {jobStatus.qa_retry_count ?? 0}
                    </p>
                    <p style={styles.jobLine}>
                      <strong>Overflow detections:</strong>{" "}
                      {jobStatus.qa_overflow_count ?? 0}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {jobId && (
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
            <button
              style={styles.secondaryButton}
              disabled={isBusy}
              onClick={handleRefresh}
            >
              Actualizar estado
            </button>

            <button
              style={styles.secondaryButton}
              disabled={isBusy}
              onClick={handleContinueWaiting}
            >
              Seguir esperando
            </button>
          </div>
        )}

        {step === "waiting" && jobStatus?.status === "processing" && (
          <div style={styles.warn}>
            El job sigue procesando. Esto puede tardar varios minutos según el PDF.
          </div>
        )}

        {error && <div style={styles.error}>⚠️ {error}</div>}
      </div>
    </div>
  );
}
