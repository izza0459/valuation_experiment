"use client";

/**
 * Include-in-report step (field dictionary round 2): once the Valuation
 * stage is complete, the valuer sees every field entered so far and unticks
 * any to leave out of the report. What a bank report must carry is always
 * in (ticked, greyed); calculated fields follow the fields they come from.
 * The server keeps the list on the job (`report_exclusions`).
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
  /** Every tab up to and including Valuation. */
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
  /** Ticks or unticks every optional field of a tab. */
  const setAll = (keys: string[], include: boolean) =>
    setOff((prev) => {
      const next = new Set(prev);
      for (const k of keys) {
        if (include) next.delete(k);
        else next.add(k);
      }
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

  const withFields = tabs.filter((t) => t.fields.length > 0);
  const oldServer = !tabs.some((t) => t.fields.some((f) => f.report));

  return (
    <Dialog
      open={open}
      title="What goes in the report?"
      subtitle="Every field entered so far. Untick anything to leave it out. Greyed ones a bank report always carries."
      onClose={onClose}
      width={720}
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
      <div style={{ display: "grid", gap: 18, maxHeight: "62vh", overflowY: "auto", paddingRight: 4 }}>
        {oldServer && (
          <div style={{ fontSize: 14, color: "var(--text-muted)" }}>
            The server is running an older version, so only some fields can be left out. Redeploy or restart the
            API, then reload this page.
          </div>
        )}
        {withFields.map((tab) => {
          const optional = tab.fields
            .filter((f) => (f.report ? f.report === "optional" : f.report_optional))
            .map((f) => `${tab.key}.${f.key}`);
          const allOn = optional.every((k) => !off.has(k));
          return (
            <div key={tab.key}>
              <div className="row" style={{ justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{tab.label}</div>
                {optional.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setAll(optional, !allOn)}
                    style={{ border: 0, background: "none", color: "var(--text-link)", fontSize: 13, cursor: "pointer", fontFamily: "inherit", padding: 0, minHeight: 0 }}
                  >
                    {allOn ? "Untick all" : "Tick all"}
                  </button>
                )}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "6px 16px" }}>
                {tab.fields.map((f) => {
                  const key = `${tab.key}.${f.key}`;
                  const kind = f.report ?? (f.report_optional ? "optional" : "always");
                  const fixed = kind !== "optional";
                  return (
                    <label
                      key={key}
                      className="row"
                      title={kind === "always" ? "Always in a bank report" : kind === "derived" ? "Worked out from other fields" : undefined}
                      style={{ gap: 8, fontSize: 14, cursor: fixed ? "default" : "pointer", color: fixed ? "var(--text-muted)" : undefined, alignItems: "flex-start" }}
                    >
                      <input
                        type="checkbox"
                        style={{ marginTop: 3, flexShrink: 0 }}
                        checked={fixed || !off.has(key)}
                        disabled={fixed}
                        onChange={() => toggle(key)}
                      />
                      <span style={{ minWidth: 0 }}>{f.label}</span>
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
