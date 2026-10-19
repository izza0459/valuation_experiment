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
import { Avatar, Button, Icon, Input, Select, Table, Tabs } from "@/design-system";
import { PageHead, Shell, StatusChip } from "@/components/vp/ui";
import { formatDateTime } from "@/components/vp/format";
import { useMe } from "@/lib/auth";
import { JOB_STATUS_LABELS, useJobKpis, useJobs, type JobFilters, type JobListItem } from "@/lib/jobs";

const VIEWS = [
  { key: "all", label: "All" },
  { key: "mine", label: "My jobs" },
  { key: "review", label: "Awaiting my review" },
] as const;

export default function JobsPage() {
  const [filters, setFilters] = useState<JobFilters>({ view: "all" });
  const { data: page, isLoading, isError, error } = useJobs(filters);
  const { data: kpis } = useJobKpis();
  const { data: me } = useMe();
  const isAdmin = me?.authenticated ? me.user.is_admin : false;

  const rows = page?.results ?? [];
  const set = (patch: Partial<JobFilters>) => setFilters((f) => ({ ...f, ...patch }));
  const hasFilters = Boolean(filters.status || filters.q);

  return (
    <Shell>
      <PageHead title="Jobs" sub={page ? `${page.count} total` : undefined}>
        {/* Admins open jobs; for everyone else the button isn't offered. */}
        {isAdmin && (
          <Link href="/jobs/new">
            <Button icon={<Icon name="plus" size={18} />}>New valuation instruction</Button>
          </Link>
        )}
      </PageHead>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 14, marginBottom: 16 }}>
        <Kpi label="Jobs in progress" value={kpis?.in_progress} />
        <Kpi label="Awaiting peer review" value={kpis?.awaiting_peer_review} />
        <Kpi label="Issued this week" value={kpis?.issued_this_week} />
        <Kpi
          label="Avg turnaround"
          value={kpis?.avg_turnaround_hours ?? undefined}
          suffix=" hrs"
          sub={kpis && kpis.avg_turnaround_hours === null ? "No issued jobs yet" : undefined}
        />
      </div>

      <div className="card" style={{ padding: 0 }}>
        <Tabs
          items={VIEWS.map((v) => (v.key === "all" ? { label: v.label, count: page?.count } : v.label))}
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
          <Select
            value={filters.status ?? ""}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => set({ status: e.target.value })}
            placeholder="Status"
            options={Object.entries(JOB_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            style={{ width: 200 }}
            aria-label="Status"
          />
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
          <Table
            columns={[
              {
                key: "ref",
                label: "Job ref",
                render: (j: JobListItem) => (
                  <Link href={`/jobs/${j.id}`} style={{ textDecoration: "none" }}>
                    {j.bayut_internal_reference_no}
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
              { key: "status", label: "Status", render: (j: JobListItem) => <StatusChip s={j.status_label} /> },
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

function Kpi({ label, value, suffix = "", sub }: { label: string; value?: number; suffix?: string; sub?: string }) {
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <div style={{ fontSize: 14, color: "var(--text-muted)" }}>{label}</div>
      <div className="num" style={{ fontSize: 30, fontWeight: 500, margin: "4px 0 2px" }}>
        {value === undefined ? <span className="skel" style={{ display: "inline-block", width: 48, height: 30 }} /> : value + suffix}
      </div>
      <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{sub ?? " "}</div>
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
