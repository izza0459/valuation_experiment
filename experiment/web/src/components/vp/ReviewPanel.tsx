"use client";

/**
 * The Review & Send tab. It shows only what matters at the job's point:
 *
 *   - Before review: send it to the peer reviewer.
 *   - In review: the report, with "Sign off" and "Return to valuer" for the
 *     assigned reviewer only. Their sign-off is the second signature and
 *     produces the final report.
 *   - Signed off: download it and send it to the bank (the admin who created
 *     the job).
 *
 * The buttons come from `job.available_actions` (TransitionBar), which the
 * server computes from the rules it enforces.
 */

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon, Input, Select, Textarea } from "@/design-system";
import { ApiError, apiFetch, apiUrl } from "@/lib/api";
import type { JobDetail } from "@/lib/jobs";
import { formatDateTime } from "./format";
import { TransitionBar } from "./TransitionBar";
import { Banner } from "./ui";

type Person = { id: number; name: string; email?: string; roles: string[] };

function personFor(job: JobDetail, role: string): Person | undefined {
  return ((job.assignees ?? []) as Person[]).find((p) => p.roles.includes(role));
}

const who = (p?: Person) => (p ? `${p.name}${p.email && p.email !== p.name ? ` (${p.email})` : ""}` : "");

function Heading({ title, sub }: { title: string; sub?: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 18 }}>{title}</div>
      {sub && <div style={{ fontSize: 14, color: "var(--text-muted)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function ReportFrame({ jobId }: { jobId: string }) {
  const src = apiUrl(`/api/jobs/${jobId}/report/preview/`);
  return (
    <div>
      <div className="row" style={{ justifyContent: "flex-end", marginBottom: 8 }}>
        {/* Its own page in the app, with a Back button (a new window has no way back on the phone). */}
        <Link href={`/jobs/${jobId}/report`} style={{ textDecoration: "none" }}>
          <Button size="sm" variant="outline" icon={<Icon name="maximize-2" size={16} />}>
            Full screen
          </Button>
        </Link>
      </div>
      <iframe
        title="Report for review"
        src={src}
        style={{ width: "100%", height: 640, border: "1px solid var(--border-subtle)", borderRadius: 8, background: "#fff" }}
      />
    </div>
  );
}

export function ReviewPanel({ job, jobId, onSend }: { job: JobDetail; jobId: string; onSend: () => void }) {
  const reviewer = personFor(job, "peer_reviewer");
  const canSignOff = (job.available_actions ?? []).some((a) => a.to === "issued" && job.status === "peer_review");

  // Signed off and issued: on to sending it.
  if (job.status === "issued") {
    return (
      <div style={{ display: "grid", gap: 18 }}>
        <Heading
          title="Signed off"
          sub={`${job.countersigned_by_name || reviewer?.name || "The peer reviewer"} signed it off. The final report is ready to send to the bank.`}
        />
        <div>
          <Button icon={<Icon name="send" size={16} />} onClick={onSend}>
            Go to Send to bank
          </Button>
        </div>
      </div>
    );
  }

  // Signed off; the final report is being produced (or needs another try).
  if (job.status === "approved_signed") {
    return (
      <div style={{ display: "grid", gap: 18 }}>
        <Heading
          title="Signed off"
          sub={
            job.issue_in_progress
              ? "The final report is being produced. The send-to-bank option appears here when it's ready."
              : "The final report hasn't been produced yet. An admin can try again below."
          }
        />
        <TransitionBar job={job} jobId={jobId} />
      </div>
    );
  }

  // With the reviewer.
  if (job.status === "peer_review") {
    return (
      <div style={{ display: "grid", gap: 18 }}>
        {canSignOff ? (
          <Heading
            title="Review and sign off"
            sub="Read the report below. Signing off is the second signature: the final PDF is produced and the job is locked. Or return it to the valuer with your comments."
          />
        ) : (
          <Heading
            title={`Waiting for ${reviewer?.name ?? "the peer reviewer"} to sign off`}
            sub={`Only ${who(reviewer) || "the assigned peer reviewer"} can sign it off or return it. The job can't be edited meanwhile.`}
          />
        )}
        <TransitionBar job={job} jobId={jobId} />
        {canSignOff && <ReportFrame jobId={jobId} />}
      </div>
    );
  }

  // Still being worked on.
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <Heading
        title="Send for review"
        sub={
          reviewer
            ? `${who(reviewer)} reviews it and signs it off. Once they do, you can download the report and send it to the bank here.`
            : "Assign a peer reviewer on the Check List first."
        }
      />
      <TransitionBar job={job} jobId={jobId} />
    </div>
  );
}

/** The Send to bank stage: the issued report, and sending it. */
export function SendPanel({ job, jobId }: { job: JobDetail; jobId: string }) {
  const reviewer = personFor(job, "peer_reviewer");
  if (job.status !== "issued") {
    return (
      <Heading
        title="Send to bank"
        sub={`This opens once ${reviewer?.name ?? "the peer reviewer"} has signed the report off.`}
      />
    );
  }
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <Heading title="Send to bank" sub="Download the signed-off report, or send it to the bank from here." />
      <TransitionBar job={job} jobId={jobId} />
      <SendToBank job={job} jobId={jobId} />
    </div>
  );
}

