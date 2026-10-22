"use client";

/**
 * Admin dashboard: the summary figures and the pipeline (CRM feedback
 * DB-01..03), moved off the Jobs list so that page stays a list. Clicking a
 * stage or a section lists its jobs underneath.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Icon } from "@/design-system";
import { PageHead, Shell } from "@/components/vp/ui";
import { PipelineFunnel, type CardFilter } from "@/components/vp/PipelineFunnel";
import { JobsTable, KpiLine } from "@/components/vp/JobsTable";
import { useMe } from "@/lib/auth";
import { useJobKpis, useJobs } from "@/lib/jobs";

export default function DashboardPage() {
  const router = useRouter();
  const { data: me } = useMe();
  const isAdmin = Boolean(me?.authenticated && me.user.is_admin);
  const [card, setCard] = useState<CardFilter>(null);
  const { data: kpis } = useJobKpis();
  const { data: page, isLoading } = useJobs(
    { view: "all", ids: card?.ids.length ? card.ids.join(",") : "0" },
    { enabled: Boolean(card) },
  );

  // The dashboard is for admins; anyone else is sent to their jobs.
  useEffect(() => {
    if (me?.authenticated && !me.user.is_admin) router.replace("/jobs");
  }, [me, router]);

  return (
    <Shell>
      <PageHead title="Dashboard" />
      {isAdmin && (
        <>
          <KpiLine kpis={kpis} />
          <PipelineFunnel selected={card} onFilter={setCard} />

          <div className="card" style={{ padding: 0 }}>
            <div className="row wrap" style={{ justifyContent: "space-between", gap: 10, padding: "14px 24px",
              borderBottom: "1px solid var(--border-divider)" }}>
              <div style={{ fontSize: 15, fontWeight: 700 }}>
                {card ? <>{card.label} <span className="num" style={{ color: "var(--text-muted)", fontWeight: 400 }}>· {card.ids.length} {card.ids.length === 1 ? "job" : "jobs"}</span></> : "Jobs"}
              </div>
              {card ? (
                <button type="button" onClick={() => setCard(null)}
                  style={{ background: "none", border: 0, color: "var(--text-link)", fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>
                  Clear
                </button>
              ) : (
                <Link href="/jobs" style={{ fontSize: 14 }}>All jobs <Icon name="arrow-right" size={14} /></Link>
              )}
            </div>
            {!card ? (
              <div style={{ padding: "28px 24px", color: "var(--text-muted)", fontSize: 14, textAlign: "center" }}>
                Click a stage or a section above to list its jobs here.
              </div>
            ) : isLoading ? (
              <div style={{ padding: 24 }}>
                {[...Array(3)].map((_, i) => <div key={i} className="skel" style={{ height: 44, marginBottom: 10 }} />)}
              </div>
            ) : (page?.results.length ?? 0) === 0 ? (
              <div style={{ padding: "28px 24px", color: "var(--text-muted)", fontSize: 14, textAlign: "center" }}>
                No jobs here.
              </div>
            ) : (
              <JobsTable rows={page!.results} />
            )}
          </div>
        </>
      )}
    </Shell>
  );
}
