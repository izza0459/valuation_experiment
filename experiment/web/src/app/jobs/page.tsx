"use client";

/**
 * Jobs list — design brief S1. Admins' pipeline and figures are on the
 * Dashboard (/dashboard); this page is the list.
 *
 * Ported from the prototype's `jobs-dashboard-and-new-instruction.jsx`,
 * with its sample JOBS/BANKS arrays and demo state/empty/loading switcher
 * replaced by the real API (filters are applied server-side).
 */

import { useState } from "react";
import Link from "next/link";
import { Button, Icon, Input, Tabs } from "@/design-system";
import { PageHead, Shell } from "@/components/vp/ui";
import { JobsTable, KpiLine } from "@/components/vp/JobsTable";
import { useMe } from "@/lib/auth";
import { useJobKpis, useJobs, type JobFilters } from "@/lib/jobs";

const VIEWS = [
  { key: "all", label: "All" },
  { key: "mine", label: "My jobs" },
  // "Awaiting review", as in the design: short enough for a phone.
  { key: "review", label: "Awaiting review" },
] as const;

export default function JobsPage() {
  const [filters, setFilters] = useState<JobFilters>({ view: "all" });
  const { data: page, isLoading, isError, error } = useJobs(filters);
  // The true total, whatever the table is filtered to (QA: counts must be accurate).
  const { data: everything } = useJobs({ view: "all" });
  const { data: kpis } = useJobKpis();
  const { data: me } = useMe();
  const canCreate = me?.authenticated ? Boolean(me.user.can_create_jobs ?? me.user.is_admin) : false;
  const isAdmin = Boolean(me?.authenticated && me.user.is_admin);

  const rows = page?.results ?? [];
  const set = (patch: Partial<JobFilters>) => setFilters((f) => ({ ...f, ...patch }));
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

      {/* Admins see the figures on the Dashboard, with the pipeline. */}
      {!isAdmin && <KpiLine kpis={kpis} />}

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
          <JobsTable rows={rows} />
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
