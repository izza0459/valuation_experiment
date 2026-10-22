"use client";

/**
 * The peer reviewer's wording changes (CRM feedback PR-01). The valuer sees
 * each one (field, before, after, who, when) and accepts them, which lets the
 * reviewer sign off; the reviewer sees what is still waiting.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import type { ReviewerEdit } from "@/lib/jobs";
import { formatDateTime } from "./format";

const asText = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return "(empty)";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) {
    return v.map((e) => (e && typeof e === "object" ? `${(e as { title?: string }).title ?? ""}: ${(e as { body?: string }).body ?? ""}` : String(e))).join("\n");
  }
  return String(v);
};

export function ReviewerChanges({
  jobId,
  edits,
  canAccept,
  reviewing,
}: {
  jobId: string;
  edits: ReviewerEdit[];
  canAccept: boolean;
  /** The current user is the reviewer, and the job is with them. */
  reviewing: boolean;
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const pending = edits.filter((e) => !e.accepted_at);
  // Reviewers no longer edit: this only shows changes recorded before that.
  if (pending.length === 0) return null;

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/reviewer-edits/accept/`, { method: "POST" });
      await qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      await qc.invalidateQueries({ queryKey: ["jobs"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const shown = showAll ? edits : pending;
  return (
    <div className="card" style={{ marginBottom: 16, borderLeft: "4px solid var(--amber-600, #b26a00)" }}>
      <div className="row wrap" style={{ justifyContent: "space-between", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 8, fontSize: 15, fontWeight: 700 }}>
            <Icon name="edit-3" size={16} />
            {pending.length
              ? `${pending.length} change${pending.length === 1 ? "" : "s"} by the peer reviewer${canAccept ? " to accept" : ""}`
              : "Peer review"}
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
            {reviewing
              ? "The valuer accepts these before you can sign off."
              : "Sign-off waits until you accept them. Each shows the text before and after."}
          </div>
        </div>
        {canAccept && pending.length > 0 && (
          <Button size="sm" disabled={busy} icon={<Icon name="check" size={16} />} onClick={() => void accept()}>
            {busy ? "Accepting…" : "Accept changes"}
          </Button>
        )}
      </div>
      {error && <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 8 }}>{error}</div>}
      {shown.length > 0 && (
        <div className="stack8" style={{ marginTop: 12 }}>
          {shown.map((e) => (
            <div key={e.id} style={{ padding: "10px 12px", border: "1px solid var(--border-subtle)", borderRadius: 8, fontSize: 14 }}>
              <div className="row wrap" style={{ justifyContent: "space-between", gap: 8 }}>
                <b>{e.label}</b>
                <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
                  {e.by} · {formatDateTime(e.at)}
                  {e.accepted_at ? ` · accepted by ${e.accepted_by}` : ""}
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10, marginTop: 6 }}>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>BEFORE</div>
                  <div style={{ whiteSpace: "pre-wrap", color: "var(--text-secondary)", textDecoration: "line-through" }}>{asText(e.old)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>AFTER</div>
                  <div style={{ whiteSpace: "pre-wrap" }}>{asText(e.new)}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {edits.length > pending.length && (
        <button type="button" onClick={() => setShowAll(!showAll)}
          style={{ marginTop: 10, border: 0, background: "none", padding: 0, minHeight: 0, cursor: "pointer", color: "var(--text-accent)", fontFamily: "inherit", fontSize: 14 }}>
          {showAll ? "Show only the ones to accept" : `Show all ${edits.length} changes`}
        </button>
      )}
    </div>
  );
}
