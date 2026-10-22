"use client";

/** The jobs list itself (phones: one card per job; wider screens: a table),
 * and the slim line of summary figures. Shared by the Jobs page and the
 * admin Dashboard. */

import Link from "next/link";
import { Avatar, Table } from "@/design-system";
import { StatusChip } from "@/components/vp/ui";
import { formatDateTime } from "@/components/vp/format";
import type { JobKpis, JobListItem } from "@/lib/jobs";

export function JobsTable({ rows }: { rows: JobListItem[] }) {
  return (
    <>
    {/* Phones: one card per job. */}
    <div className="show-app job-cards">
      {rows.map((j) => (
        <Link key={j.id} href={`/jobs/${j.id}`} className="job-card">
          <div className="row" style={{ justifyContent: "space-between", gap: 10 }}>
            <b className="num" style={{ fontSize: 15 }}>
              {j.bayut_internal_reference_no}
              {j.reviewer_changes_to_accept ? (
                <span className="changes-badge">{j.reviewer_changes_to_accept} to accept</span>
              ) : null}
            </b>
            <StatusChip s={j.progress?.stage_label ?? j.status_label} />
          </div>
          <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>{j.property_label}</div>
          <div className="row" style={{ justifyContent: "space-between", gap: 10, fontSize: 13, color: "var(--text-muted)" }}>
            <span>{j.valuer_name || "Unassigned"}</span>
            <span>
              {j.inspection_booked_at && j.progress?.stage === "inspection"
                ? `Booked ${formatDateTime(j.inspection_booked_at)}`
                : j.progress?.sub_status ?? ""}
            </span>
          </div>
        </Link>
      ))}
    </div>
    <div className="hide-app">
    <Table
      columns={[
        {
          key: "ref",
          label: "Job ref",
          render: (j: JobListItem) => (
            <Link href={`/jobs/${j.id}`} style={{ textDecoration: "none" }}>
              {j.bayut_internal_reference_no}
              {j.reviewer_changes_to_accept ? (
                <span className="changes-badge" title="Peer reviewer changes for the valuer to accept">
                  {j.reviewer_changes_to_accept} to accept
                </span>
              ) : null}
            </Link>
          ),
        },
        {
          key: "bankref",
          label: "Bank ref",
          render: (j: JobListItem) => (
            <span className="num" style={{ color: "var(--text-secondary)" }}>{j.bank_reference_no || "—"}</span>
          ),
        },
        { key: "bank", label: "Bank", render: (j: JobListItem) => j.bank_name },
        {
          key: "property",
          label: "Property",
          render: (j: JobListItem) => (
            <span style={{ display: "block", maxWidth: 260, whiteSpace: "normal" }}>{j.property_label}</span>
          ),
        },
        { key: "type", label: "Type", render: (j: JobListItem) => j.property_type || "—" },
        {
          key: "status",
          label: "Status",
          render: (j: JobListItem) =>
            j.progress ? (
              <div style={{ display: "grid", gap: 3, justifyItems: "start" }}>
                <StatusChip s={j.progress.stage_label} />
                <span style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{j.progress.sub_status}</span>
                {j.inspection_booked_at && j.progress.stage === "inspection" && (
                  <span style={{ fontSize: 12.5, color: "var(--text-accent)" }}>
                    Booked {formatDateTime(j.inspection_booked_at)}
                  </span>
                )}
              </div>
            ) : (
              <StatusChip s={j.status_label} />
            ),
        },
        {
          key: "valuer",
          label: "Valuer",
          render: (j: JobListItem) =>
            j.valuer_name ? (
              <span className="row" style={{ gap: 8 }}>
                <Avatar name={j.valuer_name} size={26} />
                {j.valuer_name}
              </span>
            ) : (
              <span style={{ color: "var(--text-muted)" }}>Unassigned</span>
            ),
        },
        {
          key: "received",
          label: "Received",
          render: (j: JobListItem) => (
            <span className="num" style={{ color: "var(--text-secondary)" }}>
              {formatDateTime(j.date_time_request_received ?? j.created_at)}
            </span>
          ),
        },
      ]}
      rows={rows}
    />
    </div>
    </>
  );
}

/** The four summary figures on one slim line (QA: fewer cards and rows). */
export function KpiLine({ kpis }: { kpis?: JobKpis }) {
  const items: [string, string, string][] = [
    ["in progress", "In progress", kpis ? String(kpis.in_progress) : "…"],
    ["awaiting peer review", "In review", kpis ? String(kpis.awaiting_peer_review) : "…"],
    ["issued in the last 7 days", "Issued (7d)", kpis ? String(kpis.issued_this_week) : "…"],
    ["avg turnaround", "Turnaround",
      kpis ? (kpis.avg_turnaround_hours === null ? "—" : `${Math.round(kpis.avg_turnaround_hours)} h`) : "…"],
  ];
  return (
    <div className="kpi-line">
      {items.map(([label, short, value]) => (
        <span key={label}>
          <b className="num">{value}</b> <span className="hide-app">{label}</span>
          <span className="show-app">{short}</span>
        </span>
      ))}
    </div>
  );
}
