"use client";

/**
 * A lead at a glance from the Jobs list, without leaving it: a panel on the
 * right laid out as a Bayut property card (photo, stage, checks, location,
 * facts, value), then the people and what is waiting. Up/down arrows move
 * between rows; Esc closes.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { Avatar, Button, Icon } from "@/design-system";
import { apiUrl } from "@/lib/api";
import { useJob } from "@/lib/jobs";
import { useOptions } from "@/lib/options";
import { aed, formatDateTime } from "./format";
import { ReassignDialog } from "./ReassignDialog";
import { CheckBadges, LocationPath, StatusChip } from "./ui";

const ROLE_NAMES: Record<string, string> = {
  admin: "Admin", inspector: "Inspector", valuer: "Valuer", peer_reviewer: "Peer reviewer",
  counter_signatory: "Counter-signatory",
};

export function LeadPreview({ jobId, onClose, onStep }: {
  jobId: number;
  onClose: () => void;
  /** Move to the previous (-1) or next (1) row. */
  onStep: (by: -1 | 1) => void;
}) {
  const { data: job, isLoading } = useJob(String(jobId));
  const [reassigning, setReassigning] = useState(false);
  const { data: options } = useOptions();

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (reassigning || (e.target as HTMLElement).closest("input, textarea, select")) return;
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") { e.preventDefault(); onStep(1); }
      if (e.key === "ArrowUp") { e.preventDefault(); onStep(-1); }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose, onStep, reassigning]);

  const summary = (job?.summary ?? {}) as { type_of_property?: string; property_category?: string; no_of_bedrooms?: number | null };
  const bua = (job?.tabs.summary?.values?.bua_sqm ?? null) as string | null;
  const buaSqft = job?.tabs.summary?.computed?.bua_sqft as string | number | undefined;
  const value = (job?.valuation as { market_value?: string | null } | null)?.market_value;
  const people = (job?.assignees ?? []) as { id: number; name: string; roles: string[] }[];
  const open = (job?.suggestions ?? []).filter((s) => s.status === "open").length;
  const category = options?.property_category?.find((o) => o.value === summary.property_category)?.label;
  const sqft = Number(buaSqft);

  return (
    <>
      <div className="preview-scrim" onClick={onClose} />
      <aside className="preview" role="dialog" aria-label="Lead preview">
        <div className="preview-head">
          <span className="eyebrow">Lead preview</span>
          <div className="row" style={{ gap: 4 }}>
            <button type="button" className="icon-btn" aria-label="Previous lead" onClick={() => onStep(-1)}><Icon name="chevron-up" size={18} /></button>
            <button type="button" className="icon-btn" aria-label="Next lead" onClick={() => onStep(1)}><Icon name="chevron-down" size={18} /></button>
            <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><Icon name="x" size={18} /></button>
          </div>
        </div>

        {isLoading || !job ? (
          <div style={{ padding: 20 }}><div className="skel" style={{ height: 320 }} /></div>
        ) : (
          <div className="preview-body">
            <div className="preview-photo">
              {job.cover_photo ? (
                // eslint-disable-next-line @next/next/no-img-element -- authenticated API thumbnail
                <img src={apiUrl(job.cover_photo)} alt="" />
              ) : (
                <div className="preview-nophoto"><Icon name="image" size={28} />No photos yet</div>
              )}
              <span className="preview-pill"><StatusChip s={job.progress?.stage_label ?? job.status_label} /></span>
            </div>

            <div style={{ padding: "16px 20px", display: "grid", gap: 10 }}>
              <div>
                <div className="preview-value">{value ? aed(value) : "Value not set"}</div>
                <div className="preview-facts">
                  {summary.type_of_property || category || "Type not set"}
                  {summary.no_of_bedrooms ? ` · ${summary.no_of_bedrooms} bed` : ""}
                  {bua ? ` · ${bua} sqm${sqft ? ` (${Math.round(sqft).toLocaleString("en-GB")} sqft)` : ""}` : ""}
                </div>
              </div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>{job.property_label}</div>
              <LocationPath parts={job.location_path} />
              <CheckBadges checks={job.checks} />
              {job.lost && (
                <div className="ov-lost"><b>Lost at {job.lost.stage}:</b> {job.lost.reason}</div>
              )}
              {open > 0 && (
                <div className="suggest-note"><Icon name="sparkles" size={14} /> {open} suggestion{open === 1 ? "" : "s"} from the peer reviewer</div>
              )}
            </div>

            <dl className="preview-rows">
              <dt>Bank</dt><dd>{job.bank_name || "—"}</dd>
              <dt>Bayut ref</dt><dd className="num">{job.bayut_internal_reference_no}</dd>
              <dt>Bank ref</dt><dd className="num">{job.bank_reference_no || "—"}</dd>
              <dt>Received</dt><dd>{formatDateTime(job.date_time_request_received ?? job.created_at)}</dd>
              <dt>Inspection</dt><dd>{job.inspection_booked_at ? formatDateTime(job.inspection_booked_at) : "Not booked"}</dd>
              <dt>Waiting on</dt><dd>{job.progress?.sub_status || "—"}</dd>
            </dl>

            <div style={{ padding: "4px 20px 16px" }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>People</div>
              <div style={{ display: "grid", gap: 8 }}>
                {people.length === 0 && <span style={{ fontSize: 14, color: "var(--text-muted)" }}>Nobody assigned yet</span>}
                {people.map((p) => (
                  <div key={p.id} className="row" style={{ gap: 10, fontSize: 14 }}>
                    <Avatar name={p.name} size={26} />
                    <span>
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
        )}

        {job && (
          <div className="preview-foot">
            {job.can_reassign && (
              <Button variant="outline" icon={<Icon name="user-round-pen" size={16} />} onClick={() => setReassigning(true)}>
                Reassign
              </Button>
            )}
            <Link href={`/jobs/${job.id}`} style={{ marginLeft: "auto" }}>
              <Button icon={<Icon name="arrow-right" size={16} />}>Open lead</Button>
            </Link>
          </div>
        )}
      </aside>
      {reassigning && job && (
        <ReassignDialog jobId={String(job.id)} onClose={() => setReassigning(false)}
          current={Object.fromEntries(people.flatMap((p) => p.roles.map((r) => [r, p.id])))} />
      )}
    </>
  );
}
