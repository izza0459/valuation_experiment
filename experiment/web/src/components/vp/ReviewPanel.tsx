"use client";

/**
 * The Review & Send tab: everything after the data is in, in one place.
 *
 *   1. Send for review (the valuer)
 *   2. Peer review: "Good to go" or return, only by the assigned reviewer
 *   3. Counter-signature, only by the assigned counter-signatory
 *   4. Issue (the admin)
 *   5. Download the final PDF and send it to the bank
 *
 * The buttons come from `job.available_actions` (TransitionBar), which the
 * server computes from the rules it enforces, so this screen never offers a
 * step the server would refuse.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon, Input, Select, Textarea } from "@/design-system";
import { ApiError, apiFetch, apiUrl } from "@/lib/api";
import type { JobDetail } from "@/lib/jobs";
import { formatDateTime } from "./format";
import { TransitionBar } from "./TransitionBar";
import { Banner } from "./ui";

type Person = { id: number; name: string; email?: string; roles: string[] };

const REVIEW_STATUSES = ["peer_review", "approved_signed", "issued"];

function personFor(job: JobDetail, role: string): Person | undefined {
  return ((job.assignees ?? []) as Person[]).find((p) => p.roles.includes(role));
}

const who = (p?: Person) => (p ? `${p.name}${p.email ? ` (${p.email})` : ""}` : "not assigned yet");

export function ReviewPanel({ job, jobId }: { job: JobDetail; jobId: string }) {
  const reviewer = personFor(job, "peer_reviewer");
  const counter = personFor(job, "counter_signatory");
  const admin = personFor(job, "admin");

  const sent = REVIEW_STATUSES.includes(job.status);
  const approved = job.status === "approved_signed" || job.status === "issued";
  const countersigned = Boolean(job.countersigned_at) || job.status === "issued";
  const issued = job.status === "issued";

  const steps = [
    { title: "Send for review", done: sent, current: !sent, detail: "The valuer sends the finished job to the peer reviewer." },
    {
      title: "Peer review",
      done: approved,
      current: job.status === "peer_review",
      detail: `Only ${who(reviewer)} can say it's good to go, or return it with comments.`,
    },
    {
      title: "Counter-signature",
      done: countersigned,
      current: job.status === "approved_signed" && !countersigned,
      detail: `Signed by ${who(counter)}.`,
    },
    {
      title: "Issue",
      done: issued,
      current: job.status === "approved_signed" && countersigned,
      detail: `Issued by ${who(admin)}, which locks the job and stores the final PDF.`,
    },
    {
      title: "Send to the bank",
      done: (job.deliveries ?? []).length > 0,
      current: issued,
      detail: `${who(admin)} downloads the report and sends it to the bank from here.`,
    },
  ];

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
        {steps.map((s, i) => (
          <li
            key={s.title}
            className="row"
            style={{
              gap: 12,
              alignItems: "flex-start",
              padding: "12px 14px",
              borderRadius: 8,
              border: "1px solid " + (s.current ? "var(--action-primary)" : "var(--border-subtle)"),
              background: s.current ? "var(--surface-subtle)" : "transparent",
            }}
          >
            <span
              style={{
                width: 24,
                height: 24,
                borderRadius: 12,
                flexShrink: 0,
                display: "grid",
                placeItems: "center",
                fontSize: 13,
                color: s.done ? "#fff" : "var(--text-secondary)",
                background: s.done ? "var(--green-600)" : "var(--gray-150)",
              }}
            >
              {s.done ? <Icon name="check" size={14} color="#fff" /> : i + 1}
            </span>
            <div>
              <div style={{ fontSize: 15, fontWeight: s.current ? 500 : 400 }}>{s.title}</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>{s.detail}</div>
            </div>
          </li>
        ))}
      </ol>

      {/* The buttons for whatever this user can do now, with what blocks them. */}
      <TransitionBar job={job} jobId={jobId} />

      {job.status === "peer_review" && (
        <div>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ fontSize: 15 }}>The report as it stands</span>
            <Button
              size="sm"
              variant="outline"
              icon={<Icon name="external-link" size={16} />}
              onClick={() => window.open(apiUrl(`/api/jobs/${jobId}/report/preview/`), "_blank", "noopener")}
            >
              Open in a new window
            </Button>
          </div>
          <iframe
            title="Report for review"
            src={apiUrl(`/api/jobs/${jobId}/report/preview/`)}
            style={{ width: "100%", height: 640, border: "1px solid var(--border-subtle)", borderRadius: 8, background: "#fff" }}
          />
        </div>
      )}

      {issued && <SendToBank job={job} jobId={jobId} />}
    </div>
  );
}

/** The issued PDF, and a request to send it to someone at the bank. Only the
 * request is recorded for now; the email itself is wired in later. */
function SendToBank({ job, jobId }: { job: JobDetail; jobId: string }) {
  const qc = useQueryClient();
  const contacts = job.bank_contacts ?? [];
  const [choice, setChoice] = useState(contacts[0]?.email ?? "other");
  const [other, setOther] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  const email = choice === "other" ? other.trim() : choice;

  async function send() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/report/send/`, {
        method: "POST",
        body: JSON.stringify({ email, message }),
      });
      setSentTo(email);
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
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 16 }}>Send the report to the bank</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
            {job.bank_name as string} · the issued PDF goes as an attachment
          </div>
        </div>
        {job.issued_report && (
          <Button
            size="sm"
            variant="outline"
            icon={<Icon name="download" size={16} />}
            onClick={() => window.open(apiUrl(`/api/jobs/${jobId}/report/${job.issued_report!.id}/pdf/`), "_blank", "noopener")}
          >
            Download PDF
          </Button>
        )}
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
                <Input type="email" value={other} placeholder="name@bank.ae" onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOther(e.target.value)} />
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
          {sentTo && !error && (
            <Banner tone="green" icon="check">
              Queued for {sentTo}. Sending by email is being set up, so it shows as queued for now.
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
