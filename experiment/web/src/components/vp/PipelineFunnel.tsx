"use client";

/**
 * Admin pipeline dashboard on the Home screen (CRM feedback DB-01..03): one
 * count per stage with the drop-off between stages, a date filter that
 * recounts everything, and per-stage section counts with their own filter.
 * Every count opens the jobs behind it. Counting rules: backend
 * apps/jobs/dashboard.py.
 */

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Input } from "@/design-system";
import { apiFetch } from "@/lib/api";

type JobRef = { id: number; ref: string; property: string; status: string };
type Stage = { key: string; label: string; count: number; jobs: JobRef[]; drop?: { count: number; pct: number | null } };
type Funnel = { from: string; to: string; stages: Stage[] };
type Section = { label: string; count: number; jobs: JobRef[] };

const PRESETS = [
  { key: "today", label: "Today" },
  { key: "week", label: "This week" },
  { key: "month", label: "This month" },
  { key: "30d", label: "Last 30 days" },
  { key: "custom", label: "Custom" },
] as const;

type Range = { preset: string; from: string; to: string };

const query = (r: Range) =>
  r.preset === "custom" ? new URLSearchParams({ from: r.from, to: r.to }) : new URLSearchParams({ range: r.preset });

function RangePicker({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  return (
    <div className="row wrap" style={{ gap: 8 }}>
      <div className="seg">
        {PRESETS.map((p) => (
          <button key={p.key} type="button" className={value.preset === p.key ? "on" : ""} onClick={() => onChange({ ...value, preset: p.key })}>
            {p.label}
          </button>
        ))}
      </div>
      {value.preset === "custom" && (
        <span className="row" style={{ gap: 6 }}>
          <Input type="date" value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} style={{ width: 160 }} aria-label="From" />
          <span style={{ color: "var(--text-muted)" }}>to</span>
          <Input type="date" value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} style={{ width: 160 }} aria-label="To" />
        </span>
      )}
    </div>
  );
}

function JobList({ title, jobs }: { title: string; jobs: JobRef[] }) {
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{title}</div>
      {jobs.length === 0 ? (
        <div style={{ fontSize: 14, color: "var(--text-muted)" }}>No jobs.</div>
      ) : (
        <div className="stack8">
          {jobs.map((j) => (
            <Link key={j.id} href={`/jobs/${j.id}`} className="row wrap"
              style={{ gap: "4px 12px", padding: "8px 12px", border: "1px solid var(--border-subtle)", borderRadius: 8, textDecoration: "none", color: "inherit", fontSize: 14 }}>
              <b className="num">{j.ref}</b>
              <span style={{ flex: 1, minWidth: 0 }}>{j.property}</span>
              <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{j.status}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function PipelineFunnel() {
  const today = new Date().toISOString().slice(0, 10);
  const [range, setRange] = useState<Range>({ preset: "30d", from: today, to: today });
  const [open, setOpen] = useState<string | null>(null);
  const [sectionRange, setSectionRange] = useState<Range>({ preset: "30d", from: today, to: today });
  const [openSection, setOpenSection] = useState<string | null>(null);

  const funnel = useQuery({
    queryKey: ["funnel", query(range).toString()],
    queryFn: () => apiFetch<Funnel>(`/api/jobs/funnel/?${query(range)}`),
  });
  const stage = funnel.data?.stages.find((s) => s.key === open) ?? null;
  const sections = useQuery({
    queryKey: ["funnel-sections", open, query(sectionRange).toString()],
    queryFn: () => apiFetch<{ sections: Section[] }>(`/api/jobs/funnel/?stage=${open}&${query(sectionRange)}`),
    enabled: Boolean(open && open !== "sent"),
  });

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="row wrap" style={{ justifyContent: "space-between", gap: 10, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Pipeline</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Jobs that reached each stage in the period. Click a count for the jobs and the breakdown.
          </div>
        </div>
        <RangePicker value={range} onChange={setRange} />
      </div>

      {funnel.isError ? (
        <div style={{ color: "var(--text-error)", fontSize: 14 }}>Couldn&apos;t load the pipeline.</div>
      ) : (
        <div className="funnel-grid">
          {(funnel.data?.stages ?? []).map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => {
                setOpen(open === s.key ? null : s.key);
                setOpenSection(null);
              }}
              title={s.drop ? "Change from the previous stage" : undefined}
              style={{
                textAlign: "left", padding: "12px 14px", borderRadius: 10, cursor: "pointer", fontFamily: "inherit",
                border: `1px solid ${open === s.key ? "var(--action-primary)" : "var(--border-subtle)"}`,
                background: open === s.key ? "var(--surface-accent)" : "var(--surface-card)",
              }}
            >
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{s.label}</div>
              <div className="num" style={{ fontSize: 26, fontWeight: 700 }}>{s.count}</div>
              <div style={{ fontSize: 12, color: s.drop && s.drop.count > 0 ? "var(--text-error)" : "var(--text-muted)", minHeight: 16 }}>
                {!s.drop
                  ? " "
                  : s.drop.count > 0
                    ? `−${s.drop.count}${s.drop.pct !== null ? ` (${s.drop.pct}%)` : ""}`
                    : s.drop.count < 0
                      ? `+${-s.drop.count}`
                      : "No drop"}
              </div>
            </button>
          ))}
          {funnel.isLoading && [...Array(6)].map((_, i) => <div key={i} className="skel" style={{ height: 88 }} />)}
        </div>
      )}

      {stage && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--border-divider)" }}>
          {stage.key !== "sent" && (
            <>
              <div className="row wrap" style={{ justifyContent: "space-between", gap: 10 }}>
                <div style={{ fontSize: 15, fontWeight: 700 }}>{stage.label} by section</div>
                <RangePicker value={sectionRange} onChange={setSectionRange} />
              </div>
              <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
                {(sections.data?.sections ?? []).map((sec) => (
                  <button key={sec.label} type="button" onClick={() => setOpenSection(openSection === sec.label ? null : sec.label)}
                    className="row" style={{ gap: 8, padding: "7px 12px", borderRadius: 999, cursor: "pointer", fontFamily: "inherit", fontSize: 14,
                      border: `1px solid ${openSection === sec.label ? "var(--action-primary)" : "var(--border-subtle)"}`, background: "var(--surface-card)" }}>
                    {sec.label} <b className="num">{sec.count}</b>
                  </button>
                ))}
                {sections.isLoading && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Counting…</span>}
                {sections.data && sections.data.sections.length === 0 && (
                  <span style={{ fontSize: 13, color: "var(--text-muted)" }}>No jobs in this stage in the period.</span>
                )}
              </div>
              {openSection && (
                <JobList title={openSection} jobs={sections.data?.sections.find((s) => s.label === openSection)?.jobs ?? []} />
              )}
            </>
          )}
          {!openSection && <JobList title={`Reached ${stage.label}`} jobs={stage.jobs} />}
        </div>
      )}
    </div>
  );
}
