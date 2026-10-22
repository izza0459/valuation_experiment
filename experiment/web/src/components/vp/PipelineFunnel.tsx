"use client";

/**
 * Admin pipeline on the Home screen (CRM feedback DB-01..03), compact: one
 * row of stages (count, drop-off from the stage before) and, for the open
 * stage, one row of section pills with counts. Clicking a stage or a section
 * filters the jobs table below. A date dropdown recounts everything.
 * Counting rules: backend apps/jobs/dashboard.py.
 */

import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon, Input, Select } from "@/design-system";
import { apiFetch } from "@/lib/api";

type JobRef = { id: number; ref: string; property: string; status: string };
type Stage = { key: string; label: string; count: number; jobs: JobRef[]; drop?: { count: number; pct: number | null } };
type Funnel = { from: string; to: string; stages: Stage[] };
type Section = { label: string; count: number; jobs: JobRef[] };

/** What the jobs table is filtered to: the jobs behind a stage or section. */
export type CardFilter = { label: string; ids: number[] } | null;

const PRESETS = [
  { value: "today", label: "Today" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
  { value: "30d", label: "Last 30 days" },
  { value: "custom", label: "Custom dates…" },
];

type Range = { preset: string; from: string; to: string };

const query = (r: Range) =>
  r.preset === "custom" ? new URLSearchParams({ from: r.from, to: r.to }) : new URLSearchParams({ range: r.preset });

function dropText(drop: Stage["drop"]): string | null {
  if (!drop || drop.count === 0) return null;
  if (drop.count > 0) return `−${drop.count}${drop.pct !== null ? ` (${drop.pct}%)` : ""}`;
  return `+${-drop.count}`;
}

export function PipelineFunnel({ selected, onFilter }: { selected: CardFilter; onFilter: (f: CardFilter) => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [range, setRange] = useState<Range>({ preset: "30d", from: today, to: today });
  const [open, setOpen] = useState<string | null>(null);

  const funnel = useQuery({
    queryKey: ["funnel", query(range).toString()],
    queryFn: () => apiFetch<Funnel>(`/api/jobs/funnel/?${query(range)}`),
  });
  const stage = funnel.data?.stages.find((s) => s.key === open) ?? null;
  const sections = useQuery({
    queryKey: ["funnel-sections", open, query(range).toString()],
    queryFn: () => apiFetch<{ sections: Section[] }>(`/api/jobs/funnel/?stage=${open}&${query(range)}`),
    enabled: Boolean(open && open !== "sent"),
  });

  const stageFilter = (s: Stage): CardFilter => ({ label: `Reached ${s.label}`, ids: s.jobs.map((j) => j.id) });
  const pickStage = (s: Stage) => {
    const closing = open === s.key;
    setOpen(closing ? null : s.key);
    onFilter(closing ? null : stageFilter(s));
  };
  const pickSection = (sec: Section) => {
    if (!stage) return;
    const label = `${stage.label} · ${sec.label}`;
    onFilter(selected?.label === label ? stageFilter(stage) : { label, ids: sec.jobs.map((j) => j.id) });
  };
  const changeRange = (next: Range) => {
    setRange(next);
    setOpen(null);
    onFilter(null);
  };

  return (
    <div className="card pipeline" style={{ marginBottom: 16, padding: "14px 18px" }}>
      <div className="row wrap" style={{ justifyContent: "space-between", gap: 10, marginBottom: 10 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>
          Pipeline{" "}
          <span style={{ fontSize: 13, fontWeight: 400, color: "var(--text-muted)" }}>· jobs that reached each stage</span>
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          {range.preset === "custom" && (
            <span className="row" style={{ gap: 6 }}>
              <Input type="date" value={range.from} onChange={(e) => changeRange({ ...range, from: e.target.value })} style={{ width: 150, height: 36 }} aria-label="From" />
              <span style={{ color: "var(--text-muted)" }}>to</span>
              <Input type="date" value={range.to} onChange={(e) => changeRange({ ...range, to: e.target.value })} style={{ width: 150, height: 36 }} aria-label="To" />
            </span>
          )}
          <div style={{ width: 170 }}>
            <Select
              value={range.preset}
              options={PRESETS}
              aria-label="Period"
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => changeRange({ ...range, preset: e.target.value })}
            />
          </div>
        </div>
      </div>

      {funnel.isError ? (
        <div style={{ color: "var(--text-error)", fontSize: 14 }}>Couldn&apos;t load the pipeline.</div>
      ) : (
        <div className="pipe-steps">
          {(funnel.data?.stages ?? []).map((s, i) => {
            const on = open === s.key;
            const drop = dropText(s.drop);
            return (
              <Fragment key={s.key}>
                {i > 0 && <Icon name="chevron-right" size={16} color="var(--gray-400)" />}
                <button type="button" className={"pipe-step" + (on ? " on" : "")} aria-pressed={on} onClick={() => pickStage(s)}>
                  <span className="pipe-label">{s.label}</span>
                  <span className="pipe-count num">{s.count}</span>
                  {drop && (
                    <span className="pipe-drop" style={{ color: drop.startsWith("−") ? "var(--text-error)" : "var(--text-muted)" }}
                      title="Change from the stage before">
                      {drop}
                    </span>
                  )}
                </button>
              </Fragment>
            );
          })}
          {funnel.isLoading && <div className="skel" style={{ height: 52, flex: 1 }} />}
        </div>
      )}

      {/* The open stage: jobs still in it, by the section they are on, each
          with its share of the stage (DB-03). */}
      {stage && stage.key !== "sent" && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border-divider)" }}>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 8 }}>
            Still in {stage.label}, by section
          </div>
          <div className="section-grid">
            {(() => {
              const list = sections.data?.sections ?? [];
              const total = list.reduce((n, s) => n + s.count, 0);
              return list.map((sec) => {
                const on = selected?.label === `${stage.label} · ${sec.label}`;
                const pct = total ? Math.round((sec.count / total) * 100) : 0;
                return (
                  <button key={sec.label} type="button" className={"section-card" + (on ? " on" : "")} aria-pressed={on}
                    onClick={() => pickSection(sec)}>
                    <span className="pipe-label">{sec.label}</span>
                    <span className="row" style={{ gap: 8, alignItems: "baseline" }}>
                      <span className="pipe-count num">{sec.count}</span>
                      <span style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{pct}%</span>
                    </span>
                    <span className="section-bar"><span style={{ width: `${pct}%` }} /></span>
                  </button>
                );
              });
            })()}
            {sections.isLoading && [...Array(4)].map((_, i) => <div key={i} className="skel" style={{ height: 70 }} />)}
          </div>
        </div>
      )}
    </div>
  );
}
