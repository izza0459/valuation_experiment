"use client";

/**
 * Jobs dashboard — design brief S1.
 *
 * Ported from the prototype's `jobs-dashboard-and-new-instruction.jsx`,
 * with its sample JOBS/BANKS arrays and demo state/empty/loading switcher
 * replaced by the real API (filters are applied server-side).
 */

import { useState } from "react";
import Link from "next/link";
import { Avatar, Button, Icon, Input, Table, Tabs } from "@/design-system";
import { PageHead, Shell, StatusChip } from "@/components/vp/ui";
import { PipelineFunnel, type CardFilter } from "@/components/vp/PipelineFunnel";
import { formatDateTime } from "@/components/vp/format";
import { useMe } from "@/lib/auth";
import { useJobKpis, useJobs, type JobFilters, type JobKpis, type JobListItem } from "@/lib/jobs";

const VIEWS = [
  { key: "all", label: "All" },
  { key: "mine", label: "My jobs" },
  // "Awaiting review", as in the design: short enough for a phone.
  { key: "review", label: "Awaiting review" },
] as const;

export default function JobsPage() {
  const [filters, setFilters] = useState<JobFilters>({ view: "all" });
  // A pipeline card the admin clicked: the table shows that card's jobs.
  const [card, setCard] = useState<CardFilter>(null);
  const { data: page, isLoading, isError, error } = useJobs(
    card ? { ...filters, view: "all", ids: card.ids.length ? card.ids.join(",") : "0" } : filters,
  );
  // The true total, whatever the table is filtered to (QA: counts must be accurate).
  const { data: everything } = useJobs({ view: "all" });
  const { data: kpis } = useJobKpis();
  const { data: me } = useMe();
  const canCreate = me?.authenticated ? Boolean(me.user.can_create_jobs ?? me.user.is_admin) : false;

  const rows = page?.results ?? [];
  const set = (patch: Partial<JobFilters>) => setFilters((f) => ({ ...f, ...patch }));
  // Stage is filtered from the Pipeline; the table keeps the search box only.
  const hasFilters = Boolean(filters.q);

  return (
    <Shell>
      <PageHead title="Jobs" sub={everything ? `${everything.count} total` : undefined}>
        {/* Ops (and admins) take instructions in; for everyone else the button isn't offered. */}
        {canCreate && (
          <Link href="/jobs/new" className="fab-link">
            <Button icon={<Icon name="plus" size={18} />}>
              <span className="hide-app">New valuation instruction</span>
              <span className="show-app">New</span>
            </Button>
          </Link>
        )}
      </PageHead>

      <KpiLine kpis={kpis} />

      {/* Admins: the pipeline by stage (CRM feedback DB-01..03). */}
      {me?.authenticated && me.user.is_admin && <PipelineFunnel selected={card} onFilter={setCard} />}

      <div className="card" style={{ padding: 0 }}>
        <Tabs
          items={VIEWS.map((v) => (v.key === "all" ? { label: v.label, count: everything?.count } : v.label))}
          active={VIEWS.find((v) => v.key === filters.view)?.label ?? "All"}
          onChange={(label: string) => set({ view: VIEWS.find((v) => v.label === label)?.key ?? "all" })}
          size="sm"
        />

        <div className="row wrap" style={{ padding: "14px 24px", gap: 10, borderBottom: "1px solid var(--border-divider)" }}>
          <div style={{ position: "relative", flex: "1 1 240px", maxWidth: 340 }}>
            <Icon name="search" size={18} color="var(--gray-500)" style={{ position: "absolute", left: 12, top: 15 }} />
            <Input
              placeholder="Search Bayut ref, bank ref, building"
              value={filters.q ?? ""}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => set({ q: e.target.value })}
              style={{ paddingLeft: 38, height: 42 }}
            />
          </div>
          {/* The Pipeline stage or section the table is showing. */}
          {card && (
            <span className="filter-chip">
              {card.label}: <b>{card.ids.length}</b>
              <button type="button" aria-label="Show all jobs" onClick={() => setCard(null)}>
                <Icon name="x" size={14} />
              </button>
            </span>
          )}
          {hasFilters && (
            <button
              onClick={() => setFilters({ view: filters.view })}
              style={{ background: "none", border: 0, color: "var(--text-link)", fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}
            >
              Clear
            </button>
          )}
        </div>

        {isLoading ? (
          <div style={{ padding: 24 }}>
            {[...Array(6)].map((_, i) => (
              <div key={i} className="skel" style={{ height: 44, marginBottom: 10 }} />
            ))}
          </div>
        ) : isError ? (
          <div style={{ padding: "48px 24px", textAlign: "center" }}>
            <div style={{ color: "var(--text-error)", fontSize: 15 }}>Could not load jobs.</div>
            <div style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 6 }}>
              {(error as Error).message?.includes("403")
                ? "Sign in first — SSO isn't wired up yet, so use the Django admin login."
                : (error as Error).message}
            </div>
          </div>
        ) : rows.length === 0 ? (
          <EmptyState filtered={hasFilters || filters.view !== "all"} />
        ) : (
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
        )}

        {page && rows.length > 0 && (
          <div className="row" style={{ justifyContent: "space-between", padding: "12px 24px", color: "var(--text-muted)", fontSize: 14 }}>
            <span>
              Showing {rows.length} of {page.count}
            </span>
            {/* TODO: page controls once the list grows past one page. */}
          </div>
        )}
      </div>
    </Shell>
  );
}

/** The four summary figures on one slim line (QA: fewer cards and rows). */
function KpiLine({ kpis }: { kpis?: JobKpis }) {
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

function EmptyState({ filtered }: { filtered: boolean }) {
  if (filtered) {
    return <div style={{ padding: "48px 24px", textAlign: "center", color: "var(--text-muted)" }}>No jobs match these filters.</div>;
  }
  return (
    <div style={{ padding: "72px 24px", textAlign: "center" }}>
      <div style={{ width: 56, height: 56, borderRadius: 28, background: "var(--surface-accent)", margin: "0 auto 16px", display: "grid", placeItems: "center" }}>
        <Icon name="briefcase" size={26} color="var(--text-accent)" />
      </div>
      <div style={{ fontSize: 20 }}>No valuation jobs yet</div>
      <div style={{ color: "var(--text-muted)", margin: "6px 0 18px" }}>
        Create a job from a bank instruction email to get started.
      </div>
    </div>
  );
}
