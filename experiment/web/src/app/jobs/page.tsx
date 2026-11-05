"use client";

/**
 * Jobs dashboard — design brief S1.
 *
 * Ported from the prototype's `jobs-dashboard-and-new-instruction.jsx`,
 * with its sample JOBS/BANKS arrays and demo state/empty/loading switcher
 * replaced by the real API (filters are applied server-side).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { Avatar, Button, Icon, Table } from "@/design-system";
import { LeadPreview } from "@/components/vp/LeadPreview";
import { Shell, StatusChip } from "@/components/vp/ui";
import { PipelineFunnel, type CardFilter } from "@/components/vp/PipelineFunnel";
import { formatDateTime } from "@/components/vp/format";
import { useMe } from "@/lib/auth";
import { useOptions } from "@/lib/options";
import { useJobs, type JobFilters, type JobListItem } from "@/lib/jobs";

const VIEWS = [
  { key: "all", label: "All" },
  { key: "mine", label: "My jobs" },
  // Managers: their own and everyone below them.
  { key: "team", label: "My team", managers: true },
  // "Awaiting review", as in the design: short enough for a phone.
  { key: "review", label: "Awaiting review" },
  { key: "lost", label: "Lost" },
] as const;

export default function JobsPage() {
  const [filters, setFilters] = useState<JobFilters>({ view: "all" });
  // A pipeline card the admin clicked: the table shows that card's jobs.
  const [card, setCard] = useState<CardFilter>(null);
  // A count clicked on the Dashboard opens here as ?ids=…&label=….
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ids = params.get("ids");
    if (ids) {
      // Read once on arrival; the URL isn't known while the page prerenders.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCard({ label: params.get("label") || "Selected", ids: ids.split(",").map(Number).filter(Boolean) });
    }
  }, []);
  const { data: page, isLoading, isError, error } = useJobs(
    card ? { ...filters, view: "all", ids: card.ids.length ? card.ids.join(",") : "0" } : filters,
  );
  // The true total, whatever the table is filtered to (QA: counts must be accurate).
  const { data: everything } = useJobs({ view: "all" });
  // The lead shown in the preview panel, if any.
  const [preview, setPreview] = useState<number | null>(null);
  const { data: me } = useMe();
  const { data: options } = useOptions();
  const categoryLabel = (v?: string) => options?.property_category?.find((o) => o.value === v)?.label ?? v;
  const canCreate = me?.authenticated ? Boolean(me.user.can_create_jobs ?? me.user.is_admin) : false;

  const rows = page?.results ?? [];
  const isManager = me?.authenticated ? Boolean(me.user.is_manager) : false;
  const views = VIEWS.filter((v) => !("managers" in v) || isManager);
  const set = (patch: Partial<JobFilters>) => setFilters((f) => ({ ...f, ...patch }));
  // Stage is filtered from the Pipeline; the table keeps the search box only.
  const hasFilters = Boolean(filters.q);
  const step = (by: -1 | 1) => {
    const at = rows.findIndex((r) => r.id === preview);
    const next = rows[at + by];
    if (next) setPreview(next.id);
  };

  return (
    <Shell>
      {/* Admins: the pipeline by stage (CRM feedback DB-01..03). */}
      {me?.authenticated && me.user.is_admin && <PipelineFunnel selected={card} onFilter={setCard} />}

      {/* One row: the views, the search, and the new-instruction button. */}
      <div className="card jobs-toolbar">
        <div className="jt-views" role="tablist">
          {views.map((v) => (
            <button key={v.key} type="button" role="tab" aria-selected={filters.view === v.key}
              className={"jt-view" + (filters.view === v.key ? " on" : "")} onClick={() => set({ view: v.key })}>
              {v.label}
              {v.key === "all" && everything ? ` ${everything.count}` : ""}
            </button>
          ))}
        </div>
        <div className="jt-right">
          <div className="jt-search">
            <Icon name="search" size={16} color="var(--gray-500)" />
            <input
              placeholder="Search Bayut ref, bank ref, building…"
              value={filters.q ?? ""}
              onChange={(e) => set({ q: e.target.value })}
              aria-label="Search jobs"
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
            <button type="button" className="jt-clear" onClick={() => setFilters({ view: filters.view })}>
              Clear
            </button>
          )}
          {/* Ops (and admins) take instructions in; for everyone else the button isn't offered. */}
          {canCreate && (
            <Link href="/jobs/new" className="fab-link">
              <Button size="sm" icon={<Icon name="plus" size={16} />}>
                <span className="hide-app">New valuation instruction</span>
                <span className="show-app">New</span>
              </Button>
            </Link>
          )}
        </div>
      </div>

      <div className="card jobs-list" style={{ padding: 0 }}>
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
                <div className="one-line" style={{ fontSize: 14, color: "var(--text-secondary)" }} title={j.location_line || j.property_label}>
                  {j.location_line || j.property_label}
                </div>
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
          <div className="hide-app jobs-table">
          <Table
            columns={[
              {
                key: "ref",
                label: "Job ref",
                render: (j: JobListItem) => (
                  <Link href={`/jobs/${j.id}`} className="jl-ref num">
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
                render: (j: JobListItem) => <span className="jl-mono num">{j.bank_reference_no || "—"}</span>,
              },
              {
                key: "property",
                label: "Property",
                render: (j: JobListItem) => (
                  <button type="button" className="jl-prop" title={`${j.location_line || j.property_label} · click to preview`}
                    onClick={() => setPreview(j.id)}>
                    <span className="one-line">{j.location_line || j.property_label}</span>
                    <span className="one-line jl-sub">{j.bank_name}</span>
                  </button>
                ),
              },
              { key: "type", label: "Type", render: (j: JobListItem) => <span className="jl-muted">{categoryLabel(j.property_type) || "—"}</span> },
              {
                key: "status",
                label: "Status",
                render: (j: JobListItem) =>
                  j.progress ? (
                    <div style={{ display: "grid", gap: 2, justifyItems: "start" }}>
                      <StatusChip s={j.progress.stage_label} />
                      <span className="jl-sub">
                        {j.inspection_booked_at && j.progress.stage === "inspection"
                          ? `Booked ${formatDateTime(j.inspection_booked_at)}`
                          : j.progress.sub_status}
                      </span>
                    </div>
                  ) : (
                    <StatusChip s={j.status_label} />
                  ),
              },
              {
                key: "valuer",
                label: "Assignee",
                render: (j: JobListItem) =>
                  j.valuer_name ? (
                    <span className="row" style={{ gap: 8 }}>
                      <Avatar name={j.valuer_name} size={24} />
                      <span className="one-line" title={j.valuer_name}>{j.valuer_name}</span>
                    </span>
                  ) : (
                    <span className="jl-muted">Unassigned</span>
                  ),
              },
              {
                key: "preview",
                label: "Action",
                render: (j: JobListItem) => (
                  <button type="button" className={"icon-btn" + (preview === j.id ? " on" : "")} aria-label="Preview lead"
                    title="Preview" onClick={() => setPreview(j.id)}>
                    <Icon name="eye" size={18} />
                  </button>
                ),
              },
            ]}
            rows={rows}
          />
          </div>
          </>
        )}

        {page && rows.length > 0 && (
          <div className="jl-foot">
            <span>
              Showing <b>{rows.length ? 1 : 0}</b> to <b>{rows.length}</b> of <b>{page.count}</b> valuation jobs
            </span>
            {/* TODO: page controls once the list grows past one page. */}
          </div>
        )}
      </div>
      {preview !== null && <LeadPreview jobId={preview} onClose={() => setPreview(null)} onStep={step} />}
    </Shell>
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
