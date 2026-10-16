"use client";

/**
 * Lifecycle actions for the workspace header (design brief S3).
 *
 * The buttons are drawn from `job.available_actions`, which the server
 * computes from the same rules it enforces: only moves this user's role may
 * make appear, and a blocked one is disabled with the reason. Nothing here
 * decides who may do what.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Dialog, Icon, Textarea } from "@/design-system";
import { ApiError, apiFetch, apiUrl } from "@/lib/api";
import type { JobAction, JobDetail } from "@/lib/jobs";
import { ReportActions } from "./ReportActions";
import { Banner } from "./ui";

type Failure = { message: string; blockers: string[] };

const EARLY_STEPS = new Set(["setup", "inspection_scheduled", "inspected", "valuation_in_progress"]);
/** From these, a move back to valuation is a return or reopen, which stays. */
const REVIEWING = new Set(["peer_review", "approved_signed"]);

function describe(err: unknown): Failure {
  if (err instanceof ApiError) {
    const blockers = Array.isArray(err.body?.blockers) ? (err.body?.blockers as string[]) : [];
    const errors = err.body?.errors as Record<string, string> | undefined;
    return { message: errors?.comments ?? err.message, blockers };
  }
  return { message: "Couldn't reach the server. Try again.", blockers: [] };
}

export function TransitionBar({ job, jobId }: { job: JobDetail; jobId: string }) {
  const qc = useQueryClient();
  const [pending, setPending] = useState<JobAction | null>(null);
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [confirming, setConfirming] = useState<JobAction | null>(null);

  // The stages before review move on by themselves as their tabs fill in, so
  // their manual steps ("Start setup" and the like) aren't offered here.
  const actions = (job.available_actions ?? []).filter((a) => !EARLY_STEPS.has(a.to) || REVIEWING.has(job.status));
  const blocked = actions.filter((a) => !a.enabled);

  // Issuing finishes in the background (the job query polls meanwhile); when
  // it ends, refresh what it changed besides the job itself.
  const wasIssuing = useRef(Boolean(job.issue_in_progress));
  useEffect(() => {
    if (wasIssuing.current && !job.issue_in_progress) {
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      void qc.invalidateQueries({ queryKey: ["job-kpis"] });
      void qc.invalidateQueries({ queryKey: ["job-activity", jobId] });
      void qc.invalidateQueries({ queryKey: ["job-transitions", jobId] });
    }
    wasIssuing.current = Boolean(job.issue_in_progress);
  }, [job.issue_in_progress, jobId, qc]);

  async function run(action: JobAction, text: string) {
    setBusy(true);
    setFailure(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/transitions/`, {
        method: "POST",
        body: JSON.stringify({ from: job.status, to: action.to, comments: text }),
      });
      setPending(null);
      setConfirming(null);
      setComments("");
      // Status, which tabs are editable, the dashboard, and the history all move.
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["jobs"] }),
        qc.invalidateQueries({ queryKey: ["job-kpis"] }),
        qc.invalidateQueries({ queryKey: ["job-activity", jobId] }),
        qc.invalidateQueries({ queryKey: ["job-transitions", jobId] }),
      ]);
    } catch (err) {
      setFailure(describe(err));
      if (err instanceof ApiError && err.status === 409) {
        // The job moved under us; show what it is now.
        qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      }
    } finally {
      setBusy(false);
    }
  }

  function click(action: JobAction) {
    setFailure(null);
    if (action.comments_required) setPending(action);
    // Issuing can't be undone: it locks the job and stores the final PDF.
    else if (action.to === "issued") setConfirming(action);
    else void run(action, "");
  }

  return (
    <>
      {failure && !pending && !confirming && (
        <div style={{ marginTop: 12 }}>
          <Banner tone="red" icon="alert-circle">
            {failure.message}
            {failure.blockers.length > 0 && (
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {failure.blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
          </Banner>
        </div>
      )}

      <div
        className="row"
        style={{ justifyContent: "flex-end", gap: 10, marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border-divider)" }}
      >
        {blocked.length > 0 && (
          <div style={{ marginRight: "auto", fontSize: 13, color: "var(--text-muted)", maxWidth: "60%" }}>
            <Icon name="info" size={14} /> {blocked[0].label} is waiting on: {blocked[0].blockers.join(" · ")}
          </div>
        )}

        {job.is_locked ? <IssuedActions job={job} jobId={jobId} /> : <ReportActions jobId={jobId} />}

        {actions.map((action) => (
          <Button
            key={action.to}
            variant={action.tone === "outline" ? "outline" : "primary"}
            size="sm"
            disabled={!action.enabled || busy}
            title={action.enabled ? undefined : action.blockers.join("\n")}
            onClick={() => click(action)}
          >
            {action.label}
          </Button>
        ))}

      </div>

      <Dialog
        open={confirming !== null}
        title={job.status === "peer_review" ? "Sign off this report?" : "Issue this report?"}
        subtitle={
          job.status === "peer_review"
            ? "Your sign-off is the report's second signature. The final PDF is produced and the job is locked; changing anything afterwards means creating a new version."
            : "This produces the final PDF and locks the job. Changing anything afterwards means creating a new version."
        }
        onClose={() => {
          setConfirming(null);
          setFailure(null);
        }}
        actions={
          <>
            <Button variant="outline" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
            <Button disabled={busy} onClick={() => confirming && run(confirming, "")}>
              {busy ? "Working…" : (confirming?.label ?? "Issue report")}
            </Button>
          </>
        }
      >
        {failure && (
          <Banner tone="red" icon="alert-circle">
            {failure.message}
            {failure.blockers.length > 0 && (
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {failure.blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
          </Banner>
        )}
      </Dialog>

      <Dialog
        open={pending !== null}
        title={pending?.label ?? ""}
        subtitle="Say why. This is kept on the job and shown to the valuer."
        onClose={() => {
          setPending(null);
          setFailure(null);
        }}
        actions={
          <>
            <Button variant="outline" onClick={() => setPending(null)}>
              Cancel
            </Button>
            <Button disabled={busy || !comments.trim()} onClick={() => pending && run(pending, comments)}>
              {pending?.label}
            </Button>
          </>
        }
      >
        <Textarea
          rows={4}
          autoFocus
          value={comments}
          invalid={Boolean(failure)}
          onChange={(e) => setComments(e.target.value)}
        />
        {failure && <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 6 }}>{failure.message}</div>}
      </Dialog>
    </>
  );
}

/** What an issued job offers instead of drafts: its signed-off PDF, and a way
 * to start the next version. */
function IssuedActions({ job, jobId }: { job: JobDetail; jobId: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function revise() {
    setBusy(true);
    setError(null);
    try {
      const revision = await apiFetch<{ id: number }>(`/api/jobs/${jobId}/revise/`, { method: "POST" });
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      router.push(`/jobs/${revision.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
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
      {job.issued_report && (
        <Button
          variant="outline"
          size="sm"
          icon={<Icon name="file-text" size={16} />}
          onClick={() => window.open(apiUrl(`/api/jobs/${jobId}/report/${job.issued_report!.id}/pdf/`), "_blank", "noopener")}
        >
          Issued report (PDF)
        </Button>
      )}
      {job.revision && (
        <Link href={`/jobs/${job.revision.id}`} style={{ fontSize: 13, color: "var(--text-accent)" }}>
          Revision v{job.revision.version} ({job.revision.reference})
        </Link>
      )}
      {job.can_revise && (
        <Button size="sm" disabled={busy} onClick={() => void revise()}>
          {busy ? "Creating…" : "Create revision"}
        </Button>
      )}
    </>
  );
}
