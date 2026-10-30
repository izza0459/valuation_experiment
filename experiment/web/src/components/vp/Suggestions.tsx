"use client";

/**
 * Peer-review suggestions (apps.jobs.suggestions). The reviewer's changes
 * are not saved: each is a suggestion the valuer accepts (saved like any
 * edit) or declines with a reason. Shown in purple, Bayut's colour for a
 * suggested figure: under the field, in the lead card and on Review.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon, Textarea } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import type { Suggestion } from "@/lib/jobs";
import { useMe } from "@/lib/auth";
import { formatDateTime } from "./format";

function useActions(jobId: string) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async (id: number, path: string, init: RequestInit) => {
    setBusy(id);
    setError(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/suggestions/${id}/${path}`, init);
      await qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      await qc.invalidateQueries({ queryKey: ["job-activity", jobId] });
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
      return false;
    } finally {
      setBusy(null);
    }
  };
  return {
    busy,
    error,
    accept: (id: number) => run(id, "accept/", { method: "POST" }),
    decline: (id: number, reason: string) => run(id, "decline/", { method: "POST", body: JSON.stringify({ reason }) }),
    withdraw: (id: number) => run(id, "", { method: "DELETE" }),
  };
}

/** One suggestion: what changes, who suggested it, and the valuer's answer. */
export function SuggestionItem({ jobId, s, canDecide, compact }: {
  jobId: string; s: Suggestion; canDecide: boolean; compact?: boolean;
}) {
  const actions = useActions(jobId);
  const { data: me } = useMe();
  const mine = me?.authenticated && me.user.id === s.by_id;
  // Nobody answers their own suggestion: its author can only withdraw it.
  const decide = canDecide && !mine;
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const open = s.status === "open";

  return (
    <div className={"suggestion" + (open ? "" : " closed")}>
      <div className="row" style={{ justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
        <b style={{ fontSize: 14 }}>{s.label}</b>
        {!open && (
          <span className={"sugg-status " + s.status}>{s.status === "accepted" ? "Accepted" : "Declined"}</span>
        )}
      </div>
      <div className="sugg-change">
        <span className="sugg-old">{s.old_text || "(empty)"}</span>
        <Icon name="arrow-right" size={13} />
        <span className="sugg-new">{s.new_text || "(empty)"}</span>
      </div>
      {s.note && <div className="sugg-note">“{s.note}”</div>}
      <div className="sugg-meta">
        {s.by} · {formatDateTime(s.at)}
        {!open && s.decided_by ? ` · ${s.status} by ${s.decided_by}` : ""}
      </div>
      {s.status === "declined" && s.decline_reason && <div className="sugg-note">Why: {s.decline_reason}</div>}

      {open && decide && !declining && (
        <div className="row" style={{ gap: 8, marginTop: 8 }}>
          <Button size="sm" disabled={actions.busy === s.id} icon={<Icon name="check" size={15} />}
            onClick={() => void actions.accept(s.id)}>
            Accept
          </Button>
          <Button size="sm" variant="outline" disabled={actions.busy === s.id} onClick={() => setDeclining(true)}>
            Decline
          </Button>
        </div>
      )}
      {open && declining && (
        <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
          <Textarea rows={compact ? 2 : 3} placeholder="Why? The reviewer sees this." value={reason}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setReason(e.target.value)} />
          <div className="row" style={{ gap: 8 }}>
            <Button size="sm" disabled={!reason.trim() || actions.busy === s.id}
              onClick={() => void actions.decline(s.id, reason).then((ok) => ok && setDeclining(false))}>
              Decline
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDeclining(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {open && mine && (
        <button type="button" className="link-btn" style={{ marginTop: 6 }} disabled={actions.busy === s.id}
          onClick={() => void actions.withdraw(s.id)}>
          Withdraw
        </button>
      )}
      {actions.error && <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 6 }}>{actions.error}</div>}
    </div>
  );
}

/** Every suggestion on the lead, open ones first (Review tab). */
export function SuggestionsPanel({ jobId, suggestions, canDecide, reviewing }: {
  jobId: string; suggestions: Suggestion[]; canDecide: boolean; reviewing: boolean;
}) {
  const qc = useQueryClient();
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = suggestions.filter((s) => s.status === "open");
  if (!suggestions.length && !reviewing) return null;
  const shown = showAll ? [...open, ...suggestions.filter((s) => s.status !== "open")] : open;

  async function acceptAll() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/reviewer-edits/accept/`, { method: "POST" });
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      await qc.invalidateQueries({ queryKey: ["job-activity", jobId] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card sugg-panel">
      <div className="row wrap" style={{ justifyContent: "space-between", gap: 10 }}>
        <div>
          <div className="row" style={{ gap: 8, fontSize: 16, fontWeight: 700 }}>
            <Icon name="sparkles" size={17} />
            {open.length ? `${open.length} suggestion${open.length === 1 ? "" : "s"} to answer` : "Suggestions"}
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
            {reviewing
              ? "Change any field on the earlier stages: it's saved as a suggestion for the valuer, not over their value."
              : canDecide
                ? "Accept to save the reviewer's value, or decline with a reason. Sign-off waits until each is answered."
                : "The valuer answers these before the report can be signed off."}
          </div>
        </div>
        {canDecide && open.length > 1 && (
          <Button size="sm" disabled={busy} icon={<Icon name="check-check" size={16} />} onClick={() => void acceptAll()}>
            {busy ? "Accepting…" : "Accept all"}
          </Button>
        )}
      </div>
      {error && <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 8 }}>{error}</div>}
      {shown.length > 0 && (
        <div className="sugg-list">
          {shown.map((s) => <SuggestionItem key={s.id} jobId={jobId} s={s} canDecide={canDecide} />)}
        </div>
      )}
      {suggestions.length > open.length && (
        <button type="button" className="link-btn" style={{ marginTop: 10 }} onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show only open ones" : `Show all ${suggestions.length}, including answered`}
        </button>
      )}
    </div>
  );
}
