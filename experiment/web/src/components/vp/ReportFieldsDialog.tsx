"use client";

/**
 * Include-in-report step (field dictionary round 2): once the Inspection
 * stage is complete, the valuer ticks which Preliminary Check and Inspection
 * fields go into the report. Unticked ones are left out of the PDF; the
 * server keeps the list on the job (`report_exclusions`).
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Dialog } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import type { TabDef } from "@/lib/fieldConfig";

export function ReportFieldsDialog({
  open,
  jobId,
  tabs,
  excluded,
  onClose,
  onSaved,
}: {
  open: boolean;
  jobId: string;
  /** The Preliminary Check and Inspection tabs. */
  tabs: TabDef[];
  excluded: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [off, setOff] = useState<Set<string>>(() => new Set(excluded));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (key: string) =>
    setOff((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/report-fields/`, {
        method: "POST",
        body: JSON.stringify({ excluded: [...off] }),
      });
      await qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="What goes in the report?"
      subtitle="Untick anything from the Preliminary Check or Inspection to leave it out of the report."
      onClose={onClose}
      width={680}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save and continue"}
          </Button>
        </>
      }
    >
      <div style={{ display: "grid", gap: 18, maxHeight: "60vh", overflowY: "auto" }}>
        {!tabs.some((t) => t.fields.some((f) => f.report_optional)) && (
          <div style={{ fontSize: 14, color: "var(--text-muted)" }}>
            The server hasn&apos;t said which fields can be left out. It is probably running an older version: redeploy
            or restart the API, then reload this page.
          </div>
        )}
        {tabs.map((tab) => {
          const fields = tab.fields.filter((f) => f.report_optional);
          if (fields.length === 0) return null;
          return (
            <div key={tab.key}>
              <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>{tab.label}</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "6px 16px" }}>
                {fields.map((f) => {
                  const key = `${tab.key}.${f.key}`;
                  return (
                    <label key={key} className="row" style={{ gap: 8, fontSize: 14, cursor: "pointer" }}>
                      <input type="checkbox" checked={!off.has(key)} onChange={() => toggle(key)} />
                      {f.label}
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}
        {error && <div style={{ fontSize: 13, color: "var(--text-error)" }}>{error}</div>}
      </div>
    </Dialog>
  );
}
