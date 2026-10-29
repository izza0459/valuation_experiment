"use client";

/**
 * The lead card on the right of the workspace: Overview (the lead at a
 * glance, with the latest AVM) and Activity (everything that happened to it,
 * newest first: stage moves, review comments, calls, sends and edits).
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Avatar, Tabs } from "@/design-system";
import { apiFetch } from "@/lib/api";
import { useJob } from "@/lib/jobs";
import { aed, formatDateTime } from "./format";
import { Conf, StatusChip, Tip } from "./ui";

type AvmSummary = {
  suggested_value: string;
  low_value: string;
  high_value: string;
  aed_per_sqft: string;
  confidence: "high" | "medium" | "low";
  created_at: string;
};

type ActivityItem = {
  kind: "stage" | "lost" | "call" | "send" | "edit";
  title: string;
  detail: string;
  old?: string;
  new?: string;
  who: string;
  at: string;
};

const ROLE_NAMES: Record<string, string> = {
  admin: "Admin", inspector: "Inspector", valuer: "Valuer", peer_reviewer: "Peer reviewer",
  counter_signatory: "Counter-signatory",
};

export function RightPanel({ jobId }: { jobId: string }) {
  const [sub, setSub] = useState("Overview");
  return (
    <aside className="rightpanel" style={{ width: 340, flexShrink: 0, alignSelf: "flex-start" }}>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <Tabs size="sm" items={["Overview", "Activity"]} active={sub} onChange={setSub} style={{ gap: 22, padding: "0 18px" }} />
        <div style={{ padding: 18, maxHeight: "calc(100vh - 220px)", overflowY: "auto" }}>
          {sub === "Overview" ? <Overview jobId={jobId} /> : <Activity jobId={jobId} />}
        </div>
      </div>
    </aside>
  );
}

function Row({ label, tip, children }: { label: string; tip?: string; children: React.ReactNode }) {
  return (
    <div className="ov-row">
      <span className="row" style={{ gap: 4 }}>
        {label}
        <Tip text={tip} size={13} />
      </span>
      <span>{children || "—"}</span>
    </div>
  );
}

function Overview({ jobId }: { jobId: string }) {
  const { data: job } = useJob(jobId);
  const [now] = useState(() => Date.now());
  const { data: evidence } = useQuery({
    queryKey: ["job-evidence", jobId],
    queryFn: () => apiFetch<{ avm: AvmSummary | null }>(`/api/jobs/${jobId}/evidence/`),
  });
  if (!job) return <div className="skel" style={{ height: 200 }} />;
  const value = (job.valuation as { market_value?: string | null } | null)?.market_value;
  const summary = (job.summary ?? {}) as { property_category?: string; type_of_property?: string };
  const property = (job.property ?? {}) as { community_name?: string };
  const people = (job.assignees ?? []) as { id: number; name: string; roles: string[] }[];
  const run = evidence?.avm;
  const received = new Date(job.date_time_request_received ?? job.created_at).getTime();

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
          <StatusChip s={job.progress?.stage_label ?? job.status_label} />
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{job.progress?.sub_status}</span>
        </div>
        {job.lost && (
          <div className="ov-lost">
            <b>Lost at {job.lost.stage}:</b> {job.lost.reason}
            {job.lost.note ? ` · ${job.lost.note}` : ""}
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
              {job.lost.by}, {formatDateTime(job.lost.at)}
            </div>
          </div>
        )}
      </div>

      <div className="ov-group">
        <Row label="Bayut ref"><span className="num">{job.bayut_internal_reference_no}</span></Row>
        <Row label="Bank ref"><span className="num">{job.bank_reference_no}</span></Row>
        <Row label="Bank">{job.bank_name}</Row>
        <Row label="Purpose">{purposeLabel(job.purpose)}</Row>
      </div>

      <div className="ov-group">
        <Row label="Property">{job.property_label}</Row>
        <Row label="Community">{property.community_name}</Row>
        <Row label="Type">{summary.type_of_property || job.property_type}</Row>
      </div>

      <div className="ov-group">
        <Row label="Received" tip="When the bank's request arrived.">
          {formatDateTime(job.date_time_request_received ?? job.created_at)}
        </Row>
        <Row label="Inspection" tip="When the inspection is booked for.">
          {job.inspection_booked_at ? formatDateTime(job.inspection_booked_at) : ""}
        </Row>
        <Row label="Age" tip="Days since the request arrived.">
          {`${Math.max(0, Math.floor((now - received) / 864e5))} days`}
        </Row>
      </div>

      <div className="ov-group">
        <Row label="Market value" tip="The valuer's figure on the Valuation tab.">{value ? aed(value) : ""}</Row>
        <Row label="AVM" tip="Latest AVM run on the ticked comparables (Evidence tab).">
          {run ? `${aed(run.suggested_value)}` : ""}
        </Row>
        {run && (
          <div className="row" style={{ justifyContent: "space-between", fontSize: 12.5, color: "var(--text-muted)" }}>
            <span>{aed(run.low_value)} – {aed(run.high_value)}</span>
            <Conf l={(run.confidence[0].toUpperCase() + run.confidence.slice(1)) as "High" | "Medium" | "Low"} />
          </div>
        )}
      </div>

      <div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>PEOPLE</div>
        <div style={{ display: "grid", gap: 8 }}>
          {people.length === 0 && <span style={{ fontSize: 14, color: "var(--text-muted)" }}>Nobody assigned yet</span>}
          {people.map((p) => (
            <div key={p.id} className="row" style={{ gap: 10, fontSize: 14 }}>
              <Avatar name={p.name} size={26} />
              <span style={{ minWidth: 0 }}>
                {p.name}
                <span style={{ display: "block", fontSize: 12, color: "var(--text-muted)" }}>
                  {p.roles.map((r) => ROLE_NAMES[r] ?? r).join(", ")}
                </span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function purposeLabel(p: string) {
  return p ? p.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "";
}

function Activity({ jobId }: { jobId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["job-activity", jobId],
    queryFn: () => apiFetch<ActivityItem[]>(`/api/jobs/${jobId}/activity/`),
  });
  const [edits, setEdits] = useState(false);
  if (isLoading) return <div className="skel" style={{ height: 120 }} />;
  if (isError) return <div style={{ fontSize: 14, color: "var(--text-error)" }}>Could not load the activity.</div>;
  const items = (data ?? []).filter((i) => edits || i.kind !== "edit");
  return (
    <div>
      <label className="row" style={{ gap: 8, fontSize: 13, color: "var(--text-secondary)", marginBottom: 12, cursor: "pointer" }}>
        <input type="checkbox" checked={edits} onChange={(e) => setEdits(e.target.checked)} />
        Show field changes
      </label>
      {items.length === 0 && <div style={{ fontSize: 14, color: "var(--text-muted)" }}>Nothing yet.</div>}
      <ol className="timeline">
        {items.map((i, n) => (
          <li key={n} className={`tl-${i.kind}`}>
            <span className="tl-dot" />
            <div style={{ fontSize: 14, fontWeight: 500 }}>{i.title}</div>
            {i.detail && <div style={{ fontSize: 13.5, whiteSpace: "pre-wrap", marginTop: 2 }}>{i.detail}</div>}
            {i.kind === "edit" && (
              <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 2, wordBreak: "break-word" }}>
                {short(i.old) || "(empty)"} → {short(i.new) || "(empty)"}
              </div>
            )}
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
              {i.who ? `${i.who} · ` : ""}
              {formatDateTime(i.at)}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function short(v?: string) {
  if (!v) return "";
  return v.length > 80 ? `${v.slice(0, 80)}…` : v;
}