/** Send the issued report to someone at the bank by email. */
function SendToBank({ job, jobId }: { job: JobDetail; jobId: string }) {
  const qc = useQueryClient();
  const contacts = job.bank_contacts ?? [];
  const [choice, setChoice] = useState(contacts[0]?.email ?? "other");
  const [other, setOther] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const email = choice === "other" ? other.trim() : choice;

  async function send() {
    setBusy(true);
    setError(null);
    setFailure(null);
    try {
      const delivery = await apiFetch<{ status: string; error: string }>(`/api/jobs/${jobId}/report/send/`, {
        method: "POST",
        body: JSON.stringify({ email, message }),
      });
      if (delivery.status === "failed") {
        setSentTo(null);
        setFailure(delivery.error || "The email could not be sent.");
      } else {
        setSentTo(email);
        setFailure(null);
      }
      setMessage("");
      setOther("");
      await qc.invalidateQueries({ queryKey: ["jobs", jobId] });
    } catch (err) {
      const errors = err instanceof ApiError ? (err.body?.errors as Record<string, string> | undefined) : undefined;
      setError(errors?.email ?? (err instanceof ApiError ? err.message : "Couldn't reach the server. Try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ padding: 18, display: "grid", gap: 14 }}>
      <div>
        <div style={{ fontSize: 16 }}>Send the report</div>
        <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
          {job.bank_name as string} · the issued PDF goes as an attachment
        </div>
      </div>

      {job.can_send_report ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 14 }}>
            <div>
              <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}>Send to</div>
              <Select
                value={choice}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setChoice(e.target.value)}
                options={[
                  ...contacts.map((c) => ({ value: c.email, label: c.name ? `${c.name} · ${c.email}` : c.email })),
                  { value: "other", label: "Someone else…" },
                ]}
              />
            </div>
            {choice === "other" && (
              <div>
                <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}>Email address</div>
                <Input
                  type="email"
                  value={other}
                  placeholder="name@bank.ae"
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOther(e.target.value)}
                />
              </div>
            )}
          </div>
          {contacts.length === 0 && (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              This bank has no contacts with an email yet. Add them under Admin › Banks to pick from a list.
            </div>
          )}
          <div>
            <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}>Message (optional)</div>
            <Textarea rows={3} value={message} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setMessage(e.target.value)} />
          </div>
          {error && <div style={{ fontSize: 13, color: "var(--text-error)" }}>{error}</div>}
          {failure && !error && <div style={{ fontSize: 13, color: "var(--text-error)" }}>Not sent: {failure}</div>}
          {sentTo && !error && !failure && (
            <Banner tone="green" icon="check">
              Report sent to {sentTo}.
            </Banner>
          )}
          <div>
            <Button disabled={busy || !email} icon={<Icon name="send" size={16} />} onClick={() => void send()}>
              {busy ? "Sending…" : "Send report"}
            </Button>
          </div>
        </>
      ) : (
        <div style={{ fontSize: 14, color: "var(--text-muted)" }}>Only the admin who created this job can send it to the bank.</div>
      )}

      {(job.deliveries ?? []).length > 0 && (
        <div style={{ borderTop: "1px solid var(--border-divider)", paddingTop: 12 }}>
          <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 8 }}>Sent so far</div>
          <div style={{ display: "grid", gap: 8 }}>
            {job.deliveries!.map((d) => (
              <div key={d.id} className="row" style={{ justifyContent: "space-between", fontSize: 14 }}>
                <span>
                  {d.recipient_name ? `${d.recipient_name} · ` : ""}
                  {d.recipient_email}
                </span>
                <span style={{ color: "var(--text-muted)" }}>
                  {d.status_label} · {formatDateTime(d.requested_at)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
