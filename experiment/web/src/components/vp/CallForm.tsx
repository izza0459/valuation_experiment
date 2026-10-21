"use client";

/**
 * Logging a call on the Scheduling stage (CRM feedback SC-03, SC-04): pick
 * how it went, add the remark (or, if booked, the date and time) and press
 * Save call. Each save is one entry in the call log; nothing is logged while
 * typing. Booking the inspection moves the job to Inspection.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon, Select, Textarea } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import { useOptions } from "@/lib/options";
import { DatePicker } from "./DatePicker";

const NEEDS_REMARK = new Set(["answered_not_scheduled", "utc"]);

export function CallForm({ jobId, canEdit, current }: { jobId: string; canEdit: boolean; current: string }) {
  const qc = useQueryClient();
  const { data: options } = useOptions();
  const [status, setStatus] = useState("");
  const [remark, setRemark] = useState("");
  const [booked, setBooked] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const choices = (options?.call_status ?? [])
    .filter((o) => o.value !== "not_called")
    .map((o) => ({ value: String(o.value), label: o.label }));
  const scheduled = status === "answered_scheduled";
  const ready = Boolean(status) && (scheduled ? Boolean(booked) : !NEEDS_REMARK.has(status) || Boolean(remark.trim()));

  async function save() {
    setBusy(true);
    setErrors({});
    setMessage(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/calls/`, {
        method: "POST",
        body: JSON.stringify({
          call_status: status,
          call_remark: remark,
          inspection_booked_at: scheduled && booked ? new Date(booked).toISOString() : null,
        }),
      });
      setStatus("");
      setRemark("");
      setBooked("");
      setMessage(scheduled ? "Inspection booked. The job has moved to Inspection." : "Call logged.");
      await qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    } catch (err) {
      if (err instanceof ApiError && err.body?.errors) setErrors(err.body.errors as Record<string, string>);
      else setMessage(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!canEdit) return null;
  const currentLabel = options?.call_status?.find((o) => o.value === current)?.label ?? "Not Called";

  return (
    <div style={{ marginTop: 20, padding: 16, borderRadius: 10, border: "1px solid var(--border-subtle)", background: "var(--surface-subtle)" }}>
      <div className="row wrap" style={{ justifyContent: "space-between", gap: 8, marginBottom: 10 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>Log a call</div>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Current status: {currentLabel}</div>
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        <div>
          <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}>How did the call go? *</div>
          <Select
            value={status}
            placeholder="Choose…"
            options={choices}
            aria-label="Call status"
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setStatus(e.target.value)}
          />
          {errors.call_status && <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 4 }}>{errors.call_status}</div>}
        </div>
        {scheduled ? (
          <div>
            <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}>Inspection date and time *</div>
            <DatePicker withTime value={booked} onConfirm={setBooked} />
            {errors.inspection_booked_at && (
              <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 4 }}>{errors.inspection_booked_at}</div>
            )}
          </div>
        ) : null}
        {status && (
          <div>
            <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}>
              Remark{NEEDS_REMARK.has(status) ? " *" : " (optional)"}
            </div>
            <Textarea
              rows={2}
              value={remark}
              placeholder={NEEDS_REMARK.has(status) ? "Why it isn't booked yet, or when to call back" : "Anything to note"}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setRemark(e.target.value)}
            />
            {errors.call_remark && <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 4 }}>{errors.call_remark}</div>}
          </div>
        )}
        <div className="row wrap" style={{ justifyContent: "space-between", gap: 10 }}>
          <span style={{ fontSize: 13, color: message?.startsWith("Couldn") ? "var(--text-error)" : "var(--green-600)" }}>{message ?? ""}</span>
          <Button size="sm" disabled={busy || !ready} icon={<Icon name="phone" size={16} />} onClick={() => void save()}>
            {busy ? "Saving…" : "Save call"}
          </Button>
        </div>
      </div>
    </div>
  );
}
