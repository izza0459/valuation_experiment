"use client";

/**
 * Report buttons for the workspace header (design brief S5).
 *
 * "Preview" opens the report as HTML straight from the live job: instant,
 * and the loop for checking wording before anything is generated. "Generate
 * PDF" renders and stores a draft version, then opens it.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon } from "@/design-system";
import { ApiError, apiFetch, apiUrl } from "@/lib/api";

type Version = { id: number };

export function ReportActions({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const version = await apiFetch<Version>(`/api/jobs/${jobId}/report/`, { method: "POST" });
      window.open(apiUrl(`/api/jobs/${jobId}/report/${version.id}/pdf/`), "_blank", "noopener");
      qc.invalidateQueries({ queryKey: ["job-report-versions", jobId] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error && (
        <div style={{ marginRight: "auto", fontSize: 13, color: "var(--text-error)", maxWidth: "55%" }}>
          <Icon name="alert-circle" size={14} /> {error}
        </div>
      )}
      <Button
        variant="outline"
        size="sm"
        icon={<Icon name="eye" size={16} />}
        onClick={() => window.open(apiUrl(`/api/jobs/${jobId}/report/preview/`), "_blank", "noopener")}
      >
        Preview report
      </Button>
      <Button
        variant="outline"
        size="sm"
        icon={<Icon name="file-text" size={16} />}
        disabled={busy}
        onClick={() => void generate()}
      >
        {busy ? "Generating…" : "Generate PDF"}
      </Button>
    </>
  );
}
