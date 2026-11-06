"use client";

/**
 * The lead card on the right of the workspace: Overview (the lead at a
 * glance, with the latest AVM), Activity (everything that happened to it,
 * newest first: stage moves, review comments, calls, sends and edits) and
 * Documents (what came with the instruction, and any added since, to read
 * without leaving the page).
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon, Tabs } from "@/design-system";
import { apiFetch, apiUrl } from "@/lib/api";
import { useMedia, type MediaItem } from "@/lib/media";
import { useOptions } from "@/lib/options";
import { useJob } from "@/lib/jobs";
import { aed, formatDateTime } from "./format";
import { LeadCardSuggestions } from "./Suggestions";
import { Conf, LocationPath, StatusChip, Tip } from "./ui";

type AvmSummary = {
  suggested_value: string;
  low_value: string;
  high_value: string;
  aed_per_sqft: string;
  confidence: "high" | "medium" | "low";
  created_at: string;
};

type ActivityItem = {
  kind: "stage" | "lost" | "call" | "send" | "edit" | "assign" | "suggest";
  title: string;
  detail: string;
  old?: string;
  new?: string;
  who: string;
  at: string;
};

export function RightPanel({ jobId }: { jobId: string }) {
  const [sub, setSub] = useState("Overview");
  return (
    <aside className="rightpanel" style={{ width: 340, flexShrink: 0, alignSelf: "flex-start" }}>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <Tabs size="sm" items={["Overview", "Activity", "Documents"]} active={sub} onChange={setSub} style={{ gap: 22, padding: "0 18px", overflowY: "hidden", scrollbarWidth: "none" }} />
        <div style={{ padding: 18 }}>
          {sub === "Overview" ? <Overview jobId={jobId} /> : sub === "Activity" ? <Activity jobId={jobId} />
            : <Documents jobId={jobId} />}
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
  const { data: options } = useOptions();
  const { data: evidence } = useQuery({
    queryKey: ["job-evidence", jobId],
    queryFn: () => apiFetch<{ avm: AvmSummary | null }>(`/api/jobs/${jobId}/evidence/`),
  });
  if (!job) return <div className="skel" style={{ height: 200 }} />;
  const value = (job.valuation as { market_value?: string | null } | null)?.market_value;
  const summary = (job.summary ?? {}) as { property_category?: string; type_of_property?: string };
  const category = options?.property_category?.find((o) => o.value === summary.property_category)?.label;
  const property = (job.property ?? {}) as { community_name?: string };
  const run = evidence?.avm;
  const received = new Date(job.date_time_request_received ?? job.created_at).getTime();

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="ov-status">
          <div style={{ minWidth: 0 }}>
            <div className="ov-eyebrow">Report status</div>
            <div className="ov-status-text">{job.progress?.sub_status || job.status_label}</div>
          </div>
          <StatusChip s={job.progress?.stage_label ?? job.status_label} />
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

      <LeadCardSuggestions
        jobId={jobId}
        suggestions={job.suggestions ?? []}
        canDecide={Boolean(job.can_decide_suggestions)}
        reviewing={Object.values(job.tabs).some((tab) => tab.can_suggest)}
      />

      <div className="ov-group">
        <Row label="Property">{job.property_label}</Row>
        <Row label="Community">{property.community_name}</Row>
        <Row label="Type">{summary.type_of_property || category}</Row>
        <LocationPath parts={job.location_path} />
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
            {(i.kind === "edit" || i.kind === "assign" || i.kind === "suggest") && (i.old !== undefined || i.new !== undefined) && (
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

/** Uploaded this soon after the lead was created: it came with the instruction. */
const WITH_INSTRUCTION_MS = 30 * 60 * 1000;

/** The lead's documents, oldest first (the bank's instruction document leads),
 * each opening into a preview here. */
function Documents({ jobId }: { jobId: string }) {
  const { data, isLoading, isError } = useMedia(jobId, "documents");
  const { data: job } = useJob(jobId);
  const [open, setOpen] = useState<number | null>(null);
  if (isLoading) return <div className="skel" style={{ height: 120 }} />;
  if (isError || !data) return <div style={{ fontSize: 14, color: "var(--text-error)" }}>Could not load the documents.</div>;
  const items = [...data.items].sort((a, b) => a.uploaded_at.localeCompare(b.uploaded_at));
  if (items.length === 0) {
    return <div style={{ fontSize: 14, color: "var(--text-muted)" }}>No documents yet. They&apos;re added with the instruction or on Documents.</div>;
  }
  const typeLabel = (v?: string) => data.doc_types.find((t) => t.value === v)?.label ?? (v ? v.replace(/_/g, " ") : "Document");
  const created = job ? new Date(job.created_at).getTime() : null;
  const withInstruction = (d: MediaItem) =>
    created !== null && new Date(d.uploaded_at).getTime() - created < WITH_INSTRUCTION_MS;
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {items.map((d) => {
        const shown = open === d.id;
        return (
          <div key={d.id} className={"doc-card" + (shown ? " on" : "")}>
            <button type="button" className="doc-head" aria-expanded={shown} onClick={() => setOpen(shown ? null : d.id)}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={apiUrl(d.thumb_url)} alt="" className="doc-thumb" loading="lazy" />
              <span style={{ minWidth: 0, display: "grid", gap: 2 }}>
                <span className="row" style={{ gap: 6 }}>
                  <b className="one-line" style={{ fontWeight: 600, fontSize: 13.5 }}>{typeLabel(d.doc_type)}</b>
                  {withInstruction(d) && <span className="doc-tag">Instruction</span>}
                </span>
                {d.caption && <span className="one-line" style={{ fontSize: 12.5 }}>{d.caption}</span>}
                <span className="one-line" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {d.uploaded_by ? `${d.uploaded_by} · ` : ""}{formatDateTime(d.uploaded_at)}
                </span>
              </span>
              <Icon name={shown ? "chevron-up" : "eye"} size={16} color="var(--text-muted)" />
            </button>
            {shown && (
              <div style={{ display: "grid", gap: 6 }}>
                {d.is_pdf ? (
                  <iframe title={typeLabel(d.doc_type)} src={apiUrl(d.url)} className="doc-frame" />
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={apiUrl(d.url)} alt={d.caption || typeLabel(d.doc_type)} className="doc-image" />
                )}
                <a href={apiUrl(d.url)} target="_blank" rel="noopener noreferrer" className="doc-open">
                  <Icon name="external-link" size={14} /> Open in a new tab
                </a>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
