"use client";

/** Marking a lead lost: a reason from the admin's list and a note. Final. */

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Dialog, Select, Textarea } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import { F } from "./ui";

export function LostDialog({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["lost-reasons", jobId],
    queryFn: () => apiFetch<{ reasons: { value: string; label: string }[] }>(`/api/jobs/${jobId}/lost/`),
  });
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failed, setFailed] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErrors({});
    setFailed(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/lost/`, { method: "POST", body: JSON.stringify({ reason, note }) });
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      await qc.invalidateQueries({ queryKey: ["job-activity", jobId] });
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        const body = (err.body ?? {}) as { errors?: Record<string, string> };
        if (body.errors) setErrors(body.errors);
        else setFailed(err.message);
      } else setFailed("Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      title="Mark this lead as lost"
      onClose={onClose}
      width={460}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>Keep it open</Button>
          <Button disabled={busy || !reason} onClick={() => void submit()}
            style={{ background: "var(--red-600)", borderColor: "var(--red-600)", color: "#fff" }}>
            {busy ? "Saving…" : "Mark as lost"}
          </Button>
        </>
      }
    >
      <div style={{ display: "grid", gap: 16 }}>
        <F label="Reason" error={errors.reason} helper="The list is edited in Admin → Dropdowns (Lost reason).">
          <Select
            value={reason}
            placeholder="Select…"
            invalid={Boolean(errors.reason)}
            options={(data?.reasons ?? []).map((r) => ({ value: r.value, label: r.label }))}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setReason(e.target.value)}
          />
        </F>
        <F label="Note" optional={reason !== "other"} error={errors.note}>
          <Textarea rows={3} value={note} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNote(e.target.value)} />
        </F>
        <div style={{ fontSize: 13.5, color: "var(--text-secondary)" }}>
          A lost lead can&apos;t be reopened or edited. A new instruction for the property starts a new lead.
        </div>
        {failed && <div style={{ color: "var(--text-error)", fontSize: 14 }}>{failed}</div>}
      </div>
    </Dialog>
  );
}
